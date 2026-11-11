#!/usr/bin/env python3
"""文明7 科技/市政进度提取器 (Batch A) — 科技/市政树进度 + 玩家组件注册表。

CLI: python3 -I tools/techlist.py <body.bin> <out.json>

为什么独立成 techlist.py 而不是扩展 progress.py:
  progress.py 已稳定承载 块层(8f 科技块/33f 文化块/15f 遗产块/金库/军事统计) 的字段映射,
  本轮新增的是另一套数据源 —— bag 内 [0x0ab848ce] 组件注册表(kind-2=SYSTEM_TECH 科技节点
  对象 / kind-3=SYSTEM_CULTURE 市政节点对象 / kind-5=BUILDING 可解锁建筑对象)与 DB 头部的
  NODE_TECH/NODE_CIVIC CRC 序表, 结构与块层完全不同, 故独立成工具并 import 复用 progress.py
  的块解析器(同一 CLI 约定 python3 -I tools/techlist.py <body.bin> <out.json>)。

本轮破解 (证据见 docs/notes/batchA-tech.md):
  1. DB 定义区(body 头部)有按定义序排列的 NODE_TECH_*/NODE_CIVIC_*/TREE_* CRC 表
     (E0: 16 科技节点表 @0x13de5 与 age-antiquity progression-trees-tech.xml Types 序一致)。
  2. bag 内每玩家组件注册表: 记录 [0x0ab848ce][kind u32][0a 00 0b 00][...]:
     kind=2: crc=NODE_TECH_*, 类CRC=SYSTEM_TECH(0x244dc1f7); kind=3: crc=NODE_CIVIC_*,
     类CRC=SYSTEM_CULTURE(0xb77b07ec); kind=5: crc=BUILDING_*; kind=10: 其它。
     记录尾含 [06 00 00 00][f2 u32][f3 u32][u16 idx][u16 idx+1][01][-1][objid]。
     f2=5 (A组, 每科技1条=已揭示节点集) / f2=2 (B组, 同一科技多条=解锁行实例) /
     f2=1/10 等变体(未定证)。
  3. 科技块 TargetTech 实测恒 -1 (7 档 31 玩家); ScienceOverflow 在下一回合被消耗
     (E0/E6/E7/E2 t21=0.75 → E5.1/E5.2 t22=0.0), 印证"研究方向选择"不落盘到科技块。
  4. E0↔E6(唯一操作=选科技 Writing) 的全量差分: 对象图仅 1 字节易变计数器差异(E6↔E7),
     bag 仅情报类 11f 块 NumUrban 1→3(E6 独有), 头部仅文件名/时间戳 —— "正在研究方向"
     与"已完成科技全清单"在已解结构中无落盘(未解 U-A1/A2, 见笔记)。

输出 JSON: {players:[{slot, tech, culture, legacy, gold, milstats_summary,
                       components:{tech_nodes, civic_nodes, buildings, other}}], unresolved[]}
"""
import sys, os, json, struct, re, glob, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propertybag import FXS, crc32_name, load_dictionary
import progress as P

_U = struct.Struct('<I')
K_COMP = 0x0ab848ce
SYSTEM_TECH = crc32_name('SYSTEM_TECH')
SYSTEM_CULTURE = crc32_name('SYSTEM_CULTURE')


def load_node_names(extra_bytes=None):
    """NODE_/TREE_/SYSTEM_/BUILDING_ 名字反查字典: 游戏本体 XML + 存档明文。"""
    names = set()
    roots = ('/Applications/CivilizationVII.app/Contents/Resources/Base',
             '/Applications/CivilizationVII.app/Contents/Resources/DLC')
    pat = re.compile(r'\b((?:NODE|TREE|SYSTEM|BUILDING|UNIT|PROJECT|DISTRICT|TRADITION|GOVERNMENT)_[A-Z0-9_]{2,60})\b')
    for root in roots:
        for path in glob.glob(root + '/**/*.xml', recursive=True):
            try:
                text = open(path, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            for m in pat.finditer(text):
                names.add(m.group(0))
    if extra_bytes is not None:
        for m in re.finditer(rb'(?:BUILDING|UNIT|PROJECT)_[A-Z0-9_]{2,60}', extra_bytes):
            names.add(m.group(0).decode('ascii', 'replace'))
    rev = {}
    for n in names:
        rev.setdefault(crc32_name(n), n)
    return rev


def find_db_crc_tables(d, rev, bag, min_len=8):
    """在 body 头部(DB 定义区)找连续 CRC 序表: 窗口内 u32 全部命中已知名。
    返回 [{offset, names:[...]}] — 名称按定义序(XML Types 序)。"""
    out = []
    n = len(d)
    # 在 [0, bag) 扫描: 对每个命中位置尝试向两边扩展
    starts = []
    for h in rev:
        if h in (0, 0xffffffff):
            continue
        pat = struct.pack('<I', h)
        i = d.find(pat, 0, bag)
        while i >= 0:
            starts.append(i)
            i = d.find(pat, i + 1, bag)
    starts = sorted(set(starts))
    used = [False] * len(starts)
    for si, s in enumerate(starts):
        if used[si]:
            continue
        # 向左右扩展连续命中 (4 字节步进)
        lo = s
        while lo - 4 >= 0:
            h = _U.unpack_from(d, lo - 4)[0]
            if h in rev and (lo - 4) in starts:
                lo -= 4
            else:
                break
        hi = s + 4
        while hi + 4 <= bag:
            h = _U.unpack_from(d, hi)[0]
            if h in rev and hi in starts:
                hi += 4
            else:
                break
        cnt = (hi - lo) // 4
        if cnt < min_len:
            continue
        for k in range(lo, hi, 4):
            try:
                used[starts.index(k)] = True
            except ValueError:
                pass
        names = [rev[_U.unpack_from(d, lo + 4 * k)[0]] for k in range(cnt)]
        out.append({'offset': lo, 'count': cnt, 'names': names})
    out.sort(key=lambda x: x['offset'])
    # 只保留 tech/civic/tree 相关表
    keep = []
    for t in out:
        if any(nm.startswith(('NODE_TECH', 'NODE_CIVIC', 'TREE_TECHS', 'TREE_CIVICS'))
               for nm in t['names']):
            keep.append(t)
    return keep


def parse_component_records(d, lo, hi, rev):
    """解析 [K=0x0ab848ce][kind][body] 组件注册表记录 (到下一个 K 或区域尾)。
    kind=2/3 记录体: [0a 00 0b 00][02 00 00 00][crc][01 00 00 00][class_crc][idx u32]
                     [06 00 00 00][f2 u32][f3 u32][u16 idx][u16 idx+1][8B][...尾]。"""
    pat = struct.pack('<I', K_COMP)
    offs = []
    i = d.find(pat, lo)
    while 0 <= i < hi:
        offs.append(i)
        i = d.find(pat, i + 1, hi)
    recs = []
    for k, o in enumerate(offs):
        end = offs[k + 1] if k + 1 < len(offs) else min(hi, o + 500)
        kind = _U.unpack_from(d, o + 4)[0]
        body = d[o + 8:end]
        rec = {'offset': o, 'kind': kind, 'len': len(body)}
        if kind in (2, 3) and len(body) >= 36:
            crc = _U.unpack_from(body, 8)[0]
            cls = _U.unpack_from(body, 16)[0]
            idx = _U.unpack_from(body, 20)[0]
            f2 = _U.unpack_from(body, 28)[0]
            f3 = _U.unpack_from(body, 32)[0]
            rec.update({'crc': '%08x' % crc, 'name': rev.get(crc), 'class_crc': '%08x' % cls,
                        'idx': idx, 'f2': f2, 'f3': f3,
                        'group': {5: 'A', 2: 'B', 10: 'C', 1: 'D', 3: 'E'}.get(f2, 'f2=%d' % f2)})
        elif kind == 5 and len(body) >= 12:
            crc = _U.unpack_from(body, 4)[0]
            rec.update({'crc': '%08x' % crc, 'name': rev.get(crc)})
        rec['body_hex'] = body.hex()
        recs.append(rec)
    return recs


def fmt_culture(f, node_rev):
    """文化块格式化 (与 progress.py 一致, 保留供独立使用)。"""
    def val(k):
        v = f.get(k)
        return v[1] if v else None
    trs = val('UnlockedTraditions')
    trl = P.decode_u32_list(trs) if isinstance(trs, bytes) else None
    trees = P.decode_u32_list(val('Trees')) if isinstance(val('Trees'), bytes) else None
    return {
        'trees': trees,
        'tree_names': [node_rev.get(t & 0xffffffff) for t in (trees or [])],
        'unlocked_traditions': trl,
        'unlocked_tradition_names': [node_rev.get(t & 0xffffffff) for t in (trl or [])],
        'main_tree': val('MainTree'), 'main_tree_name': node_rev.get((val('MainTree') or 0) & 0xffffffff),
        'active_tree': val('ActiveTree'), 'active_tree_name': node_rev.get((val('ActiveTree') or 0) & 0xffffffff),
        'last_completed_node': val('LastCompletedNode'),
        'last_completed_node_name': node_rev.get((val('LastCompletedNode') or 0) & 0xffffffff),
        'active_government': val('ActiveGovernment'),
        'active_government_name': node_rev.get((val('ActiveGovernment') or 0) & 0xffffffff),
        'target_culture_node': val('TargetCultureNode'),
        'target_culture_node_name': node_rev.get((val('TargetCultureNode') or 0) & 0xffffffff),
        'culture_overflow': val('CultureOverflow'), 'culture_debt': val('CultureDebt'),
    }


def load_tech_prereqs():
    """从游戏本体 XML 提取 ProgressionTreePrereqs: {tech: [prereqs]} (全部时代合并)。"""
    prereqs = {}
    roots = ('/Applications/CivilizationVII.app/Contents/Resources/Base',
             '/Applications/CivilizationVII.app/Contents/Resources/DLC')
    row = re.compile(r'<Row\s+Node="([A-Z0-9_]+)"\s+PrereqNode="([A-Z0-9_]+)"')
    for root in roots:
        for path in glob.glob(root + '/**/progression-trees-tech*.xml', recursive=True):
            try:
                text = open(path, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            for m in row.finditer(text):
                prereqs.setdefault(m.group(1), set()).add(m.group(2))
    return prereqs


def prereq_closure(node, prereqs):
    """LastCompletedNode 的前置闭包(含自身) — 已完成集的下界(分支完成项不在闭包内)。"""
    out = []
    seen = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
        stack.extend(prereqs.get(n, ()))
    return sorted(out)


def fmt_tech(f, node_rev, prereqs):
    def val(k):
        v = f.get(k)
        return v[1] if v else None
    lc = val('LastCompletedNode')
    lc_name = node_rev.get((lc or 0) & 0xffffffff) if lc not in (None, -1, 0xffffffff) else None
    closure = prereq_closure(lc_name, prereqs) if lc_name else []
    tt = val('TargetTech')
    return {
        'tree': val('Tree'), 'tree_name': node_rev.get((val('Tree') or 0) & 0xffffffff),
        'last_completed_node': lc, 'last_completed_node_name': lc_name,
        'completed_lower_bound': closure,
        'completed_lower_bound_note': '前置闭包=已完成集下界; 分支上额外完成的科技(如 E0 人类'
                                      '的 SAILING/ANIMAL_HUSBANDRY)不在闭包内且无落盘清单(U-A1)',
        'target_tech': tt,
        'target_tech_name': node_rev.get(tt & 0xffffffff)
            if tt not in (None, -1, 0xffffffff) else None,
        'science_overflow': val('ScienceOverflow'), 'science_debt': val('ScienceDebt'),
        'mastery_cost_handle': val('MasteryCost'),
        'note': 'TargetTech=手动选择的研究方向(现代档人类=NODE_TECH_MO_MASS_PRODUCTION ✓); '
                '远古档全 -1 且选科技(E6)不写入 — 人类选择在远古档的落盘时机/字段未定证(U-A2); '
                'AI 玩家恒 -1(自动研究不落盘, 与 TargetCultureNode AI=None 同构); '
                'ScienceOverflow 于下一回合被研究消耗(E0 t21=0.75 → E5.1 t22=0.0)',
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, outp = sys.argv[1], sys.argv[2]
    d = open(src, 'rb').read()
    bag = d.find(FXS)
    dic = load_dictionary()
    node_rev = load_node_names(d)
    node_rev.update(dic)  # 字段名兜底(不覆盖已有)
    prereqs = load_tech_prereqs()

    # 玩家块
    players = []
    pheads = P.find_heads(d, *P.SIGS['player'])
    poffs = [o for o, b, c, k in pheads]
    for pi, (off, base, ctx, k) in enumerate(pheads):
        try:
            f, _ = P.parse_block(d, base, 56, dic)
            slot = f.get('ID', (None, None))[1]
            alive = f.get('IsAlive', (None, None))[1]
            civ = f.get('Civilization', (None, None))[1]
        except P.ParseError:
            slot, alive, civ = None, None, None
        players.append({'off': off, 'slot': slot, 'alive': alive, 'civ_handle': civ})
    hi_all = poffs[-1] if poffs else len(d)
    # 最后一个玩家区域延伸到结尾前 2MB(现代档名人堂区不含组件)
    region_end = min(len(d), (poffs[-1] if poffs else bag) + 0x300000)

    # 组件注册表 (按玩家区域切分)
    comp_by_slot = {}
    allrecs = []
    for pi, pl in enumerate(players):
        lo = pl['off']
        hi = poffs[pi + 1] if pi + 1 < len(poffs) else region_end
        recs = parse_component_records(d, lo, hi, node_rev)
        if recs:
            comp_by_slot[pl['slot']] = recs
            allrecs.extend(recs)

    # DB 头部 CRC 序表
    tables = find_db_crc_tables(d, node_rev, bag)
    tech_tables = [t for t in tables
                   if sum(1 for nm in t['names'] if nm.startswith('NODE_TECH')) >= 8]
    civ_tables = [t for t in tables
                  if sum(1 for nm in t['names'] if nm.startswith('NODE_CIVIC')) >= 8]

    result = {'source': None, 'bag_start': bag, 'num_players': len(players), 'players': []}
    for pl in players:
        slot = pl['slot']
        rec = {'slot': slot, 'alive': pl['alive']}
        # 块层: 科技/文化/遗产/金库 (复用 progress.py 签名定位)
        for name, sig in (('tech', P.SIGS['tech']), ('culture', P.SIGS['culture']),
                          ('legacy', P.SIGS['legacy']), ('gold', P.SIGS['gold'])):
            bb = [x for x in P.find_heads(d, *sig) if x[0] > pl['off'] and
                  (poffs.index(pl['off']) + 1 >= len(poffs) or x[0] < poffs[poffs.index(pl['off']) + 1])]
            if not bb:
                continue
            try:
                f, _ = P.parse_block(d, bb[0][1], sig[1], dic)
            except P.ParseError:
                continue
            if name == 'tech':
                rec['tech'] = fmt_tech(f, node_rev, prereqs)
            elif name == 'culture':
                rec['culture'] = fmt_culture(f, node_rev)
            elif name == 'legacy':
                rec['legacy_path_points_proxy'] = '见 progress.py legacy 块(模板无运行时VP)'
            elif name == 'gold':
                g = {k: (v[1] / 256.0 if v[0] == 'fp8' else v[1])
                     for k, v in f.items() if k != 'Properties' and v[0] in ('fp8', 'blob4', 'scalar')}
                rec['gold'] = {k: g[k] for k in ('GoldBalance',) if k in g}
        # 组件注册表
        recs = comp_by_slot.get(slot, [])
        tech_nodes = [r for r in recs if r.get('kind') == 2]
        civic_nodes = [r for r in recs if r.get('kind') == 3]
        buildings = [r for r in recs if r.get('kind') == 5]
        others = [r for r in recs if r.get('kind') in (9, 10)]
        rec['components'] = {
            'tech_nodes': [{'idx': r.get('idx'), 'name': r.get('name'), 'group': r.get('group'),
                            'f2': r.get('f2')} for r in tech_nodes],
            'civic_nodes': [{'idx': r.get('idx'), 'name': r.get('name'), 'group': r.get('group'),
                             'f2': r.get('f2')} for r in civic_nodes],
            'buildings': sorted({r.get('name') for r in buildings if r.get('name')}),
            'building_components': len(buildings),
            'other_components': len(others),
            'note': 'kind2=SYSTEM_TECH 科技节点对象(f2=5 A组=每科技1条/已揭示集; f2=2 B组=解锁行'
                    '实例, 同科技多条; AI 玩家 B 组大, 人类 slot0 在远古档 B 组为空); '
                    'kind3=SYSTEM_CULTURE 市政节点对象; kind5=BUILDING 可解锁建筑对象',
        }
        # 尽力推断: A组=树中已揭示科技节点; 与文化块不同, 科技无 UnlockedCRC 列表
        grpA = [r['name'] for r in tech_nodes if r.get('group') == 'A' and r.get('name')]
        grpB = [r['name'] for r in tech_nodes if r.get('group') == 'B' and r.get('name')]
        rec['components']['groupA_techs'] = grpA
        rec['components']['groupB_unlock_rows'] = grpB
        result['players'].append(rec)

    result['db_crc_tables'] = {
        'tech_node_tables': [{'offset': hex(t['offset']), 'count': t['count'], 'names': t['names']}
                             for t in tech_tables],
        'civic_node_tables': [{'offset': hex(t['offset']), 'count': t['count'],
                               'names': t['names'][:40]} for t in civ_tables],
        'note': 'body 头部 DB 定义区按定义序(XML Types 序)排列的 NODE_* CRC 表; '
                '表内索引=定义序, 名字经 CRC32 反查(game XML + fieldnames)',
    }
    result['unresolved'] = [
        'U-A1 已完成科技全清单: 无落盘 CRC 列表(文化块 UnlockedTraditions 的科技侧等价物不存在;'
        ' 科技块 8 字段仅 Tree/LastCompletedNode/MasteryCost/NodeCostDiscount/ScienceOverflow/'
        'ScienceDebt/TargetTech)。可用代理: 组件注册表 A 组(f2=5, 每科技 1 条, =已揭示科技节点集, '
        'E0 人类=12/16) + LastCompletedNode(最后完成)。A 组与"已完成集"不重合(人类 E0: AGRI/AH/'
        'POTTERY 在 A 组而截图示已完成, SAILING 已完成却不在 A 组) — 语义未定证',
        'U-A2 正在研究的科技: TargetTech 字段本身有效(现代档人类=NODE_TECH_MO_MASS_PRODUCTION, '
        'AI 全 -1, 与 TargetCultureNode 人类有值/AI=None 同构)。但远古档含 E6(唯一操作=选科技 '
        'Writing)在内 TargetTech 恒 -1: 选科技(E0→E6)后 科技块零变化、对象图 E6↔E7 仅 1 字节'
        '易变计数器差、bag 仅情报类 11f 块 NumUrban 1→3(E6 独有, 语义未定证)、头部仅文件名/'
        '时间戳差。即远古档"选中科技"未落盘(或落盘于未解结构); ScienceOverflow 在下一回合被'
        '消耗(E0/E6 0.75 → E5.1 0.0)旁证研究已开始但目标节点不可读',
        'U-A3 组件记录 f2 语义: f2=5(A组)/2(B组)/10/1 的准确含义未定证; B 组记录的解锁行与 '
        'progression-trees-tech.xml NodeUnlocks 行的对应关系未对账',
        'U-A4 11f 情报类块(CityId/Location/Region/.../NumWalls/NumUrban/NumWonders) 的归属与'
        ' NumUrban 计数语义未定证(E6 独有 1→3 与选科技同帧出现)',
        'U-A5 图尾 [A][N][ids...] 数组(E0 N=107 → 重存 ~7000/3098 波动)为易变运行时结构, '
        '非科技清单',
    ]
    result['source'] = os.path.abspath(src)
    with open(outp, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1,
                  default=lambda o: o.hex() if isinstance(o, (bytes, bytearray)) else str(o))
    n_tech = sum(1 for p in result['players'] if p.get('components', {}).get('tech_nodes'))
    print('玩家=%d 有组件注册表=%d DB科技表=%d -> %s' % (
        len(result['players']), n_tech, len(tech_tables), outp))


if __name__ == '__main__':
    main()
