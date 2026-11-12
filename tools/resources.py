#!/usr/bin/env python3
"""文明7 玩家资源库存提取器 (Batch A 收尾①)

CLI: python3 -I tools/resources.py <body.bin> <out.json>

破解结论 (证据见 docs/notes/batchA-misc.md §1):
- 每玩家 1 个资源库存块 (hash 0x926896f2 "Resources", 16 字段, 紧随玩家实例块之后 ~1.7KB)。
- AvailableResourceCounts = [0x80000000|n][n × u32 句柄]: n 恒 55, 每资源类型 1 个句柄,
  指向 bag 对象图节点。节点 = [tag][id][hA=数组下标][t2=3][hB=资源定义hash][载荷 FP8 raw/256]
  [尾=id]; 零库存 = 空载荷节点。hA==数组下标 是强签名 (E0 31块×2数组=3410 节点全唯一命中)。
- 资源名映射: body DB 定义区有一条 55 项 RESOURCE_* CRC 序表 (定义序 = 数组下标序;
  E0 @0x165e5 / MODERN @0x15b61, 两档逐项相同)。body 明文/LOC_RESOURCE_*_NAME 推断若拼不全
  (如 RESOURCE_GOLD_DISTANT_LANDS 只共享 LOC_RESOURCE_GOLD_NAME), 候选表经类别自检仲裁,
  仍选不出时用内置序 (FALLBACK_ORDER, 与 E0/MODERN 实测一致)。
- ResourceClassCounts = 3 句柄 (数组序 = [BONUS, CITY, EMPIRE]; E0 slot0 WOOL(BONUS)+
  HARDWOOD(EMPIRE)=[1,0,1]、slot1 WOOL+FLAX(CITY)=[1,1,0] 定证; 类别名册内置自游戏本体
  base-standard/data/resources.xml + resources-v2.xml)。
- TotalResourceCount/UniqueResourceCount/ImportedResourceCount/DistantLandsResourceCount/
  UnassignedResourceCount = 4B 句柄 → 对象图 FP8 标量节点 (E0 slot0: 总 2.0 = 1 WOOL +
  1 HARDWOOD ✓)。
- Assignments = [count][count × 20B]: [hdr 0x0016ffff][plot=y*W+x][amount][u32][u32];
  资源种类由 plot 上的地图资源决定 (E0 六国 11 条 assignment 全部与库存交叉吻合)。
  尾部两个 u32 语义未定证 (0x0001000X 疑含 slot, 0x0001ffff/ffffffff 变体)。
- 归属 slot = 最近前置玩家实例块 (0x00000003/56f) 的 ID 字段 (复用 units.py 定位)。
- CityAssignedResourceCounts 的 55 句柄节点载荷 = [u16 1][u32 递增列表句柄]; 逐城数量
  列表节点结构未解 (节点 hA/hB 与计数节点逐项配对已验证)。

自检 (输出 self_check): ①55 计数节点 hA==下标 全命中; ②sum(counts)==TotalResourceCount;
③非零种数==UniqueResourceCount; ④类别和==ResourceClassCounts; ⑤assignment plot 资源
∈ 非零库存。任何一项不过 = 输出里如实标注, 不静默。
"""
import sys, os, json, struct, re, bisect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propertybag import FXS, crc32_name
import terrain as T
import units as U

_U32 = struct.Struct('<I')
K_RES = 0x926896f2

RES_FIELD_NAMES = [
    'Properties', 'AvailableResourceCounts', 'ResourceCountModifier',
    'CityAssignedResourceCounts', 'ResourceClassCounts', 'UnassignedResourceYieldBonus',
    'Assignments', 'TotalResourceCount', 'UniqueResourceCount', 'ImportedResourceCount',
    'DistantLandsResourceCount', 'UnassignedResourceCount', 'YieldPerImprovedResource',
    'TurnLastConsidered', 'TurnLastReceived', 'NoTreasureFleetsFromResourcesCounter']

# 55 种资源的类别 (游戏本体 base-standard/data/resources.xml + resources-v2.xml;
# 上 41 种在 resources.xml, 后 14 种在 resources-v2.xml)。类别数组序 = CLASS_ORDER,
# 由 E0 slot0/slot1 交叉定证 (见文件头)。
RESOURCE_CLASSES = {
    'RESOURCE_COTTON': 'BONUS', 'RESOURCE_DATES': 'BONUS', 'RESOURCE_DYES': 'BONUS',
    'RESOURCE_FISH': 'BONUS', 'RESOURCE_GOLD': 'EMPIRE',
    'RESOURCE_GOLD_DISTANT_LANDS': 'EMPIRE', 'RESOURCE_GYPSUM': 'CITY',
    'RESOURCE_INCENSE': 'CITY', 'RESOURCE_IVORY': 'EMPIRE', 'RESOURCE_JADE': 'CITY',
    'RESOURCE_KAOLIN': 'CITY', 'RESOURCE_MARBLE': 'EMPIRE', 'RESOURCE_PEARLS': 'CITY',
    'RESOURCE_SILK': 'CITY', 'RESOURCE_SILVER': 'EMPIRE',
    'RESOURCE_SILVER_DISTANT_LANDS': 'EMPIRE', 'RESOURCE_WINE': 'EMPIRE',
    'RESOURCE_CAMELS': 'CITY', 'RESOURCE_HIDES': 'BONUS', 'RESOURCE_HORSES': 'EMPIRE',
    'RESOURCE_IRON': 'EMPIRE', 'RESOURCE_SALT': 'CITY', 'RESOURCE_WOOL': 'BONUS',
    'RESOURCE_LAPIS_LAZULI': 'CITY', 'RESOURCE_COCOA': 'EMPIRE', 'RESOURCE_FURS': 'EMPIRE',
    'RESOURCE_SPICES': 'EMPIRE', 'RESOURCE_SUGAR': 'EMPIRE', 'RESOURCE_TEA': 'EMPIRE',
    'RESOURCE_TRUFFLES': 'CITY', 'RESOURCE_NITER': 'EMPIRE', 'RESOURCE_CLOVES': 'CITY',
    'RESOURCE_WHALES': 'BONUS', 'RESOURCE_COFFEE': 'BONUS', 'RESOURCE_TOBACCO': 'BONUS',
    'RESOURCE_CITRUS': 'BONUS', 'RESOURCE_COAL': 'EMPIRE', 'RESOURCE_NICKEL': 'CITY',
    'RESOURCE_OIL': 'EMPIRE', 'RESOURCE_QUININE': 'BONUS', 'RESOURCE_RUBBER': 'EMPIRE',
    'RESOURCE_MANGOS': 'CITY', 'RESOURCE_CLAY': 'BONUS', 'RESOURCE_FLAX': 'CITY',
    'RESOURCE_RUBIES': 'BONUS', 'RESOURCE_RICE': 'EMPIRE', 'RESOURCE_LIMESTONE': 'EMPIRE',
    'RESOURCE_TIN': 'BONUS', 'RESOURCE_LLAMAS': 'BONUS', 'RESOURCE_HARDWOOD': 'EMPIRE',
    'RESOURCE_WILD_GAME': 'BONUS', 'RESOURCE_CRABS': 'BONUS', 'RESOURCE_COWRIE': 'BONUS',
    'RESOURCE_TURTLES': 'BONUS', 'RESOURCE_PITCH': 'BONUS',
}
CLASS_ORDER = ['BONUS', 'CITY', 'EMPIRE']

# DB 定义序 fallback (body 内候选序表全部验证失败时使用; E0/MODERN 实测一致)
FALLBACK_ORDER = [
    'RESOURCE_COTTON', 'RESOURCE_DATES', 'RESOURCE_DYES', 'RESOURCE_FISH', 'RESOURCE_GOLD',
    'RESOURCE_GOLD_DISTANT_LANDS', 'RESOURCE_GYPSUM', 'RESOURCE_INCENSE', 'RESOURCE_IVORY',
    'RESOURCE_JADE', 'RESOURCE_KAOLIN', 'RESOURCE_MARBLE', 'RESOURCE_PEARLS', 'RESOURCE_SILK',
    'RESOURCE_SILVER', 'RESOURCE_SILVER_DISTANT_LANDS', 'RESOURCE_WINE', 'RESOURCE_CAMELS',
    'RESOURCE_HIDES', 'RESOURCE_HORSES', 'RESOURCE_IRON', 'RESOURCE_SALT', 'RESOURCE_WOOL',
    'RESOURCE_LAPIS_LAZULI', 'RESOURCE_COCOA', 'RESOURCE_FURS', 'RESOURCE_SPICES',
    'RESOURCE_SUGAR', 'RESOURCE_TEA', 'RESOURCE_TRUFFLES', 'RESOURCE_NITER',
    'RESOURCE_CLOVES', 'RESOURCE_WHALES', 'RESOURCE_COFFEE', 'RESOURCE_TOBACCO',
    'RESOURCE_CITRUS', 'RESOURCE_COAL', 'RESOURCE_NICKEL', 'RESOURCE_OIL', 'RESOURCE_QUININE',
    'RESOURCE_RUBBER', 'RESOURCE_MANGOS', 'RESOURCE_CLAY', 'RESOURCE_FLAX', 'RESOURCE_RUBIES',
    'RESOURCE_RICE', 'RESOURCE_LIMESTONE', 'RESOURCE_TIN', 'RESOURCE_LLAMAS',
    'RESOURCE_HARDWOOD', 'RESOURCE_WILD_GAME', 'RESOURCE_CRABS', 'RESOURCE_COWRIE',
    'RESOURCE_TURTLES', 'RESOURCE_PITCH']


# ---------- 对象图节点 (记录形状见 phase2-cities.md §1) ----------
def node_candidates(d, rid, want_hA=None, max_scan=400):
    """body 全文找 [tag][rid][hA][t2][hB?][载荷][尾=rid] 记录。
    want_hA: 要求节点 hA == 该值 (计数数组的强签名)。返回 [(off, tag, hA, t2, hB, payload)]。
    只接受载荷 ≤8B 的记录 (标量/零值/短引用) —— 长载荷命中一律视为它类记录的巧合。"""
    out = []
    tb = struct.pack('<I', rid)
    n = len(d)
    i = 0
    while True:
        j = d.find(tb, i)
        if j < 0:
            break
        i = j + 1
        h = j - 1
        if h < 0:
            continue
        tag = d[h]
        if not (tag <= 0x0F or 0x80 <= tag <= 0x8F):
            continue
        t2 = d[h + 9]
        if t2 not in (0, 1, 2, 3):
            continue
        hA = _U32.unpack_from(d, j + 4)[0]
        if want_hA is not None and hA != want_hA:
            continue
        hend = h + 10 + (4 if t2 == 3 else 0)
        hB = _U32.unpack_from(d, j + 9)[0] if t2 == 3 else 0
        P = None
        for L in range(0, max_scan):
            if hend + L + 4 > n:
                break
            if _U32.unpack_from(d, hend + L)[0] == rid:
                P = L
                break
        if P is None or P > 8:
            continue
        out.append((h, tag, hA, t2, hB, d[hend:hend + P]))
        if len(out) >= 8:
            break
    return out


def resolve_scalar(d, rid, want_hA=None, notes=None, what=''):
    """标量节点解析: 唯一候选 → (FP8 float 值/None, off)。多候选 → 取最可信者并记 notes。"""
    c = node_candidates(d, rid, want_hA)
    if not c:
        if notes is not None:
            notes.append(f'{what}: 节点 {rid} (hA={want_hA}) 无候选记录')
        return None, None
    if len(c) > 1:
        if notes is not None:
            notes.append(f'{what}: 节点 {rid} {len(c)} 个候选, 取 tag={c[0][1]:#x} @ {c[0][0]:#x}')
        c = sorted(c, key=lambda r: (0 if (r[1] in (0x80, 0x81) and len(r[5]) == 0) else
                                     (1 if r[3] == 3 else 2), r[0]))
    off, tag, hA, t2, hB, payload = c[0]
    if len(payload) == 4:
        return struct.unpack_from('<I', payload, 0)[0] / 256.0, off
    if len(payload) == 0:
        return 0.0, off
    return None, off


# ---------- 资源库存块 ----------
def find_res_blocks(d):
    """扫描 [K_RES][1][-1][1][1][count] 锚。返回 [(off, count)]。"""
    pat = struct.pack('<I', K_RES) + struct.pack('<i', 1) + struct.pack('<I', 0xffffffff) \
        + struct.pack('<i', 1) + struct.pack('<i', 1)
    out = []
    i = 0
    while True:
        j = d.find(pat, i)
        if j < 0:
            break
        out.append((j, _U32.unpack_from(d, j + 20)[0]))
        i = j + 1
    return out


def parse_res_block(d, off, count):
    """按 schema 读 16 字段值。返回 (fields{name: (kind, 值)}, end_pos 或 None)。"""
    pos = off + 24
    entries = []
    for _ in range(count):
        h, t = struct.unpack_from('<II', d, pos)
        entries.append((h, t))
        pos += 8
    fields = {}
    for (h, t), nm in zip(entries, RES_FIELD_NAMES):
        base = t & 0xFF
        mod = t & 0xFFFF
        try:
            if mod == 0x402:            # Properties 空串
                ln = _U32.unpack_from(d, pos)[0]
                pos += 4 + ln + (-(4 + ln)) % 4 + 8
                fields[nm] = ('str', '')
            elif mod in (0x400, 0x403):  # 尺寸块
                sz = _U32.unpack_from(d, pos)[0]
                pos += 4
                fields[nm] = ('blob', d[pos:pos + sz])
                pos += sz
            elif base == 8:              # Int
                fields[nm] = ('int', struct.unpack_from('<i', d, pos)[0])
                pos += 4
            else:
                return fields, None
        except struct.error:
            return fields, None
    if d[pos:pos + 8] != FXS:
        return fields, None
    return fields, pos + 8


def handle_array(blob):
    """[0x80000000|n][n × u32] → n, [u32]"""
    if blob is None or len(blob) < 4:
        return None, []
    v = _U32.unpack_from(blob, 0)[0]
    n = v & 0x7FFFFFFF
    if 4 + 4 * n > len(blob):
        return None, []
    return n, list(struct.unpack_from(f'<{n}I', blob, 4))


# ---------- 资源名序表 ----------
def _resource_rev_dict(d):
    """RESOURCE_* 名字 → CRC 反查表: body 明文 + LOC_RESOURCE_*_NAME 剥前缀推断
    (units.py 同款技巧; E0 body 有 53 个 loc key, 覆盖仅以 _NAME 形式落盘的资源名)。"""
    names = {m.decode() for m in re.findall(rb'RESOURCE_[A-Z0-9_]{2,60}', d)}
    for m in re.findall(rb'LOC_RESOURCE_([A-Z0-9_]+)_NAME', d):
        names.add('RESOURCE_' + m.decode())
    rev = {}
    for nm in names:
        rev.setdefault(crc32_name(nm), nm)
    return rev


def _db_crc_runs(d, rev, bag, gap=8):
    """DB 区 (bag 之前) 的 RESOURCE_* CRC 连续段; gap≤8B (≤2 个未知名格子) 时合并。
    返回 [(lo, cell_count)] 按偏移序。"""
    starts = set()
    for h in rev:
        if h in (0, 0xFFFFFFFF):
            continue
        b = struct.pack('<I', h)
        i = d.find(b, 0, bag)
        while i >= 0:
            starts.add(i)
            i = d.find(b, i + 1, bag)
    used = set()
    runs = []
    for s in sorted(starts):
        if s in used:
            continue
        lo = s
        while lo - 4 >= 0 and (lo - 4) in starts:
            lo -= 4
        hi = s + 4
        while hi + 4 <= bag and hi in starts:
            hi += 4
        for k in range(lo, hi, 4):
            used.add(k)
        runs.append([lo, hi])
    merged = []
    for lo, hi in runs:
        if merged and lo - merged[-1][1] <= gap:
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    return [(lo, (hi - lo) // 4) for lo, hi in merged]


def _table_check(names, blocks_data, terr):
    """候选序表验证。返回 (informative_checks, failures):
    - 类别和==ResourceClassCounts (仅 3 类档(远古)=直接标量且类别映射已定证的玩家)
    - assignment plot 地图资源 ∈ 非零库存 (逐条计 1 次)
    blocks_data: [{'counts': {idx: val}, 'class': [..] 或 None, 'n_cls': int,
                   'assignments': [...] 或 None}]"""
    ok = fail = 0
    for bd in blocks_data:
        cls = bd.get('class')
        if cls and bd.get('n_cls') == len(CLASS_ORDER) and bd.get('class_direct') \
                and all(v is not None for v in cls):
            sums = {c: 0.0 for c in CLASS_ORDER}
            for idx, v in bd['counts'].items():
                if v and idx < len(names) and names[idx] in RESOURCE_CLASSES:
                    sums[RESOURCE_CLASSES[names[idx]]] += v
            if all(abs(sums[c] - cls[ci]) < 0.001 for ci, c in enumerate(CLASS_ORDER)):
                ok += 1
            else:
                fail += 1
        asg = bd.get('assignments')
        if asg and terr:
            for e in asg:
                plot = e['plot']
                if plot is None:
                    continue
                rn = terr['res_at'].get(plot)
                v = bd['counts'].get(next((i for i, nm in enumerate(names) if nm == rn), None)) \
                    if rn else None
                if rn is None:
                    continue
                if v is not None and v >= e['amount'] - 0.001:
                    ok += 1
                else:
                    fail += 1
    return ok, fail


def pick_res_table(d, rev, n_res, blocks_data, terr):
    """选资源名序表: DB CRC 段 (严格/合并) 中长度==n_res 的候选, 经 类别和+assignment
    交叉 仲裁 (须 ≥1 次有效检查且 0 失败); 平手取非字典序者 (定义序表前 17 项与字典序
    重合, 后 38 项 CAMELS… 打破); 全败 → None (调用方用内置序)。"""
    bag = d.find(FXS)
    bag = bag if bag > 0 else len(d)
    cands = []
    seen = set()
    for lo, cnt in _db_crc_runs(d, rev, bag):
        if cnt != n_res or lo in seen:
            continue
        seen.add(lo)
        names = []
        ok = True
        for k in range(cnt):
            h = _U32.unpack_from(d, lo + 4 * k)[0]
            nm = rev.get(h)
            if nm is None:  # 推断 _DISTANT_LANDS 变体 (GOLD→GOLD_DISTANT_LANDS 类)
                nm = next((b + '_DISTANT_LANDS' for b, hb in
                           ((n, crc32_name(n + '_DISTANT_LANDS')) for n in rev.values())
                           if hb == h), None)
            if nm is None:
                ok = False
                break
            names.append(nm)
        if ok:
            cands.append((lo, names))
    best = None
    for lo, names in cands:
        ok, fail = _table_check(names, blocks_data, terr)
        if fail == 0 and ok >= 1:
            nonlex = any(names[i] > names[i + 1] for i in range(len(names) - 1))
            if best is None or (nonlex and not best[2]):
                best = (lo, names, nonlex)
    if best:
        return {'offset': best[0], 'count': n_res, 'names': best[1], 'source': 'db_crc_run'}
    return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    d = open(src, 'rb').read()
    notes = []

    # --- 玩家实例 (归属锚点, 复用 units.py) ---
    ux = U.UnitExtractor(d)
    players = []
    for pp in ux.find_heads(U.SIG_PLAYER):
        base, vend = ux._head_at(pp, U.SIG_PLAYER)
        props_c, props_e = ux._skip_props(vend)
        if props_e is None:
            players.append({'offset': pp, 'slot': None, 'alive': None})
            continue
        try:
            _, slot, p = ux._read_value(props_e, 8)
            _, alive, p = ux._read_value(p, 1)
        except U.ParseError:
            slot = alive = None
        players.append({'offset': pp, 'slot': slot, 'alive': alive})
    poffs = [pl['offset'] for pl in players]

    def owner_slot(off):
        k = bisect.bisect_right(poffs, off) - 1
        return (players[k]['slot'], players[k]) if k >= 0 else (None, None)

    # --- 资源库存块: 无名解析 (counts 按下标) ---
    blocks = find_res_blocks(d)
    if not blocks:
        print('错误: 未找到资源库存块 (0x926896f2)', file=sys.stderr)
        sys.exit(2)
    parsed = []
    for off, cnt in blocks:
        f, end = parse_res_block(d, off, cnt)
        slot, pl = owner_slot(off)
        bd = {'off': off, 'count': cnt, 'terminated': end is not None, 'slot': slot,
              'alive': (pl or {}).get('alive'), 'fields': f, 'error': None}
        if end is None or 'AvailableResourceCounts' not in f:
            bd['error'] = '块解析失败 (schema/终止符不对位)'
            parsed.append(bd)
            continue

        def harr(nm):
            return handle_array(f[nm][1]) if nm in f else (None, [])

        n_av, hs_av = harr('AvailableResourceCounts')
        n_mod, hs_mod = harr('ResourceCountModifier')
        n_cls, hs_cls = harr('ResourceClassCounts')
        n_cas, hs_cas = harr('CityAssignedResourceCounts')
        bd.update({'n_av': n_av, 'hs_av': hs_av, 'n_mod': n_mod, 'hs_mod': hs_mod,
                   'n_cls': n_cls, 'hs_cls': hs_cls, 'n_cas': n_cas, 'hs_cas': hs_cas})

        counts = {}
        ok_ha = True
        if n_av:
            for idx, rid in enumerate(hs_av):
                val, noff = resolve_scalar(d, rid, want_hA=idx, notes=notes,
                                           what=f'slot{slot} count[{idx}]')
                if val is None:
                    ok_ha = False
                counts[idx] = val
        bd['counts'] = counts
        bd['ok_ha'] = ok_ha and (n_av == (parsed[0]['n_av'] if parsed else n_av))

        def h4(nm):
            v = f.get(nm)
            return _U32.unpack_from(v[1], 0)[0] if v and v[0] == 'blob' and len(v[1]) == 4 else None
        bd['tot'] = resolve_scalar(d, h4('TotalResourceCount'), notes=notes,
                                   what=f'slot{slot} total')[0] if h4('TotalResourceCount') else None
        bd['unq'] = resolve_scalar(d, h4('UniqueResourceCount'), notes=notes,
                                   what=f'slot{slot} unique')[0] if h4('UniqueResourceCount') else None
        bd['imp'] = resolve_scalar(d, h4('ImportedResourceCount'), notes=notes,
                                   what=f'slot{slot} imported')[0] if h4('ImportedResourceCount') else None
        bd['dis'] = resolve_scalar(d, h4('DistantLandsResourceCount'), notes=notes,
                                   what=f'slot{slot} distant')[0] if h4('DistantLandsResourceCount') else None
        bd['una'] = resolve_scalar(d, h4('UnassignedResourceCount'), notes=notes,
                                   what=f'slot{slot} unassigned')[0] if h4('UnassignedResourceCount') else None
        bd['class'] = None
        bd['class_direct'] = False
        if n_cls and n_cls >= len(CLASS_ORDER):
            vals = []
            direct = True
            for ci, rid in enumerate(hs_cls):
                val, noff = resolve_scalar(d, rid, notes=None, what=f'slot{slot} class[{ci}]')
                if val is None:
                    # MODERN 实测: 类别节点可为 [u16 1][u32 引用] 指针链 (非标量); 跟一层,
                    # 值只有通过类别和验证才采用 (链中间值不可信)
                    direct = False
                    c0 = node_candidates(d, rid)
                    if c0 and len(c0[0][5]) == 6 and c0[0][5][:2] == b'\x01\x00':
                        ref = struct.unpack_from('<I', c0[0][5], 2)[0]
                        val, noff = resolve_scalar(d, ref, notes=None,
                                                   what=f'slot{slot} class[{ci}]->{ref}')
                vals.append(val)
            bd['class'] = vals
            bd['class_direct'] = direct and all(v is not None for v in vals)

        # Assignments: [count][count × 20B]
        assignments = []
        av = f['Assignments'][1]
        if av and len(av) >= 4:
            na = _U32.unpack_from(av, 0)[0]
            body_a = av[4:]
            if len(body_a) == 20 * na:
                for ai in range(na):
                    e = body_a[20 * ai:20 * ai + 20]
                    hdr, plot, amount = struct.unpack_from('<3I', e, 0)
                    t3, t4 = struct.unpack_from('<2I', e, 12)
                    assignments.append({'plot': plot if plot != 0xFFFFFFFF else None,
                                        'amount': amount,
                                        'hdr_kind': (hdr >> 16) & 0xFFFF,
                                        'hdr_lo': hdr & 0xFFFF, 'tail': [t3, t4]})
            else:
                notes.append(f'slot{slot}: Assignments 长度 {len(body_a)} != {na}×20, 结构未解')
                assignments = None
        bd['assignments'] = assignments
        parsed.append(bd)

    n_res = next((bd['n_av'] for bd in parsed if bd.get('n_av')), None)
    if not n_res:
        print('错误: AvailableResourceCounts 无法解析', file=sys.stderr)
        sys.exit(2)

    # --- 地图资源 (assignment 交叉检查 + 序表仲裁用) ---
    terr = None
    try:
        td = T.build_dict(d)
        terr_hashes = {h for h, nm in td.items() if nm.startswith('TERRAIN_')}
        found = T.find_map(d, terr_hashes)
        if found:
            p, q, w, h, cnt = found
            plots, _ = T.parse_plots(d, q, cnt, terr_hashes, td)
            terr = {'w': w, 'res_at': {pl['i']: pl['resource'] for pl in plots if pl['resource']}}
    except Exception as e:
        notes.append(f'地图解析失败 (assignment 交叉检查跳过): {e}')

    # --- 资源名序表 (候选 + 类别和/assignment 交叉仲裁) ---
    rev = _resource_rev_dict(d)
    table = pick_res_table(d, rev, n_res, parsed, terr)
    table_src = 'db_crc_run'
    if table is None:
        if n_res <= len(FALLBACK_ORDER):
            order = FALLBACK_ORDER[:n_res]
            table_src = 'builtin_fallback'
            notes.append(f'资源序表: body 内候选 CRC 段全部未通过交叉自检/长度不符, '
                         f'使用内置序 (与 E0/MODERN 实测一致, 换游戏版本需复核)')
        else:
            print('错误: 资源序表缺失且 n_res 超出 fallback', file=sys.stderr)
            sys.exit(2)
    else:
        order = table['names']
    missing_cls = [nm for nm in order if nm not in RESOURCE_CLASSES]

    # --- 第三阶段: 命名 + 交叉 + 输出 ---
    out_players = []
    check_agg = {'hA_signature': 0, 'hA_signature_bad': 0, 'total_sum_ok': 0,
                 'total_sum_bad': 0, 'unique_ok': 0, 'unique_bad': 0,
                 'class_sum_ok': 0, 'class_sum_bad': 0, 'assign_cross_ok': 0,
                 'assign_cross_bad': 0, 'assign_cross_skip': 0}
    for bd in parsed:
        f = bd['fields']
        slot = bd['slot']
        rec = {'block_offset': bd['off'], 'block_terminated': bd['terminated'],
               'slot': slot, 'alive': bd['alive']}
        if bd['error']:
            rec['error'] = bd['error']
            out_players.append(rec)
            check_agg['total_sum_bad'] += 1
            continue
        counts = {}
        counts_raw = {}
        node_meta = []
        for idx, val in bd['counts'].items():
            nm = order[idx] if idx < len(order) else f'idx{idx}'
            counts[nm] = val
            if val is not None:
                counts_raw[nm] = int(round(val * 256))
        if bd.get('ok_ha'):
            check_agg['hA_signature'] += n_res
        else:
            check_agg['hA_signature_bad'] += 1

        class_counts = None
        cls_ok = None
        if bd['class'] is not None:
            if bd.get('n_cls') == len(CLASS_ORDER):
                # 3 类档 (远古): 类别序已定证, 交叉结果如实计
                class_counts = {c: v for c, v in zip(CLASS_ORDER, bd['class'])}
                if all(v is not None for v in bd['class']) and bd.get('ok_ha') and not missing_cls:
                    sums = {c: 0.0 for c in CLASS_ORDER}
                    for nm, v in counts.items():
                        if v and nm in RESOURCE_CLASSES:
                            sums[RESOURCE_CLASSES[nm]] += v
                    cls_ok = all(abs(sums[c] - class_counts[c]) < 0.001 for c in CLASS_ORDER)
                    check_agg['class_sum_ok' if cls_ok else 'class_sum_bad'] += 1
            else:
                # 4 类档 (探索/现代, MODERN 实测 4 直接 FP8 标量): 4 值之和 == 总库存
                # 但与 XML 类别映射不符 (逐资源类别疑随时代变化), 语义未定证 → 原值输出
                vals = bd['class']
                class_counts = {f'class{ci}': v for ci, v in enumerate(vals)}
                if all(v is not None for v in vals) and bd.get('tot') is not None \
                        and bd.get('ok_ha'):
                    s4 = sum(vals)
                    if abs(s4 - bd['tot']) >= 0.001:
                        check_agg['class_sum_bad'] += 1
                        notes.append(f'slot{slot}: 4 类值和 {s4} != 总库存 {bd["tot"]}')
                    else:
                        check_agg['class_sum_ok'] += 1

        assignments = bd['assignments']
        if assignments is not None and terr:
            for entry in assignments:
                plot = entry['plot']
                if plot is None:
                    check_agg['assign_cross_skip'] += 1
                    continue
                entry['x'] = plot % terr['w']
                entry['y'] = plot // terr['w']
                rn = terr['res_at'].get(plot)
                entry['map_resource'] = rn
                if rn is not None and counts.get(rn) is not None:
                    if counts[rn] >= entry['amount'] - 0.001:
                        check_agg['assign_cross_ok'] += 1
                    else:
                        check_agg['assign_cross_bad'] += 1
                else:
                    check_agg['assign_cross_skip'] += 1

        rec.update({
            'resource_order_count': bd['n_av'],
            'counts': {k: v for k, v in counts.items() if v} or None,
            'counts_all_raw': counts_raw or None,
            'total_resource_count': bd['tot'],
            'unique_resource_count': bd['unq'],
            'imported_resource_count': bd['imp'],
            'distant_lands_resource_count': bd['dis'],
            'unassigned_resource_count': bd['una'],
            'class_counts': class_counts,
            'class_sum_match': cls_ok,
            'modifier_handles': [f'{x:x}' for x in bd['hs_mod']] if bd['n_mod'] == n_res else None,
            'city_assigned_handles': [f'{x:x}' for x in bd['hs_cas']] if bd['n_cas'] else None,
            'assignments': assignments,
            'turn_last_considered': f['TurnLastConsidered'][1] if 'TurnLastConsidered' in f else None,
            'turn_last_received': f['TurnLastReceived'][1] if 'TurnLastReceived' in f else None,
            'no_treasure_fleets_counter': (f['NoTreasureFleetsFromResourcesCounter'][1]
                                           if 'NoTreasureFleetsFromResourcesCounter' in f else None),
            'unassigned_yield_bonus_raw': (f['UnassignedResourceYieldBonus'][1].hex()
                                           if 'UnassignedResourceYieldBonus' in f else None),
            'yield_per_improved_resource_raw': (f['YieldPerImprovedResource'][1].hex()
                                                if 'YieldPerImprovedResource' in f else None),
        })
        # 合计自检: sum(counts) == TotalResourceCount
        if bd.get('ok_ha') and bd['tot'] is not None and all(v is not None for v in counts.values()):
            s = sum(v for v in counts.values() if v)
            if abs(s - bd['tot']) < 0.001:
                check_agg['total_sum_ok'] += 1
            else:
                check_agg['total_sum_bad'] += 1
                notes.append(f'slot{slot}: sum(counts)={s} != TotalResourceCount={bd["tot"]}')
        if bd.get('ok_ha') and bd['unq'] is not None and all(v is not None for v in counts.values()):
            nz = sum(1 for v in counts.values() if v)
            if nz == int(round(bd['unq'])):
                check_agg['unique_ok'] += 1
            else:
                check_agg['unique_bad'] += 1
                notes.append(f'slot{slot}: 非零种数={nz} != UniqueResourceCount={bd["unq"]}')
        out_players.append(rec)

    out = {
        'source': src,
        'resource_table': {'offset': table['offset'] if table else None,
                           'count': n_res, 'names': order, 'source': table_src},
        'resource_classes': {nm: RESOURCE_CLASSES[nm] for nm in order if nm in RESOURCE_CLASSES},
        'class_order': CLASS_ORDER,
        'players_found': len(players),
        'resource_blocks': len(blocks),
        'players': out_players,
        'self_check': check_agg,
        'notes': notes,
        'unresolved': [
            'Assignments 尾部两个 u32 (0x0001000X/0x0001ffff/ffffffff) 语义未定证',
            'CityAssignedResourceCounts 句柄节点载荷 = [u16 1][u32 递增列表句柄], 逐城分配值'
            '所在列表节点结构未解',
            'ResourceClassCounts: 远古档 3 类 = [BONUS,CITY,EMPIRE] 直接 FP8 (类别和与库存'
            '逐玩家吻合, E0 31/31); MODERN 档 4 类直接 FP8 且 4 值之和==总库存, 但与 XML '
            '类别映射的逐类和不符 (逐资源类别疑随时代/DLC 变化) → 4 类语义未定证',
            'UnassignedResourceYieldBonus / YieldPerImprovedResource 的 7 项原值语义未定证'
            '(疑 7 产量 bonus, 常全 0)',
            'ResourceCountModifier 55 句柄已按下标解析 (hA 签名全命中) 但含义未对账 (疑全 0)',
        ],
    }
    with open(dst, 'w') as fp:
        json.dump(out, fp, ensure_ascii=False)
    nz = sum(1 for p in out_players if p.get('counts'))
    tot_c = sum(sum((p.get('counts') or {}).values()) for p in out_players)
    print(f"资源块 {len(blocks)}/{out['players_found']} 玩家 | 有库存玩家 {nz} | "
          f"库存总量 {tot_c:g} | 序表 {table_src} {n_res}项 | "
          f"自检 hA={check_agg['hA_signature']}(+{check_agg['hA_signature_bad']}坏) "
          f"total={check_agg['total_sum_ok']}/{check_agg['total_sum_ok']+check_agg['total_sum_bad']} "
          f"unique={check_agg['unique_ok']}/{check_agg['unique_ok']+check_agg['unique_bad']} "
          f"class={check_agg['class_sum_ok']}/{check_agg['class_sum_ok']+check_agg['class_sum_bad']} "
          f"assign={check_agg['assign_cross_ok']}/{check_agg['assign_cross_ok']+check_agg['assign_cross_bad']}"
          f"(skip {check_agg['assign_cross_skip']}) -> {dst}")
    for s in notes[:8]:
        print('  注:', s)


if __name__ == '__main__':
    main()
