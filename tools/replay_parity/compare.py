"""Compare exact observable simulation records, rejecting incomplete traces."""
import argparse,hashlib,itertools,json,zlib
from pathlib import Path

def frames(path):
    with Path(path).open('rb') as f:
        expected=None
        while line:=f.readline():
            fields=line.decode().strip().split('\t')
            if fields[0]=='COMPLETE':
                if expected!=int(fields[1]):raise ValueError('completion frame mismatch')
                if f.read(1):raise ValueError('trailing data')
                return
            if len(fields)!=3 or fields[0]!='FRAME':raise ValueError('invalid frame header')
            frame,size=map(int,fields[1:])
            if expected is not None and frame<=expected:raise ValueError('nonincreasing sample frames')
            expected=frame
            compressed=f.read(size)
            if len(compressed)!=size:raise ValueError('truncated frame')
            yield frame,zlib.decompress(compressed)
        raise ValueError('trace missing COMPLETE marker')

def compare(a,b):
    count=0;first=None;different=0;ha=hashlib.sha256();hb=hashlib.sha256()
    for pair in itertools.zip_longest(frames(a),frames(b)):
        left,right=pair
        if left is None or right is None or left[0]!=right[0]:raise ValueError('frame coverage differs')
        frame,sa=left;_,sb=right;count+=1;ha.update(sa);hb.update(sb)
        if sa!=sb:
            different+=1
            if first is None:
                def keyed(s):return {tuple(row.split('\t')[:2]):row for row in s.decode().splitlines()}
                la,lb=keyed(sa),keyed(sb)
                differences=[dict(key=list(k),baseline=la.get(k),candidate=lb.get(k)) for k in sorted(la.keys()|lb.keys()) if la.get(k)!=lb.get(k)]
                first=dict(frame=frame,differing_records=len(differences),examples=differences[:30])
    if not count:raise ValueError('empty traces')
    return dict(samples=count,equal=different==0,different_frames=different,first_difference=first,baseline_sha256=ha.hexdigest(),candidate_sha256=hb.hexdigest())
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('baseline');p.add_argument('candidate');p.add_argument('--output');args=p.parse_args()
    result=compare(args.baseline,args.candidate);text=json.dumps(result,indent=2)+'\n'
    if args.output:Path(args.output).write_text(text)
    print(text)
