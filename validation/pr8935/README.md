# PR #8935: historical replay comparison branch

Clean PR revision: `5be6c6a71113175842d282ed78e8c43aa8648273`.
It is stacked on clean #9541 `9629ae3c1ac2c946972184f256c0b10dc2d87f02`,
which contains upstream `c8363dedb2a65d11c82f569b54e0209c524dfd7c`.
Compatibility runtime revision: `fcca1a0d347ffe4a6f5ddc2e6c0c45d89aa6a0df`.
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

- `20f2ba974c`: restore the 128-target limit for old single/area Set Target
  commands. Compact lists and builder inheritance remain uncapped.
- `fcca1a0d34`: restore the 15-frame full sweep, historical pruning and
  acquisition cadence, deferred empty-list removal, synchronous transfer
  pruning, and absence of reassertion outside the acquisition chunk.

Both variants retain append visibility deadlines, builder inheritance and
queue/cursor correctness fixes. Attack lists retain their native sensor-loss
semantics in both variants. The compatibility branch deliberately does not
promise the clean branch's validation budget or reassertion behavior.

```sh
git diff 5be6c6a71113175842d282ed78e8c43aa8648273 fcca1a0d347ffe4a6f5ddc2e6c0c45d89aa6a0df -- luarules spec
```

The Attack controller and gadget lifecycle dispatch are unchanged from the
previous PR head `9f235eac9913d385619ef2cad618292da3f99688`. Relative to that
head, the compatibility targeting gadget retains only the validation-queue
index and replacement-list cursor fixes. This makes the replay-only delta
reviewable without discarding those correctness fixes.

## Validation and reproduction

From each checkout, run the full suite in both orders:

```sh
lx --lua-version 5.1 test
SPEC_ORDER=reverse lx --lua-version 5.1 test
```

The clean revision passes 819 tests in each order, with one existing pending
unit-definition test. The compatibility revision passes 813 tests in each
order, with the same pending test. Both variants pass all four engine fixtures
(two scenarios, native and compact), with equal movement, weapon-target and
event traces: 305 observations per pending run and 307 per recycle run.
StyLua 2.5.2 checks the changed Lua files. Whole-tree EmmyLua 0.22.0 reports the
same three errors as upstream, in AtlasOnDemand.lua and gui_pip.lua; this is
not a passing CI-pinned 0.24.0 type gate.

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
under `pr8935-validation-20261018/` preserve the exact invocations and comparison.
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
