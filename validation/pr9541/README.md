# PR #9541: historical replay comparison branch

This branch is a validation companion, not the proposed merge result.
The clean PR is `9629ae3c1ac2c946972184f256c0b10dc2d87f02`, rebased onto
upstream `c8363dedb2a65d11c82f569b54e0209c524dfd7c`.
The compatibility code revision is `292125f07c65b7294f6956592090c7060ad667c1`;
subsequent documentation/tooling commits do not change the runtime.

## Review the split

The clean PR has four commits: shared lists/native packet batching; visibility
lifetime preservation and builder inheritance coverage; mouse/split modifiers;
and budgeted validation with deferred transfer pruning and active-target
reassertion. It has no historical 128-entry command cap or full slow sweep.
8192 is a per-frame work budget, not a target-list size limit.

The companion adds two independently reviewable runtime commits:

- `59021cb66a`: restore the 128-entry cap for old single/area commands. Compact
  commands and inherited builder lists remain uncapped. Tests assert the
  historical cap only on this branch.
- `292125f07c`: restore the old 15-frame full sweep, slow-frame acquisition gap,
  deferred empty-list removal, synchronous transfer pruning, and lack of
  per-frame reassertion outside the acquisition chunk. These deliberately
  restore historical timing and its performance/behavior limitations. The
  corresponding budget/transfer/reassertion tests remain on the clean branch;
  this branch uses the historical timing expectations. Queue-index wrapping,
  validation-cursor preservation, shared-store cursor fixes, append deadlines,
  and builder inheritance coverage remain.

```sh
git diff 9629ae3c1ac2c946972184f256c0b10dc2d87f02 292125f07c65b7294f6956592090c7060ad667c1 -- luarules spec
```

Do not infer that all historical behavior is desirable, or that replay equality
proves the clean implementation incorrect. In particular, the companion's full
sweep is intentionally not bounded by the clean branch's validation budget.

## Validation, 2026-10-18

| Check | Clean runtime SHA above | Compatibility runtime SHA above |
| --- | --- | --- |
| Full Lua suite, normal order | 782 passed, 1 existing pending | 776 passed, 1 existing pending |
| Full Lua suite, reverse file order | 782 passed, 1 existing pending | 776 passed, 1 existing pending |
| Transfer engine test | 544 assertions passed | 544 assertions passed |
| List rebuilt inside transfer callback | no | yes (historical behavior) |
| StyLua 2.5.2, changed files | passed | passed |

The existing pending test concerns turret aim in unit scripts (#7961).
The whole-tree type check used the locally installed EmmyLua 0.22.0, not CI's
0.24.0. Clean PR and unmodified upstream report the same three errors in
`AtlasOnDemand.lua` and `gui_pip.lua`; this is not a clean pinned-version gate.
The unmodified headless integration runner skipped all 20 tests, so its zero
exit status is not integration coverage. No new full historical replay parity
run or full-game player resign/take run is claimed for these SHAs.

## Reproduce the transfer test

Keep this directory outside a checkout you intend to switch, or invoke it from
a separate companion checkout. The source checkout must remain fixed throughout
the run. Supply development assets with map `Quicksilver Remake 1.24` and engine
`engine/recoil_2026.09.01/spring-headless`. Never point output at a production
installation. The output directory must not already exist.

```sh
python3 validation/pr9541/transfer.py \
  --source /path/to/checkout-at-the-tested-SHA \
  --assets /path/to/development-assets \
  --output /tmp/pr9541-transfer-clean

lx --lua-version 5.1 test
SPEC_ORDER=reverse lx --lua-version 5.1 test
```

Repeat with the compatibility checkout and a different output directory.
The runner records source SHA, gadget and harness hashes, invocation, exit
status, and engine log. Temporary game overlays link unchanged files and are
removed after execution. It creates 128 owners and 768 targets, shares 256,
captures/returns 32 owners, reassigns lists, and transfers the remaining 512.
Other gameplay gadgets are disabled after frame 1. This tests real engine
transfer callbacks, not lobby resign/take or whole-game replay determinism.

## Historical replay A/B protocol

Use the replay's recorded game revision and engine as the baseline, not current
master. Apply only the target-list/native-command runtime delta to a separate
copy of that recorded revision; resolve old gadget-handler APIs explicitly.
Use this branch's two compatibility commits for the parity variant and record
both the source SHA and resulting backport SHA/patch hash. Do not change
unrelated unit definitions or balance to current master.

Run identical recorded packets, engine, map, RNG seed, observer and endpoint
for baseline and candidate. Compare sampled gameplay state and damage/death
events, require complete samples and clean Lua/engine completion, and record
actual multi-target command coverage. Run the clean variant separately and
report intentional cadence/limit differences. Replays do not rerun the LuaUI
packet sender; packet batching needs its own tests. Do not reuse older parity
results as evidence for these new SHAs, and do not compare performance as equal
workloads when gameplay diverges.
