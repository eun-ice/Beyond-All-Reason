"""Compare sampled state AND event hashes without treating unfinished runs as passes."""
import argparse
import json
from pathlib import Path


def read_run(directory):
    root = Path(directory)
    info = json.loads((root / 'run.json').read_text())
    rows = {}
    path = root / 'hashes.tsv'
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split('\t')
            if len(parts) != 3:
                raise ValueError(f'malformed hash record in {path}')
            frame = int(parts[0])
            if frame in rows or (rows and frame <= max(rows)):
                raise ValueError(f'invalid frame ordering in {path}')
            rows[frame] = parts[1:]
    complete = info.get('complete', False) and info.get('exit_code') == 0 and not info.get('lua_errors', False)
    return info, rows, complete


def report(baseline, candidate):
    ai, a, ac = read_run(baseline)
    bi, b, bc = read_run(candidate)
    common = sorted(a.keys() & b.keys())
    first_state = next((f for f in common if a[f][0] != b[f][0]), None)
    first_events = next((f for f in common if a[f][1] != b[f][1]), None)
    same_engine = ai['engine_sha256'] == bi['engine_sha256']
    equal = bool(common) and ac and bc and a == b and same_engine
    return dict(
        baseline=str(baseline), candidate=str(candidate),
        baseline_complete=ac, candidate_complete=bc, same_engine=same_engine,
        baseline_samples=len(a), candidate_samples=len(b), common_samples=len(common),
        last_common_frame=common[-1] if common else None,
        first_state_difference=first_state, first_event_difference=first_events,
        result='equal' if equal else 'different' if first_state is not None or first_events is not None else 'incomplete_or_incompatible',
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline')
    parser.add_argument('candidate')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(report(args.baseline, args.candidate), indent=2) + '\n'
    if args.output:
        args.output.write_text(result)
    print(result)
