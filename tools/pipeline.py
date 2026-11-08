"""Civ7 存档通用解析流水线: extract -> roster -> replay datasets -> JSON"""
import sys, struct, re, zlib, json, pickle
sys.path.insert(0, '/tmp/civ7_analysis')
from civ7parse import parse_raw

def le(b): return int.from_bytes(b, 'little')

MARK = {
 le(b'\x9d\x2c\xe6\xbd'):'GAME_TURN', le(b'\x84\x84\xc6\xd0'):'GAME_AGE',
 le(b'\x0f\xfb\x8c\xc1'):'LEADER_NAME', le(b'\x76\x97\x40\xde'):'CIV_NAME',
 le(b'\x7a\x9c\xa0\x19'):'CIV_LEVEL', le(b'\xd4\x5f\x83\x28'):'PLAYER_TYPE',
 le(b'\xde\xf6\x2d\x9b'):'TEAM_ID', le(b'\x0e\xed\x6e\x29'):'ALIVE_FLAGS',
 le(b'\x99\xb0\xd9\x05'):'GAME_SPEED', le(b'\x40\x5c\x83\x0b'):'MAP_SIZE',
 le(b'\xfe\x5a\x61\xe8'):'GAME_DATE', le(b'\xd8\x40\xe5\xf4'):'GAME_GUID',
}
SLOTS = [le(bytes.fromhex(h)) for h in
 'b861f0f4 2e51f783 9400fe1a 0230f96d a1a59df3 37959a84 8dc4931d 1bf4946a 8ae92bfa 1cd92c8d 32ca8cfa a4fa8b8d'.split()]

def extract(save_path, workdir='/tmp/civ7_analysis'):
    buf = open(save_path, 'rb').read()
    MARKER = bytes([0,0,1,0,0x78,0x9c])
    start = buf.find(MARKER)
    pos = start; chunks = []
    while pos + 4 <= len(buf):
        size = struct.unpack_from('<I', buf, pos)[0]
        if size <= 1:
            pos += 4; break
        chunks.append(buf[pos+4:pos+4+size]); pos += 4 + size
    d = zlib.decompressobj()
    out = bytearray()
    for i in range(0, len(b''.join(chunks)), 1<<20):
        pass
    comp = b''.join(chunks)
    for i in range(0, len(comp), 1<<20):
        out += d.decompress(comp[i:i+(1<<20)])
    out += d.flush(zlib.Z_SYNC_FLUSH)
    open(f'{workdir}/body.bin','wb').write(bytes(out))
    open(f'{workdir}/header.dat','wb').write(buf[:start])
    return bytes(out), buf[:start]

def parse_header(header_bytes):
    raw = parse_raw(header_bytes)
    meta = {}
    for c in raw['g1']:
        n = MARK.get(c.marker)
        if n and n in ('GAME_TURN','GAME_DATE','GAME_GUID') and isinstance(c.value,(str,int)):
            meta[n] = c.value
        elif n=='GAME_AGE' and isinstance(c.value,str):
            meta['AGE'] = c.value
    roster = []
    for c in raw['g3']:
        if c.type != 29: continue
        d = {}
        for sub in c.children:
            n = MARK.get(sub.marker)
            if n in ('LEADER_NAME','CIV_NAME','CIV_LEVEL') and isinstance(sub.value,str):
                d[n] = sub.value
            elif n=='PLAYER_TYPE': d['ptype'] = {3:'HUMAN',1:'AI'}.get(sub.value, sub.value)
            elif n=='ALIVE_FLAGS' and len(sub.value)>=12:
                d['alive'] = struct.unpack_from('<I', sub.value, 8)[0]
        d['slot'] = SLOTS.index(c.marker) if c.marker in SLOTS else None
        if d.get('CIV_LEVEL') == 'CIVILIZATION_LEVEL_FULL_CIV':
            roster.append(d)
    return meta, roster

def locend_of(data, p):
    loc = data.find(b'LOC_', p)
    return data.find(b'\x00', loc)

def parse_datasets(data):
    NAMES = sorted(set(m.group().decode() for m in re.finditer(rb'REPLAYDATASET_[A-Z0-9_]+', data)))
    pos = sorted((data.find(n.encode()), n) for n in NAMES)
    big, small = {}, {}
    for i,(p,name) in enumerate(pos):
        end = pos[i+1][0]-4 if i+1 < len(pos) else len(data)
        le_ = locend_of(data, p)
        # big format
        best_big = None
        for o in range(le_, le_+40):
            q=o; cnt=0; rows=set()
            while q+12 <= end:
                c,t,v = struct.unpack_from('<III', data, q)
                if c>200 or t>400: break
                rows.add(c); q+=12; cnt+=1
            if cnt > 100:
                best_big = o; break
        if best_big is not None:
            q=best_big; series={}
            while q+12 <= end:
                c,t,v = struct.unpack_from('<III', data, q)
                if c>200 or t>400: break
                series.setdefault(c,{})[t]=v/256
                q+=12
            big[name]=series
            continue
        best = []
        for o in range(le_, le_+40):
            q=o; recs=[]
            while q+12 <= end:
                a,b,c = struct.unpack_from('<III', data, q)
                if a==256 and b<=60 and c<=400: recs.append((b,c)); q+=12
                elif c==256 and a<=60 and b<=400: recs.append((a,b)); q+=12
                else: break
            if len(recs)>len(best): best=recs
        small[name]=best
    return big, small

if __name__ == '__main__':
    save = sys.argv[1]
    data, header = extract(save)
    meta, roster = parse_header(header)
    big, small = parse_datasets(data)
    print('META:', json.dumps(meta, ensure_ascii=False))
    print('\nROSTER (full civs):')
    for r in sorted(roster, key=lambda x: (x['slot'] is None, x['slot'])):
        print(f"  slot={r['slot']} leader={r.get('LEADER_NAME','-'):28s} civ={r.get('CIV_NAME','-'):30s} type={r.get('ptype','-'):6s} alive={r.get('alive','-')}")
    print('\nBIG datasets:')
    for name, series in big.items():
        cols = sorted(series.keys())
        lastvals = {c: series[c][sorted(series[c].keys())[-1]] for c in cols}
        print(f'  {name}: cols={cols}')
        for c in cols: print(f'    col{c:2d}: final={lastvals[c]:.1f}')
    print('\nSMALL datasets:')
    for name, recs in small.items():
        if recs: print(f'  {name}: {recs}')
    pickle.dump({'meta':meta,'roster':roster,'big':big,'small':small}, open('/tmp/civ7_analysis/new.pkl','wb'))
