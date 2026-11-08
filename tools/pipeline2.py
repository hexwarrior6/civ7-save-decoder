import sys, struct, re, json, pickle
sys.path.insert(0, '/tmp/civ7_analysis')
from pipeline import extract, parse_header, locend_of

data, header = extract(sys.argv[1])
meta, roster = parse_header(header)

NAMES = sorted(set(m.group().decode() for m in re.finditer(rb'REPLAYDATASET_[A-Z0-9_]+', data)))
pos = sorted((data.find(n.encode()), n) for n in NAMES)

def parse_big(le_, end):
    best_off, best_cnt = None, 0
    for o in range(le_, le_+40):
        q=o; cnt=0
        while q+12 <= end:
            c,t,v = struct.unpack_from('<III', data, q)
            if c>200 or t>400: break
            q+=12; cnt+=1
        if cnt > best_cnt:
            best_off, best_cnt = o, cnt
    if best_off is None or best_cnt < 5:
        return None
    series={}
    q=best_off
    while q+12 <= end:
        c,t,v = struct.unpack_from('<III', data, q)
        if c>200 or t>400: break
        series.setdefault(c,{})[t]=v/256
        q+=12
    return series

def parse_small(le_, end):
    best=[]
    for o in range(le_, le_+40):
        q=o; recs=[]
        while q+12 <= end:
            a,b,c = struct.unpack_from('<III', data, q)
            if a==256 and b<=60 and c<=400: recs.append((b,c)); q+=12
            elif c==256 and a<=60 and b<=400: recs.append((a,b)); q+=12
            else: break
        if len(recs)>len(best): best=recs
    return best

# datasets where values are per-turn increments (sum them) vs snapshots
INC = ['TOTALCOMBATS','TOTALDISTRICTSBUILT','TOTALBUILDINGSBUILT','TOTALUNITSDESTROYED','TOTALPLAYERUNITSDESTROYED']
SNAP = ['TOTALCITIESBUILT','TOTALWONDERSBUILT']

result = {}
for i,(p,name) in enumerate(pos):
    end = pos[i+1][0]-4 if i+1 < len(pos) else len(data)
    le_ = locend_of(data, p)
    core = name.replace('REPLAYDATASET_','')
    series = parse_big(le_, end)
    if series is not None:
        result[name] = {'kind':'matrix', 'series':series}
    else:
        result[name] = {'kind':'events', 'recs':parse_small(le_, end)}

print('META:', json.dumps(meta, ensure_ascii=False))
for r in sorted(roster, key=lambda x: x['slot'] if x['slot'] is not None else 99):
    print(f"  slot={r['slot']} {r.get('LEADER_NAME','-'):26s} {r.get('CIV_NAME','-'):28s} {r.get('ptype','')} alive={r.get('alive','-')}")

PN = {0:'你(阿拔斯)',1:'诺曼',2:'夏威夷',3:'桑海',4:'印加',5:'西班牙✝'}
print('\n=== 产量类 (最新值) ===')
for name in ['REPLAYDATASET_SCIENCEPERTURN','REPLAYDATASET_CULTURE','REPLAYDATASET_TOTALGOLD']:
    s = result[name]['series']
    line = ' | '.join(f"{PN.get(c,c)}={sorted(s[c].items())[-1][1]:.1f}" for c in sorted(s.keys()) if c<=5)
    print(f'{name[14:]}: {line}')

print('\n=== 累计类 (求和) ===')
for name in result:
    core = name.replace('REPLAYDATASET_','')
    if result[name]['kind'] != 'matrix' or core not in INC: continue
    s = result[name]['series']
    line = ' | '.join(f"{PN.get(c,c)}={sum(s[c].values()):.0f}" for c in sorted(s.keys()) if c<=5)
    print(f'{core}: {line}')

print('\n=== 快照类 (t1快照+增量=总数) ===')
for name in result:
    core = name.replace('REPLAYDATASET_','')
    if result[name]['kind'] != 'matrix' or core not in SNAP: continue
    s = result[name]['series']
    for c in sorted(s.keys()):
        if c>5: continue
        ts = sorted(s[c].keys())
        snap = s[c].get(1, 0)
        inc = sum(v for t,v in s[c].items() if t>1)
        print(f'{core} col{c} {PN.get(c,c)}: 快照={snap:.0f} 增量={inc:.0f} 总={snap+inc:.0f}  ({ts[0]}..{ts[-1]})')

print('\n=== 事件类 ===')
for name in result:
    if result[name]['kind'] != 'events' or not result[name]['recs']: continue
    core = name.replace('REPLAYDATASET_','')
    from collections import Counter
    per = Counter(p for p,t in result[name]['recs'])
    print(f'{core}: ' + ' | '.join(f"{PN.get(p,p)}×{n}(t{sorted(t for pp,t in result[name]['recs'] if pp==p)})" for p,n in sorted(per.items())))

pickle.dump({'meta':meta,'roster':roster,'result':result}, open('/tmp/civ7_analysis/new2.pkl','wb'))
