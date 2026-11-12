#!/usr/bin/env python3
"""文明7 地图地形/资源提取器 (Phase 6, 2026-11-12)

用法: python3 -I tools/terrain.py <body.bin> <out.json>

破解结论 (详见 docs/notes/phase6-terrain.md):
- 地图数据在 FXS 属性包内 Plots 块 (hash 0x4b8d928f, 字段名 Plots) 的 0x402 容器里。
  容器负载头: [u32 1][u32 W][u32 H][u32 6][u32 W*H][3 x u32 0x00010000][u32 -1][u32 0][u32 6]
- 其后为 W*H 条 plot 记录, 每条以地形类型 CRC 哈希开头 (自定界, 无统一 stride):
  记录 = [terrain u32][biome u32][continent u32][可变段][尾 24B = 8 x i16 + u32 + u32]
  常规记录 73 B; 自然奇观格 125 B (附加 52 B 奇观数据); 数组最后一条仅 49 B (无尾 24B)。
- 字段 CRC = CRC32(0xEDB88320, init -1) (复用 propertybag.crc32_name)。
- 已解字段: 地形/生物群系/大陆/特征(含自然奇观)/资源/道路/单位存在位(u41)/高度场(u12)。
- 探索迷雾位图 (BatchA 收尾②已破解): 每玩家一条 3404B 数组 (0/1, 1=已探索), 位于
  Plots 块之后的视野大区 (E0 0x3364fe 起), 由 extract_explored() 提取, 证据见
  docs/notes/batchA-misc.md §2。
- 未解: u14 (平滑静态场) / u18 (6 位掩码) / u39 (半静态小计数) / 尾 24B g-h 的语义, 原值输出。
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propertybag import crc32_name  # CRC32(0xEDB88320, init=-1), 与字段名哈希同一算法

# 游戏本体 XML (modules/*/data) 提取的标准词表 —— 地形/生态/大陆名为地图脚本生成,
# 不落盘明文, 必须内置; 资源/特征名同时在存档 DB 快照明文出现 (运行时会再 grep body 补充)。
VOCAB = """
BIOME_1 BIOME_2 BIOME_3 BIOME_4 BIOME_DESERT BIOME_GRASSLAND BIOME_MARINE BIOME_PLAINS
BIOME_TROPICAL BIOME_TUNDRA CONTINENT_AFRICA CONTINENT_AMASIA CONTINENT_AMERICA
CONTINENT_ANTARCTICA CONTINENT_ARCTICA CONTINENT_ASIA CONTINENT_ASIAMERICA CONTINENT_ATLANTICA
CONTINENT_ATLANTIS CONTINENT_AUSTRALIA CONTINENT_AVALONIA CONTINENT_AZANIA CONTINENT_BALTICA
CONTINENT_CIMMERIA CONTINENT_COLUMBIA CONTINENT_CONGO_CRATON CONTINENT_EURAMERICA
CONTINENT_EUROPE CONTINENT_GONDWANA CONTINENT_KALAHARIA CONTINENT_KAZAKHSTANIA
CONTINENT_KERNORLAND CONTINENT_KUMARI_KANDAM CONTINENT_LAURASIA CONTINENT_LAURENTIA
CONTINENT_LEMURIA CONTINENT_MU CONTINENT_NENA CONTINENT_NORTH_AMERICA CONTINENT_NOVOPANGAEA
CONTINENT_NUNA CONTINENT_OCEANIA CONTINENT_PANGAEA CONTINENT_PANGAEA_ULTIMA CONTINENT_PANNOTIA
CONTINENT_RODINIA CONTINENT_SIBERIA CONTINENT_SOUTH_AMERICA CONTINENT_TERRA_AUSTRALIS
CONTINENT_UR CONTINENT_VAALBARA CONTINENT_VENDIAN CONTINENT_ZEALANDIA FEATURE_ADDED_TO_MAP
FEATURE_ATOLL FEATURE_ATTRIBUTE FEATURE_BARRIER_REEF FEATURE_BERMUDA_TRIANGLE FEATURE_CHANGED
FEATURE_CLASS_AQUATIC FEATURE_CLASS_FLOODPLAIN FEATURE_CLASS_VEGETATED FEATURE_CLASS_WET
FEATURE_COLD_REEF FEATURE_DESERT_FLOODPLAIN FEATURE_DESERT_FLOODPLAIN_MINOR
FEATURE_DESERT_FLOODPLAIN_NAVIGABLE FEATURE_FOREST FEATURE_GRAND_CANYON
FEATURE_GRASSLAND_FLOODPLAIN FEATURE_GRASSLAND_FLOODPLAIN_MINOR
FEATURE_GRASSLAND_FLOODPLAIN_NAVIGABLE FEATURE_GULLFOSS FEATURE_HOERIKWAGGO FEATURE_ICE
FEATURE_IGUAZU_FALLS FEATURE_KILIMANJARO FEATURE_LOTUS FEATURE_MANGROVE FEATURE_MARSH
FEATURE_MOUNT_EVEREST FEATURE_MOUNT_FUJI FEATURE_OASIS FEATURE_PLAINS_FLOODPLAIN
FEATURE_PLAINS_FLOODPLAIN_MINOR FEATURE_PLAINS_FLOODPLAIN_NAVIGABLE FEATURE_RAINFOREST
FEATURE_REDWOOD_FOREST FEATURE_REEF FEATURE_REMOVED_FROM_MAP FEATURE_SAGEBRUSH_STEPPE
FEATURE_SAVANNA_WOODLAND FEATURE_TAIGA FEATURE_THERA FEATURE_TORRES_DEL_PAINE
FEATURE_TROPICAL_FLOODPLAIN FEATURE_TROPICAL_FLOODPLAIN_MINOR
FEATURE_TROPICAL_FLOODPLAIN_NAVIGABLE FEATURE_TUNDRA_BOG FEATURE_TUNDRA_FLOODPLAIN
FEATURE_TUNDRA_FLOODPLAIN_MINOR FEATURE_TUNDRA_FLOODPLAIN_NAVIGABLE FEATURE_ULURU
FEATURE_VALLEY_OF_FLOWERS FEATURE_VISIBILITY_CHANGED FEATURE_VOLCANO FEATURE_WATERING_HOLE
FEATURE_ZHANGJIAJIE RESOURCE_ADDED_TO_MAP RESOURCE_AMOUNT_CHANGED RESOURCE_CAMELS
RESOURCE_CAP_CHANGED RESOURCE_CHANGED RESOURCE_CITRUS RESOURCE_CLAY RESOURCE_CLOVES
RESOURCE_COAL RESOURCE_COCOA RESOURCE_COFFEE RESOURCE_CONSUMED RESOURCE_COTTON RESOURCE_COWRIE
RESOURCE_CRABS RESOURCE_DATES RESOURCE_DYES RESOURCE_FISH RESOURCE_FLAX RESOURCE_FURS
RESOURCE_GOLD RESOURCE_GOLD_DISTANT_LANDS RESOURCE_GYPSUM RESOURCE_HARDWOOD RESOURCE_HIDES
RESOURCE_HORSES RESOURCE_INCENSE RESOURCE_IRON RESOURCE_IVORY RESOURCE_JADE RESOURCE_KAOLIN
RESOURCE_LAPIS_LAZULI RESOURCE_LIMESTONE RESOURCE_LLAMAS RESOURCE_MANGOS RESOURCE_MARBLE
RESOURCE_NICKEL RESOURCE_NITER RESOURCE_OIL RESOURCE_PEARLS RESOURCE_PITCH RESOURCE_QUININE
RESOURCE_REMOVED_FROM_MAP RESOURCE_RICE RESOURCE_RUBBER RESOURCE_RUBIES RESOURCE_SALT
RESOURCE_SILK RESOURCE_SILVER RESOURCE_SILVER_DISTANT_LANDS RESOURCE_SLOT_1 RESOURCE_SPICES
RESOURCE_SUGAR RESOURCE_TAG RESOURCE_TEA RESOURCE_TIN RESOURCE_TOBACCO RESOURCE_TRUFFLES
RESOURCE_TURTLES RESOURCE_VISIBILITY_CHANGED RESOURCE_WHALES RESOURCE_WILD_GAME RESOURCE_WINE
RESOURCE_WOOL ROUTE_ADDED_TO_MAP ROUTE_CHANGED ROUTE_RAILROAD ROUTE_REMOVED_FROM_MAP ROUTE_ROAD
ROUTE_STAATSEISENBAHN TERRAIN_COAST TERRAIN_FLAT TERRAIN_HILL TERRAIN_MOUNTAIN
TERRAIN_NAVIGABLE_RIVER TERRAIN_OCEAN TERRAIN_STATE_CHANGED TERRAIN_SUBTYPE_CHANGED
TERRAIN_TYPE_CHANGED
""".split()

FXS = b'FXSBLKED'
NONE32 = 0xFFFFFFFF


def build_dict(body):
    """内置词表 + 存档 DB 快照明文 grep (RESOURCE_/FEATURE_ 等新名字)。"""
    names = set(VOCAB)
    for m in re.finditer(rb'[A-Z][A-Z0-9_]{4,60}', body):
        s = m.group().decode('ascii')
        if s.split('_')[0] in ('RESOURCE', 'FEATURE', 'TERRAIN', 'BIOME', 'CONTINENT', 'ROUTE', 'LANDMASS', 'REGION'):
            names.add(s)
    return {crc32_name(n): n for n in names}


def find_map(body, terr_hashes):
    """扫描 Plots 容器负载头 [1][W][H][6][W*H], 用后续记录的地形哈希验证。"""
    n = len(body)
    for p in range(0x200000, n - 64):
        if struct.unpack_from('<I', body, p)[0] != 1:
            continue
        w, h, six, cnt = struct.unpack_from('<IIII', body, p + 4)
        if not (8 <= w <= 512 and 8 <= h <= 512 and six == 6 and cnt == w * h):
            continue
        q = p + 44  # 20B 头 + 12B (3 x 0x00010000) + 12B (-1, 0, 6)
        if q + 8 > n:
            continue
        ok = 0
        for k in range(min(6, cnt)):
            off = q + 73 * k
            if off + 4 <= n and struct.unpack_from('<I', body, off)[0] in terr_hashes:
                ok += 1
        if ok >= min(5, cnt):
            return p, q, w, h, cnt
    return None


def parse_plots(body, q, cnt, terr_hashes, d):
    """逐条解析 plot 记录。记录以 terrain hash 开头自定界; 最后一条以数组后的 FXSBLKED 收尾。"""
    starts = []
    pos = q
    for k in range(cnt):
        t = struct.unpack_from('<I', body, pos)[0]
        if t not in terr_hashes:
            raise ValueError(f'记录 {k} @ {pos:#x}: 首字段不是地形哈希 ({t:#010x})')
        starts.append(pos)
        j = pos + 4
        nxt = None
        while j < pos + 200:
            v = struct.unpack_from('<I', body, j)[0]
            if v in terr_hashes:
                nxt = j
                break
            j += 1
        if k < cnt - 1:
            if nxt is None:
                raise ValueError(f'记录 {k} @ {pos:#x}: 200B 内找不到下一条记录边界')
            pos = nxt
        else:
            # 最后一条: 数组结尾 = 其后第一个 FXSBLKED (块终止符)
            end = body.find(FXS, pos, pos + 200)
            if end < 0:
                raise ValueError(f'最后一条记录 @ {pos:#x}: 200B 内找不到 FXSBLKED')
            starts.append(end)
    plots = []
    for k in range(cnt):
        s = starts[k]
        e = starts[k + 1] if k < cnt - 1 else starts[cnt]
        L = e - s
        row = body[s:s + L]
        th, bh, ch = struct.unpack_from('<III', row, 0)
        fh = struct.unpack_from('<I', row, 19)[0]
        rh = struct.unpack_from('<I', row, 25)[0]
        roh = struct.unpack_from('<I', row, 31)[0]
        p = {
            'i': k, 'x': k % 74, 'y': k // 74,  # x/y 下面用真实 W 重算
            'terrain': d.get(th, f'unknown:{th:08x}'),
            'biome': d.get(bh, f'unknown:{bh:08x}'),
            'continent': None if ch == NONE32 else d.get(ch, f'unknown:{ch:08x}'),
            'feature': None if fh == NONE32 else d.get(fh, f'unknown:{fh:08x}'),
            'resource': None if rh == NONE32 else d.get(rh, f'unknown:{rh:08x}'),
            'len': L,
            'wonder': L == 125,
            'elv': struct.unpack_from('<H', row, 12)[0],       # 高度场: 0=海,200=湖,30-140=陆,180=山
            'v14': struct.unpack_from('<H', row, 14)[0],       # 未解: 平滑静态场 (空间自相关0.81), 仅陆地+湖非零
            'u16': row[16],                                    # 岛群标志: 2 ⟺ u17==0 (region0), 否则 0 (两图精确)
            'u17': row[17],                                    # 地图大区 id: 0=岛群(多blob),1/2=连续大陆区,255=外洋
            'u18': row[18],                                    # 未解: 6 位掩码 (每 bit 121-135 格, 富集海岸/资源邻接)
            'road': None if roh == NONE32 else d.get(roh, f'unknown:{roh:08x}'),
            'u39': row[39],                                    # 未解: 半静态计数 0-30 (建城区格被覆写, 高值集中奇观)
            'unit': row[41],                                   # 单位存在位 (E0 68/69 与 units.py 吻合, 迁民单位除外)
            'u42': row[42],                                    # 地形分类: 255=水/山/可航河, 0=丘陵, 1=平地裸, 2=平地湿润植被
            'u43': struct.unpack_from('<H', row, 43)[0],       # 地块上的 城区/城市 实例 id (城市中心非 0)
            'u45': struct.unpack_from('<H', row, 45)[0],
            'u47': row[47],                                    # bit3=不可通行(冰/山/THERA/GC/ZJJ/ULURU), bit4-6=u18 bit3/1/2 镜像
            'tail': (list(struct.unpack_from('<8h', row, L - 24))
                     if L >= 73 else None),  # 末 24B: 8 x i16 (3+1 个 (start,end) 区间对) + u32 + u32(=6)
            'g': struct.unpack_from('<I', row, L - 8)[0] if L >= 73 else None,
            'h': struct.unpack_from('<I', row, L - 4)[0] if L >= 73 else None,  # 常为 6 (语义未定证)
        }
        if L == 125:
            p['wonder_extra'] = row[49:L - 24].hex()
        # BatchA 收尾③ 定证的语义字段 (证据见 docs/notes/batchA-misc.md §3)
        p['terrain_class'] = {255: 'water_or_mountain', 0: 'hill', 1: 'flat_bare',
                              2: 'flat_vegetated'}.get(row[42], f'raw{row[42]}')
        p['region_id'] = None if row[17] == 255 else row[17]  # 0=岛群, 1/2=连续大陆区
        p['island_region'] = row[16] == 2
        p['impassable'] = bool(row[47] >> 3 & 1)
        plots.append(p)
    return plots, starts


def scan_plots_revealed(body):
    """每玩家 PlotsRevealed 计数 (块 hash_b6be9ade: Properties/PlotsRevealed:Int/CommanderWarReinforcementCalls)。
    块按文件序 = 玩家实例序 (slot 0..N-1, 含 id=63 的第 31 玩家)。值偏移 = 块头24 + schema3x8 + Properties值16 = +64。"""
    pat = bytes.fromhex('de9abeb601000000ffffffff010000000100000003000000')
    out = []
    i = 0
    while True:
        j = body.find(pat, i)
        if j < 0:
            break
        out.append(struct.unpack_from('<I', body, j + 64)[0])
        i = j + 1
    return out


def extract_explored(body, scan_lo=0x2e0000, scan_hi=0xd80000):
    """BatchA 收尾②已破解: 每玩家探索迷雾 = 逐格 3404B 字节数组 (0/1, 1=已探索),
    位于 Plots 块之后 / 玩家实例区之前的视野大区 (E0 0x3364fe 起, 步长 ~0x92D9/玩家)。
    记录 = [u32 k][u32 2][u32 k][u32 pc][u8 flag][u32 3404][3404 字节] (前 5 项按 4B 字节
    包打包, 3404 为 LE): k = 玩家实例 id (0..29,63), pc = popcount (flag=1 的记录不写, 恒 0,
    实际数以数组为准), 数据段即位图本体。
    校验: E0==E1==E2==E6==E7 逐字节一致 (迷雾不随已探索区内移动变化); E0→E5.1 每玩家
    新增 bit 数 == b6be9ade PlotsRevealed 增量 (24 玩家中 23 个精确相等); 单位位置
    186/186(MODERN)+69/69(E0) 全部落在本玩家已探索格; 死亡城邦 (从未探索) 全 0。
    返回 {k: {'offset', 'popcount', 'plots':[...], 'pc_field', 'flag'}}。"""
    out = {}
    pos = scan_lo
    n = min(scan_hi, len(body))
    while True:
        j = body.find(struct.pack('<I', 3404), pos, n)
        if j < 0:
            break
        seg = body[j + 4:j + 4 + 3404]
        if len(seg) == 3404:
            k = struct.unpack_from('<I', body, j - 9)[0]
            mid = struct.unpack_from('<I', body, j - 13)[0]
            if mid == 2 and k < 0x10000 and k not in out and max(seg) <= 3:
                out[k] = {
                    'offset': j - 17,
                    'popcount': sum(1 for b in seg if b),
                    'pc_field': struct.unpack_from('<I', body, j - 5)[0],
                    'flag': body[j - 1],
                    'plots': [i for i, b in enumerate(seg) if b],
                }
        pos = j + 1
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    body = open(src, 'rb').read()
    d = build_dict(body)
    terr_hashes = {h for h, n in d.items() if n.startswith('TERRAIN_')}
    found = find_map(body, terr_hashes)
    if not found:
        print('错误: 未找到 Plots 数组头', file=sys.stderr)
        sys.exit(2)
    p, q, w, h, cnt = found
    plots, starts = parse_plots(body, q, cnt, terr_hashes, d)

    for pl in plots:  # 用真实 W 修正 x/y
        pl['x'] = pl['i'] % w
        pl['y'] = pl['i'] // w

    def counter(key):
        c = {}
        for pl in plots:
            v = pl[key]
            if v is None:
                continue
            c[v] = c.get(v, 0) + 1
        return dict(sorted(c.items(), key=lambda kv: -kv[1]))

    land = sum(1 for pl in plots if pl['terrain'] in ('TERRAIN_FLAT', 'TERRAIN_HILL', 'TERRAIN_MOUNTAIN', 'TERRAIN_NAVIGABLE_RIVER'))
    resources = {}
    for pl in plots:
        if pl['resource']:
            resources.setdefault(pl['resource'], []).append([pl['x'], pl['y']])
    unresolved_hashes = sum(1 for pl in plots if pl['terrain'].startswith('unknown:')
                            or pl['biome'].startswith('unknown:')
                            or (pl['feature'] or '').startswith('unknown:')
                            or (pl['resource'] or '').startswith('unknown:'))
    # --- 探索迷雾位图 (每玩家, BatchA 收尾②) ---
    explored = extract_explored(body)
    pr_counts = scan_plots_revealed(body)
    exp_players = {}
    pop_eq_pr = 0
    for idx, k in enumerate(sorted(explored)):
        e = explored[k]
        pr = pr_counts[idx] if idx < len(pr_counts) else None
        if pr is not None and e['popcount'] == pr:
            pop_eq_pr += 1
        exp_players[str(k)] = {
            'offset': f"{e['offset']:#x}", 'popcount': e['popcount'],
            'plots_revealed_count_same_index': pr,
            'plots': e['plots'],
        }
    out = {
        'source': src,
        'map': {'header_offset': p, 'array_offset': q, 'width': w, 'height': h, 'plots': cnt},
        'self_check': {
            'count_eq_WxH': cnt == w * h,
            'records_parsed': len(plots),
            'record_len_73': sum(1 for pl in plots if pl['len'] == 73),
            'record_len_125_wonder': sum(1 for pl in plots if pl['len'] == 125),
            'names_unresolved': unresolved_hashes,
        },
        'summary': {
            'land_plots': land,
            'terrain': counter('terrain'),
            'biome': counter('biome'),
            'continent': counter('continent'),
            'feature': counter('feature'),
            'road_plots': sum(1 for pl in plots if pl['road']),
            'unit_present': sum(1 for pl in plots if pl['unit']),
            'wonder_plots': [pl['i'] for pl in plots if pl['wonder']],
            'terrain_class': counter('terrain_class'),
            'region_id': {str(k): v for k, v in sorted(counter('region_id').items(), key=lambda kv: str(kv[0]))},
            'island_region_plots': sum(1 for pl in plots if pl['island_region']),
            'impassable_plots': sum(1 for pl in plots if pl['impassable']),
        },
        'resources': {k: {'count': len(v), 'plots_xy': v} for k, v in sorted(resources.items(), key=lambda kv: -len(kv[1]))},
        'exploration': {
            'status': '已破解: 每玩家一条 3404B 数组 (0/1, 1=已探索), 记录头 '
                      '[u32 玩家id][u32 2][u32 玩家id][u32 pc][u8 flag][u32 3404]; '
                      'key = 玩家实例 id (0..N-1 + 63)。证据: 同局各档逐字节一致; '
                      'E0→E5.1 每玩家新增格数与 b6be9ade PlotsRevealed 增量 30/31 精确相等; '
                      '单位位置全落本玩家已探索格 (E0 69/69, MODERN 186/186 有效位); '
                      '各玩家位图 = 围绕首都的连通区域。见 batchA-misc.md §2。',
            'players': exp_players,
            'popcount_eq_plotsrevealed': f'{pop_eq_pr}/{len(explored)} '
                '(城邦精确相等; 主要文明 popcount>PlotsRevealed, 差额来源未定证)',
            'plots_revealed_counts_by_index': pr_counts,
        },
        'plots': plots,
    }
    with open(dst, 'w') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"地图 {w}x{h} = {cnt} 格 | 陆地 {land} | 资源 {sum(len(v) for v in resources.values())}格/"
          f"{len(resources)}种 | 奇观格 {sum(1 for pl in plots if pl['wonder'])} | 道路 {out['summary']['road_plots']}"
          f" | 名称未反查 {unresolved_hashes} -> {dst}")


if __name__ == '__main__':
    main()
