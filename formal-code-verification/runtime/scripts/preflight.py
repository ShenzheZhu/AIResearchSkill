#!/usr/bin/env python3
# Modified by AIResearchSkill: honor declared source directories in standalone preflight.
import argparse, json
from _common import project, state
import checkpoint
from orchestrate import valid_settings
import versioning

parser = argparse.ArgumentParser(description="Validate a target before agent-led FM-Agent analysis.")
parser.add_argument("--project", required=True)
parser.add_argument("--submodule", action="append", default=None)
args = parser.parse_args()
target = project(args)
saved = state.read_json(state.skill_dir(target) / "config.json", {})
inputs = state.active_record(target).get("inputs", {})
scopes = args.submodule if args.submodule is not None else inputs.get("submodules", saved.get("submodules", []))
issues = valid_settings(target, {"submodules": scopes, "knowledge": []})
if issues:
    result = {"ok": False, "project": str(target), "source_file_count": 0, "issues": issues}
else:
    scopes = [(target / item).resolve().relative_to(target).as_posix() for item in scopes]
    result = state.preflight(target, [] if "." in scopes else sorted(set(scopes)))
active_ref = state.git(target, "rev-parse", "--verify", "refs/fm-agent-skill/active", check=False)
if result["ok"] and active_ref and (checkpoint.root(target) / "HEAD").is_file():
    compatibility = versioning.checkpoint_compatibility(checkpoint.source_project(target))
    result["checkpoint_version"] = compatibility
    if not compatibility.get("compatible"):
        result["ok"] = False
        result["issues"].append("active checkpoint is incompatible with the installed runtime")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["ok"] else 2)
