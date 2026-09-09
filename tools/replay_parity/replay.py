"""Strict Spring demo packet reader; originals are never modified."""
import gzip
import struct
from pathlib import Path

class Demo:
    def __init__(self, path):
        self.path = Path(path)
        self.data = gzip.decompress(self.path.read_bytes())
        if not self.data.startswith(b'spring demofile'):
            raise ValueError('not a Spring demo')
        self.header_size = struct.unpack_from('<I', self.data, 20)[0]
        self.script_size, self.stream_size = struct.unpack_from('<II', self.data, 304)
        self.script = self.data[self.header_size:self.header_size+self.script_size].decode()
        self.packets = []
        pos = self.header_size+self.script_size
        end = pos+self.stream_size
        frame = -1
        while pos < end:
            time, size = struct.unpack_from('<fI', self.data, pos)
            packet = self.data[pos+8:pos+8+size]
            if len(packet) != size or not packet: raise ValueError('invalid packet')
            if packet[0] == 1: frame = struct.unpack_from('<i', packet, 1)[0]
            elif packet[0] == 2: frame += 1
            self.packets.append((frame, time, packet))
            pos += 8+size
        if pos != end: raise ValueError('invalid stream length')
        self.tail = self.data[end:]

    def write(self, path, packets=None, script=None, speed=1):
        script = (self.script if script is None else script).encode()
        packets = self.packets if packets is None else packets
        stream = b''.join(struct.pack('<fI', t/speed, len(p))+p for _,t,p in packets)
        header = bytearray(self.data[:self.header_size])
        struct.pack_into('<II', header, 304, len(script), len(stream))
        Path(path).write_bytes(gzip.compress(header+script+stream+self.tail, mtime=0))


def commands(packet):
    """Return command records and absolute ID offsets; preserve other bytes."""
    kind = packet[0]
    if kind == 11:
        cid, timeout, options, count = struct.unpack_from('<iiBI',packet,4)
        assert len(packet) == 17+4*count
        return [(cid,options,struct.unpack_from(f'<{count}f',packet,17),4)], None
    if kind in (14,76):
        cid,timeout,options,count=struct.unpack_from('<iiBI',packet,8)
        offset = 25 if kind == 76 else 21
        assert len(packet) == offset+4*count
        return [(cid,options,struct.unpack_from(f'<{count}f',packet,offset),8)], [struct.unpack_from('<h',packet,6)[0]]
    if kind != 15: return [], None
    player,ai,pairwise,shared_id,shared_opt,shared_count,units_count=struct.unpack_from('<BBBiBHh',packet,3)
    offset=15
    units=struct.unpack_from(f'<{units_count}h',packet,offset);offset+=units_count*2
    count=struct.unpack_from('<h',packet,offset)[0];offset+=2
    result=[]
    for _ in range(count):
        cid=shared_id;id_offset=6
        if cid == 0: id_offset=offset;cid=struct.unpack_from('<i',packet,offset)[0];offset+=4
        opt=shared_opt
        if opt==255: opt=packet[offset];offset+=1
        n=shared_count
        if n==65535: n=struct.unpack_from('<H',packet,offset)[0];offset+=2
        params=struct.unpack_from(f'<{n}f',packet,offset);offset+=4*n
        result.append((cid,opt,params,id_offset))
    assert offset==len(packet),(offset,len(packet))
    return result, None if pairwise else units

def attack_runs(cs):
    runs=[];run=[]
    for index,c in enumerate(cs):
        eligible=c[0]==20 and len(c[2])==1 and c[1] & ~48 == 0
        if run and (not eligible or not c[1]&32):
            if len(run)>=2:runs.append(run)
            run=[]
        if eligible:run.append(index)
    if len(run)>=2:runs.append(run)
    return [r for r in runs if len({cs[i][2][0] for i in r})==len(r)]

if __name__=='__main__':
    import json,sys
    rows=[]
    for path in Path(sys.argv[1]).glob('*.sdfz'):
        d=Demo(path); first=None;count=0
        for frame,time,p in d.packets:
            cs,units=commands(p)
            run=[]
            for c in cs:
                if c[0]==20 and len(c[2])==1 and c[1] & ~32 == 0 and (not run or c[1]&32):run.append(c)
                else:run=[]
                if len(run)>=2 and units:
                    count+=1
                    if first is None: first=frame
        if count: rows.append(dict(path=str(path),first=first,chains=count))
    rows.sort(key=lambda x:x['first'])
    print(json.dumps(rows,indent=2))

def queued_attack_chains(demo):
    """Find explicit per-unit attack runs, including separate packets/frames.

    Never merge packets or move commands in time. Duplicate-target runs are
    excluded because native queue cancellation needs a separate translation.
    """
    selections={};pending={};groups=[]
    def finish(unit):
        run=pending.pop(unit,[])
        if len(run)>=2 and len({e['target'] for e in run})==len(run):
            groups.append({'unit':unit,'entries':run})
    for packet_index,(frame,time,packet) in enumerate(demo.packets):
        if packet[0]==12:
            selections[packet[3]]=struct.unpack_from(f'<{(len(packet)-4)//2}h',packet,4)
            continue
        cs,units=commands(packet)
        if packet[0]==11:units=selections.get(packet[3],())
        if not units:continue
        for cid,opt,params,offset in cs:
            if cid in (45,50,85,95,115,120):continue
            valid=cid==20 and len(params)==1 and opt&~48==0
            for unit in units:
                if not valid or not opt&32:finish(unit)
                if valid:
                    pending.setdefault(unit,[]).append(dict(packet=packet_index,offset=offset,frame=frame,time=time,target=params[0],options=opt))
    for unit in list(pending):finish(unit)
    # Shared ID fields must not incidentally rewrite a ground attack.
    safe=[]
    for group in groups:
        valid=True
        for e in group['entries']:
            cs,_=commands(demo.packets[e['packet']][2])
            if any(c[3]==e['offset'] and not(c[0]==20 and len(c[2])==1 and c[1]&~48==0) for c in cs):valid=False
        if valid:safe.append(group)
    return safe
