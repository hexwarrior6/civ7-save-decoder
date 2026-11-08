#!/usr/bin/env python3
"""文明7 FXSBLKED 属性包解析器 (DelineatedData / VariantValue 格式)

格式逆向结论 (2026-11-09, 基于游戏二进制反汇编 + 存档双重验证):
- 字段名哈希 = CRC32(ASCII), poly=0xEDB88320, init=0xFFFFFFFF, 无终值异或
- 类型 = VariantValueType (0..0x20 基础类型; 0x400|base = 修饰类型)
- 块 = [u32 hash][1][-1][1][1][count][count x (hash,type)][values 按序]
- 0x402 = 字符串: [u32 len][bytes][u64 "FXSBLKED" 终止符]
- 0x400/0x403 = 尺寸块: [u32 size][size bytes]
- 0x407 = FixedPoint<8>: u32 raw, 值 = raw/256
"""
import struct, sys, re, json
from collections import Counter

FXS = b'FXSBLKED'

# ---------- CRC32 名称哈希 ----------
_TBL = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ (0xEDB88320 if _c & 1 else 0)
    _TBL.append(_c)

def crc32_name(s: str) -> int:
    c = 0xFFFFFFFF
    for b in s.encode('ascii'):
        c = ((c >> 8) ^ _TBL[(c ^ b) & 0xFF]) & 0xFFFFFFFF
    return c

# ---------- 类型表 ----------
BASE_TYPES = {0:'None',1:'Bool',2:'Char',3:'Char16',4:'Int8',5:'UInt8',6:'Int16',7:'UInt16',
 8:'Int',9:'UInt',10:'Int64',11:'UInt64',12:'Float',13:'Double',14:'VariantObject',
 15:'PairInt16',16:'PairUInt16',17:'PairInt32',18:'PairInt64',19:'PairFloat',20:'PairDouble',
 21:'TripletInt16',22:'TripletUInt16',23:'TripletInt32',24:'TripletInt64',25:'TripletFloat',
 26:'TripletDouble',27:'VariantMap',28:'VariantVector',29:'TypedVariantMap',
 30:'TypedVariantVector',31:'TypedVariantVectorMap',32:'GUID'}
SCALAR_SIZE = {1:1,2:1,3:2,4:1,5:1,6:2,7:2,8:4,9:4,10:8,11:8,12:4,13:8,
 15:4,16:4,17:8,18:16,19:8,20:16,21:6,22:6,23:12,24:24,25:12,26:24,32:16}

def type_name(t):
    base = t & 0xff
    mod = t & 0xffff
    n = BASE_TYPES.get(base, f'?{base}')
    if mod == 0x400: return f'Block[{n}]'
    if mod == 0x402: return 'String'
    if mod == 0x407: return 'FixedPoint8'
    if mod == 0x403: return f'BlockS[{n}]'
    if mod == 0x405: return f'TermBlock[{n}]'
    return n

# ---------- 字段名字典 ----------
def load_dictionary(extra_files=()):
    names = set()
    here = __file__.rsplit('/', 1)[0]
    for fn in ['fieldnames.txt', 'opennames.txt', *extra_files]:
        try:
            with open(f'{here}/{fn}') as f:
                names.update(l.strip() for l in f if l.strip())
        except FileNotFoundError:
            pass
    return {crc32_name(n): n for n in names}

# ---------- 解析器 ----------
class Bag:
    def __init__(self, data, dic):
        self.data = data
        self.dic = dic
        self.unk = Counter()

    def name(self, h):
        return self.dic.get(h, f'hash_{h:08x}')

    def read_value(self, pos, vtype):
        """返回 (value, new_pos)。value = ('str',s)|('fp8',float)|('block',start,size)|('scalar',int/float)|('raw',bytes)"""
        d = self.data
        mod = vtype & 0xffff
        base = vtype & 0xff
        if mod == 0x402:                      # 字符串 + FXSBLKED 终止符
            ln = struct.unpack_from('<I', d, pos)[0]; pos += 4
            s = d[pos:pos+ln]; pos += ln
            pos += 8                          # Terminator64
            return ('str', s.decode('utf-8', 'replace')), pos
        if mod in (0x400, 0x403):             # 尺寸块
            size = struct.unpack_from('<I', d, pos)[0]; pos += 4
            return ('block', pos, size), pos + size
        if mod == 0x407:                      # FixedPoint<8>
            v = struct.unpack_from('<I', d, pos)[0]; pos += 4
            return ('fp8', v / 256.0), pos
        if mod == 0x405:                      # 终止块 (待细究)
            size = struct.unpack_from('<I', d, pos)[0]; pos += 4
            return ('block', pos, size), pos + size + 8
        sz = SCALAR_SIZE.get(base)
        if sz is None:
            raise ValueError(f'unsupported type {vtype:#x} at {pos:#x}')
        raw = d[pos:pos+sz]; pos += sz
        if base in (8,):    v = struct.unpack('<i', raw)[0]
        elif base == 9:     v = struct.unpack('<I', raw)[0]
        elif base in (10,): v = struct.unpack('<q', raw)[0]
        elif base == 11:    v = struct.unpack('<Q', raw)[0]
        elif base == 12:    v = struct.unpack('<f', raw)[0]
        elif base == 13:    v = struct.unpack('<d', raw)[0]
        elif base in (1,):  v = raw[0]
        elif sz == 1:       v = raw[0]
        elif sz == 2:       v = struct.unpack('<H', raw)[0]
        else:               v = raw
        return ('scalar', v), pos

    def parse_block(self, pos, depth=0):
        """块 = [hash][1][-1][1][1][count][entries][values]. 返回 (dict, pos)"""
        d = self.data
        start = pos
        block_hash = struct.unpack_from('<I', d, pos)[0]
        a, b = struct.unpack_from('<II', d, pos+4)
        assert a == 1 and b == 0xffffffff, f'bad block header at {pos:#x}: {a:#x}/{b:#x}'
        c1, c2 = struct.unpack_from('<II', d, pos+12)
        assert c1 == 1 and c2 == 1, f'bad block consts at {pos:#x}'
        count = struct.unpack_from('<I', d, pos+16)[0]
        pos += 20
        entries = []
        for _ in range(count):
            h, t = struct.unpack_from('<II', d, pos)
            entries.append((h, t)); pos += 8
        fields = {}
        for h, t in entries:
            try:
                val, pos = self.read_value(pos, t)
            except (ValueError, struct.error) as e:
                raise ValueError(f'{e} (field {self.name(h)} at {pos:#x})')
            fields[self.name(h)] = (type_name(t), val)
        meta = {'hash': f'{block_hash:08x}', 'name': self.name(block_hash),
                'offset': start}
        return ({'__meta': meta, **fields}, pos)

def parse_stream(data, dic, start=0, max_blocks=100000):
    """从 start 起连续解析块流; 块以 FXSBLKED 字符串终止符分隔"""
    bag = Bag(data, dic)
    blocks = []
    pos = start
    while pos < len(data) - 20 and len(blocks) < max_blocks:
        # 对齐: 跳过到下一个块头模式 [u32][1][-1]
        while pos < len(data) - 24:
            a, b = struct.unpack_from('<II', data, pos+4)
            if a == 1 and b == 0xffffffff:
                break
            pos += 4
        if pos >= len(data) - 24:
            break
        try:
            blk, pos = bag.parse_block(pos)
        except (ValueError, AssertionError) as e:
            blocks.append({'__error': str(e), 'offset': hex(pos)})
            pos += 4
            continue
        blocks.append(blk)
    return bag, blocks

def main():
    if len(sys.argv) < 2:
        print('用法: propertybag.py <解压后的body.bin> [关键词过滤]')
        sys.exit(1)
    data = open(sys.argv[1], 'rb').read()
    dic = load_dictionary()
    print(f'字典大小: {len(dic)}')
    filt = sys.argv[2] if len(sys.argv) > 2 else None

    bag, blocks = parse_stream(data, dic)
    print(f'解析出 {len(blocks)} 个块')
    errs = sum(1 for b in blocks if '__error' in b)
    print(f'错误块: {errs}')

    if filt:
        shown = 0
        for blk in blocks:
            s = json.dumps(blk, ensure_ascii=False, default=str)
            if filt.lower() in s.lower():
                print(s[:2000])
                shown += 1
                if shown >= 5: break
    else:
        # 统计块名分布
        names = Counter(b.get('__meta', {}).get('name', '?') for b in blocks)
        for n, c in names.most_common(30):
            print(f'  {n}: {c}')

if __name__ == '__main__':
    main()
