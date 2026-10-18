from pathlib import Path
import io
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import sys

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--assets', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
source = args.source.resolve()
assets = args.assets.resolve()
root = args.output.resolve()
root.mkdir(parents=True, exist_ok=False)
engine = assets / 'engine/recoil_2026.09.01/spring-headless'
target_path = Path('luarules/gadgets/unit_target_on_the_move.lua')
baseline_ref = 'a15e8dad08ce8168634d456b74d27c313c1cf9fd'
harness = Path(__file__).resolve().with_name('transfer_gadget.lua')

for variant in ("candidate",):
    data = root / variant
    data.mkdir(exist_ok=True)
    (data / "games").mkdir(exist_ok=True)
    maps = data / "maps"
    if not maps.is_symlink():
        maps.symlink_to(assets / "maps")
    game = Path(tempfile.mkdtemp(prefix="pr9541-game-", dir=root))
    try:
        for current, directories, filenames in os.walk(source):
            directories[:] = [name for name in directories if name not in (".git", ".lux", "spec", "recoil-lua-library")]
            directory = Path(current).relative_to(source)
            destination = game / directory
            destination.mkdir(parents=True, exist_ok=True)
            for filename in filenames:
                relative = directory / filename
                if relative == target_path or filename == ".git":
                    continue
                (game / relative).symlink_to(source / relative)
        (game / target_path).symlink_to(source / target_path)
        (game / "luarules/gadgets/dbg_pr9541_transfer.lua").symlink_to(harness)
        game_link = data / "games/validation.sdd"
        if game_link.is_symlink():
            game_link.unlink()
        game_link.symlink_to(game)
        startscript = data / "startscript.txt"
        startscript.write_text("""[GAME]
{
 MapName=Quicksilver Remake 1.24;
 GameType=Beyond All Reason $VERSION;
 GameStartDelay=0;
 StartPosType=0;
 RecordDemo=0;
 MyPlayerName=Validation;
 IsHost=1;
 FixedRNGSeed=1;
 MaxUnits=2000;
 HostPort=49410;
 [MODOPTIONS] { deathmode=neverend; debugcommands=1:cheat|2:godmode|3:globallos; }
 [ALLYTEAM0] { }
 [ALLYTEAM1] { }
 [ALLYTEAM2] { }
 [TEAM0] { allyteam=0; teamleader=0; }
 [TEAM1] { allyteam=1; teamleader=0; }
 [TEAM2] { allyteam=2; teamleader=0; }
 [PLAYER0] { name=Validation; team=0; }
}
""")
        config = data / "springsettings.cfg"
        config.write_text("LuaSocketEnabled = 0\nUseHighResTimer = 1\nMaxSpeed = 20\nMinSpeed = 20\nServerSleepTime = 1\n")
        command = [str(engine), "--isolation", "--write-dir", str(data), "--config", str(config), str(startscript)]
        metadata = {
            "command": command,
            "pr_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
            "gadget_sha256": hashlib.sha256((game / target_path).read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256((harness).read_bytes()).hexdigest(),
        }
        with (data / "engine.log").open("w") as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=150)
        metadata["returncode"] = result.returncode
        (data / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(variant, "exit", result.returncode, flush=True)
        log = (data / "engine.log").read_text(errors="replace")
        for line in log.splitlines():
            if "PR9541_RESULT" in line or "PR9541_CALLBACK_REBUILT" in line or "RunCallInTraceback" in line:
                print(line, flush=True)
        assert result.returncode == 0 and "PR9541_RESULT failures=0" in log, "isolated test failed: " + variant
        checks = re.findall(r"PR9541_CHECK \S+ (PASS|FAIL)", log)
        assert len(checks) == 544 and set(checks) == {"PASS"}, "missing or failed assertions: " + variant
    finally:
        game_link = data / "games/validation.sdd"
        if game_link.is_symlink():
            game_link.unlink()
        shutil.rmtree(game)
