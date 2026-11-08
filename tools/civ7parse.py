import struct

CHUNK_TYPES = {1:'U1',2:'UTF8',3:'UTF16',8:'NUM32',9:'U9',10:'U10',11:'U11',12:'U12',17:'U17',29:'ARR',30:'NESTED',32:'U32'}

PLAYER_SLOT_MARKERS = [
    0xb861f0f4,0x2e51f783,0x9400fe1a,0x0230f96d,0xa1a59df3,0x37959a84,
    0x8dc4931d,0x1bf4946a,0x8ae92bfa,0x1cd92c8d,0x32ca8cfa,0xa4fa8b8d]

MARKERS = {
    0x9d2ce6bd:'GAME_TURN', 0x8484c6d0:'GAME_AGE', 0x0ffb8cc1:'LEADER_NAME',
    0x769740de:'CIV_NAME', 0x7a9ca019:'CIV_LEVEL', 0xd45f8328:'PLAYER_TYPE',
    0xdef62d9b:'TEAM_ID', 0x0eed6e29:'ALIVE_FLAGS', 0x99b0d905:'GAME_SPEED',
    0x405c830b:'MAP_SIZE', 0x5cae2784:'ENABLED_MODS', 0x76612fe5:'MOD_ID',
    0x98260bea:'MOD_DISPLAY_NAME', 0x8cce874d:'MOD_ENABLED',
    0xd840e5f4:'GAME_GUID', 0xfe5a61e8:'GAME_DATE'}

class Chunk:
    __slots__=('offset','marker','type','value','children','end')
    def __init__(self,offset,marker,type_,value,children=None):
        self.offset=offset; self.marker=marker; self.type=type_
        self.value=value; self.children=children

def parse_chunk(data, offset, has_marker=True):
    if has_marker:
        marker = struct.unpack_from('<I', data, offset)[0]
        type_  = struct.unpack_from('<I', data, offset+4)[0]
        dstart = offset + 12
    else:
        marker = None
        type_  = struct.unpack_from('<I', data, offset)[0]
        dstart = offset + 8
    if type_ in (1,12):
        end = dstart + 12; val = data[dstart:dstart+12]
    elif type_ == 8:
        end = dstart + 12; val = struct.unpack_from('<I', data, dstart+8)[0]
    elif type_ == 9:
        ln = struct.unpack_from('<H', data, dstart)[0]
        end = dstart + 8 + ln*4; val = data[dstart+8:end]
    elif type_ in (10,11,17):
        ln = struct.unpack_from('<H', data, dstart)[0]
        end = dstart + 8 + ln*8; val = data[dstart+4:end]
    elif type_ == 2:
        ln = struct.unpack_from('<H', data, dstart)[0]
        end = dstart + 8 + ln
        val = data[dstart+8:end-1].decode('utf-8','replace')
    elif type_ == 3:
        ln = struct.unpack_from('<H', data, dstart)[0]
        end = dstart + 8 + ln*2
        val = data[dstart+8:end-2].decode('utf-16-le','replace')
    elif type_ == 29:
        cnt = struct.unpack_from('<I', data, dstart+8)[0]
        kids=[]; off=dstart+12
        for i in range(cnt):
            c=parse_chunk(data,off); kids.append(c); off=c.end
        end=off; val=None
        return Chunk(offset,marker,type_,val,kids) if False else _mk(offset,marker,type_,None,kids,end)
    elif type_ == 30:
        cnt = struct.unpack_from('<I', data, dstart+8)[0]
        items=[]; off=dstart+12
        for i in range(cnt):
            c=parse_chunk(data,off,has_marker=False)
            items.append(c.children if c.type==29 else [c])
            off=c.end
        end=off; val=None
        return _mk(offset,marker,type_,None,items,end)
    elif type_ == 32:
        ln = struct.unpack_from('<I', data, dstart+4)[0]
        end = dstart + 8 + ln; val = data[dstart+8:end]
    else:
        raise Exception(f'unknown chunk type {type_} at {offset}')
    return _mk(offset,marker,type_,val,None,end)

def _mk(offset,marker,type_,val,kids,end):
    c=Chunk.__new__(Chunk)
    c.offset=offset; c.marker=marker; c.type=type_; c.value=val; c.children=kids
    c.end=end
    return c

def read_n_chunks(data, offset, n):
    out=[]; off=offset
    for i in range(n):
        c=parse_chunk(data,off); out.append(c); off=c.end
    return out

def parse_raw(data):
    g1 = read_n_chunks(data, 12, struct.unpack_from('<I',data,8)[0])
    off = g1[-1].end
    g2 = read_n_chunks(data, off+12, struct.unpack_from('<I',data,off+8)[0])
    off = g2[-1].end
    g3 = read_n_chunks(data, off+8, struct.unpack_from('<I',data,off+4)[0])
    off = g3[-1].end
    # var separator
    count = struct.unpack_from('<I',data,off+4)[0]
    inter=[]; o2=off+8
    for i in range(count):
        c=parse_chunk(data,o2); inter.append(c); o2=c.end
    group_len = struct.unpack_from('<I',data,o2+8)[0]
    g4 = read_n_chunks(data,o2+12,group_len)
    off = g4[-1].end
    # group5 best effort
    g5=[]
    try:
        for p in range(off, off+64, 4):
            if p+8>len(data): break
            mm = struct.unpack_from('<I',data,p)[0]
            tt = struct.unpack_from('<I',data,p+4)[0]
            if mm>=256 and 0<tt<=32:
                glen = struct.unpack_from('<I',data,p-4)[0]
                g5 = read_n_chunks(data,p,glen)
                break
    except Exception:
        pass
    return {'g1':g1,'g2':g2,'g3':g3,'interstitial':inter,'g4':g4,'g5':g5}
