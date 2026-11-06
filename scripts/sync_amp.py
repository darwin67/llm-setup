#!/usr/bin/env python3
"""Export Amp tool snapshots or plan guarded updates; never call private APIs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


STATE = ".sync-state.json"
GUIDANCE = {"user": "global_agent_guidance", "workspace": "workspace_global_agent_guidance"}
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def directory(root, scope):
    if scope == "user":
        return root / "user"
    kind, _, name = scope.partition(":")
    if kind != "workspace" or not NAME.fullmatch(name):
        raise ValueError(f"Invalid scope: {scope}")
    return root / "workspaces" / name


def guidance(scope):
    return GUIDANCE[scope.split(":")[0]]


def prompts_by_name(prompts):
    result = {}
    for prompt in prompts:
        name = prompt["name"]
        if (not NAME.fullmatch(name) or name in result
                or not isinstance(prompt["title"], str) or len(prompt["title"]) > 80
                or not isinstance(prompt["body"], str) or len(prompt["body"]) > 20000):
            raise ValueError("Invalid or duplicate prompt")
        result[name] = {key: prompt[key] for key in ("title", "body")}
    return result


def snapshot(path, managed_scopes):
    raw = json.loads(path.read_text())
    account = next(item["value"] for item in raw["settings"]
                   if item["key"] == "username" and item["scope"] == "user")
    if not isinstance(account, str) or not account:
        raise ValueError("Snapshot must identify the signed-in username")
    scopes, metadata = {}, {}
    for item in raw["settings"]:
        if item["key"] not in GUIDANCE.values():
            continue
        scope = item["scope"]
        if scope == "workspace":
            scope += ":" + item["workspaceName"]
        if scope not in managed_scopes:
            continue
        directory(Path(), scope)
        if item["key"] != guidance(scope) or scope in scopes or not item["editable"]:
            raise ValueError(f"Invalid, duplicate, or uneditable guidance: {scope}")
        if item["value"] is not None and not isinstance(item["value"], str):
            raise ValueError("Guidance must be text or null")
        prompts = raw["prompts"][scope]
        scopes[scope] = {"guidance": item["value"],
                         "prompts": prompts_by_name(prompts) if prompts is not None else None}
        metadata[scope] = item
    if scopes.keys() != managed_scopes:
        raise ValueError("Snapshot must include guidance for every configured scope")
    return {"account": account, "scopes": scopes}, metadata


def read_local(root, state):
    scopes = {}
    for scope, baseline in state["scopes"].items():
        folder = directory(root, scope)
        text = None
        if (folder / "AGENTS.md").exists():
            with (folder / "AGENTS.md").open(encoding="utf-8", newline="") as file:
                text = file.read()
        prompts = json.loads((folder / "prompts.json").read_text())
        if (prompts is None) != (baseline["prompts"] is None):
            raise ValueError(f"{scope}: refresh prompts from Amp before changing their managed status")
        scopes[scope] = {"guidance": text,
                         "prompts": prompts_by_name(prompts) if prompts is not None else None}
    return {"account": state["account"], "scopes": scopes}


def fingerprints(config):
    return {"account": config["account"], "scopes": {
        scope: {"guidance": digest(values["guidance"]), "prompts": {
            name: digest(value) for name, value in values["prompts"].items()
        } if values["prompts"] is not None else None}
        for scope, values in config["scopes"].items()
    }}


def require_complete(live, state):
    if live["account"] != state["account"]:
        raise ValueError("Snapshot belongs to a different Amp account")
    for scope, values in state["scopes"].items():
        if (scope not in live["scopes"] or
                (values["prompts"] is not None and live["scopes"][scope]["prompts"] is None)):
            raise ValueError(f"Incomplete snapshot: {scope}")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def export(root, live):
    state_path = root / STATE
    managed_scopes = set()
    if state_path.exists():
        state = json.loads(state_path.read_text())
        require_complete(live, state)
        managed_scopes = state["scopes"].keys()
        local = read_local(root, state)
        desired, remote = fingerprints(local), fingerprints(live)
        for scope, values in desired["scopes"].items():
            baseline, current = state["scopes"][scope], remote["scopes"][scope]
            if values["guidance"] not in (baseline["guidance"], current["guidance"]):
                raise ValueError(f"Unapplied local edits: {scope}/AGENTS.md")
            if baseline["prompts"] is not None:
                for name in baseline["prompts"].keys() | values["prompts"].keys():
                    if values["prompts"].get(name) not in (baseline["prompts"].get(name), current["prompts"].get(name)):
                        raise ValueError(f"Unapplied local prompt edits: {scope}/{name}")
    for scope in live["scopes"].keys() - managed_scopes:
        if directory(root, scope).exists():
            raise ValueError("Refusing to overwrite an export without sync state")
    for scope, values in live["scopes"].items():
        folder = directory(root, scope)
        folder.mkdir(parents=True, exist_ok=True)
        text = values["guidance"]
        if isinstance(text, str):
            (folder / "AGENTS.md").write_text(text, encoding="utf-8", newline="")
        else:
            (folder / "AGENTS.md").unlink(missing_ok=True)
        write_json(folder / "prompts.json", [
            {"name": name, **value} for name, value in sorted(values["prompts"].items())
        ] if values["prompts"] is not None else None)
    write_json(state_path, fingerprints(live))


def plan(root, live, metadata):
    state = json.loads((root / STATE).read_text())
    require_complete(live, state)
    local = read_local(root, state)
    changes = []
    for scope, values in local["scopes"].items():
        current, baseline = live["scopes"][scope], state["scopes"][scope]
        if values["guidance"] != current["guidance"]:
            if digest(current["guidance"]) != baseline["guidance"]:
                raise ValueError(f"Drift detected: {scope}/AGENTS.md; reconcile before applying")
            parameters = {"key": guidance(scope), "value": values["guidance"]}
            if scope.startswith("workspace:"):
                parameters["workspace"] = scope.split(":", 1)[1]
            changes.append({"topic": "settings", "operation": "update", "parameters": parameters,
                            "requires_approval": metadata[scope]["risky"]})
        if values["prompts"] is None:
            continue
        for name in sorted(baseline["prompts"].keys() | values["prompts"].keys()):
            desired, remote = values["prompts"].get(name), current["prompts"].get(name)
            if desired == remote:
                continue
            if (digest(remote) if remote is not None else None) != baseline["prompts"].get(name):
                raise ValueError(f"Drift detected in prompt: {scope}/{name}")
            change = {"topic": "prompts", "operation": "set" if desired else "delete",
                      "parameters": {"name": name, **(desired or {})}, "requires_approval": True}
            if scope.startswith("workspace:"):
                del change["topic"]
                change.update(manual=True, workspace=scope.split(":", 1)[1])
            changes.append(change)
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("amp"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--export", type=Path, metavar="SNAPSHOT")
    mode.add_argument("--plan", type=Path, metavar="SNAPSHOT")
    args = parser.parse_args()
    try:
        managed_scopes = json.loads((args.root.parent / "amp-sync.json").read_text())["repositories"].keys()
        state_path = args.root / STATE
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["scopes"].keys() != managed_scopes:
                raise ValueError("Sync state scopes must match amp-sync.json; split the baseline when moving scopes")
        if args.check:
            state = json.loads(state_path.read_text())
            local = read_local(args.root, state)
            print(f"Validated Amp configuration for {local['account']}")
        else:
            live, metadata = snapshot(args.export or args.plan, managed_scopes)
            if args.export:
                export(args.root, live)
                print(f"Exported Amp configuration for {live['account']}")
            else:
                print(json.dumps(plan(args.root, live, metadata), indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        print(f"Sync failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
