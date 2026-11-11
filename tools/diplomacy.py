#!/usr/bin/env python3
"""文明7 外交关系提取器 (Phase 4) — 从 body.bin 提取全文明外交关系表。

CLI: python3 -I tools/diplomacy.py <body.bin> <out.json>

复用 propertybag.py 的 CRC32/字段名字典与 save-format.md §6 的块语法。
块定位按"块头签名 + schema 首条目 hash + 值区严格解析"全文搜索（同 units.py）。

外交数据落盘位置（E0/E2 差分 + 截图锚点验证，见 docs/notes/phase4-diplomacy.md）:
  1) 玩家实例块 (K=00000003, 56字段)  → ID=slot, IsAlive          （归属锚点）
  2) 影响力/外交状态块 (K=00000005, 78字段, 每玩家 1 个):
       HasOpenBordersFrom    blob 64×u8   ← 开放边界状态: 值[slot]=1 ⇒ 该玩家
                                            可进入 slot 的边界（我方付影响力买
                                            "对方的边界对我开放"），未开放=0
       OpenBordersEndedTurn  blob 64×u32  ← 协议结束回合（-1=无）
       RelationshipLevel     blob 64×FP8  ← 对各 slot 的关系分（0=中立）
       Grievances/Favors/WarWeariness/NumWarsInitiatedAgainstPlayer  64×u32
       HasNonAggressionPact  64×u8
       Tokens/AvailableTokens/…  blob4 = 外交影响力对象句柄（值非直读）
  3) 影响力余额块 (K=7d74610f, 15字段, 每玩家 1 个):
       DiplomacyBalance      FP8          ← 顶栏影响力数值（E0 slot0=80.0 ✓）
  4) 全局战争/外交事件块 (K=dced693c, 18字段, owner=最后一个玩家 63):
       HasMet / HasDeclaredFriendship / IsAllied / IsPermanentlyAllied /
       IsInDefensivePact: [2016][C(64,2)×(u8 + u32)] 三角阵（64 slot 两两）
       AtWar / AtWarEvent / WarInitiator / JointWarTarget: [2016][C(64,2)×8B]
       ActiveDiplomacyEventsV2 / ConcludedDiplomacyEvents: [count][事件×N]
       TotalDiplomacyEvents / MaxNumPlayers 标量
  5) 协议块 (K=36007b22, 3字段): EnactedDealID + Deals
  6) 部落块 (K=357d796d, 16字段, 每玩家 1 个): Suzerain/OpenBordersCount/
       TribeRelationships（独立势力关系，语义部分未解）
  7) 外交修正块 (K=3a9f4f31, 13字段, 每玩家 1 个): DiplomaticModifiers 等
       [count=64][64×u32] 数组（E0/E2 全 0）

输出 JSON: players（每 slot 的余额/开放边界/关系分）+ pairs（两两关系）+
events（外交事件表）+ unresolved。
"""
import sys, os, json, struct, bisect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propertybag import FXS, load_dictionary

U32 = struct.Struct('<I')
FXSBLKED = FXS

# 块签名: (key, count, 首条目hash)。头部两种形态: form5 [K][-1][1][1][cnt], form6 [K][1][-1][1][1][cnt]
SIG_PLAYER  = (0x00000003, 56, 0x3761cde8)   # Properties
SIG_INFL    = (0x00000005, 78, 0x3761cde8)
SIG_BALANCE = (0x7d74610f, 15, 0x3761cde8)   # DiplomacyBalance
SIG_TRIBE   = (0x357d796d, 16, 0x3761cde8)
SIG_DIPLO   = (0x3a9f4f31, 13, 0x3761cde8)
SIG_WAR     = (0xdced693c, 18, 0x3761cde8)
SIG_DEALS   = (0x36007b22, 3,  0x3761cde8)

SCALAR_SIZE = {1: 1, 2: 1, 3: 2, 4: 1, 5: 1, 6: 2, 7: 2, 8: 4, 9: 4,
               10: 8, 11: 8, 12: 4, 13: 8, 32: 16}

MAX_PLAYERS = 64   # 关系矩阵维度（MaxNumPlayers 字段实测 64）


class ParseError(Exception):
    pass


class DiplomacyExtractor:
    def __init__(self, data):
        self.data = data
        self.n = len(data)
        self.dic = load_dictionary()
        self.bag = data.find(FXSBLKED)
        if self.bag < 0:
            raise ParseError('未找到 FXSBLKED 属性包起点')
        self.unresolved = []

    def name(self, h):
        return self.dic.get(h) or f'hash_{h:08x}'

    # ---------- 底层（同 units.py 的严格块定位） ----------
    def _head_at(self, pos, sig):
        key, cnt, ent0 = sig
        d = self.data
        if pos + 24 > self.n:
            return None
        if U32.unpack_from(d, pos)[0] != key:
            return None
        w1 = U32.unpack_from(d, pos + 4)[0]
        if w1 == 1 and U32.unpack_from(d, pos + 8)[0] == 0xffffffff \
                and U32.unpack_from(d, pos + 12)[0] == 1 and U32.unpack_from(d, pos + 16)[0] == 1 \
                and U32.unpack_from(d, pos + 20)[0] == cnt:
            base = pos + 24
        elif w1 == 0xffffffff and U32.unpack_from(d, pos + 8)[0] == 1 \
                and U32.unpack_from(d, pos + 12)[0] == 1 and U32.unpack_from(d, pos + 16)[0] == cnt:
            base = pos + 20
        else:
            return None
        if base + 8 * cnt > self.n:
            return None
        if U32.unpack_from(d, base)[0] != ent0:
            return None
        for i in range(cnt):
            if (U32.unpack_from(d, base + 8 * i + 4)[0] & 0xffff) > 0x407:
                return None
        return base, base + 8 * cnt

    def find_heads(self, sig):
        key, cnt, ent0 = sig
        offs = set()
        for form in (struct.pack('<IIIII', key, 0xffffffff, 1, 1, cnt),
                     struct.pack('<IIIIII', key, 1, 0xffffffff, 1, 1, cnt)):
            start = 0
            while True:
                i = self.data.find(form, start)
                if i < 0:
                    break
                if self._head_at(i, sig):
                    offs.add(i)
                start = i + 1
        return sorted(offs)

    def _read_value(self, pos, t):
        """按 VariantValueType 读一个值。返回 (kind, value, new_pos)。"""
        d = self.data
        m = t & 0xffff
        if m == 0x402:
            if pos + 4 > self.n:
                raise ParseError('eof')
            ln = U32.unpack_from(d, pos)[0]
            end = pos + 4 + ln
            padded = end + ((-ln) % 4)
            if padded + 8 <= self.n and d[padded:padded + 8] == FXSBLKED:
                return 'str', d[end:padded].decode('utf-8', 'replace'), padded + 8
            t2 = d.find(FXSBLKED, end, end + 65536)   # 0x402 容器形（无终止符）
            if t2 < 0:
                raise ParseError('container without terminator')
            return 'props_container', None, t2 + 8
        if m in (0x400, 0x403):
            if pos + 4 > self.n:
                raise ParseError('eof')
            sz = U32.unpack_from(d, pos)[0]
            if sz > self.n - pos - 4:
                raise ParseError('bad blob size')
            return 'blob', d[pos + 4:pos + 4 + sz], pos + 4 + sz
        if m == 0x407:
            if pos + 4 > self.n:
                raise ParseError('eof')
            return 'fp8', U32.unpack_from(d, pos)[0], pos + 4
        sz = SCALAR_SIZE.get(m)
        if sz is None or pos + sz > self.n:
            raise ParseError('bad scalar type 0x%x' % t)
        raw = d[pos:pos + sz]
        if m == 8:
            v = struct.unpack('<i', raw)[0]
        elif m == 9:
            v = U32.unpack(raw)[0]
        elif m == 10:
            v = struct.unpack('<q', raw)[0]
        elif m == 11:
            v = struct.unpack('<Q', raw)[0]
        elif m == 12:
            v = struct.unpack('<f', raw)[0]
        elif m == 13:
            v = struct.unpack('<d', raw)[0]
        elif m == 32:
            v = raw.hex()
        elif sz == 1:
            v = raw[0]
        elif sz == 2:
            v = struct.unpack('<H', raw)[0]
        else:
            v = raw.hex()
        return 'scalar', v, pos + sz

    def parse_block(self, pos, sig):
        """解析指定签名块。返回 (fields {名: (kind, value, voff)}, vend) 或 None。
        0x402 容器形首字段(Properties)跳到终止符。"""
        r = self._head_at(pos, sig)
        if r is None:
            return None
        base, vend = r
        cnt = sig[1]
        p = vend
        fields = {}
        try:
            for i in range(cnt):
                h, t = struct.unpack_from('<II', self.data, base + 8 * i)
                kind, v, p2 = self._read_value(p, t)
                fields[self.name(h)] = (kind, v, p)
                p = p2
        except ParseError:
            return None
        return fields, p

    # ---------- 数组解码 ----------
    @staticmethod
    def _u32_array(blob):
        """blob → u32 列表（4 字节对齐截断）。"""
        n = len(blob) // 4
        return list(struct.unpack_from('<%dI' % n, blob)) if n else []

    @staticmethod
    def _u8_array(blob):
        return list(blob)

    @staticmethod
    def _count_prefixed(blob):
        """[count u32][count×elem] 形（OpenBordersCount/DiplomaticModifiers 等）。"""
        if len(blob) < 4:
            return None
        cnt = U32.unpack_from(blob)[0]
        rest = blob[4:]
        return cnt, rest

    @staticmethod
    def _tri_index(k):
        """三角阵线性下标 k → (i, j)（i<j，64 slot 行优先三角）。"""
        i = 0
        while k >= MAX_PLAYERS - 1 - i:
            k -= MAX_PLAYERS - 1 - i
            i += 1
        return i, i + 1 + k

    def _matrix(self, blob, elem_size):
        """[count=2016][elem×2016] 三角阵 → {(i,j): elem bytes}。"""
        if len(blob) < 4:
            return None
        cnt = U32.unpack_from(blob)[0]
        body = blob[4:]
        if cnt == 0 or len(body) < cnt * elem_size:
            return None
        out = {}
        for k in range(cnt):
            el = body[k * elem_size:(k + 1) * elem_size]
            if el.count(0xff) == elem_size or el == b'\x00' * elem_size:
                continue
            out[self._tri_index(k)] = el
        return out

    # ---------- 事件流 ----------
    @staticmethod
    def split_events(blob):
        """[count][事件×count]。事件边界 = 头部 [3][-1] 模式；事件0 固定从 body[0] 起
        （active 事件头 = [A][3][-1][1][1][F]...，concluded 事件头 = [3][-1][1][1][F]...）。"""
        if len(blob) < 4:
            return []
        body = blob[4:]
        pat = struct.pack('<II', 3, 0xffffffff)
        starts = [0] if body else []
        i = body.find(pat, 4)
        while i >= 0:
            if i > 4:                      # i==4 ⇒ 事件0 头就是 [A][3][-1]，已含在 starts[0]
                starts.append(i - 4)
            i = body.find(pat, i + 1)
        events = []
        for idx, s in enumerate(starts):
            e = starts[idx + 1] if idx + 1 < len(starts) else len(body)
            events.append(body[s:e])
        return events

    # ---------- 主提取 ----------
    def extract(self):
        data = self.data
        # 1) 玩家实例（slot 锚点）
        players = []
        poffs = []
        for po in self.find_heads(SIG_PLAYER):
            r = self.parse_block(po, SIG_PLAYER)
            if not r:
                continue
            fields, _ = r
            slot = fields.get('ID', (None, None, None))[1]
            alive = fields.get('IsAlive', (None, None, None))[1]
            players.append({'slot': slot, 'alive': alive, 'offset': po})
            poffs.append(po)

        def owner(pos):
            i = bisect.bisect_right(poffs, pos) - 1
            return players[i]['slot'] if i >= 0 else None

        # 2) 每玩家块
        infl_by_slot, bal_by_slot, tribe_by_slot, diplo_by_slot = {}, {}, {}, {}
        for off in self.find_heads(SIG_INFL):
            r = self.parse_block(off, SIG_INFL)
            if r:
                s = owner(off)
                if s is not None:
                    infl_by_slot[s] = (off, r[0])
        for off in self.find_heads(SIG_BALANCE):
            r = self.parse_block(off, SIG_BALANCE)
            if r:
                s = owner(off)
                if s is not None:
                    bal_by_slot[s] = (off, r[0])
        for off in self.find_heads(SIG_TRIBE):
            r = self.parse_block(off, SIG_TRIBE)
            if r:
                s = owner(off)
                if s is not None:
                    tribe_by_slot[s] = (off, r[0])
        for off in self.find_heads(SIG_DIPLO):
            r = self.parse_block(off, SIG_DIPLO)
            if r:
                s = owner(off)
                if s is not None:
                    diplo_by_slot[s] = (off, r[0])

        # 3) 全局块
        war_block = deals_block = None
        for off in self.find_heads(SIG_WAR):
            r = self.parse_block(off, SIG_WAR)
            if r:
                war_block = {'offset': off, 'owner': owner(off), 'fields': r[0]}
        for off in self.find_heads(SIG_DEALS):
            r = self.parse_block(off, SIG_DEALS)
            if r:
                deals_block = {'offset': off, 'owner': owner(off), 'fields': r[0]}

        # ---- 玩家表 ----
        players_out = []
        for pl in players:
            s = pl['slot']
            rec = {'slot': s, 'alive': pl['alive'], 'player_block_offset': pl['offset']}
            if s in bal_by_slot:
                _, f = bal_by_slot[s]
                kind, v, _ = f.get('DiplomacyBalance', (None, None, None))
                rec['influence_balance'] = v / 256.0 if kind == 'fp8' else None
            if s in infl_by_slot:
                off, f = infl_by_slot[s]
                rec['infl_block_offset'] = off
                kind, v, _ = f.get('HasOpenBordersFrom', (None, None, None))
                if kind == 'blob':
                    rec['open_borders_to'] = [i for i, b in enumerate(self._u8_array(v)) if b]
                    rec['open_borders_raw'] = self._u8_array(v)
                kind, v, _ = f.get('OpenBordersEndedTurn', (None, None, None))
                if kind == 'blob':
                    rec['open_borders_ended_turn'] = self._u32_array(v)
                kind, v, _ = f.get('RelationshipLevel', (None, None, None))
                if kind == 'blob':
                    rec['relationship_level'] = [x / 256.0 for x in self._u32_array(v)]
                for fname, keyname in (('Grievances', 'grievances'),
                                       ('Favors', 'favors'),
                                       ('WarWeariness', 'war_weariness'),
                                       ('NumWarsInitiatedAgainstPlayer', 'num_wars_initiated_against')):
                    kind, v, _ = f.get(fname, (None, None, None))
                    if kind == 'blob':
                        rec[keyname] = self._u32_array(v)
                kind, v, _ = f.get('HasNonAggressionPact', (None, None, None))
                if kind == 'blob':
                    rec['non_aggression_pact'] = self._u8_array(v)
                toks = {}
                for fname in ('Tokens', 'AvailableTokens', 'ReservedTokens', 'CommittedTokens',
                              'ExhaustedTokens', 'EscrowTokens', 'NumProjects', 'NumEndeavors',
                              'NumSanctions', 'NumEspionage', 'NumTreaties', 'NumAlliances',
                              'NumSanctionsNoDenounce', 'NumSanctionedLeadersND',
                              'NumActiveEndeavorsStarted', 'NumActiveEndeavorsSupported'):
                    kind, v, _ = f.get(fname, (None, None, None))
                    if kind == 'blob' and len(v) == 4:
                        toks[fname] = U32.unpack(v)[0]          # 对象句柄（值非直读）
                rec['token_handles'] = toks
            players_out.append(rec)

        # ---- 全局战争块 ----
        met_m = war_m = initiator_m = allied_m = friend_m = pact_m = perma_m = joint_m = None
        events_out = []
        war_info = {}
        if war_block:
            f = war_block['fields']
            kind, v, _ = f.get('HasMet', (None, None, None))
            if kind == 'blob':
                met_m = self._matrix(v, 5)
            for fname in ('AtWar', 'WarInitiator', 'JointWarTarget'):
                kind, v, _ = f.get(fname, (None, None, None))
                if kind == 'blob':
                    m = self._matrix(v, 8)
                    if fname == 'AtWar':
                        war_m = m
                    elif fname == 'WarInitiator':
                        initiator_m = m
                    else:
                        joint_m = m
            for fname in ('HasDeclaredFriendship', 'IsAllied', 'IsPermanentlyAllied',
                          'IsInDefensivePact'):
                kind, v, _ = f.get(fname, (None, None, None))
                if kind == 'blob':
                    m = self._matrix(v, 5)
                    if fname == 'HasDeclaredFriendship':
                        friend_m = m
                    elif fname == 'IsAllied':
                        allied_m = m
                    elif fname == 'IsPermanentlyAllied':
                        perma_m = m
                    else:
                        pact_m = m
            kind, v, _ = f.get('TotalDiplomacyEvents', (None, None, None))
            war_info['total_diplomacy_events'] = v if kind == 'scalar' else None
            kind, v, _ = f.get('MaxNumPlayers', (None, None, None))
            war_info['max_num_players'] = v if kind == 'scalar' else None
            for evname in ('ActiveDiplomacyEventsV2', 'ConcludedDiplomacyEvents'):
                kind, v, _ = f.get(evname, (None, None, None))
                if kind != 'blob':
                    continue
                evs = self.split_events(v)
                war_info[evname + '_count'] = len(evs)
                if evname == 'ActiveDiplomacyEventsV2':
                    for e in evs:
                        if len(e) >= 24:
                            a, b3, m1, d, ee, cnt2 = struct.unpack_from('<6I', e)
                            events_out.append({
                                'type_a': a,
                                'head': {'b': b3, 'c': m1, 'd': d, 'e': ee, 'req_count': cnt2},
                                'length': len(e),
                                'raw_hex': e.hex()[:256],
                            })
                else:
                    war_info['concluded_events'] = [
                        {'length': len(e), 'head_hex': e.hex()[:48]} for e in evs]

        # ---- 两两关系表 ----
        real_slots = sorted({p['slot'] for p in players if p['slot'] is not None and p['slot'] != 63})
        ob = {p['slot']: p.get('open_borders_raw') for p in players_out}
        rl = {p['slot']: p.get('relationship_level') for p in players_out}
        pairs_out = []
        tribe_pairs = []
        for a in real_slots:
            for b in real_slots:
                if b <= a:
                    continue
                pair = {'a': a, 'b': b}
                m = met_m.get((a, b)) if met_m else None
                if m:
                    pair['met'] = bool(m[0])
                    pair['met_value'] = U32.unpack_from(m, 1)[0]
                else:
                    pair['met'] = None
                w = war_m.get((a, b)) if war_m else None
                if w:
                    v1, v2 = struct.unpack('<2I', w)
                    # 有非默认条目 ⇒ 存在战争记录（实测两种形态: [hash][2] / [-1][2]，
                    # 确切语义未解）；真实玩家槽 0-29 之间在 E0/E2 全部无条目（=和平 ✓）
                    pair['at_war'] = True
                    pair['war_value'] = ('0x%08x' % v1) if v1 != 0xffffffff else None
                    pair['war_value2'] = v2
                else:
                    pair['at_war'] = False
                ini = initiator_m.get((a, b)) if initiator_m else None
                if ini:
                    pair['war_initiator'] = struct.unpack_from('<I', ini)[0]
                for key, m2 in (('has_declared_friendship', friend_m), ('is_allied', allied_m),
                                ('is_permanently_allied', perma_m), ('in_defensive_pact', pact_m)):
                    e = m2.get((a, b)) if m2 else None
                    if e:
                        pair[key] = bool(e[0])
                # 开放边界: a 块的 HasOpenBordersFrom[b]=1 ⇒ a 可进入 b
                if ob.get(a) is not None and b < len(ob[a]):
                    pair['open_borders_a_into_b'] = bool(ob[a][b])
                if ob.get(b) is not None and a < len(ob[b]):
                    pair['open_borders_b_into_a'] = bool(ob[b][a])
                # 关系分（FP8, 双向对称存储）
                if rl.get(a) is not None and b < len(rl[a]):
                    pair['relationship_level_a'] = rl[a][b]
                if rl.get(b) is not None and a < len(rl[b]):
                    pair['relationship_level_b'] = rl[b][a]
                pairs_out.append(pair)

        # 实体槽位 ≥32 的矩阵条目（疑似独立势力/部落槽，语义未解）→ 原样输出
        if war_m:
            for (i, j), el in sorted(war_m.items()):
                if i >= 32 or j >= 32:
                    v1, v2 = struct.unpack('<2I', el)
                    tribe_pairs.append({'i': i, 'j': j,
                                        'value1': ('0x%08x' % v1) if v1 != 0xffffffff else None,
                                        'value2': v2,
                                        'initiator': (struct.unpack_from('<I', initiator_m[(i, j)])[0]
                                                      if initiator_m and (i, j) in initiator_m else None)})
        # ---- 修正块（13 字段）----
        diplo_mods = {}
        for s, (off, f) in sorted(diplo_by_slot.items()):
            rec = {'offset': off}
            for fname in ('DiplomaticModifiers', 'OneSidedTradeValue', 'BrokenPromises',
                          'KeptPromises', 'NoPromises', 'FirstImpressions'):
                kind, v, _ = f.get(fname, (None, None, None))
                if kind == 'blob':
                    cp = self._count_prefixed(v)
                    rec[fname] = {'count': cp[0], 'values': self._u32_array(cp[1])} if cp else None
            kind, v, _ = f.get('WarmongerScalingMultiplier', (None, None, None))
            if kind == 'fp8':
                rec['warmonger_scaling_multiplier'] = v / 256.0
            diplo_mods[s] = rec

        # ---- 部落块（16 字段）----
        tribe_out = {}
        for s, (off, f) in sorted(tribe_by_slot.items()):
            rec = {'offset': off}
            kind, v, _ = f.get('Suzerain', (None, None, None))
            rec['suzerain'] = v if kind == 'scalar' else None
            kind, v, _ = f.get('OpenBordersCount', (None, None, None))
            if kind == 'blob':
                cp = self._count_prefixed(v)
                rec['open_borders_count'] = {'count': cp[0],
                                             'values': self._u32_array(cp[1])} if cp else None
            kind, v, _ = f.get('TribeRelationships', (None, None, None))
            if kind == 'props_container':
                rec['tribe_relationships'] = 'container(未定界, 见 phase4 笔记)'
            tribe_out[s] = rec

        # ---- 协议块 ----
        deals_out = None
        if deals_block:
            f = deals_block['fields']
            deals_out = {'offset': deals_block['offset'], 'owner': deals_block['owner'],
                         'enacted_deal_id': f.get('EnactedDealID', (None, None, None))[1],
                         'deals': f.get('Deals', (None, None, None))[1]}

        unresolved = []
        for p in players_out:
            if p.get('influence_balance') is None:
                unresolved.append(f"slot{p['slot']}: DiplomacyBalance 未解析")
            if p.get('open_borders_raw') is None:
                unresolved.append(f"slot{p['slot']}: HasOpenBordersFrom 未解析")
        if war_block is None:
            unresolved.append('全局战争/事件块 (dced693c) 未找到')
        if deals_block is None:
            unresolved.append('协议块 (36007b22) 未找到')
        unresolved.append('外交事件 type_a → 动作名映射未标定（A=12=开放边界，经 E2/E0 差分证实）')
        unresolved.append('Token/NumX blob4 = 对象句柄，数值未直读（Token 对象为引用聚合节点，'
                          '对象图反查无 FP8 标量，见 phase4 笔记 §5）')
        unresolved.append('AtWar/HasMet 矩阵 (i,j)→玩家 slot 映射未定证：行主序三角读法下 '
                          'E0/E2 实体 0-29 之间无战争条目（=和平）；但条目集中在行 40-57 且 '
                          'WarInitiator=63−行，存在"实体=63−行号"的反转读法（见 phase4 笔记 §6）')
        unresolved.append('HasMet 元素 [u8 met][u32 X] 的 X 语义未解（E0 X∈1..14、现代档 X=9>t4，'
                          '非首见回合）；FirstMeetIndexes 值 700/563/775/482 语义未解')

        return {
            'source': None,
            'bag_start': self.bag,
            'war_block': war_info,
            'deals_block': deals_out,
            'num_players': len(players),
            'players': players_out,
            'pairs': pairs_out,
            'tribe_war_entries': tribe_pairs,
            'diplomacy_modifier_blocks': diplo_mods,
            'tribe_blocks': tribe_out,
            'events': events_out,
            'unresolved': unresolved,
        }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    body_path, out_path = sys.argv[1], sys.argv[2]
    data = open(body_path, 'rb').read()
    ex = DiplomacyExtractor(data)
    result = ex.extract()
    result['source'] = os.path.abspath(body_path)
    with open(out_path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    n_ob = sum(1 for p in result['players'] if p.get('open_borders_to'))
    wars = sum(1 for pr in result['pairs'] if pr.get('at_war'))
    ob_pairs = sum(1 for pr in result['pairs'] if pr.get('open_borders_a_into_b') or pr.get('open_borders_b_into_a'))
    print(f"玩家={result['num_players']} 事件={len(result['events'])} "
          f"(总{result['war_block'].get('total_diplomacy_events')}) "
          f"开放边界出境对={ob_pairs} 战争对={wars} "
          f"未解={len(result['unresolved'])} -> {out_path}")


if __name__ == '__main__':
    main()
