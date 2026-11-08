import struct, pickle

data = open('body.bin','rb').read()

DATASETS = [
    'REPLAYDATASET_TOTALPLAYERUNITSDESTROYED',
    'REPLAYDATASET_TOTALWONDERSBUILT',
    'REPLAYDATASET_TOTALCOMBATS',
    'REPLAYDATASET_TOTALCITIESCAPTURED',
    'REPLAYDATASET_TOTALWARSDECLARED',
    'REPLAYDATASET_TOTALGOLD',
    'REPLAYDATASET_CULTURE',
    'REPLAYDATASET_GREATPEOPLEEARNED',
    'REPLAYDATASET_TOTALCITIESDESTROYED_NAME',
    'REPLAYDATASET_TOTALCITIESLOST',
    'REPLAYDATASET_TOTALDISTRICTSBUILT',
    'REPLAYDATASET_TOTALWARSAGAINSTPLAYER',
    'REPLAYDATASET_TOTALRELIGIONSFOUNDED_NAME',
    'REPLAYDATASET_TOTALUNITSDESTROYED',
    'REPLAYDATASET_SCOREPERTURN',
    'REPLAYDATASET_TOTALBUILDINGSBUILT',
    'REPLAYDATASET_TOTALWARSWON_NAME',
    'REPLAYDATASET_SCIENCEPERTURN',
    'REPLAYDATASET_TOTALCITIESBUILT',
    'REPLAYDATASET_TOTALPANTHEONSFOUNDED_NAME',
    'REPLAYDATASET_TOTALRELIGIONSFOUNDED',
    'REPLAYDATASET_TOTALWARSWON',
    'REPLAYDATASET_TOTALPANTHEONSFOUNDED',
]

# order datasets by position
pos = []
for name in set(DATASETS):
    p = data.find(name.encode())
    if p >= 0: pos.append((p, name))
pos.sort()

def parse_dataset(start, end):
    # find alignment: 12-byte (col,row,val) records
    for off in range(start, start+64):
        q = off; cnt = 0; okmax = 0
        while q + 12 <= end:
            c, r, v = struct.unpack_from('<III', data, q)
            if c > 200 or r > 400: break
            q += 12; cnt += 1
        if cnt > 30:
            return off, cnt
    return None, 0

all_data = {}
for i, (p, name) in enumerate(pos):
    end = pos[i+1][0] - 4 if i+1 < len(pos) else len(data)
    # search data start after the loc key (skip name+loc strings)
    loc = data.find(b'LOC_', p)
    search_from = loc if loc >= 0 else p
    off, cnt = parse_dataset(search_from, end)
    if off is None:
        print(f'{name}: no data'); continue
    series = {}  # col -> {turn: val}
    q = off
    while q + 12 <= end:
        c, r, v = struct.unpack_from('<III', data, q)
        if c > 200 or r > 400: break
        series.setdefault(c, {})[r] = v
        q += 12
    all_data[name] = series
    cols = sorted(series.keys())
    print(f'{name}: cols={cols} total_rec={cnt}')

pickle.dump(all_data, open('replay2.pkl','wb'))
