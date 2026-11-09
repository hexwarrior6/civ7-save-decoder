#!/usr/bin/env python3
"""文明7 城市提取器 (Phase 2) — 从 body.bin 提取每座定居点的可解字段。

CLI: python3 -I tools/cities.py <body.bin> <out.json>

复用 blockwalk.py 的块遍历器（格式见 docs/save-format.md §6），仅扩展:
  1. CityWalker: blob/字符串字段保留原始字节（blockwalk 的 dict 输出会丢高位字节）。
  2. 句柄→对象图取值: 人口等字段在块里是对象句柄（U1 判据，见 docs/notes/phase1-unknowns.md），
     真值在 bag 之前的"对象图区间"里，节点形状 [tag][id][hashA][03][hashB][FP8 u32][id-again]。

已解字段（对面板验证，见 docs/notes/phase2-cities.md）:
  - 名字(loc key)/坐标(blob8 x,y)/人口(总数 HighestPopulation + 乡村/市区/专家 句柄反查)
  - 增长 CurrentFood(FP8) / TurnLastGrowth / GrowthType 等
  - 归属 OwnerIDHistory: [count×(slot,1,turn,hash)]，当前归属/建城者 slot 已解（44 城零冲突）
未解字段（如实输出 null + unresolved 列表）:
  - 七项产量每回合值（存档存的是修正对象 DAG，面板值运行时计算）
  - 增长阈值（U2）/ 幸福度分档值 / 建筑清单（容器未定界）
"""
import sys, os, json, struct, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blockwalk
from blockwalk import Walker, find_bag_start
from propertybag import FXS, load_dictionary

_U = struct.Struct('<I')


class CityWalker(Walker):
    """blockwalk.Walker + blob/字符串原始字节保留。"""

    def read_value(self, pos, vtype, depth):
        d = self.data
        t = vtype & 0xffff
        if t in (0x400, 0x403):                      # 尺寸块 → 保留原始字节
            if pos + 4 > self.n:
                raise blockwalk.Unknown(pos)
            size = _U.unpack_from(d, pos)[0]
            if size > self.n - pos - 4:
                raise blockwalk.Unknown(pos)
            return ('rawblob', d[pos + 4:pos + 4 + size], pos + 4 + size)
        if t == 0x402:                               # 带终止符字符串 → 保留原始字节
            if pos + 4 > self.n:
                raise blockwalk.Unknown(pos)
            ln = _U.unpack_from(d, pos)[0]
            if ln > self.n:
                raise blockwalk.Unknown(pos)
            end = pos + 4 + ln
            padded = end + ((-ln) % 4)
            if padded + 8 <= self.n and d[padded:padded + 8] == FXS:
                return ('rawstr', d[end:padded], padded + 8)
        return super().read_value(pos, vtype, depth)


# ---------- 城市相关块的 schema 签名（keyName 不固定，按字段集识别） ----------

def _is_city_instance(fs):
    return 'HighestPopulation' in fs and 'Name' in fs and 'RuralPopulation' in fs


def _is_growth(fs):
    return 'CurrentFood' in fs and 'NextGrowthFoodThreshold' in fs


def _is_happiness(fs):
    return 'Unhappiness' in fs or 'SuplusHappiness' in fs


def _is_yields(fs):
    return 'Yields' in fs and 'YieldIncomes' in fs


def _is_constructibles_block(fs):
    return 'Constructibles' in fs


# ---------- 对象图取值 ----------

def resolve_handle(data, h, lo, hi):
    """对象图区间内反查句柄 h 的节点值。
    节点形状（E0/现代档双验证）:
      标量节点: [tag][id][hashA][03][hashB][FP8 u32][id-again=id]  → 值 = raw/256
      零值节点: [tag(0x80)][id][hashA][03][hashB][id-again=id]      → 值 = 0
    返回 {'value': float|None, 'how': str}。"""
    if h in (0, 0xffffffff):
        return {'value': None, 'how': 'sentinel'}
    pat = _U.pack(h)
    i = data.find(pat, lo, hi)
    while i >= 0:
        if i + 21 <= hi and data[i + 8] == 3:
            if _U.unpack_from(data, i + 17)[0] == h:          # 标量节点
                v = _U.unpack_from(data, i + 13)[0]
                if v < (1 << 24):                             # 排除句柄/指针式大数
                    return {'value': v / 256.0, 'how': 'scalar@0x%x' % (i - 1)}
            if _U.unpack_from(data, i + 13)[0] == h:          # 零值节点
                return {'value': 0.0, 'how': 'zero@0x%x' % (i - 1)}
        i = data.find(pat, i + 1, hi)
    if i == -1:
        # 至少出现过一次但形状不符
        j = data.find(pat, lo, hi)
        if j >= 0:
            return {'value': None, 'how': 'handle-no-scalar-node (%d occ)' % _count_occ(data, h, lo, hi)}
        return {'value': None, 'how': 'not-in-graph'}


def _count_occ(data, h, lo, hi):
    pat = _U.pack(h)
    n, i = 0, lo
    while True:
        i = data.find(pat, i, hi)
        if i < 0:
            return n
        n += 1
        i += 1


# ---------- OwnerIDHistory 解码 ----------

def decode_owner_history(raw):
    """OwnerIDHistory blob: [u32 count][count × (u32 slot, u32 1, u32 turn, u32 hash)]。
    语义（44 城全量交叉验证，见 phase2-cities.md）:
      slot = 该事件后的归属玩家 slot（条目 f0）；
      turn = 事件发生回合（时代内回合，推断）；
      hash = 事件类型：db081d9b=建立；ba0d/0259/9368/9654…=征服/易主类（细分为未解）；
      hash=ffffffff 的条目是"当前归属"标记，slot 仍是有效归属。
    当前归属 = 最后一条目的 slot；建城者 = 第一条目的 slot。"""
    if raw is None or len(raw) < 4:
        return None
    cnt = _U.unpack_from(raw, 0)[0]
    out = []
    p = 4
    for _ in range(cnt):
        if p + 16 > len(raw):
            break
        slot, one, turn, h = struct.unpack_from('<4I', raw, p)
        p += 16
        out.append({'slot': slot, 'turn': turn, 'hash': '%08x' % h})
    cand = out[-1]['slot'] if out else None
    found = out[0]['slot'] if out else None
    return {'entries': out, 'owner_slot': cand, 'founding_slot': found}


# ---------- 城市名 ----------

_NAME_RE = re.compile(rb'LOC_CITY_NAME_[A-Z0-9_]+')
_CITYSTATE_RE = re.compile(rb'LOC_[A-Z0-9_]+')


def parse_name(raw):
    m = _NAME_RE.search(raw)
    if m:
        return m.group(0).decode('ascii'), 'city'
    m = _CITYSTATE_RE.search(raw)
    if m:
        return m.group(0).decode('ascii'), 'city-state-or-other'
    return None, 'unknown'


# ---------- 主提取 ----------

def extract(body_path):
    data = open(body_path, 'rb').read()
    dic = load_dictionary()
    bag = find_bag_start(data)
    if bag < 0:
        raise SystemExit('未找到 FXSBLKED 属性包')
    w = CityWalker(data, dic)
    w.walk(bag + 8)

    cities = []
    cur = None
    for nd in w.nodes:
        if nd.get('kind') != 'block':
            continue
        fs = nd.get('fields', {})
        if _is_city_instance(fs):
            cur = {'inst': nd, 'growth': None, 'happy': None, 'yields': None,
                   'constructibles': None, 'other': []}
            cities.append(cur)
            continue
        if cur is None:
            continue
        if _is_growth(fs) and cur['growth'] is None:
            cur['growth'] = nd
        elif _is_happiness(fs) and cur['happy'] is None:
            cur['happy'] = nd
        elif _is_yields(fs) and cur['yields'] is None:
            cur['yields'] = nd
        elif _is_constructibles_block(fs) and cur['constructibles'] is None:
            cur['constructibles'] = nd
        else:
            cur['other'].append(nd)

    out_cities = []
    for idx, c in enumerate(cities):
        inst, growth, happy = c['inst'], c['growth'], c['happy']
        fs = inst['fields']

        # --- 名字 ---
        name_raw = fs.get('Name')
        if name_raw and name_raw[0] == 'rawstr':
            name_raw = name_raw[1]
        elif name_raw and name_raw[0] == 'rawblob' and isinstance(name_raw[1], bytes):
            name_raw = name_raw[1]
        else:
            name_raw = b''
        loc_key, name_kind = parse_name(name_raw)

        # --- 坐标 ---
        loc = fs.get('Location')
        if loc and loc[0] == 'rawblob' and isinstance(loc[1], bytes) and len(loc[1]) == 8:
            plot_xy = list(struct.unpack('<2i', loc[1]))
        elif loc and loc[0] == 'blob8':
            plot_xy = list(loc[1])
        else:
            plot_xy = None
        plot = plot_xy[1] * 74 + plot_xy[0] if plot_xy else None   # 地图宽 74（见 save-format §3.4）

        # --- 人口（总数直读 + 分项句柄反查） ---
        def blob4(nm):
            v = fs.get(nm)
            if v and v[0] == 'rawblob' and isinstance(v[1], bytes) and len(v[1]) == 4:
                return _U.unpack(v[1])[0]
            return v[1] if v and v[0] == 'blob4' else None

        def rawval(nm, fields=None):
            v = (fields or fs).get(nm)
            if v and v[0] == 'rawblob' and isinstance(v[1], bytes) and len(v[1]) == 4:
                return _U.unpack(v[1])[0]
            return v[1] if v and v[0] == 'scalar' else None

        highest = rawval('HighestPopulation')
        pops = {}
        for nm in ('RuralPopulation', 'UrbanPopulation', 'WorkerPopulation',
                   'OverGrowthUnitPopulation', 'Population', 'NumRandomEventsFertility'):
            h = blob4(nm)
            if h is not None:
                r = resolve_handle(data, h, 0, bag)
            else:
                r = {'value': None, 'how': 'no-field'}
            pops[nm] = {'handle': h}
            pops[nm].update(r)
        rural = pops['RuralPopulation']['value']
        urban = pops['UrbanPopulation']['value']
        worker = pops['WorkerPopulation']['value']
        pop_sum = None
        if None not in (rural, urban, worker):
            pop_sum = rural + urban + worker

        # --- 增长 ---
        g = {}
        if growth is not None:
            gf = growth['fields']
            g['current_food'] = (rawval('CurrentFood', gf) or 0) / 256.0 \
                if rawval('CurrentFood', gf) is not None else None
            for nm in ('TurnLastGrowth', 'OverGrowthCount', 'PercentGrowthAfterWorkerPlacement',
                       'PercentGrowthAfterRuralPlacement'):
                g[nm] = rawval(nm, gf)
            thr = gf.get('NextGrowthFoodThreshold')
            g['growth_threshold'] = {
                'handle': rawval('NextGrowthFoodThreshold', gf),
                'value': None,
                'note': 'U2 未解: 句柄→修正对象, 面板值运行时计算'}
            g['growth_type_raw'] = rawval('GrowthType', gf)

        # --- 幸福度块（块可读, 数值未解） ---
        hinfo = None
        if happy is not None:
            hf = happy['fields']
            hinfo = {}
            for nm in ('OvercrowdingCount', 'GarrisonCount', 'SiegeCount', 'NoFreshWater', 'CanRevolt'):
                v = hf.get(nm)
                hinfo[nm] = v[1] if v and v[0] == 'scalar' else None
            uh = hf.get('Unhappiness')
            hinfo['unhappiness_handle'] = rawval('Unhappiness', hf)
            sh = hf.get('SuplusHappiness')
            hinfo['surplus_happiness_handle'] = rawval('SuplusHappiness', hf)
            hinfo['mood_value'] = None
            hinfo['note'] = '幸福度分档值未解: Unhappiness/SuplusHappiness 均为句柄, 面板"愉快"档对应值未还原'

        # --- 连接定居点（贸易/城镇网络, 直读 blob: [u32 count][count × (u16,u16)]） ---
        ccl = fs.get('ConnectedCitiesList')
        connected = None
        if ccl and ccl[0] == 'rawblob' and isinstance(ccl[1], bytes) and len(ccl[1]) >= 4:
            connected = _U.unpack_from(ccl[1], 0)[0]

        # --- 归属 ---
        oh = fs.get('OwnerIDHistory')
        owner = decode_owner_history(oh[1]) if oh and oh[0] == 'rawblob' else None

        # --- 建筑清单（尽力: 容器未定界, 如实未解） ---
        buildings = None
        cb = c['constructibles']
        if cb is not None:
            con = cb['fields'].get('Constructibles')
            if isinstance(con, dict):
                buildings = {'container_children': len(con.get('children', [])),
                             'truncated': bool(con.get('truncated')),
                             'note': '0x402 容器形未定界, 建筑子块未全部解出'}

        out_cities.append({
            'index': idx,
            'name': loc_key,
            'name_kind': name_kind,
            'location': plot_xy,
            'plot': plot,
            'population': {
                'highest': highest,
                'rural': rural, 'urban': urban, 'worker': worker,
                'sum': pop_sum,
                'handles': pops,
            },
            'growth': g,
            'happiness': hinfo,
            'connected_settlements': connected,
            'owner': owner,
            'buildings': buildings,
            'block_offsets': {'instance': hex(inst['offset']),
                              'growth': hex(growth['offset']) if growth else None,
                              'happiness': hex(happy['offset']) if happy else None,
                              'yields': hex(c['yields']['offset']) if c['yields'] else None},
        })

    return {
        'source': os.path.abspath(body_path),
        'bag_start': bag,
        'num_settlements': len(out_cities),
        'unresolved': [
            '七项产量每回合值: Yields/YieldIncomes 等为修正对象 DAG 句柄, 面板值运行时计算, 公式未解',
            '增长阈值 (U2): NextGrowthFoodThreshold/Base/Discount 为句柄',
            '幸福度分档值: Unhappiness/SuplusHappiness 为句柄, 无 0~20 区间标量落盘',
            '建筑清单: Constructibles 为 0x402 容器形, 边界未定界',
            'OwnerIDHistory 的 turn 时代对齐与 4 种易主事件 hash 细分未解 (slot 语义已解)',
        ],
        'cities': out_cities,
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    result = extract(sys.argv[1])
    with open(sys.argv[2], 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    n = result['num_settlements']
    ok = sum(1 for c in result['cities']
             if c['population']['sum'] is not None)
    print(f'定居点={n} 人口分项可解={ok} -> {sys.argv[2]}')


if __name__ == '__main__':
    main()
