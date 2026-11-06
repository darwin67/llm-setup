#!/usr/bin/env python3
"""Validate scoped skills/plugins and prepare an Amp checkout for a normal Git push."""

import argparse
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

import yaml


NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def validate(source, scope, kind):
    entries = json.loads((source / "amp-sync.json").read_text())["repositories"][scope][kind]
    if not isinstance(entries, dict):
        raise ValueError(f"{kind} must map names to source paths")
    packages = {}
    for name, relative in entries.items():
        stem = name.removesuffix(".ts").removesuffix(".js") if kind == "plugins" else name
        if not NAME.fullmatch(stem) or len(stem) > 64:
            raise ValueError(f"Invalid {kind} name: {name}")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path.name != name:
            raise ValueError(f"Invalid source path: {relative}")
        path = source / path
        if not path.exists():
            raise ValueError(f"Missing package: {relative}")
        if any(parent.is_symlink() for parent in [path, *path.parents] if parent != source.parent):
            raise ValueError(f"{name}: symlinks cannot be published")
        if kind == "skills":
            text = (path / "SKILL.md").read_text()
            if not text.startswith("---\n") or "\n---\n" not in text[4:]:
                raise ValueError(f"{name}: missing YAML frontmatter")
            metadata = yaml.safe_load(text[4:].split("\n---\n", 1)[0])
            if not isinstance(metadata, dict) or metadata.get("name") != name:
                raise ValueError(f"{name}: invalid or mismatched skill name")
            description = metadata.get("description")
            if not isinstance(description, str) or not description.strip() or len(description) > 1024:
                raise ValueError(f"{name}: description must contain 1–1024 characters")
        elif path.is_dir():
            if not any((path / entry).is_file() for entry in ("index.ts", "index.js")):
                raise ValueError(f"{name}: plugin directory needs index.ts or index.js")
        elif path.suffix not in (".ts", ".js"):
            raise ValueError(f"{name}: plugin file must be TypeScript or JavaScript")
        for item in [path, *path.rglob("*")]:
            if item.is_symlink():
                raise ValueError(f"{name}: symlinks cannot be published")
            if item.is_file() and "\0" in item.read_text():
                raise ValueError(f"{name}: only text resources can be published")
        packages[name] = path
    return packages


def tree(repo, name):
    result = git(repo, "ls-tree", "HEAD", "--", name)
    return result.split()[2] if result else None


def prepare(source, target, scope, kind):
    if source == target:
        raise ValueError("Source and target must be different checkouts")
    packages = validate(source, scope, kind)
    config = json.loads((source / "amp-sync.json").read_text())
    for repo in (source, target):
        if git(repo, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError(f"Checkout must be clean: {repo}")
    current = {name: tree(source, str(path.relative_to(source))) for name, path in packages.items()}
    if any(value is None for value in current.values()):
        raise ValueError("Every package must be committed in the source checkout")
    state_path = target / f".llm-{kind}-sync.json"
    if state_path.is_symlink():
        raise ValueError("Sync state must not be a symlink")
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    # Without prior state, adopt existing packages only when they match the source.
    expected = state[kind] if state else {
        name: current[name] for name in packages if tree(target, name) is not None
    }
    migrating = False
    if state:
        if state["source_repository"] != config["source_repository"]:
            previous = {key: state[key] for key in ("source_repository", "source_commit")}
            if config.get("migrate_from") != previous:
                raise ValueError("Target is managed by another source repository")
            if current != expected:
                raise ValueError("Source migration must preserve every managed package unchanged")
            migrating = True
        if state["scope"] != scope:
            raise ValueError("Target is managed by another scope")
        if not migrating:
            ancestor = subprocess.run(
                ["git", "-C", str(source), "merge-base", "--is-ancestor", state["source_commit"], "HEAD"],
                capture_output=True,
            )
            if ancestor.returncode:
                raise ValueError("Refusing an older or unrelated source revision; fetch full source history")
    for name, expected_tree in expected.items():
        stem = name.removesuffix(".ts").removesuffix(".js") if kind == "plugins" else name
        if not NAME.fullmatch(stem) or not isinstance(expected_tree, str):
            raise ValueError("Invalid managed package in sync state")
        if tree(target, name) != expected_tree:
            raise ValueError(f"Drift detected in {name}; reconcile the Amp edit in the source repo first")
    for name in packages.keys() - expected.keys():
        if tree(target, name) is not None:
            raise ValueError(f"Refusing to replace unmanaged package: {name}")
    if state and current == expected and not migrating:
        print(f"{scope} {kind} already synchronized")
        return
    archives = {name: subprocess.check_output([
        "git", "-C", str(source), "archive", "HEAD", str(path.relative_to(source))
    ]) for name, path in packages.items()}
    # All drift/collision checks finish before any target files are changed.
    for name in expected.keys() | packages.keys():
        path = target / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    for name, archive in archives.items():
        prefix = str(packages[name].relative_to(source))
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:
            members = []
            for member in files:
                if member.name != prefix and not member.name.startswith(prefix + "/"):
                    continue
                member.name = name + member.name[len(prefix):]
                members.append(member)
            files.extractall(target, members=members, filter="data")
    state_path.write_text(json.dumps({
        "source_repository": config["source_repository"],
        "source_commit": git(source, "rev-parse", "HEAD"),
        "scope": scope,
        kind: current,
    }, indent=2, sort_keys=True) + "\n")
    print(f"Prepared {len(packages)} {scope} {kind}; unmanaged target content left untouched")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--target", type=Path)
    parser.add_argument("--scope", help="user or workspace:<name>")
    parser.add_argument("--kind", choices=("skills", "plugins"))
    args = parser.parse_args()
    source = Path.cwd()
    try:
        if args.check:
            repositories = json.loads((source / "amp-sync.json").read_text())["repositories"]
            for scope in repositories:
                if scope != "user" and not re.fullmatch(r"workspace:[a-z0-9]+(?:-[a-z0-9]+)*", scope):
                    raise ValueError(f"Invalid scope: {scope}")
                for kind in ("skills", "plugins"):
                    print(f"Validated {len(validate(source, scope, kind))} {scope} {kind}")
        else:
            if not args.scope or not args.kind:
                parser.error("--target requires --scope and --kind")
            prepare(source, args.target.resolve(), args.scope, args.kind)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print(f"Sync failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
