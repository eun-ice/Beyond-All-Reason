#!/usr/bin/env bash
# Recreate the two game checkouts the runner compares (they live in /tmp and vanish on reboot):
#   base_game: the historical game revision as released
#   pr_game:   the same revision plus the runtime files of the candidate branch
# usage: prepare_games.sh [<game-repo>] [<historical-commit>] [<candidate-ref>]
set -euo pipefail
REPO=${1:-/home/aron/Projects/bar/Beyond-All-Reason}
BASE_COMMIT=${2:-0ceadc7472}
CANDIDATE=${3:-fix/pr8935-parity}
BASE=/tmp/pr8935-replay-0cea-base
PR=/tmp/pr8935-replay-0cea-candidate
[ -e "$BASE" ] || git -C "$REPO" worktree add --detach "$BASE" "$BASE_COMMIT"
[ -e "$PR" ] || git -C "$REPO" worktree add --detach "$PR" "$BASE_COMMIT"
# runtime files the PR touches (unsynced widgets included so the checkout is self-consistent)
for f in luarules/gadgets/unit_target_on_the_move.lua luarules/gadgets/cmd_attack_targets.lua \
         luarules/Utilities/shared_target_list_store.lua common/luaUtilities/target_list_orders.lua \
         luarules/gadgets/cmd_alliance_break.lua luarules/gadgets/game_no_rush_mode.lua \
         luarules/gadgets/unit_areaattack_limiter.lua luaui/Widgets/cmd_area_commands_filter.lua \
         luaui/Widgets/cmd_exclude_walls_area_attacks.lua modules/customcommands.lua; do
  mkdir -p "$PR/$(dirname "$f")"
  git -C "$REPO" show "$CANDIDATE:$f" > "$PR/$f"
done
echo "base: $BASE ($(git -C "$BASE" rev-parse --short HEAD))"
echo "candidate: $PR ($BASE_COMMIT + $CANDIDATE runtime files)"
echo "point parity_runner.json pr_game at $PR"
