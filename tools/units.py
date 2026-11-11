#!/usr/bin/env python3
"""文明7 单位提取器 (Phase 3) — 从 body.bin 提取全部单位。

CLI: python3 -I tools/units.py <body.bin> <out.json>

复用 propertybag.py 的 CRC32/字典与 save-format.md §6 的块语法（不重写格式逻辑）。
每个单位输出: id/类型(loc key 反查)/归属 slot/位置(x,y+plot)/HP(=100-Damage)/
剩余移动力(FP8)/朝向/已moved/经验/等级(尽力)。

单位组语法（E0/E1/E5.1/E5.2 四档验证，见 docs/notes/phase3-units.md）:
  每个玩家一段: 玩家实例块(K=00000003,56字段,ID=slot) → ... → Units块(K=crc"Units",
  25字段) → Units容器子流 = N × 单位组:
    [组前缀 32B: 序号/FormationID 等 8×u32] + 实例块(K=ffffffff,47字段) +
    组件块 a0404aaa/8be272e4/00000002(6f)/00000003(81f)/e1b1aae9 +
    战斗块(K=78de489d,10字段,Damage) + 移动块(K=ca643c19,6字段,MovesRemaining FP8) +
    宗教块(K=2eec5d17,6字段) + 经验块(K=00000006,18字段,Experience) +
    奖励块×2 → 下一组。
  Units 块其余字段里有 Formations 容器 = 每单位 1 条 14 字段命令记录
  (Location/MovesRemaining/…/HasMoved/LastPath, 末字段含 FormationID)。

关键实现点:
  - 实例/子块按 "块头签名 + schema 首条目 + 值区严格对位(以 FXSBLKED 块终止符收尾)" 定位，
    不依赖 blockwalk 的容器解析（其 0x402 容器形会吞子块）。
  - 子块首字段 Properties (0x402 容器形) = [len=1][条目数 u8][pad3][属性条目×N][FXSBLKED]，
    跳过到终止符后按 schema 读剩余字段。
  - 单位类型 Type = CRC32 名称哈希: 用 DB 定义区(属性包起点之前) grep 到的 UNIT_* 名单
    (+ UNIT_X_NAME 剥掉 _NAME 的推断名) 建反向字典。
  - 归属 = 最近前置玩家实例块的 ID 字段（E0: 31 玩家 ID 0..30，其中 24-29 已死亡无单位）。
"""
import sys, os, json, struct, re
import bisect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propertybag import FXS, load_dictionary, crc32_name

FXSBLKED = FXS
_U32 = struct.Struct('<I')

# 块签名: (key, count, 首条目hash)。块头两种形态: form5 [K][-1][1][1][cnt], form6 [K][1][-1][1][1][cnt]
SIG_INSTANCE = (0xffffffff, 47, 0xd31307e8)    # Type
SIG_PLAYER   = (0x00000003, 56, 0x3761cde8)    # Properties
SIG_COMBAT   = (0x78de489d, 10, 0x3761cde8)
SIG_MOVE     = (0xca643c19, 6, 0x3761cde8)
SIG_EXP      = (0x00000006, 18, 0x3761cde8)
SIG_RECORD   = (0xffffffff, 14, 0x58171462)    # Location(命令/Formations 记录)

SCALAR_SIZE = {1: 1, 2: 1, 3: 2, 4: 1, 5: 1, 6: 2, 7: 2, 8: 4, 9: 4,
               10: 8, 11: 8, 12: 4, 13: 8, 32: 16}
MAP_W = 74   # plot = y*W+x，本局地图宽 74（save-format.md §3.4；换地图需重标定）


class ParseError(Exception):
    pass


class UnitExtractor:
    def __init__(self, data):
        self.data = data
        self.n = len(data)
        self.dic = load_dictionary()
        self.bag = data.find(FXSBLKED)
        if self.bag < 0:
            raise ParseError('未找到 FXSBLKED 属性包起点')
        # 单位类型反向字典: DB 定义区(以及全文) grep UNIT_* 名
        names = set()
        for m in re.finditer(rb'UNIT_[A-Z0-9_]{2,60}', data):
            names.add(m.group(0).decode('ascii'))
        self.game_data_names = self._load_game_data_names()
        names |= self.game_data_names
        inferred = set()
        for n in names:
            if n.endswith('_NAME'):
                inferred.add(n[:-len('_NAME')])
        self.unit_rev = {}
        for n in names | inferred:
            self.unit_rev[crc32_name(n)] = n
        self.unit_names_direct = {crc32_name(n): n for n in names}

    @staticmethod
    def _load_game_data_names():
        """尽力补充: 从游戏本体 data XML/sql 里 grep UNIT_* 类型名（存档 DB 快照不含的
        单位——如城邦 UNIT_SLINGER——可由此反查）。游戏不在标准路径则返回空集。"""
        import glob
        names = set()
        for root in ('/Applications/CivilizationVII.app/Contents/Resources/Base/modules',
                     '/Applications/CivilizationVII.app/Contents/Resources/DLC'):
            for path in glob.glob(root + '/**/*.xml', recursive=True) + \
                    glob.glob(root + '/**/*.sql', recursive=True):
                try:
                    text = open(path, encoding='utf-8', errors='ignore').read()
                except OSError:
                    continue
                for m in re.finditer(r'\bUNIT_[A-Z0-9_]{2,60}\b', text):
                    names.add(m.group(0))
        return names

    # ---------- 底层 ----------
    def name(self, h):
        return self.dic.get(h) or f'hash_{h:08x}'

    def _head_at(self, pos, sig):
        """pos 处是否为指定签名的块头。返回 (entries_end, values_start) 或 None。"""
        key, cnt, ent0 = sig
        d = self.data
        if pos + 24 > self.n:
            return None
        if _U32.unpack_from(d, pos)[0] != key:
            return None
        w1 = _U32.unpack_from(d, pos + 4)[0]
        if w1 == 1 and _U32.unpack_from(d, pos + 8)[0] == 0xffffffff \
                and _U32.unpack_from(d, pos + 12)[0] == 1 and _U32.unpack_from(d, pos + 16)[0] == 1 \
                and _U32.unpack_from(d, pos + 20)[0] == cnt:
            base = pos + 24
        elif w1 == 0xffffffff and _U32.unpack_from(d, pos + 8)[0] == 1 \
                and _U32.unpack_from(d, pos + 12)[0] == 1 and _U32.unpack_from(d, pos + 16)[0] == cnt:
            base = pos + 20
        else:
            return None
        if base + 8 * cnt > self.n:
            return None
        if _U32.unpack_from(d, base)[0] != ent0:
            return None
        return base, base + 8 * cnt

    def find_heads(self, sig):
        """全文搜索指定签名的块头，按 offset 排序。"""
        key, cnt, ent0 = sig
        offs = set()
        for form in (struct.pack('<IIIII', key, 0xffffffff, 1, 1, cnt),
                     struct.pack('<IIIIII', key, 1, 0xffffffff, 1, 1, cnt)):
            for m in re.finditer(re.escape(form), self.data):
                r = self._head_at(m.start(), sig)
                if r:
                    offs.add(m.start())
        return sorted(offs)

    def _read_value(self, pos, t):
        """按 VariantValueType 读一个值。返回 (kind, value, new_pos)。失败抛 ParseError。"""
        d = self.data
        m = t & 0xffff
        if m == 0x402:                                   # 字符串（必须带终止符）
            if pos + 4 > self.n:
                raise ParseError('eof')
            ln = _U32.unpack_from(d, pos)[0]
            end = pos + 4 + ln
            padded = end + ((-ln) % 4)
            if padded + 8 > self.n or d[padded:padded + 8] != FXSBLKED:
                raise ParseError('bad string terminator')
            return 'str', d[end:padded], padded + 8
        if m in (0x400, 0x403):                          # 尺寸块
            if pos + 4 > self.n:
                raise ParseError('eof')
            sz = _U32.unpack_from(d, pos)[0]
            if sz > self.n - pos - 4:
                raise ParseError('bad blob size')
            raw = d[pos + 4:pos + 4 + sz]
            if sz == 4:
                return 'blob4', _U32.unpack(raw)[0], pos + 4 + sz
            if sz == 8:
                return 'blob8', struct.unpack('<2i', raw), pos + 4 + sz
            return 'blob', raw, pos + 4 + sz
        if m == 0x407:                                   # FixedPoint<8>
            if pos + 4 > self.n:
                raise ParseError('eof')
            return 'fp8', _U32.unpack_from(d, pos)[0] / 256.0, pos + 4
        sz = SCALAR_SIZE.get(m)
        if sz is None or pos + sz > self.n:
            raise ParseError('bad scalar type 0x%x' % t)
        raw = d[pos:pos + sz]
        if m == 8:
            v = struct.unpack('<i', raw)[0]
        elif m == 9:
            v = _U32.unpack(raw)[0]
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

    def _skip_props(self, vpos):
        """跳过子块首字段 Properties (0x402 容器形): [len=1][条目数 u8][pad3][条目区][FXSBLKED]。
        返回 (content_start, content_end=终止符后)。"""
        d = self.data
        if vpos + 4 > self.n:
            return None, None
        ln = _U32.unpack_from(d, vpos)[0]
        content = vpos + 4 + ln + ((-ln) % 4)
        t = d.find(FXSBLKED, content, content + 65536)
        if t < 0:
            return None, None
        return content, t + 8

    def parse_block(self, pos, sig, skip_props=True, require_term=True):
        """解析指定签名的块。返回 (fields dict, values_end)。
        fields: {字段名: (kind, value)}；require_term=False 时值区读完后不要求 FXSBLKED
        （用于命令记录——其尾部可有未入 schema 的附加字节）。"""
        r = self._head_at(pos, sig)
        if r is None:
            return None, None
        base, vend = r
        cnt = sig[1]
        entries = []
        for i in range(cnt):
            entries.append(struct.unpack_from('<II', self.data, base + 8 * i))
        p = vend
        fields = {}
        for i, (h, t) in enumerate(entries):
            nm = self.name(h)
            if skip_props and i == 0 and (t & 0xffff) == 0x402:
                c, ce = self._skip_props(p)
                if ce is None:
                    return None, None
                fields[nm] = ('props_container', p, ce)
                p = ce
                continue
            try:
                kind, v, p2 = self._read_value(p, t)
            except ParseError:
                return None, None
            fields[nm] = (kind, v)
            p = p2
        if require_term:
            if p + 8 > self.n or self.data[p:p + 8] != FXSBLKED:
                return None, None
        return fields, p

    # ---------- 顶层提取 ----------
    def extract(self):
        data = self.data
        # 玩家实例（ID/IsAlive）——归属锚点
        player_offs = self.find_heads(SIG_PLAYER)
        players = []
        for pp in player_offs:
            base, vend = self._head_at(pp, SIG_PLAYER)
            vp = vend
            props_c, props_e = self._skip_props(vp)
            if props_e is None:
                players.append({'offset': pp, 'slot': None})
                continue
            p = props_e
            # ID:Int, IsAlive:Bool, WasEverAlive:Bool, IsTurnActive:Bool, Civilization:Int
            try:
                _, slot, p = self._read_value(p, 8)
                _, alive, p = self._read_value(p, 1)
                _, ever, p = self._read_value(p, 1)
                _, turnactive, p = self._read_value(p, 1)
                _, civh, p = self._read_value(p, 8)
            except ParseError:
                slot = alive = None
                civh = None
            players.append({'offset': pp, 'slot': slot, 'alive': alive,
                            'was_ever_alive': ever, 'civ_handle': civh})
        pslots = [pl['offset'] for pl in players]

        def owner_slot(off):
            i = bisect.bisect_right(pslots, off) - 1
            if i < 0:
                return None, None
            return i, players[i]

        # 单位实例
        inst_offs = self.find_heads(SIG_INSTANCE)
        units = []
        for k, ip in enumerate(inst_offs):
            nxt = inst_offs[k + 1] if k + 1 < len(inst_offs) else self.n
            base, vend = self._head_at(ip, SIG_INSTANCE)
            entries = [struct.unpack_from('<II', self.data, base + 8 * i) for i in range(47)]
            p = vend
            vals = {}
            components_ok = True
            for h, t in entries:
                nm = self.name(h)
                if (t & 0xffff) == 0x402:                 # Components（末字段）: 容器形，跳到终止符
                    c, ce = self._skip_props(p)
                    if ce is None:
                        components_ok = False
                        break
                    p = ce
                    continue
                try:
                    kind, v, p2 = self._read_value(p, t)
                except ParseError:
                    components_ok = False
                    break
                vals[nm] = (kind, v, p)
                p = p2
            if not components_ok:
                units.append({'offset': ip, 'parse_error': 'instance fields unreadable'})
                continue
            inst_end = p

            slot, pl = owner_slot(ip)
            u = self._assemble(ip, vals, inst_end, nxt, slot, pl)

            # 同组子块: 在 (inst_end, 下一实例) 窗口内找第一个通过校验的战斗/移动/经验块
            for sig, key in ((SIG_COMBAT, 'combat'), (SIG_MOVE, 'move'), (SIG_EXP, 'exp')):
                blk = self._first_subblock(sig, inst_end, nxt)
                if blk:
                    u[key] = blk
            units.append(u)

        # 命令/Formations 记录（14 字段）→ has_moved / 镜像移动力
        rec_offs = self.find_heads(SIG_RECORD)
        records = []
        for rp in rec_offs:
            f, end = self.parse_block(rp, SIG_RECORD, skip_props=False, require_term=False)
            if f is None:
                continue
            records.append({'offset': rp, 'end': end, 'fields': f})

        self._match_records(units, records, pslots)
        return self._finalize(units, records, players)

    def _first_subblock(self, sig, lo, hi):
        """窗口内第一个通过严格校验的子块。"""
        pos = lo
        d = self.data
        pat5 = re.escape(struct.pack('<IIIII', sig[0], 0xffffffff, 1, 1, sig[1]))
        pat6 = re.escape(struct.pack('<IIIIII', sig[0], 1, 0xffffffff, 1, 1, sig[1]))
        cands = []
        for pat in (pat5, pat6):
            for m in re.finditer(pat, d):
                if m.start() <= lo or m.start() >= hi:
                    continue
                cands.append(m.start())
        for cp in sorted(set(cands)):
            f, end = self.parse_block(cp, sig, skip_props=True, require_term=True)
            if f is not None:
                return {'offset': cp, 'end': end + 8,
                        'fields': {k: v for k, v in f.items()
                                   if not (isinstance(v, tuple) and v and v[0] == 'props_container')}}
        return None

    def _assemble(self, ip, vals, inst_end, nxt, slot, pl):
        def gv(nm):
            v = vals.get(nm)
            return v[1] if v else None

        typ = gv('Type')
        typ_u32 = typ & 0xffffffff if typ is not None else None
        tname = self.unit_rev.get(typ_u32)
        loc = gv('Location')
        plot = loc[1] * MAP_W + loc[0] if loc else None
        return {
            'offset': ip,
            'instance_end': inst_end,
            'owner_slot': slot,
            'owner_alive': pl.get('alive') if pl else None,
            'type_hash': ('0x%08x' % typ_u32) if typ_u32 is not None else None,
            'type': tname,                       # None = 反查未命中
            'type_source': ('db-direct' if tname and self.unit_names_direct.get(typ_u32) == tname
                            else ('loc-inferred' if tname else None)),
            'location': list(loc) if loc else None,
            'plot': plot,
            'facing': gv('FacingDirection'),
            'formation_id': gv('FormationID'),
            'domain': gv('Domain'),
            'embarked': gv('Embarked'),
            'delayed_death': gv('DelayedDeath'),
            'build_charges': gv('BuildCharges'),
            'kill_count': gv('KillCount'),
            'ai_type': gv('AIType'),
            'origin_city_id': gv('OriginCityID'),
            'damage': None, 'hp': None,
            'moves_remaining': None,
            'has_moved': None,
            'experience': None, 'level': None, 'can_promote': None,
        }

    def _match_records(self, units, records, pslots):
        """命令记录 → 单位: 先同 slot 区间内按 FormationID 精确匹配，再按 Location。"""
        for rp in records:
            f = rp['fields']
            loc = f.get('Location', (None, None))[1]
            if loc is None:
                continue
            rec_slot = bisect.bisect_right(pslots, rp['offset']) - 1
            rp['owner_slot'] = rec_slot if rec_slot >= 0 else None
        for u in units:
            if u.get('parse_error') or u['owner_slot'] is None:
                continue
            cands = [r for r in records if r.get('owner_slot') == u['owner_slot']]
            hit = None
            fid = u.get('formation_id')
            if fid is not None:
                for r in cands:
                    last = r['fields'].get('hash_40f0e20c') or list(r['fields'].values())[-1]
                    if last and last[0] == 'blob' and len(last[1]) == 8 \
                            and struct.unpack_from('<I', last[1], 4)[0] == (fid & 0xffffffff):
                        hit = r
                        break
            if hit is None and u['location'] is not None:
                for r in cands:
                    rl = r['fields'].get('Location', (None, None))[1]
                    if rl == tuple(u['location']):
                        hit = r
                        break
            if hit is None:
                continue
            u['has_moved'] = bool(hit['fields'].get('HasMoved', (None, 0))[1])
            mv = hit['fields'].get('MovesRemaining')
            u['moves_mirror'] = mv[1] if mv else None
            u['record_offset'] = hit['offset']

    def _finalize(self, units, records, players):
        out_units = []
        for u in units:
            if u.get('parse_error'):
                out_units.append(u)
                continue
            cb = u.get('combat')
            if cb:
                dmg = cb['fields'].get('Damage')
                u['damage'] = dmg[1] if dmg else None
                if u['damage'] is not None:
                    u['hp'] = 100 - u['damage']
            mv = u.get('move')
            if mv:
                mrv = mv['fields'].get('MovesRemaining')
                u['moves_remaining'] = mrv[1] if mrv else None
            ex = u.get('exp')
            if ex:
                xp = ex['fields'].get('Experience')
                u['experience'] = xp[1] if xp else None
                cp = ex['fields'].get('CanPromote')
                u['can_promote'] = cp[1] if cp else None
                lv = ex['fields'].get('Level')
                if lv and lv[0] == 'blob4':
                    u['level_handle'] = lv[1]
                    u['level'] = self._resolve_level(lv[1])
            out_units.append(u)
        return {
            'source': None,  # main() 填
            'bag_start': self.bag,
            'map_width': MAP_W,
            'num_players': len(players),
            'players': [{'slot': pl['slot'], 'offset': pl['offset'], 'alive': pl.get('alive'),
                         'civ_handle': ('0x%08x' % pl['civ_handle']) if pl.get('civ_handle') else None}
                        for pl in players if pl.get('slot') is not None],
            'num_units': sum(1 for u in out_units if not u.get('parse_error')),
            'num_command_records': len(records),
            'unresolved': self._unresolved(out_units),
            'units': out_units,
        }

    def _resolve_level(self, handle):
        """经验块 Level=blob4 句柄 → 对象图节点反查（复用 phase2 节点形状: 标量 FP8 / 零值）。
        尽力而为: 反查不到返回 None。"""
        if handle in (0, 0xffffffff):
            return None
        d = self.data
        pat = _U32.pack(handle)
        i = d.find(pat, 0, self.bag)
        while i >= 0:
            if i + 21 <= self.bag and d[i + 8] == 3:
                if _U32.unpack_from(d, i + 17)[0] == handle:
                    v = _U32.unpack_from(d, i + 13)[0]
                    if v < (1 << 24):
                        return v / 256.0
                if _U32.unpack_from(d, i + 13)[0] == handle:
                    return 0.0
            i = d.find(pat, i + 1, self.bag)
        return None

    @staticmethod
    def _unresolved(units):
        bad = [u for u in units if u.get('parse_error')]
        no_type = [u for u in units if not u.get('parse_error') and u.get('type') is None]
        no_owner = [u for u in units if not u.get('parse_error') and u.get('owner_slot') is None]
        no_move = [u for u in units if not u.get('parse_error') and u.get('moves_remaining') is None]
        no_combat = [u for u in units if not u.get('parse_error') and u.get('damage') is None]
        no_rec = [u for u in units if not u.get('parse_error') and u.get('has_moved') is None]
        return {
            'units_with_parse_error': len(bad),
            'type_unresolved': len(no_type),
            'owner_unresolved': len(no_owner),
            'moves_unresolved': len(no_move),
            'combat_unresolved': len(no_combat),
            'has_moved_unresolved': len(no_rec),
        }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    body_path, out_path = sys.argv[1], sys.argv[2]
    data = open(body_path, 'rb').read()
    ex = UnitExtractor(data)
    result = ex.extract()
    result['source'] = os.path.abspath(body_path)
    with open(out_path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    st = result['unresolved']
    print(f"单位={result['num_units']} 玩家={result['num_players']} "
          f"命令记录={result['num_command_records']} | "
          f"类型未反查={st['type_unresolved']} 归属未定={st['owner_unresolved']} "
          f"移动未解={st['moves_unresolved']} 战斗未解={st['combat_unresolved']} "
          f"has_moved未匹配={st['has_moved_unresolved']} 解析失败={st['units_with_parse_error']}"
          f" -> {out_path}")


if __name__ == '__main__':
    main()
