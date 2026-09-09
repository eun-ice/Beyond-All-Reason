# Replay A/B comparison for shared target lists

Runs a recorded public replay on its historical game revision (A), then on the
same revision with this PR's runtime files (B), on the same engine, and compares
observed gameplay state every 150 frames. A third variant rewrites eligible
recorded Attack chains into compact `ATTACK_TARGETS` commands so the compact
controller is exercised as well. Frame times are recorded in every run.

Everything in this directory is standard-library Python plus one Lua gadget; it
never touches an installed client.

## Why two engine builds

The compact Attack controller materializes one ordinary Attack per unit through
`CMD.INSERT`. Two Recoil `CommandAI` details make a bit-exact comparison against
native Attack queues impossible on release `2026.07.04`:

1. `ExecuteInsert` registers no death dependence for the inserted command, so an
   inserted Attack outlives its target until the unit's next SlowUpdate, while a
   native queued Attack is removed the moment the target is deleted
   (RecoilEngine PR #3344). The gadget works around this by giving and removing
   a throwaway order on the same target.
2. `targetDied` survives the queue flush of a non-shift order. After an
   automatic target died, the player's next Attack is finished in the same frame
   it is given and the unit falls back to auto-targeting (RecoilEngine issue
   #3345, PR #3346). The controller rewrites the queue before its first Attack
   executes, which clears the flag, so it does not reproduce the drop, and it
   cannot: internal auto-attacks raise no Lua callins.

Both fixes are one-liners with minimal gameplay effect (an inserted Attack
reacts to its target's death immediately instead of up to half a second later; a
player's first Attack after an automatic kill is no longer silently dropped).
For the comparison they matter: on the release engine the controller path
differs from the native path exactly at those drops, on an engine with both
fixes it is identical wherever translated commands reached their units. The
runner therefore compares on both engines. Because fix 2 changes what happened
in the recorded games, the patched-engine baseline leaves the recorded timeline
at the first affected event; the runner reports that frame, and later recorded
commands may no longer find their units there, which is why it also counts how
many translated commands were actually delivered.

## Setup

- Linux, Python 3.11+, Git, the maps of the replays, the replay's exact release
  engine (`spring-headless` with its runtime files), and optionally a headless
  build of the same release tag with the two engine fixes.
- Two game checkouts: the historical revision, and the same revision plus this
  PR's runtime files. `prepare_games.sh` creates both as detached worktrees in
  `/tmp` (`prepare_games.sh <game-repo> <historical-commit> <candidate-ref>`).
- Copy `parity_runner.example.json` to `parity_runner.json` and set the paths.
  `game_version_suffix` and `engine_version` guard against replays from other
  releases.

## One replay, one row

```sh
python3 parity_runner.py <replay-id>            # id from bar-rts.com
python3 parity_runner.py <replay-id> --jobs 4   # concurrent engine runs, ~6 GB RAM each
python3 parity_runner.py <replay-id> --skip-patched --no-classify
```

The runner downloads the replay into `replays/`, runs `base`, `base-repeat`,
`pr-original` and `pr-controller` on the release engine and `base`,
`pr-original`, `pr-controller` on the patched engine, and then

- appends a row to `results/parity-runs.csv` with: baseline reproducibility,
  Set Target parity (`base` vs `pr-original`), controller parity
  (`pr-original` vs `pr-controller`), translated commands delivered, the frame
  where master and the patched engine diverge, and mean/p95 frame time and peak
  synced Lua memory for base and PR;
- writes `results/runs/<id>/summary.json` and `frametimes.png`, a base-vs-PR
  frame-time graph with markers for the first translated chain, the
  master/patched-engine divergence and a release-engine controller difference;
- if the release-engine controller path differs, reruns a traced window and
  reports `stale-targetDied` when a native Attack was accepted and finished in
  the same frame (the engine issue above), otherwise `unclassified`.

Cells read `equal:<last frame>` or `diff:<first differing sample>`. A controller
result only counts as evidence when translated commands were delivered.

`fetch_more.py <maps-dir> "<game version>" <engine> <count>` downloads more
public replays matching the configured versions and lists their attack chains,
useful for picking replays with controller coverage.

## Building blocks

`prepare.py`, `run.py`, `report.py`, `compare.py`, `observer.lua` and
`replay.py` are the harness the runner drives; they can be used on their own
(`prepare.py --help`). `--detail-start/--detail-end` record every frame of a
window for diagnosis; dropping an instrumented copy of a gadget into
`<root>/<variant>/games/parity.sdd/luarules/gadgets/` shadows the game's file
for that run. `perf_report.py` draws the frame-time comparison from two run
directories. `python3 -m unittest discover -s . -p 'test_*.py'` checks the
packet tooling.
