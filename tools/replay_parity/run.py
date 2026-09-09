"""Run one prepared replay variant and preserve its exit status and engine identity."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--engine',type=Path,required=True);args=p.parse_args()
root=args.directory.resolve();engine=args.engine.resolve()
if not (root/'input.sdfz').is_file():p.error('prepare the run first')
if (root/'run.json').exists():p.error('run already exists; prepare a new directory')
info={'engine':str(engine),'engine_sha256':hashlib.file_digest(engine.open('rb'),'sha256').hexdigest(),'started':time.time()}
for key,path in [('game',root/'games/BAR.sdd')]:
 info[key+'_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()
 info[key+'_diff_sha256']=hashlib.sha256(subprocess.check_output(['git','diff','HEAD'],cwd=path)).hexdigest()
cmd=[str(engine),'--isolation','--write-dir',str(root),str(root/'input.sdfz')];info['command']=cmd
with (root/'console.log').open('w') as log:
 child=subprocess.Popen(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
 info['pid']=child.pid;(root/'run.json').write_text(json.dumps(info,indent=2))
 try:info['exit_code']=child.wait()
 except KeyboardInterrupt:
  child.terminate();info['exit_code']=child.wait();raise
 finally:
  info['finished']=time.time();(root/'run.json').write_text(json.dumps(info,indent=2))
logtext=(root/'console.log').read_text(errors='replace')
info['complete']='[ReplayParity] COMPLETE ' in logtext
info['lua_errors']='RunCallInTraceback' in logtext
(root/'run.json').write_text(json.dumps(info,indent=2))
print(json.dumps(info))
raise SystemExit(info['exit_code'] or (0 if info['complete'] and not info['lua_errors'] else 2))
