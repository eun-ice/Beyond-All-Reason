"""Prepare isolated baseline/controller runs with an auditable byte-level rewrite."""
import argparse,hashlib,json,re,struct,zlib
from pathlib import Path
from replay import Demo,commands,queued_attack_chains
P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('replay',type=Path);p.add_argument('--root',type=Path,required=True);p.add_argument('--finish',type=int,required=True);p.add_argument('--base-game',required=True);p.add_argument('--pr-game',required=True);p.add_argument('--maps',type=Path,required=True);p.add_argument('--interval',type=int,default=150);p.add_argument('--port',type=int,default=18900);p.add_argument('--detail-start',type=int,default=-1);p.add_argument('--detail-end',type=int,default=-1);p.add_argument('--allow-empty',action='store_true');args=p.parse_args()
args.root=args.root.resolve()
args.base_game=str(Path(args.base_game).resolve())
args.pr_game=str(Path(args.pr_game).resolve())
args.maps=args.maps.resolve()
for directory in (Path(args.base_game),Path(args.pr_game),args.maps):
 if not directory.is_dir():p.error(f'missing input directory: {directory}')
if args.finish<=0:p.error('--finish must be positive')
assert args.interval>0
assert not args.root.exists(),'prepare requires a fresh output directory'
d=Demo(args.replay)
script=re.sub(r'(?im)^(gametype\s*=)[^;]*;',r'\g<1>BAR Replay Parity 1;',d.script)
assert script!=d.script
script=re.sub(r'(?im)^(?:autohostport|hostport)\s*=[^;]*;','',script)
script=re.sub(r'(?im)^(?:minspeed|maxspeed)\s*=[^;]*;','',script)
script=script.replace('{','{\nminspeed=100;\nmaxspeed=100;',1)
# The script occurs in both the header and compressed initial GAMEDATA packet.
packets=[];translation=[]
for index,(frame,time,packet) in enumerate(d.packets):
 if packet[0]==52:
  n=struct.unpack_from('<H',packet,3)[0]
  assert zlib.decompress(packet[5:5+n]).decode()==d.script
  compressed=zlib.compress(script.encode());tail=packet[5+n:]
  packet=bytes([52])+struct.pack('<HH',5+len(compressed)+len(tail),len(compressed))+compressed+tail
 packets.append((frame,time,packet))
converted=list(packets)
marks=set()
for group in queued_attack_chains(d):
 if group['entries'][0]['frame']>args.finish:continue
 entries=[e for e in group['entries'] if e['frame']<=args.finish]
 if len(entries)<2:continue
 translation.append(dict(unit=group['unit'],entries=entries))
 for entry in entries:marks.add((entry['packet'],entry['offset']))
for index,offset in marks:
 frame,time,packet=converted[index];patched=bytearray(packet)
 struct.pack_into('<i',patched,offset,34927)
 converted[index]=(frame,time,bytes(patched))
assert translation or args.allow_empty,'no eligible chains in selected interval'
args.root.mkdir(parents=True,exist_ok=True)
for variant_index,(name,game,stream) in enumerate([('base',args.base_game,packets),('base-repeat',args.base_game,packets),('pr-original',args.pr_game,packets),('pr-controller',args.pr_game,converted)]):
 root=args.root/name;root.mkdir(exist_ok=True)
 games=root/'games';games.mkdir(exist_ok=True)
 link=games/'BAR.sdd'
 if not link.exists():link.symlink_to(game,target_is_directory=True)
 maps=root/'maps'
 if not maps.exists():maps.symlink_to(args.maps,target_is_directory=True)
 overlay=games/'parity.sdd';(overlay/'luarules/gadgets').mkdir(parents=True,exist_ok=True)
 (overlay/'modinfo.lua').write_text('return {name="BAR Replay Parity",version="1",modtype=1,depend={"Beyond All Reason $VERSION"}}\n')
 sources=','.join(str(u) for u in sorted({t['unit'] for t in translation}))
 (overlay/'parity_config.lua').write_text(f'return {{finish={args.finish},interval={args.interval},detailStart={args.detail_start},detailEnd={args.detail_end},sources={{{sources}}}}}\n')
 (overlay/'luarules/gadgets/dbg_replay_parity.lua').write_bytes((P/'observer.lua').read_bytes())
 (root/'springsettings.cfg').write_text(f'HostPortDefault = {args.port+variant_index}\nDisableDemoVersionCheck = 1\nNoSound = 1\nLuaUI = 0\nWorkerThreadCount = 1\nHardwareThreadCount = 1\nMaxSpeed = 100\nMinSpeed = 1\n')
 d.write(root/'input.sdfz',stream,script,speed=100)
manifest=dict(source=str(args.replay.resolve()),sha256=hashlib.sha256(args.replay.read_bytes()).hexdigest(),finish=args.finish,interval=args.interval,base_game=args.base_game,pr_game=args.pr_game,maps=str(args.maps),translation=translation,observer_sha256=hashlib.sha256((P/'observer.lua').read_bytes()).hexdigest())
(args.root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'root':str(args.root),'chains':len(translation),'first':min((t['entries'][0]['frame'] for t in translation),default=None),'command_fields':len(marks)}))
