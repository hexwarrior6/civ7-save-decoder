#!/usr/bin/env python3
"""文明7 名人堂 GAME_SUMMARY 建造编年史提取器 (BatchA)。

CLI: python3 -I tools/chronicle.py <body.bin> <out.json>

逆向结论 (2026-11-12, 证据字节见 docs/notes/batchA-chronicle.md):
  名人堂第 2 块布局:
    [06]['Player']×N 玩家对象表
    [04]['City']×M 城市注册表, 每条:
        [u32 seq][u32 owner] (与下一条共享的 8B 前缀)
        [04 00 00 00]['City'][u32 nameLen][名字]
        [u16 owner][u16 1][u16 idxA][u16 idxB][u32 plot][u64 0]
    [u32 dpCount] + dpCount × DataPoint (建造编年史事件流)
    [u32 dpTotal] + 尾部逐回合聚合数据集 (Gold/Culture/Score/...)
  DataPoint = [u32 keyLen][key][u32 f0][u32 f1][u32 valLen][val][u8 tag=1][i64]
  归属:  f0 = 城市对象 seq, 与注册表条目前缀 [u32 seq][u32 owner] 的 seq 匹配。
    - TurnFounded[f0] i64 = 建城回合 (与 REPLAYDATASET_TOTALCITIESBUILT 的
      (civ, turn, 256) 记录逐一互证, E0/E5.1/E5.2 七城全对上)
    - BuildingsBuiltByType/WondersBuiltByType/DistrictsBuiltByType/
      UnitsTrainedByType/UnitsLostByType[f0][val=类型名] = 该城逐次建造事件
    - Player[f0][val=建造物] = 玩家级行为落在城 #f0 (改良/购买/城市大厅)
    - City[f0] i64 = 建城回合 (本局新建城的注册标记, 如 E5.2 图拉 = 22)
    - Religion[f0] i64 = 该城主流宗教 id
    - LOC_RELIGION_*_NAME[f0][val=城区类型] = 宗教传播到城 #f0 的该城区
    - Founder[f0][f1=f0-1] = 宗教创立标记 (MODERN 6 条, f1 语义未解)
    - LOC_CITY_NAME_X[lo-id][城区类型] = 以城名为键的建造/补录记录
      (E5.x 7 条; f0=每玩家建造物实例 lo-id 假设, 归属键=注册表城名)
  已知怪癖: seq 1..6 (小图) / 1..12 (MODERN) = 开局预置城邦, 有编年史事件
    但无注册表条目 (与 '新时代 t1 只注册部分定居点' 同源)。
"""
import struct, sys, json, os, re
from collections import defaultdict

CITY_KEY = b'\x04\x00\x00\x00City'
PLAYER_KEY = b'\x06\x00\x00\x00Player'
_U32 = struct.Struct('<I')
_U64 = struct.Struct('<Q')

# 事件键 → 每城桶
SECTION_KEYS = {
    'BuildingsBuiltByType': 'buildings',
    'WondersBuiltByType': 'wonders',
    'DistrictsBuiltByType': 'districts',
    'UnitsTrainedByType': 'units_trained',
    'UnitsLostByType': 'units_lost',
    'UnitsKilledByType': 'units_killed',
    'TurnFounded': 'founded',
    'Player': 'player_actions',
    'Religion': 'religion',
    'City': 'city_marker',
}


def find_gs_blocks(data):
    offs = []
    i = 0
    while True:
        i = data.find(b'GAME_SUMMARY', i)
        if i < 0:
            break
        offs.append(i)
        i += 1
    return offs


def locate_block2(data):
    """返回 (player_registry_off, city_registry_off, block_end)。
    block2 = 后跟 City 注册表的 GAME_SUMMARY 块。"""
    for m in find_gs_blocks(data):
        first_city = data.find(CITY_KEY, m, m + 0x2000)
        if first_city < 0:
            continue
        # City 注册表前应有 Player 注册表 (06 00 00 00 Player)
        first_player = data.rfind(PLAYER_KEY, m, first_city)
        if first_player < 0:
            continue
        # 块尾 = 下一个"远离"的 GAME_SUMMARY 标记 (相邻 0x40 内的重复标记不算)
        end = len(data)
        i = m + 12
        while True:
            nxt = data.find(b'GAME_SUMMARY', i)
            if nxt < 0:
                break
            if nxt - m > 0x100:
                end = nxt
                break
            i = nxt + 12
        return first_player, first_city, end
    return None


def parse_player_registry(data, start, end):
    """[u32 6]['Player'][u16 slot][u16 0][11 00 00 00][u16 0][ff ff ff ff]×N"""
    players = []
    pos = start
    while True:
        klen = _U32.unpack_from(data, pos)[0] if pos + 4 <= end else 0
        if klen != 6 or data[pos + 4:pos + 10] != b'Player':
            break
        p = pos + 10
        slot, zero = struct.unpack_from('<2H', data, p); p += 4
        # 值域: 11 00 00 00 / 00 00 / ff ff ff ff 等, 步进到下一个 Player/City
        nxt_p = data.find(PLAYER_KEY, p, end)
        nxt_c = data.find(CITY_KEY, p, end)
        cand = [x for x in (nxt_p, nxt_c) if x > 0]
        if not cand:
            break
        pos = min(cand)
        players.append({'slot': slot})
    return players, pos


def parse_city_registry(data, start):
    """从第一条 [04]['City'] 起逐条解析; 返回 (entries, log_meta_off)。
    每条: PRE[u32 seq][u32 owner] + [04]['City'][len][name][u16×4][u32 plot][u64 0]"""
    entries = []
    pos = start
    while True:
        if pos < 8:
            break
        pre_seq, pre_owner = struct.unpack_from('<2I', data, pos - 8)
        klen = _U32.unpack_from(data, pos)[0]
        if klen != 4 or data[pos + 4:pos + 8] != b'City':
            break
        p = pos + 8
        vlen = _U32.unpack_from(data, p)[0]; p += 4
        name = data[p:p + vlen]; p += vlen
        if p + 16 > len(data):
            break
        owner, one, idx_a, idx_b = struct.unpack_from('<4H', data, p); p += 8
        plot = _U32.unpack_from(data, p)[0]; p += 4
        zero = _U64.unpack_from(data, p)[0]; p += 8
        entries.append({
            'seq': pre_seq, 'pre_owner': pre_owner,
            'name': name.decode('ascii', 'replace'),
            'owner_slot': owner, 'idx_a': idx_a, 'idx_b': idx_b,
            'plot': plot,
        })
        nxt = data.find(CITY_KEY, p, p + 4096)
        if nxt < 0:
            break
        pos = nxt
    # 最后一条之后: [u64 0][u32 dpCount][DataPoint...]
    log_meta = p
    return entries, log_meta


def parse_datapoints(data, start, end, max_records=200000):
    """DataPoint = [klen][key][f0][f1][vlen][val][tag u8][i64 s64]"""
    recs = []
    pos = start
    while pos + 4 <= end and len(recs) < max_records:
        klen = _U32.unpack_from(data, pos)[0]
        if not (2 <= klen <= 64):
            break
        key = data[pos + 4:pos + 4 + klen]
        if not all(33 <= c < 127 for c in key):
            break
        p = pos + 4 + klen
        if p + 12 > end:
            break
        f0, f1 = struct.unpack_from('<2I', data, p); p += 8
        vlen = _U32.unpack_from(data, p)[0]; p += 4
        if vlen > 4096 or p + vlen + 9 > end:
            break
        val = data[p:p + vlen]; p += vlen
        tag = data[p]; p += 1
        if tag not in (0, 1):
            break
        if p + 8 > end:
            break
        i64 = struct.unpack_from('<q', data, p)[0]; p += 8
        if not (-1 << 40 < i64 < 1 << 40):
            break
        recs.append({
            'off': pos, 'key': key.decode('ascii'),
            'f0': f0, 'f1': f1,
            'val': val.decode('ascii', 'replace'),
            'tag': tag, 'i64': i64,
        })
        pos = p
    return recs, pos


def classify_city_state_or_major(owner_slot):
    return 'major' if owner_slot is not None and owner_slot < 6 else 'independent'


def extract(body_path):
    data = open(body_path, 'rb').read()
    loc = locate_block2(data)
    if loc is None:
        raise SystemExit('未找到名人堂第 2 块 (GAME_SUMMARY + City 注册表)')
    player_off, city_off, block_end = loc

    players, reg_end = parse_player_registry(data, player_off, city_off)
    entries, log_meta = parse_city_registry(data, city_off)
    dp_count = _U32.unpack_from(data, log_meta)[0]
    log_start = log_meta + 4

    recs, log_stop = parse_datapoints(data, log_start, len(data))
    # 尾部第二计数 + 逐玩家逐回合聚合序列 (Gold/Culture/...)
    # 尾部记录 = [klen][key][(u32 turn, u32 value)×N] 无 vlen/count, 边界由回合数决定,
    # 与 REPLAYDATASET_* (块1) 同源, 此处只做键直方图扫描。
    total2 = _U32.unpack_from(data, log_stop)[0] if log_stop + 4 <= len(data) else None
    tail_start = log_stop + 4
    tail_region = data[tail_start:block_end]
    tail_keys = {}
    pos = 0
    while pos + 6 < len(tail_region):
        klen = _U32.unpack_from(tail_region, pos)[0]
        if 3 <= klen <= 32:
            key = tail_region[pos + 4:pos + 4 + klen]
            if all(33 <= c < 127 for c in key):
                k = key.decode('ascii')
                tail_keys[k] = tail_keys.get(k, 0) + 1
                pos += 4 + klen
                continue
        pos += 4
    tail_scanned = sum(tail_keys.values())

    seq2city = {e['seq']: e for e in entries}
    name2seq = {e['name']: e['seq'] for e in entries}

    cities = []
    for e in entries:
        x, y = e['plot'] % 74, e['plot'] // 74
        cities.append({
            'seq': e['seq'],
            'name': e['name'],
            'owner_slot': e['owner_slot'],
            'owner_kind': classify_city_state_or_major(e['owner_slot']),
            'registry_idx': {'a': e['idx_a'], 'b': e['idx_b']},
            'plot': e['plot'],
            'location': [x, y],
            'founded_turn': None,
            'buildings': [], 'wonders': [], 'districts': [],
            'improvements': [], 'units_trained': [], 'units_lost': [],
            'units_killed': [],
            'player_actions': [], 'religion_events': [],
            'city_marker_turn': None,
            'aux_namekey_events': [],
        })
    by_seq = {c['seq']: c for c in cities}

    # seq 无注册表条目的城邦 (预置定居点)
    city_states = {}

    def cs_bucket(seq):
        if seq not in city_states:
            city_states[seq] = {
                'seq': seq, 'name': None,
                'note': '预置城邦: 有编年史事件但无注册表条目 (已知怪癖)',
                'buildings': [], 'wonders': [], 'districts': [],
                'improvements': [], 'units_trained': [], 'units_lost': [],
                'units_killed': [], 'player_actions': [],
                'founded_turn': None, 'religion_events': [],
            }
        return city_states[seq]

    BUCKET_KEYS = {'buildings', 'wonders', 'districts', 'improvements',
                   'units_trained', 'units_lost', 'units_killed',
                   'player_actions'}

    founder_records = []
    unmatched = []

    for r in recs:
        key = r['key']
        bucket = SECTION_KEYS.get(key)
        if key == 'Founder':
            founder_records.append({'f0': r['f0'], 'f1': r['f1'],
                                    'note': '宗教创立标记 (假设: f0/f1=宗教对象 id 对 hi/lo)'})
            continue
        if key.startswith('LOC_RELIGION_') and key.endswith('_NAME'):
            ev = {'religion': key, 'thing': r['val'], 'i64': r['i64']}
            tgt = by_seq.get(r['f0'])
            if tgt is None and r['f0'] > 0:
                tgt = cs_bucket(r['f0'])  # 传播到预置城邦
            if tgt is not None:
                tgt['religion_events'].append(ev)
            else:
                unmatched.append(r)  # f0=0: 改宗单位等无城归属
            continue
        if bucket is None and key.startswith('LOC_CITY_NAME_'):
            seq = name2seq.get(key)
            if seq is not None and seq in by_seq:
                by_seq[seq]['aux_namekey_events'].append(
                    {'f0': r['f0'], 'f1': r['f1'], 'val': r['val'], 'i64': r['i64'],
                     'note': '以城名为键; f0=建造物实例 lo-id (假设, 未定证)'})
            else:
                unmatched.append(r)
            continue
        if bucket is None:
            unmatched.append(r)
            continue

        tgt = by_seq.get(r['f0'])
        if tgt is None:
            # 无注册表条目的 seq = 预置城邦/已消失定居点 (已知怪癖)
            tgt = cs_bucket(r['f0'])

        if bucket == 'buildings':
            # BuildingsBuiltByType 值含 BUILDING_* 与 IMPROVEMENT_* 两类, 按前缀分桶
            if r['val'].startswith('IMPROVEMENT_'):
                tgt['improvements'].append({'type': r['val'], 'i64': r['i64']})
            else:
                tgt['buildings'].append({'type': r['val'], 'i64': r['i64']})
        elif bucket in ('wonders', 'districts', 'units_trained', 'units_lost',
                        'units_killed', 'player_actions'):
            tgt[bucket].append({'type': r['val'], 'i64': r['i64']})
        elif bucket == 'founded':
            tgt['founded_turn'] = r['i64']
        elif bucket == 'religion':
            tgt['religion_events'].append({'religion_id': r['i64'], 'i64': r['i64']})
        elif bucket == 'city_marker':
            tgt['city_marker_turn'] = r['i64']
            if tgt['founded_turn'] is None:
                tgt['founded_turn'] = r['i64']

    # 汇总校验信息
    n_attributed = sum(
        len(c[b]) for c in cities for b in BUCKET_KEYS) + sum(
        len(cs[b]) for cs in city_states.values() for b in BUCKET_KEYS)

    return {
        'source': os.path.abspath(body_path),
        'format': 'GAME_SUMMARY block2 建造编年史 (见 docs/notes/batchA-chronicle.md)',
        'players': players,
        'registry_count': len(entries),
        'datapoint_count_declared': dp_count,
        'datapoint_count_parsed': len(recs),
        'tail_series_declared': total2,
        'tail_series_scanned': tail_scanned,
        'tail_keys': dict(tail_keys),
        'tail_note': '尾部 = [u32 记录数][逐条 (键=指标名或城名) + (u32 回合, u32 值) 对序列]; '
                     '与块1 REPLAYDATASET_* 同源的 HOF 图表数据, 精确逐条解析未做',
        'cities': cities,
        'city_states_unregistered': city_states,
        'founder_records': founder_records,
        'unmatched_records': unmatched,
        'unresolved': [
            'Founder[f0][f1=f0-1] 的 f1 语义未解 (MODERN 6 条, 疑为宗教对象 id 对 hi/lo)',
            'BuildingsBuiltByType 等的 i64 疑为建筑所在城区的城内序号 (TurnFounded/City 的 i64=回合已证, 其余未定证)',
            'LOC_CITY_NAME_* 为键的记录: f0=每玩家建造物实例 lo-id 为假设; E5.2 [ROME1][1][DISTRICT_CITY_CENTER] 经建造物实例序号交叉验证对应图拉市中心, 键为何取 ROME1 未解',
            '城邦/预置定居点 (seq<13) 无注册表条目: 名字/归属缺失 (与新时代 t1 只注册部分定居点同源)',
            '注册表 owner 为存档时归属; 建城者需 cross-check cities.py OwnerIDHistory 首条目',
        ],
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    result = extract(sys.argv[1])
    with open(sys.argv[2], 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    n = result['registry_count']
    dp = result['datapoint_count_parsed']
    ok = 'OK' if dp == result['datapoint_count_declared'] else 'MISMATCH'
    print('注册表城市=%d 编年史记录=%d/%d %s 尾部序列=%d/%d -> %s'
          % (n, dp, result['datapoint_count_declared'], ok,
             result['tail_series_scanned'], result['tail_series_declared'],
             sys.argv[2]))


if __name__ == '__main__':
    main()
