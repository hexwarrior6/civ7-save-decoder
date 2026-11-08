#!/usr/bin/env python3
"""文明7 FXS 属性包通用块遍历器 (DelineatedData / VariantValue 格式)

Phase1 修订版 (2026-11-09 验收修复):
- 全程字节精确定位: 块头/终止符可出现在任意字节对齐 (流非 4 对齐), 裸区跳转与
  重同步改用字节级锚点搜索 (FXSBLKED 或 [-1][1][1][count] 模式)。
- 容器形 0x402 (Properties/Components 等): [len]["\\x00"] 后无终止符, 子流从填充区之后
  开始, 按块语法连续解析子块 (container 节点), 直到外层块下一 schema 字段能对位
  (恢复外层继续) 或长裸区/流终止 (标记 truncated)。
- partial 块保留全部已解析字段, 不丢数据。

CLI: python3 tools/blockwalk.py <body.bin> <out.json>
"""
import struct, sys, os, json, re
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propertybag import FXS, SCALAR_SIZE, load_dictionary

_TERM = FXS  # b'FXSBLKED'
_U = struct.Struct('<I')
# 锚点: FXSBLKED 或 [-1][1][1] (任意字节对齐)
_ANCHOR_PAT = re.compile(
    re.escape(_TERM) + b'|' +
    re.escape(struct.pack('<III', 0xffffffff, 1, 1)))
MAX_DEPTH = 12
MAX_CHILDREN = 4096
MAX_BARE_IN_CONTAINER = 256   # 容器内裸区超过此长度 ⇒ 容器到此为止
MAX_CONTAINER_SPAN = 2_000_000  # 容器字节跨度安全上限
MAX_BLOCK_COUNT = 0xFFFF        # schema 条目数上限 (实测最大 81)


def _plausible_entries(d, ent, cnt):
    """前 min(cnt,4) 条目的类型字低16位必须 ≤0x407 (全部合法 VariantValueType)。
    用于剔除数据区里 [-1][1][1][大数] 的假块头。"""
    m = min(cnt, 4)
    for i in range(m):
        tw = _U.unpack_from(d, ent + 8 * i + 4)[0]
        if (tw & 0xffff) > 0x407:
            return False
    return True


class Unknown(Exception):
    """值解析失败"""


class Walker:
    def __init__(self, data, dic):
        self.data = data
        self.dic = dic
        self.nodes = []
        self.unknowns = []
        self.resyncs = 0
        self.stats = Counter()
        self.n = len(data)

    def name(self, h):
        return self.dic.get(h) or f'hash_{h:08x}'

    # ---------- 值读取 ----------
    def read_value(self, pos, vtype, depth):
        """返回 (kind, value, new_pos)。失败抛 Unknown。
        kind: str/blob4/blob8/blob/fp8/scalar/container"""
        d = self.data
        n = self.n
        t = vtype & 0xffff
        if t == 0x402:                                   # 字符串 / 容器形
            if pos + 4 > n:
                raise Unknown(pos)
            ln = _U.unpack_from(d, pos)[0]
            if ln > n:
                raise Unknown(pos)
            end = pos + 4 + ln
            padded = end + ((-ln) % 4)
            if padded + 8 > n:
                raise Unknown(pos)
            if d[padded:padded + 8] == _TERM:
                s = d[end:padded] if ln else b''
                return 'str', s.decode('utf-8', 'replace'), padded + 8
            # 容器形: 无终止符, 子流扫描从 [len] 之后开始 (容许裸前导)
            return 'container', None, pos + 4
        if t in (0x400, 0x403):                          # 尺寸块
            if pos + 4 > n:
                raise Unknown(pos)
            size = _U.unpack_from(d, pos)[0]
            if size > n - pos - 4:
                raise Unknown(pos)
            raw = d[pos + 4:pos + 4 + size]
            if size == 4:
                return 'blob4', _U.unpack(raw)[0], pos + 4 + size
            if size == 8:
                a, b = struct.unpack('<II', raw)
                return 'blob8', (a, b), pos + 4 + size
            return 'blob', raw.decode('utf-8', 'replace'), pos + 4 + size
        if t == 0x407:                                   # FixedPoint<8>
            if pos + 4 > n:
                raise Unknown(pos)
            return 'fp8', _U.unpack_from(d, pos)[0], pos + 4
        if t in (0x401, 0x404, 0x405) or t == 0:
            raise Unknown(pos)
        sz = SCALAR_SIZE.get(t)
        if sz is None or pos + sz > n:
            raise Unknown(pos)
        raw = d[pos:pos + sz]
        if t == 8:
            v = struct.unpack('<i', raw)[0]
        elif t == 9:
            v = _U.unpack(raw)[0]
        elif t == 10:
            v = struct.unpack('<q', raw)[0]
        elif t == 11:
            v = struct.unpack('<Q', raw)[0]
        elif t == 12:
            v = struct.unpack('<f', raw)[0]
        elif t == 13:
            v = struct.unpack('<d', raw)[0]
        elif sz == 1:
            v = raw[0]
        elif sz == 2:
            v = struct.unpack('<H', raw)[0]
        else:
            v = raw.hex()
        return 'scalar', v, pos + sz

    # ---------- 块头探测 ----------
    def _block_at(self, pos):
        """若 pos 处是块头, 返回 (flag, key, count, base)；否则 None。
        6-u32 形式 [K][1][-1][1][1][count]；5-u32 形式 [K][-1][1][1][count]。"""
        d, n = self.data, self.n
        if pos + 20 > n:
            return None
        k = _U.unpack_from(d, pos)[0]
        w1, w2, w3, w4 = struct.unpack_from('<IIII', d, pos + 4)
        if w1 == 1 and w2 == 0xffffffff and w3 == 1 and w4 == 1:
            cnt = _U.unpack_from(d, pos + 20)[0] if pos + 24 <= n else 0
            if 0 < cnt <= MAX_BLOCK_COUNT and pos + 24 + 8 * cnt <= n \
                    and _plausible_entries(d, pos + 24, cnt):
                return (True, k, cnt, pos + 24)
        if w1 == 0xffffffff and w2 == 1 and w3 == 1:
            cnt = w4
            if 0 < cnt <= MAX_BLOCK_COUNT and pos + 20 + 8 * cnt <= n \
                    and _plausible_entries(d, pos + 20, cnt):
                return (False, k, cnt, pos + 20)
        return None

    # ---------- 容器子块 schema 特征 ----------
    def _child_sig(self, base, cnt):
        d = self.data
        m = min(cnt, 4)
        hs = struct.unpack_from('<%dI' % m, d, base)
        return (cnt, hs)

    # ---------- 严格对位探测 ----------
    def _probe(self, pos, entries, depth):
        """对位证据只认自校验类型: 0x402 带终止符 / 固定尺寸 blob4/blob8。
        标量与变长 blob 不作数(任意字节都能'解析')。成功返回消费终点。"""
        h, t = entries[0]
        try:
            kind, v, q = self.read_value(pos, t, depth + 1)
        except Unknown:
            return None
        if kind in ('str', 'blob4', 'blob8'):
            return q
        return None

    # ---------- 容器子流 ----------
    def parse_container(self, cpos, remaining, depth):
        """容器形 0x402 子流: 从 [len] 之后字节级连续解析子块。终止条件:
        (a) 严格对位(下一 schema 字段为自校验类型且解析成功);
        (b) 异构子块(schema 特征与首个干净子块不同);
        (c) 子块损坏 / 裸区超限 / 流终止 / 上限。
        返回 (node, end_pos, aligned)。"""
        d, n = self.data, self.n
        children = []
        pos = cpos
        aligned = False
        remaining = list(remaining)
        sig = None                               # 首个干净子块的 schema 特征
        while pos < n and len(children) < MAX_CHILDREN:
            if pos - cpos > MAX_CONTAINER_SPAN:
                break
            blk = self._block_at(pos)
            if blk:
                flag, k, cnt, base = blk
                csig = self._child_sig(base, cnt)
                if sig is not None and csig != sig:
                    break                        # 异构子块 ⇒ 容器结束, 交还外层
                if sig is None:
                    sig = csig
                child, pos2 = self._parse_block(pos, flag, k, cnt, base, depth + 1)
                children.append(child)
                if 'partial' in child:
                    pos = child['failedAt']      # 子块损坏 ⇒ 容器截断
                    break
                pos = pos2
                continue
            if d[pos:pos + 8] == _TERM:
                children.append({'kind': 'term', 'offset': pos})
                pos += 8
                continue
            if remaining and depth < MAX_DEPTH:
                q = self._probe(pos, remaining, depth)
                if q is not None:
                    aligned = True               # 对位: 外层从 pos 继续读下一字段
                    break
            # 裸区: 字节级找下一锚点 (块锚回退到 [K] 位置)
            m = _ANCHOR_PAT.search(d, pos + 1)
            if not m:
                break
            bare_end = m.start()
            if d[m.start():m.start() + 8] != _TERM:
                kpos = m.start() - 4
                if kpos > pos:
                    bare_end = kpos
            if bare_end - pos > MAX_BARE_IN_CONTAINER:
                break                            # 长裸区 ⇒ 容器终止(未对位)
            children.append({'kind': 'bare', 'offset': pos, 'end': bare_end,
                             'bytes': d[pos:bare_end].hex()[:128]})
            pos = bare_end
        node = {'kind': 'container', 'offset': cpos, 'end': pos, 'children': children}
        if not aligned:
            node['truncated'] = True
        return node, pos, aligned

    # ---------- 块解析 ----------
    def _parse_block(self, pos, flag, key, count, base, depth):
        d, n = self.data, self.n
        ent = base                              # base = header 之后 = 条目区起点
        entries = []
        for i in range(count):
            h, t = struct.unpack_from('<II', d, ent + 8 * i)
            entries.append((h, t))
        p = ent + 8 * count
        fields = {}
        partial = None
        i = 0
        while i < count:
            h, t = entries[i]
            nm = self.name(h)
            try:
                kind, v, q = self.read_value(p, t, depth)
            except Unknown:
                fields[nm] = ('unreadable', p)
                partial = (nm, t, p)
                break
            if kind == 'container':
                cnode, p2, aligned = self.parse_container(q, entries[i + 1:], depth)
                cnode['field'] = nm
                fields[nm] = cnode
                p = p2
                if aligned:
                    i += 1                                # 已对位, 继续下一字段
                    continue
                # 未对位: 保留已解字段, 从 p 重同步
                partial = (nm, t, p)
                break
            fields[nm] = (kind, v)
            p = q
            i += 1
        node = {
            'kind': 'block', 'offset': pos,
            'key': f'{key:08x}', 'keyName': self.name(key),
            'count': count, 'fields': fields,
        }
        if flag:
            node['flag'] = 1
        if partial is not None:
            node['partial'] = partial[0]
            node['failedType'] = f'0x{partial[1]:x}'
            node['failedAt'] = partial[2]
            resync = self._resync(partial[2])
            if resync > partial[2]:
                self.unknowns.append({
                    'start': partial[2], 'end': resync,
                    'reason': f"block {node['keyName']} field '{partial[0]}' "
                              f"type 0x{partial[1]:x} unreadable (partial, "
                              f"{len(fields)} fields kept)"})
            self.resyncs += 1
            self.stats['block_partial'] += 1
            return node, resync
        term = False
        if p + 8 <= n and d[p:p + 8] == _TERM:
            p += 8
            term = True
        node['terminated'] = term
        self.stats['block_ok'] += 1
        self.stats['blk:' + node['keyName']] += 1
        return node, p

    # ---------- 重同步 ----------
    def _resync(self, pos):
        """字节级: 下一 FXSBLKED 起点 或 下一块锚 [-1][1][1] 前的 [K] 位置。"""
        d, n = self.data, self.n
        m = _ANCHOR_PAT.search(d, pos)
        if not m:
            return n
        if d[m.start():m.start() + 8] == _TERM:
            return m.start()                                # walk 顶层会消费为 term
        # 块锚: 回退到 [-1] 前的 [K]
        k = m.start() - 4
        return k if k >= pos else m.start()

    # ---------- 主循环 ----------
    def walk(self, start):
        d, n = self.data, self.n
        pos = start
        while pos < n:
            blk = self._block_at(pos)
            if blk:
                flag, k, cnt, base = blk
                node, pos = self._parse_block(pos, flag, k, cnt, base, 0)
                self.nodes.append(node)
                continue
            if d[pos:pos + 8] == _TERM:
                self.nodes.append({'kind': 'term', 'offset': pos})
                pos += 8
                continue
            # 裸区: 字节级跳到下一锚点 (块锚回退到 [K] 位置)
            m = _ANCHOR_PAT.search(d, pos + 1)
            if not m:
                self.nodes.append({'kind': 'bare', 'offset': pos, 'end': n,
                                   'size': n - pos,
                                   'bytes': d[pos:min(n, pos + 64)].hex()})
                self.stats['bare_regions'] += 1
                break
            bare_end = m.start()
            if d[m.start():m.start() + 8] != _TERM:
                kpos = m.start() - 4
                if kpos > pos:
                    bare_end = kpos
            self.nodes.append({'kind': 'bare', 'offset': pos, 'end': bare_end,
                               'size': bare_end - pos,
                               'bytes': d[pos:min(bare_end, pos + 64)].hex()})
            self.stats['bare_regions'] += 1
            pos = max(bare_end, pos + 1)
        return self.nodes


def find_bag_start(data):
    return data.find(_TERM)


def main():
    if len(sys.argv) < 3:
        print('用法: blockwalk.py <body.bin> <out.json>')
        sys.exit(1)
    data = open(sys.argv[1], 'rb').read()
    dic = load_dictionary()
    w = Walker(data, dic)
    start = find_bag_start(data)
    if start < 0:
        print('未找到 FXSBLKED')
        sys.exit(2)
    w.walk(start + 8)
    blocks = [x for x in w.nodes if x['kind'] == 'block']
    out = {
        'bagStart': start,
        'nodes': w.nodes,
        'unknowns': w.unknowns,
        'stats': {
            'blocks_ok': w.stats['block_ok'],
            'blocks_partial': w.stats['block_partial'],
            'bare_regions': w.stats['bare_regions'],
            'resyncs': w.resyncs,
            'unknown_regions': len(w.unknowns),
            'top_block_names': dict(Counter(
                b['keyName'] for b in blocks).most_common(40)),
        },
    }
    with open(sys.argv[2], 'w') as f:
        json.dump(out, f, ensure_ascii=False)
    s = out['stats']
    print(f"bagStart=0x{start:x} 节点={len(w.nodes)} "
          f"块ok={s['blocks_ok']} 块partial={s['blocks_partial']} "
          f"裸区={s['bare_regions']} 重同步={s['resyncs']}")


if __name__ == '__main__':
    main()
