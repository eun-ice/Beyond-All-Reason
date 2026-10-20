# PR #8935: historical replay comparison branch

Clean PR revision: `33230e4420` (runtime tested at `59795df9fa`).
It is stacked on clean #9541 `e3dd33508a`, including #9787's fix for #9786.
Compatibility runtime tested at `945ef8f4e4`; rebased runtime is `ea20d6808e`.
The intervening clean-branch change strengthens command-ID assertions only.
Subsequent documentation commits do not change the runtime.

## Scope of the split

The clean PR retains the Attack controller's pending-target precedence,
independent Attack/Set Target ownership, movement stops, per-unit target
removal, recycled-ID protection and UnitPreDelete handling. These are
correctness requirements. Native-queue fallback on engines missing the
required capabilities also remains: removing it would break movement and
lifecycle behavior on those engines.

Historical replay behavior is isolated in two commits adapted from #9541's
[comparison branch](https://github.com/eun-ice/Beyond-All-Reason/tree/validation/pr9541-historical-replay-parity/validation/pr9541):

- `6929d6d9e6`: restore the 128-target limit for old single/area Set Target
  commands. Compact lists and builder inheritance remain uncapped.
- `4dc96e879e`: restore the 15-frame full sweep, historical pruning and
  acquisition cadence, deferred empty-list removal, synchronous transfer
  pruning, and absence of reassertion outside the acquisition chunk.

Both variants retain append visibility deadlines, builder inheritance and
queue/cursor correctness fixes. Attack lists retain their native sensor-loss
semantics in both variants. The compatibility branch deliberately does not
promise the clean branch's validation budget or reassertion behavior.

```sh
git diff feature/stacked-attack-target-controller validation/pr8935-historical-replay-parity -- luarules spec
```

Both branches inherit the reviewed allocation, selection-state and selective
alliance-pruning fixes. The clean branch caps Set Target at 512; Attack remains
uncapped. This comparison branch restores the historical 128 limit for legacy
single/area commands and leaves compact lists uncapped. The inherited mouse-press
origin fix affects live gestures; recorded network commands already contain their
coordinates. Historical equality still needs replay-specific validation.

Known pre-existing limitation: a shared Attack owner can keep Set Target entries
past sensor expiry through `keepUnseen`. This refresh does not fix that issue.

## Validation and reproduction

From each checkout, run the full suite in both orders:

```sh
lx --lua-version 5.1 test
SPEC_ORDER=reverse lx --lua-version 5.1 test
```

On October 21, the full clean suite passed 887 tests and the compatibility
suite passed 881, each with one existing pending test. The strengthened drag
command-ID fixture passes all nine cases on both branches. Both variants pass
all four engine fixtures (two scenarios, native and compact), with equal
movement, weapon-target and event traces: 305 observations per pending run and
307 per recycle run. Evidence and exact tested SHAs are preserved locally under
`stack-refresh-20261021/`. Full historical replays were not rerun.

Archived October 18 validation: the earlier clean and compatibility revisions
passed 819 and 813 tests respectively in both suite orders. Their type-check
results and replay evidence do not establish validation of the current heads.

Engine checks use the existing UnitPreDelete development build, SHA-256
`690c0d4b39e86750b258fdca2842e5f6432f08647d3c3d5cb16071a20a54c70b`, and the
[compact lifecycle fixture at engine commit 8e873413c9](https://github.com/eun-ice/RecoilEngine/blob/8e873413c9c4fe67c1ac9af2e1d7d1c40d6e9abd/test/validation/unit_deleted/run_compact.py).
Use development maps, never the production installation. For each BAR SHA,
run `pending` and `recycle`, each with native orders and with `--compact`:

```sh
python3 /path/to/engine/test/validation/unit_deleted/run_compact.py \
  --engine /path/to/UnitPreDelete/spring-headless \
  --game /path/to/BAR-checkout --bar-repo /path/to/BAR-checkout \
  --bar-ref FULL_BAR_SHA --maps /path/to/development/maps \
  --output /tmp/unique-case-directory --callin UnitPreDelete \
  --ground --scenario pending --compact
```

The source checkout must stay at the tested revision throughout each run.
Require completion and actual compact-controller coverage. Compare movement,
weapon targets and events in `behavior.json`, allowing the queue-head
representation to differ. The local `lifecycle.py` runner and JSON manifests
under `stack-refresh-20261021/` preserve the exact invocations and comparison.
These focused fixtures are not full replay or full-game resign/take tests.

The UI integration runner currently shares a mutable function environment
between loaded tests. An exploratory test-only override produced environment
errors and repeated test behavior, so its apparent passes are rejected as
coverage. No runner change is included in either branch.

Historical replay equality has not been rerun for these SHAs. Use the recorded
game revision and engine, apply only the runtime delta, and record the resulting
backport SHA separately. Keep native packets, map, RNG seed, observer and
endpoint identical. Compare complete state/event samples and verify actual
controller coverage; earlier replay reports do not establish parity for these
new revisions. Follow the A/B protocol in the linked #9541 documentation.
