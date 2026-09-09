#!/usr/bin/env python3
"""Run the full PR #8935 replay comparison for one replay id and record the outcome.

For a replay id (bar-rts.com) this script
  1. downloads the replay if needed and checks game/engine version,
  2. prepares two run roots (release engine, patched engine) with the harness,
  3. runs base / pr-original / pr-controller on both engines (+ base-repeat on release),
  4. compares: Set Target parity, controller parity, master-vs-patched-engine divergence,
  5. counts controller coverage (translated commands delivered, list assignments),
  6. optionally classifies a release-engine controller difference (stale targetDied),
  7. draws the frame-time graph (release engine, base vs PR) with divergence markers,
  8. appends one row to results/parity-runs.csv and writes results/runs/<id>/summary.json.

Configuration lives in parity_runner.json next to this file (paths, versions).
"""
import argparse, csv, json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The harness scripts sit next to this file in the repository; the local workspace keeps them in distribution/.
HARNESS = HERE / 'distribution' / 'pr8935-replay-ab' if (HERE / 'distribution' / 'pr8935-replay-ab' / 'prepare.py').exists() else HERE
sys.path.insert(0, str(HARNESS))
from replay import Demo, commands  # noqa: E402

CMD_ATTACK_TARGETS = 34927
VARIANTS_RELEASE = ('base', 'base-repeat', 'pr-original', 'pr-controller')
VARIANTS_PATCHED = ('base', 'pr-original', 'pr-controller')


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def load_config(path):
    cfg = json.loads(Path(path).read_text())
    for key in ('base_game', 'pr_game', 'maps', 'release_engine', 'patched_engine'):
        cfg[key] = str(Path(cfg[key]).expanduser())
        if not Path(cfg[key]).exists():
            sys.exit(f'config: {key} does not exist: {cfg[key]}')
    cfg['work_dir'] = str(Path(cfg.get('work_dir', '/tmp/pr8935-runner')).expanduser())
    return cfg


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def get_replay(replay_id, cfg, force):
    root = HERE / 'replays'
    root.mkdir(exist_ok=True)
    existing = sorted(root.glob(replay_id + '__*.sdfz'))
    details_path = root / (replay_id + '.json')
    if details_path.exists():
        details = json.loads(details_path.read_text())
    else:
        details = json.loads(fetch('https://api.bar-rts.com/replays/' + replay_id))
        details_path.write_text(json.dumps(details, indent=2))
    game = details.get('gameVersion') or ''
    engine = details.get('engineVersion') or ''
    if not force:
        if not game.endswith(cfg['game_version_suffix']):
            sys.exit(f'replay game version {game!r} does not match {cfg["game_version_suffix"]!r} (use --force)')
        if engine != cfg['engine_version']:
            sys.exit(f'replay engine {engine!r} does not match {cfg["engine_version"]!r} (use --force)')
    if existing:
        return existing[0], details
    filename = details['fileName']
    assert Path(filename).name == filename
    path = root / (replay_id + '__' + filename)
    log(f'downloading {filename}')
    path.write_bytes(fetch('https://storage.uk.cloud.ovh.net/v1/AUTH_10286efc0d334efd917d476d7183232e/BAR/demos/' + urllib.parse.quote(filename, safe='')))
    return path, details


def prepare(replay, root, finish, cfg, port):
    if root.exists():
        sys.exit(f'{root} exists; remove it or use --work-dir')
    cmd = [sys.executable, str(HARNESS / 'prepare.py'), str(replay), '--root', str(root), '--finish', str(finish),
           '--base-game', cfg['base_game'], '--pr-game', cfg['pr_game'], '--maps', cfg['maps'], '--port', str(port), '--allow-empty']
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
    return json.loads(out)


def run_variant(root, variant, engine):
    cmd = [sys.executable, str(HARNESS / 'run.py'), str(root / variant), '--engine', engine]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    run_json = json.loads((root / variant / 'run.json').read_text())
    run_json['wall_s'] = round(time.time() - started)
    if proc.returncode != 0 or not run_json.get('complete'):
        log(f'WARNING {root.name}/{variant}: exit={proc.returncode} complete={run_json.get("complete")} {proc.stderr.strip()[-300:]}')
    return run_json


def report(a, b):
    if not (a / 'hashes.tsv').exists() or not (b / 'hashes.tsv').exists():
        return None
    proc = subprocess.run([sys.executable, str(HARNESS / 'report.py'), str(a), str(b)], capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {'result': 'error', 'error': proc.stdout[-300:] + proc.stderr[-300:]}


def load_hashes(path):
    out = {}
    for line in open(path):
        parts = line.rstrip('\n').split('\t')
        if len(parts) >= 3:
            out[int(parts[0])] = (parts[1], parts[2])
    return out


def first_hash_difference(a, b):
    ha, hb = load_hashes(a / 'hashes.tsv'), load_hashes(b / 'hashes.tsv')
    common = sorted(set(ha) & set(hb))
    return next((f for f in common if ha[f] != hb[f]), None), (common[-1] if common else None)


def delivered_commands(variant_dir):
    path = variant_dir / 'commands.tsv'
    if not path.exists():
        return 0
    return sum(1 for line in open(path) if line.split('\t')[2:3] == [str(CMD_ATTACK_TARGETS)])


def count_lines(path):
    return sum(1 for _ in open(path)) if path.exists() else 0


def summarize(rep):
    if not rep:
        return 'not run'
    if rep.get('result') == 'equal':
        return f"equal:{rep['last_common_frame']}"
    if rep.get('result') == 'different':
        return f"diff:{rep.get('first_state_difference') or rep.get('first_event_difference')}"
    return rep.get('result', 'unknown')


def first_diff_frame(rep):
    if rep and rep.get('result') == 'different':
        return rep.get('first_state_difference') or rep.get('first_event_difference')
    return None


TRACE_GADGET = '''function gadget:GetInfo() return {name='CmdTrace', desc='', author='parity runner', layer=-1000000, enabled=true} end
if not gadgetHandler:IsSyncedCode() then return end
local WATCH = { UNITS }
local function q(u) local t={} for _,c in ipairs(Spring.GetUnitCommands(u,3) or {}) do t[#t+1]=c.id..'('..table.concat(c.params,',')..'|'..(c.options.coded or -1)..')' end return table.concat(t,' ') end
local function inwin() local f=Spring.GetGameFrame() return f>=DS and f<=DE end
function gadget:Initialize() gadgetHandler:RegisterAllowCommand(CMD.ATTACK); gadgetHandler:RegisterAllowCommand(34927) end
function gadget:UnitCommand(u,ud,team,cmd,params,opts,tag)
  if WATCH[u] and inwin() then Spring.Echo('[CMDTRACE] f='..Spring.GetGameFrame()..' u='..u..' unitcommand cmd='..cmd..' params='..table.concat(params,',')..' opts='..tostring(opts.coded)..' queue='..q(u)) end
end
function gadget:UnitCmdDone(u,ud,team,cmd,params,opts,tag)
  if WATCH[u] and inwin() then Spring.Echo('[CMDTRACE] f='..Spring.GetGameFrame()..' u='..u..' cmddone cmd='..cmd..' params='..table.concat(params,',')..' queue='..q(u)) end
end
'''


def classify_release_difference(replay, cfg, work, first_diff, manifest, port):
    """Run a traced pr-original window on the release engine and look for the stale-targetDied pattern:
    a native Attack accepted and finished in the same frame with an empty queue."""
    ds, de = max(0, first_diff - 150), first_diff
    units = sorted({t['unit'] for t in manifest['translation'] if any(e['frame'] <= de for e in t['entries'])})
    if not units:
        return 'no translated units before the difference'
    root = work / 'classify'
    prepare(replay, root, de, cfg, port)
    gadget = TRACE_GADGET.replace('UNITS', ','.join(f'[{u}]=true' for u in units)).replace('DS', str(ds)).replace('DE', str(de))
    (root / 'pr-original' / 'games' / 'parity.sdd' / 'luarules' / 'gadgets' / 'dbg_cmdtrace.lua').write_text(gadget)
    run_variant(root, 'pr-original', cfg['release_engine'])
    pattern = re.compile(r'\[CMDTRACE\] f=(\d+) u=(\d+) (unitcommand|cmddone) cmd=20 params=(\d+)[^\n]*queue=(.*)$')
    accepted = set()
    dropped = []
    for line in open(root / 'pr-original' / 'infolog.txt', errors='replace'):
        m = pattern.search(line)
        if not m:
            continue
        frame, unit, kind, target, queue = m.groups()
        key = (frame, unit, target)
        if kind == 'unitcommand':
            accepted.add(key)
        elif kind == 'cmddone' and key in accepted and queue.strip() == '':
            dropped.append(key)
    if dropped:
        return f'stale-targetDied: {len(dropped)} native Attack(s) finished in the frame they were given, e.g. frame {dropped[0][0]} unit {dropped[0][1]} target {dropped[0][2]}'
    return 'unclassified'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('replay_id')
    ap.add_argument('--config', default=str(HERE / 'parity_runner.json'))
    ap.add_argument('--finish', type=int, help='last simulated frame (default: replay end rounded down to the sample interval)')
    ap.add_argument('--jobs', type=int, default=3, help='concurrent engine runs (each needs ~6 GB RAM)')
    ap.add_argument('--port', type=int, default=45000)
    ap.add_argument('--work-dir', help='override work_dir from the config')
    ap.add_argument('--skip-patched', action='store_true', help='release engine only')
    ap.add_argument('--no-classify', action='store_true', help='skip the trace run that classifies a release-engine controller difference')
    ap.add_argument('--force', action='store_true', help='ignore game/engine version mismatch')
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.work_dir:
        cfg['work_dir'] = args.work_dir
    replay, details = get_replay(args.replay_id, cfg, args.force)
    short = args.replay_id[:4]
    demo = Demo(replay)
    last_frame = demo.packets[-1][0]
    finish = args.finish or ((last_frame - 150) // 150 * 150)
    players = sum(len(t.get('Players', [])) for t in details.get('AllyTeams', []))
    map_name = details.get('Map', {}).get('scriptName')
    log(f'{args.replay_id} {map_name} {players} players, last frame {last_frame}, finish {finish}')

    work = Path(cfg['work_dir']) / args.replay_id
    work.mkdir(parents=True, exist_ok=True)
    release_root = work / 'release'
    patched_root = work / 'patched'
    info = prepare(replay, release_root, finish, cfg, args.port)
    if not args.skip_patched:
        prepare(replay, patched_root, finish, cfg, args.port + 10)
    manifest = json.loads((release_root / 'manifest.json').read_text())
    chains = len(manifest['translation'])
    first_chain = min((e['frame'] for t in manifest['translation'] for e in t['entries']), default=None)
    log(f'prepared: {chains} attack chains, first at {first_chain}')

    jobs = [(release_root, v, cfg['release_engine']) for v in VARIANTS_RELEASE]
    if not args.skip_patched:
        jobs += [(patched_root, v, cfg['patched_engine']) for v in VARIANTS_PATCHED]
    runs = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_variant, root, v, eng): (root.name, v) for root, v, eng in jobs}
        for fut, key in futures.items():
            runs[key] = fut.result()
            log(f'done {key[0]}/{key[1]} in {runs[key]["wall_s"]} s')

    R = release_root
    result = {
        'replay_id': args.replay_id, 'map': map_name, 'players': players, 'finish': finish, 'chains': chains, 'first_chain_frame': first_chain,
        'release': {
            'engine': runs[('release', 'base')]['engine_sha256'][:12],
            'baseline_repeat': report(R / 'base', R / 'base-repeat'),
            'set_target': report(R / 'base', R / 'pr-original'),
            'controller': report(R / 'pr-original', R / 'pr-controller'),
            'controller_delivered': delivered_commands(R / 'pr-controller'),
            'controller_assignments': count_lines(R / 'pr-controller' / 'controllers.tsv'),
            'desync_warnings_base': runs[('release', 'base')].get('native_desync_warnings'),
        },
    }
    if not args.skip_patched:
        P = patched_root
        divergence, last_common = first_hash_difference(R / 'base', P / 'base')
        result['patched'] = {
            'engine': runs[('patched', 'base')]['engine_sha256'][:12],
            'master_vs_patched_divergence': divergence,
            'set_target': report(P / 'base', P / 'pr-original'),
            'controller': report(P / 'pr-original', P / 'pr-controller'),
            'controller_delivered': delivered_commands(P / 'pr-controller'),
            'controller_assignments': count_lines(P / 'pr-controller' / 'controllers.tsv'),
        }

    classification = ''
    rel_ctrl_diff = first_diff_frame(result['release']['controller'])
    if rel_ctrl_diff and not args.no_classify:
        log(f'classifying release controller difference at {rel_ctrl_diff}')
        classification = classify_release_difference(replay, cfg, work, rel_ctrl_diff, manifest, args.port + 20)
        log(classification)
    result['release']['controller_classification'] = classification

    out_dir = HERE / 'results' / 'runs' / args.replay_id
    out_dir.mkdir(parents=True, exist_ok=True)
    vlines = []
    if not args.skip_patched and result['patched']['master_vs_patched_divergence']:
        vlines += ['--vline', f"{result['patched']['master_vs_patched_divergence']}:master and patched engine diverge"]
    if first_chain:
        vlines += ['--vline', f'{first_chain}:first translated attack chain']
    if rel_ctrl_diff:
        vlines += ['--vline', f'{rel_ctrl_diff}:controller difference (release)']
    graph = out_dir / 'frametimes.png'
    perf = subprocess.run([sys.executable, str(HERE / 'perf_report.py'), '--label', short,
                           '--title', f'{args.replay_id[:8]} {map_name} {players}p: base vs PR, release engine {cfg["engine_version"]}',
                           '--base', str(R / 'base'), '--pr', str(R / 'pr-original'), '--output', str(graph)] + vlines,
                          capture_output=True, text=True)
    perf_stats = json.loads(perf.stdout)['stats'] if perf.returncode == 0 else {}
    result['perf'] = perf_stats
    result['graph'] = str(graph)
    (out_dir / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    for name in ('manifest.json',):
        shutil.copy(release_root / name, out_dir / name)

    base_stats = perf_stats.get('Baseline', {})
    pr_stats = perf_stats.get('PR #8935', {})
    row = {
        'replay_id': args.replay_id, 'map': map_name, 'players': players, 'finish': finish, 'chains': chains, 'first_chain': first_chain,
        'rel_baseline_repeat': summarize(result['release']['baseline_repeat']),
        'rel_set_target': summarize(result['release']['set_target']),
        'rel_controller': summarize(result['release']['controller']),
        'rel_delivered': result['release']['controller_delivered'],
        'rel_classification': classification,
        'patched_divergence': result.get('patched', {}).get('master_vs_patched_divergence', ''),
        'patched_set_target': summarize(result.get('patched', {}).get('set_target')),
        'patched_controller': summarize(result.get('patched', {}).get('controller')),
        'patched_delivered': result.get('patched', {}).get('controller_delivered', ''),
        'base_mean_ms': round(base_stats.get('mean_ms', 0), 3), 'pr_mean_ms': round(pr_stats.get('mean_ms', 0), 3),
        'base_p95_ms': round(base_stats.get('p95_ms', 0), 3), 'pr_p95_ms': round(pr_stats.get('p95_ms', 0), 3),
        'base_lua_mb_max': round(base_stats.get('synced_lua_mb_max') or 0, 1), 'pr_lua_mb_max': round(pr_stats.get('synced_lua_mb_max') or 0, 1),
        'graph': str(graph.relative_to(HERE)), 'date': time.strftime('%Y-%m-%d %H:%M'),
    }
    csv_path = HERE / 'results' / 'parity-runs.csv'
    new = not csv_path.exists()
    with csv_path.open('a', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        if new:
            writer.writeheader()
        writer.writerow(row)
    log(f'row appended to {csv_path}')
    for key, value in row.items():
        print(f'  {key}: {value}')


if __name__ == '__main__':
    main()
