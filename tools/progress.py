#!/usr/bin/env python3
"""文明7 进度提取器 (Phase 5) — 从 body.bin 提取每文明的科技树/传统/遗产路径/生产/政策卡状态。

CLI: python3 -I tools/progress.py <body.bin> <out.json>

块签名与值区语法见 docs/save-format.md §6 与 docs/notes/phase3-units.md §1
(块头 5/6-u32 双形式, 值区按 schema 定长消费, 0x402 容器形跳到 FXSBLKED)。
名称反查: fieldnames.txt + 游戏本体 XML (NODE_/TREE_/TRADITION_/GOVERNMENT_/BUILDING_/UNIT_/PROJECT_)。

已解 (E0/E6/E7/E5.1/E5.2/现代档 7 档验证, 见 docs/notes/phase5-progress.md):
  科技块(K=d60fd288):  Tree/LastCompletedNode(CRC→节点名)/ScienceOverflow/ScienceDebt/
                       MasteryCost(句柄)/NodeCostDiscount(句柄数组); TargetTech 实测恒 -1
  文化块(K=86eb5a88):  Trees[]/UnlockedTraditions[](CRC→传统名)/MainTree/ActiveTree/
                       LastCompletedNode/ActiveGovernment/TargetCultureNode(=所选市政)/
                       CultureSlots(激活传统槽, 含传统 CRC)/CultureSlotSwaps
  遗产块(K=418d123e):  EnabledLegacyPaths/*ScoringItems(计分项定义, 全玩家同模板)/
                       MilestonesAchieved(12×(hash,flag)); 面板 VP 为运行时值, 存档仅存
                       定义项(未解 U5.3); 军事 VP 代理 = CitiesFounded+TownsFounded+2×征服
  军事统计(K=6979b751): CitiesFounded/TownsFounded(建城差分验证 +1)/征服系列(句柄)
  政策卡块(K=acc4feca): AvailableCards/Cards/LegacyPoints/HistoricalLegacyPoints(6×(hash,句柄))
  生产(尽力):          城区块(18f) Constructibles=[count][n×(state, id_lo, id_hi, ?)]，
                       (id_lo,id_hi)=(n,n+1)=建造物实例序号对(每玩家序列: 宫=0/城区=1..5/
                       祭坛=6/图拉中心=7, E5.2 交叉验证); 宗教块→产量块间隙的"当前生产记录"
                       (type CRC, 祭坛记录与城区 Constructibles 同 id 对)
"""
import sys, os, json, struct, re, glob, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propertybag import FXS, load_dictionary, crc32_name

_U = struct.Struct('<I')
FXSBLKED = FXS
SCALAR_SIZE = {1:1,2:1,3:2,4:1,5:1,6:2,7:2,8:4,9:4,10:8,11:8,12:4,13:8,32:16}
MAP_W = 74

# 块签名: name -> (K, count, ent0, ent1|None)。K=None = 通配(按 ent0/ent1 识别)
SIGS = {
    'player':    (0x00000003, 56, 0x3761cde8, None),
    'tech':      (0xd60fd288,  8, 0x3761cde8, 0xe8f30e1d),   # ent1=Tree
    'culture':   (0x86eb5a88, 33, 0x3761cde8, 0xaae2bf51),   # ent1=Trees
    'legacy':    (0x418d123e, 15, 0x3761cde8, 0xc2961ada),   # ent1=EnabledLegacyPaths
    'gold':      (0xd34dab99, 19, 0x3761cde8, 0x5b34386f),   # ent1=GoldBalance
    'milstats':  (0x6979b751, 75, 0x3761cde8, None),
    'prodmods':  (0x47e3881f, 11, 0x845f7b57, None),          # 无 Properties
    'cityinst':  (None,        29, 0x58171462, None),         # K=每文明模板 id
    'district':  (None,        18, 0xbca42673, None),         # ent0=CityID; K=0, ctx=ffffffff
    'cards':     (None,         8, 0x3761cde8, 0x758e557f),   # ent1=AvailableCards
    'religion':  (0xc7eded87,  5, 0x3761cde8, None),
}
SIGS['resources'] = (0x926896f2, 16, 0x3761cde8, None)

CRC_AVAILABLE_CARDS = crc32_name('AvailableCards')
CRC_CONSTRUCTIBLES  = crc32_name('Constructibles')
CRC_CITYID          = crc32_name('CityID')
CRC_LOCATION        = crc32_name('Location')
CRC_DISTRICT_TYPE   = crc32_name('DistrictType')


class ParseError(Exception):
    pass


def read_value(d, pos, t):
    n = len(d)
    m = t & 0xffff
    if m == 0x402:
        if pos+4 > n: raise ParseError('eof')
        ln = _U.unpack_from(d, pos)[0]; end = pos+4+ln
        padded = end + ((-ln) % 4)
        if padded+8 > n or d[padded:padded+8] != FXSBLKED: raise ParseError('badstr')
        return ('str', d[end:padded], padded+8)
    if m in (0x400, 0x403):
        if pos+4 > n: raise ParseError('eof')
        sz = _U.unpack_from(d, pos)[0]
        if sz > n-pos-4 or sz > (1<<20): raise ParseError('badsize')
        raw = d[pos+4:pos+4+sz]
        if sz == 4: return ('blob4', _U.unpack(raw)[0], pos+4+sz)
        if sz == 8:
            a,b = struct.unpack_from('<2i', raw, 0)
            return ('blob8', [a,b], pos+4+sz)
        return ('blob', raw, pos+4+sz)
    if m == 0x407:
        if pos+4 > n: raise ParseError('eof')
        return ('fp8', _U.unpack_from(d, pos)[0]/256.0, pos+4)
    sz = SCALAR_SIZE.get(m)
    if sz is None or pos+sz > n: raise ParseError('bad scalar')
    raw = d[pos:pos+sz]
    if m == 8: v = struct.unpack('<i', raw)[0]
    elif m == 9: v = _U.unpack(raw)[0]
    elif m == 10: v = struct.unpack('<q', raw)[0]
    elif m == 11: v = struct.unpack('<Q', raw)[0]
    elif m == 12: v = struct.unpack('<f', raw)[0]
    elif m == 32: v = raw.hex()
    elif sz == 1: v = raw[0]
    elif sz == 2: v = struct.unpack('<H', raw)[0]
    else: v = raw.hex()
    return ('scalar', v, pos+sz)


def _skip_container(d, vpos):
    ln = _U.unpack_from(d, vpos)[0]
    content = vpos + 4 + ln + ((-ln) % 4)
    t = d.find(FXSBLKED, content, content + (1<<20))
    if t < 0: raise ParseError('container no term')
    return t + 8


def find_heads(d, K, cnt, ent0, ent1=None):
    """返回 [(koff, base, ctx, Kactual)]。5-form: K@i-4; 6-form: K@i-8,ctx@i-4。"""
    out = []
    seq = struct.pack('<IIII', 0xffffffff, 1, 1, cnt)
    i = d.find(seq)
    n = len(d)
    while i >= 0:
        base = i + 16
        if base + 8*cnt <= n:
            ok = True
            for k in range(min(cnt,4)):
                tw = _U.unpack_from(d, base + 8*k + 4)[0]
                if (tw & 0xffff) > 0x407: ok = False; break
            if ok and _U.unpack_from(d, base)[0] == ent0:
                if ent1 is not None and _U.unpack_from(d, base+8)[0] != ent1:
                    ok = False
                if ok:
                    k5 = _U.unpack_from(d, i-4)[0]
                    k6 = _U.unpack_from(d, i-8)[0]
                    if K is None:
                        out.append((i-4, base, [k6], k5))
                    elif k6 == K:
                        out.append((i-8, base, [k5], k6))
                    elif k5 == K:
                        out.append((i-4, base, [], k5))
        i = d.find(seq, i+1)
    return out


def parse_block(d, base, cnt, dic):
    entries = [struct.unpack_from('<II', d, base+8*i) for i in range(cnt)]
    p = base + 8*cnt
    fields = {}
    for i,(h,t) in enumerate(entries):
        nm = dic.get(h) or 'h%08x' % h
        try:
            kind, v, p2 = read_value(d, p, t)
        except ParseError:
            if (t & 0xffff) == 0x402:
                p2 = _skip_container(d, p)
                kind, v = 'container', None
            else:
                raise
        if i == 0 and (t & 0xffff) == 0x402 and kind == 'str':
            kind = 'props_str'
        fields[nm] = (kind, v)
        p = p2
    return fields, p


def load_game_names():
    """游戏本体 XML 的 NODE_/TREE_/TRADITION_/GOVERNMENT_ 名 (科技/传统/政府反查后备)。"""
    names = set()
    roots = ('/Applications/CivilizationVII.app/Contents/Resources/Base',
             '/Applications/CivilizationVII.app/Contents/Resources/DLC')
    for root in roots:
        for path in glob.glob(root + '/**/*.xml', recursive=True):
            try:
                text = open(path, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            for m in re.finditer(r'\b(?:NODE|TREE|TRADITION|GOVERNMENT|DISTRICT)_[A-Z0-9_]{2,60}\b', text):
                names.add(m.group(0))
    return names


def load_constructible_names(data):
    """BUILDING_/UNIT_/PROJECT_ 名: 存档全文 grep + _NAME 剥离。"""
    names = set()
    for m in re.finditer(rb'(?:BUILDING|UNIT|PROJECT)_[A-Z0-9_]{2,60}', data):
        names.add(m.group(0).decode('ascii'))
    inferred = set()
    for n in names:
        if n.endswith('_NAME'):
            inferred.add(n[:-5])
    return names | inferred


def decode_scoring_blob(raw):
    """*ScoringItems blob 尽力解读: [count][entries]。
    SettlementCountScoringItems 实测 16B 条目 (4×u32): 第 3 个 u32 = VP 值
    (E0: 征服 2 / 非征服 1, 与 DB VICTORY_ANTIQUITY_MILITARY_*_SCORING 的 VP=2/1 吻合)。
    其他 *ScoringItems 条目长度不一 (15/17/21B), 无法统一定长 → 原样 hex。"""
    if raw is None or len(raw) < 4:
        return None
    cnt = _U.unpack_from(raw, 0)[0]
    body = len(raw) - 4
    if cnt and body == cnt * 16:
        out = []
        for i in range(cnt):
            a, b, c, e = struct.unpack_from('<IIII', raw, 4 + 16*i)
            out.append({'f0': a, 'vp_or_b': c, 'f2': b, 'f3': '%08x' % e})
        return {'count': cnt, 'entry_len': 16, 'entries': out,
                'note': 'E0 两条款目 VP=2(征服)/1(非征服) 与 DB 军事计分定义吻合'}
    return {'count': cnt, 'entry_len': None, 'hex': raw.hex()}


def decode_milestones(raw):
    """MilestonesAchieved blob: [count=12][12 × (u32 hash, u8 flag)] — 遗产路径里程碑定义+达成位。"""
    if raw is None or len(raw) < 4:
        return None
    cnt = _U.unpack_from(raw, 0)[0]
    out = []
    p = 4
    for _ in range(cnt):
        if p + 5 <= len(raw):
            h = _U.unpack_from(raw, p)[0]
            out.append({'hash': '%08x' % h, 'flag': raw[p+4]})
            p += 5
        else:
            break
    return out


def decode_u32_list(raw):
    if raw is None or len(raw) < 4:
        return None
    cnt = _U.unpack_from(raw, 0)[0]
    if cnt > 4096 or len(raw) < 4 + 4*cnt:
        return None
    return [_U.unpack_from(raw, 4+4*i)[0] for i in range(cnt)]


class ProgressExtractor:
    def __init__(self, data):
        self.data = data
        self.n = len(data)
        self.dic = load_dictionary()
        self.bag = data.find(FXSBLKED)
        if self.bag < 0:
            raise ParseError('未找到 FXSBLKED')
        # 名称反查字典
        gnames = load_game_names()
        self.node_rev = {crc32_name(n): n for n in gnames}
        self.cons_rev = {crc32_name(n): n for n in load_constructible_names(data)}

    def nodename(self, h):
        if h in (0xffffffff, 0): return None
        return self.node_rev.get(h & 0xffffffff)

    def consname(self, h):
        if h in (0xffffffff, 0): return None
        return self.cons_rev.get(h & 0xffffffff)

    def extract(self):
        d = self.data
        # 玩家
        players = []
        for off, base, ctx, K in find_heads(d, *SIGS['player']):
            try:
                f, _ = parse_block(d, base, 56, self.dic)
            except ParseError:
                players.append({'offset': off}); continue
            players.append({'offset': off,
                            'slot': f.get('ID',(None,None))[1],
                            'alive': f.get('IsAlive',(None,None))[1],
                            'civ_handle': f.get('Civilization',(None,None))[1]})
        poffs = [p['offset'] for p in players]

        def owner(off):
            i = bisect.bisect_right(poffs, off) - 1
            return players[i].get('slot') if 0 <= i < len(players) else None

        # 各类块
        blocks = {}
        for name, sig in SIGS.items():
            if name == 'player': continue
            K, cnt, ent0, ent1 = sig
            bl = []
            for off, base, ctx, k in find_heads(d, K, cnt, ent0, ent1):
                try:
                    f, endp = parse_block(d, base, cnt, self.dic)
                except ParseError as e:
                    bl.append({'offset': off, 'parse_error': str(e)}); continue
                bl.append({'offset': off, 'end': endp, 'key': '%08x' % k, 'ctx': ctx,
                           'owner_slot': owner(off), 'fields': f})
            bl.sort(key=lambda x: x['offset'])
            blocks[name] = bl

        # 城市实例: ctx = owner slot (E0 全 7 档验证); name/location/has_build_queue
        cities = []
        for b in blocks['cityinst']:
            f = b.get('fields')
            if not f: continue
            nm = f.get('Name')
            name = None
            if nm:
                raw = nm[1]
                if isinstance(raw, (bytes, bytearray)):
                    m = re.search(rb'LOC_[A-Z0-9_]+', raw)
                    name = m.group(0).decode() if m else None
                elif isinstance(raw, str):
                    m = re.search(r'LOC_[A-Z0-9_]+', raw)
                    name = m.group(0) if m else None
            loc = f.get('Location')
            xy = list(loc[1]) if loc and loc[0]=='blob8' else None
            hbq = f.get('HasBuildQueue')
            cities.append({'offset': b['offset'], 'key': b['key'],
                           'owner_slot': b['ctx'][0] if b.get('ctx') else b.get('owner_slot'),
                           'name': name, 'location': xy,
                           'plot': xy[1]*MAP_W+xy[0] if xy else None,
                           'has_build_queue': hbq[1] if hbq and hbq[0] in ('blob4','scalar') else None,
                           'highest_population': f.get('HighestPopulation',(None,None))[1]})
        for c in cities:
            if c['owner_slot'] is None:
                c['owner_slot'] = owner(c['offset'])
        cities.sort(key=lambda x: x['offset'])

        # 城区块 → 按 CityID 分组
        districts = []
        for b in blocks['district']:
            f = b.get('fields')
            if not f or 'Constructibles' not in f: continue
            cid = f.get('CityID')
            cidv = cid[1] if cid and cid[0]=='blob4' else None
            con = f['Constructibles']
            entries = []
            if con[0] == 'blob':
                raw = con[1]
                if len(raw) >= 4:
                    cnt = _U.unpack_from(raw, 0)[0]
                    p = 4
                    for _ in range(cnt):
                        if p+12 <= len(raw):
                            st, ab, c = struct.unpack_from('<III', raw, p)
                            entries.append({'state': st, 'a': ab & 0xffff, 'b': ab >> 16, 'c': c})
                            p += 12
            dt = f.get('DistrictType')
            dtv = dt[1] if dt and dt[0] in ('blob4','scalar') else None
            districts.append({'offset': b['offset'], 'owner_slot': b.get('owner_slot'),
                              'city_id': ('%08x' % cidv) if cidv is not None else None,
                              'district_type_hash': ('%08x' % dtv) if dtv else None,
                              'district_type_name': self.nodename(dtv) if dtv else None,
                              'location': list(f['Location'][1]) if f.get('Location') and f['Location'][0]=='blob8' else None,
                              'constructibles': entries})
        districts.sort(key=lambda x: x['offset'])

        # 当前生产记录: 宗教块→下一 prodmods 块之间的间隙 (每城一段) — 尽力
        prodrec = self._scan_production(blocks)

        # 组装每玩家
        out_players = []
        for pl in players:
            slot = pl.get('slot')
            if slot is None: continue
            rec = {'slot': slot, 'alive': pl.get('alive')}
            for name in ('tech','culture','legacy','gold','milstats','cards','resources'):
                bb = [x for x in blocks[name] if x.get('owner_slot')==slot]
                rec[name] = self._fmt(name, bb[0]['fields']) if bb else None
            rec['settlements'] = [
                {'name': c['name'], 'location': c['location'], 'plot': c['plot'],
                 'population': c['highest_population'],
                 'has_build_queue': c['has_build_queue']}
                for c in cities if c['owner_slot']==slot]
            # 城区: CityID 与城市实例 id 的编码未定证 (U5.6), 按拥有者分组输出
            rec['districts'] = [x for x in districts if x['owner_slot']==slot]
            rec['production_records'] = [x for x in prodrec if x.get('owner_slot')==slot]
            out_players.append(rec)
        return {
            'source': None,
            'bag_start': self.bag,
            'num_players': len(out_players),
            'players': out_players,
            'unresolved': self._unresolved(),
        }

    def _scan_production(self, blocks):
        """宗教块→下一 prodmods 块间隙中的"当前生产记录"。
        记录含 constructible CRC + (可选)城市坐标 + (a,b) u16 对。
        E7 锚点: 祭坛记录 (6,7) ↔ 面板 ⏱6 (疑=剩余回合,总回合, 未定证)。"""
        d = self.data
        rel = blocks.get('religion', [])
        pm  = blocks.get('prodmods', [])
        pmoffs = [b['offset'] for b in pm]
        out = []
        for b in rel:
            lo = b.get('end') or b['offset']
            i = bisect.bisect_right(pmoffs, b['offset'])
            hi = pmoffs[i] if i < len(pmoffs) else min(lo + 4096, self.n)
            seg = d[lo:hi]
            found = []
            for h in set(self.cons_rev):
                pat = struct.pack('<I', h)
                j = seg.find(pat)
                while j >= 0:
                    # 后 80B 内找 (a,a+1) u16 对
                    tail = seg[j+4:j+84]
                    pair = None
                    for q in range(0, len(tail)-3):
                        a1, a2 = struct.unpack_from('<HH', tail, q)
                        if a2 == a1 + 1 and 0 < a1 < 4096:
                            pair = (a1, a2); break
                    found.append({'type': self.cons_rev[h],
                                  'instance_id_pair': pair,
                                  'offset': lo + j})
                    j = seg.find(pat, j+1)
            if found:
                out.append({'owner_slot': b.get('owner_slot'), 'record_offset': lo,
                            'items': found[:8]})
        return out

    def _fmt(self, name, f):
        def val(k):
            v = f.get(k)
            return v[1] if v else None
        if name == 'tech':
            return {
                'tree': val('Tree'), 'tree_name': self.nodename(val('Tree')),
                'last_completed_node': val('LastCompletedNode'),
                'last_completed_node_name': self.nodename(val('LastCompletedNode')),
                'target_tech': val('TargetTech'),
                'target_tech_name': self.nodename(val('TargetTech')) if val('TargetTech') not in (None,-1) else None,
                'science_overflow': val('ScienceOverflow'), 'science_debt': val('ScienceDebt'),
                'mastery_cost_handle': val('MasteryCost'),
                'node_cost_discount_handles': len(f['NodeCostDiscount'][1])//4
                    if f.get('NodeCostDiscount') and f['NodeCostDiscount'][0]=='blob' else None,
                'note': 'TargetTech 实测恒 -1 (4档31玩家); 当前研究方向在对象图 DAG 中(未解 U5.2)',
            }
        if name == 'culture':
            trees = decode_u32_list(val('Trees')) if f.get('Trees') and f['Trees'][0]=='blob' else None
            trs = val('UnlockedTraditions')
            trl = decode_u32_list(trs) if trs is not None and isinstance(trs, bytes) else None
            slots = val('CultureSlots')
            return {
                'trees': trees,
                'tree_names': [self.nodename(t) for t in (trees or [])],
                'unlocked_traditions': trl,
                'unlocked_tradition_names': [self.nodename(t) for t in (trl or [])],
                'main_tree': val('MainTree'), 'main_tree_name': self.nodename(val('MainTree')),
                'active_tree': val('ActiveTree'), 'active_tree_name': self.nodename(val('ActiveTree')),
                'last_completed_node': val('LastCompletedNode'),
                'last_completed_node_name': self.nodename(val('LastCompletedNode')),
                'active_government': val('ActiveGovernment'),
                'active_government_name': self.nodename(val('ActiveGovernment')),
                'target_culture_node': val('TargetCultureNode'),
                'target_culture_node_name': self.nodename(val('TargetCultureNode')),
                'culture_overflow': val('CultureOverflow'), 'culture_debt': val('CultureDebt'),
                'culture_slots_raw': slots.hex() if isinstance(slots, bytes) else slots,
                'culture_slot_swaps_raw': (val('CultureSlotSwaps') or b'').hex()
                    if isinstance(val('CultureSlotSwaps'), bytes) else val('CultureSlotSwaps'),
            }
        if name == 'legacy':
            out = {}
            for k, v in f.items():
                if k == 'Properties': continue
                kind, vv = v
                if kind == 'blob4':
                    out[k] = {'kind': 'blob4', 'value': vv}
                elif kind == 'blob':
                    if 'ScoringItems' in k:
                        out[k] = decode_scoring_blob(vv)
                    elif k == 'MilestonesAchieved':
                        out[k] = decode_milestones(vv)
                    else:
                        out[k] = {'kind': 'blob', 'len': len(vv), 'hex': vv[:64].hex()}
                else:
                    out[k] = vv
            return out
        if name == 'gold':
            return {k: (v[1]/256.0 if v[0]=='fp8' else v[1]) for k,v in f.items() if k != 'Properties'}
        if name == 'milstats':
            keep = {}
            for k, v in f.items():
                if k == 'Properties': continue
                kind, vv = v
                if kind == 'blob4':
                    # 小值 = 计数, 大值 = 句柄
                    keep[k] = {'value': vv, 'is_count': 0 <= vv < 1024}
            return {k: keep[k] for k in keep if any(s in k for s in
                    ('CitiesFounded','TownsFounded','Conquered','Razed','Reconquered','Treasure','War'))}
        if name == 'cards':
            hlp = val('HistoricalLegacyPoints')
            entries = None
            if isinstance(hlp, bytes) and len(hlp) >= 4:
                cnt = _U.unpack_from(hlp, 0)[0]
                entries = []
                p = 4
                for _ in range(cnt):
                    if p+8 <= len(hlp):
                        entries.append({'hash': '%08x' % _U.unpack_from(hlp,p)[0],
                                        'handle': _U.unpack_from(hlp,p+4)[0]})
                        p += 8
            return {'available_cards': val('AvailableCards'), 'cards': val('Cards'),
                    'next_card_id': val('NextCardID'),
                    'placement_complete': f['PlacementComplete'][1].hex() if f.get('PlacementComplete') and isinstance(f['PlacementComplete'][1], bytes) else val('PlacementComplete'),
                    'legacy_points': val('LegacyPoints'),
                    'historical_legacy_points': entries,
                    'note': '政策=卡(Cards)运行时哈希态; E0/E6/E7 全 0/空 — 远古时代无政策卡; HistoricalLegacyPoints=6×(hash,句柄)'}
        if name == 'resources':
            keep = {}
            for k, v in f.items():
                if k == 'Properties': continue
                kind, vv = v
                if kind == 'blob4' and 0 <= vv < 4096:
                    keep[k] = vv
            return keep
        return None

    def _unresolved(self):
        return [
            'U5.1 遗产路径面板 VP 值: 15f 遗产块为全玩家一致模板(计分项定义+里程碑定义); 运行时 VP 无逐玩家落盘, 建城差分(E5.1→E5.2)仅军事统计 TownsFounded +1; 面板按运行时计算。E0 截图 军事 8/12/8 与存档任何逐玩家统计不符(定居点最多 2) — 未解',
            'U5.2 当前研究方向: 科技块 TargetTech 恒 -1; 选科技(E6)在对象图新增 ~250 节点(两类 class), 节点以定义索引引用科技, 节点语法/映射未解',
            'U5.3 *ScoringItems 条目语义: (state,a,b,c) 中 (a,b) 疑 (VP值,序号), 未对锚点定证',
            'U5.4 MilestonesAchieved 12 个 hash 无字符串可反查 (里程碑定义名不在存档/游戏 XML)',
            'U5.5 队列结构: 排产记录散布在 0x402 容器内(U3b 遗留), 仅能按间隙模式提取; (a,a+1) 对已证为建造物实例序号(每玩家序列)而非回合; 队列"剩余回合/完成回合"无落盘原值(运行时), 截图 ⏱6 为显示值',
            'U5.6 城市实例 id 与城区 CityID 编码未定证 (0x00010000/0x00020001 观察)',
            'U5.7 HistoricalLegacyPoints 的 6 个 hash 与 LegacyPoints 句柄未反查',
        ]


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    data = open(sys.argv[1], 'rb').read()
    ex = ProgressExtractor(data)
    result = ex.extract()
    result['source'] = os.path.abspath(sys.argv[1])
    with open(sys.argv[2], 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=lambda o: o.hex() if isinstance(o,(bytes,bytearray)) else str(o))
    n = result['num_players']
    tr = sum(1 for p in result['players'] if p['culture'] and p['culture']['unlocked_tradition_names'])
    print(f"玩家={n} 传统可解={tr} -> {sys.argv[2]}")


if __name__ == '__main__':
    main()
