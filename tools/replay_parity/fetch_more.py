"""Download more completed public replays matching the historical game/engine used by the A/B harness."""
import json,sys,urllib.request,urllib.parse
from collections import Counter
from pathlib import Path
from replay import Demo,commands,queued_attack_chains
root=Path(__file__).resolve().parent/'replays'
maps=Path(sys.argv[1]);want_game=sys.argv[2];want_engine=sys.argv[3];limit=int(sys.argv[4])
have={p.name.split('__')[0] for p in root.glob('*.sdfz')}
def get(url):
 with urllib.request.urlopen(url,timeout=120) as r:return r.read()
rows=[]
for page in range(1,8):
 listing=json.loads(get(f'https://api.bar-rts.com/replays?limit=100&page={page}'))
 for e in listing['data']:
  if e['id'] in have or not 600000<e['durationMs']<2400000:continue
  if not (maps/(e['Map']['fileName']+'.sd7')).exists():continue
  d=json.loads(get('https://api.bar-rts.com/replays/'+e['id']))
  if d['gameVersion']!=want_game or d['engineVersion']!=want_engine or d.get('hasBots') or not d.get('gameEndedNormally',True):continue
  players=sum(len(t['Players']) for t in d['AllyTeams'])
  if players<4:continue
  filename=d['fileName'];assert Path(filename).name==filename
  path=root/(e['id']+'__'+filename)
  if not path.exists():path.write_bytes(get('https://storage.uk.cloud.ovh.net/v1/AUTH_10286efc0d334efd917d476d7183232e/BAR/demos/'+urllib.parse.quote(filename,safe='')))
  (root/(e['id']+'.json')).write_text(json.dumps(d,indent=2))
  demo=Demo(path);hist=Counter()
  for frame,t,p in demo.packets:
   cs,units=commands(p)
   for c in cs:
    if c[0]>=34000 or c[0]==20:hist[c[0]]+=1
  row=dict(id=e['id'],path=str(path),map=e['Map']['scriptName'],players=players,duration_min=round(e['durationMs']/60000,1),last_frame=demo.packets[-1][0],attack_chains=len(queued_attack_chains(demo)),cmd_hist={str(k):v for k,v in sorted(hist.items())})
  rows.append(row);print(json.dumps(row),flush=True)
  if len(rows)>=limit:break
 if len(rows)>=limit:break
(root/'more-candidates.json').write_text(json.dumps(rows,indent=2))
