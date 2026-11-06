import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sync_amp.py"


class ConfigurationSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "amp"
        self.snapshot = Path(self.temp.name) / "snapshot.json"
        self.manifest = Path(self.temp.name) / "amp-sync.json"
        self.manifest.write_text(json.dumps({"repositories": {"user": {}, "workspace:team": {}}}))
        self.live = {"settings": [
            {"key": "username", "scope": "user", "value": "alice", "editable": False},
            {"key": "color_filters", "scope": "user", "value": False,
             "editable": True, "risky": False},
            {"key": "global_agent_guidance", "scope": "user", "value": "Personal guidance\n",
             "editable": True, "risky": False},
            {"key": "workspace_global_agent_guidance", "scope": "workspace", "workspaceName": "team",
             "value": "Different shared guidance", "editable": True, "risky": True},
            {"key": "workspace_puck_instructions", "scope": "workspace", "workspaceName": "team",
             "value": None, "editable": True, "risky": True},
        ], "prompts": {
            "user": [{"name": "review", "title": "Review", "body": "Original review instructions"}],
            "workspace:team": [{"name": "review", "title": "Shared Review", "body": "Shared instructions"}],
        }}
        self.run_sync("--export")

    def run_sync(self, mode, success=True):
        self.snapshot.write_text(json.dumps(self.live))
        command = [sys.executable, str(SCRIPT), "--root", str(self.root), mode]
        if mode != "--check":
            command.append(str(self.snapshot))
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_export_separates_scopes_preserves_values_and_is_idempotent(self):
        self.assertEqual((self.root / "user/AGENTS.md").read_text(), "Personal guidance\n")
        self.assertEqual((self.root / "workspaces/team/AGENTS.md").read_text(), "Different shared guidance")
        self.assertFalse(list(self.root.rglob("settings.json")))
        self.assertEqual(json.loads((self.root / "workspaces/team/prompts.json").read_text()),
                         self.live["prompts"]["workspace:team"])
        self.live["settings"][1]["value"] = True
        self.live["settings"][4]["value"] = "This must never be exported or planned"
        before = self.files()
        self.run_sync("--export")
        self.assertEqual(self.files(), before)
        self.assertEqual(json.loads(self.run_sync("--plan").stdout), [])
        self.run_sync("--check")

    def test_guidance_line_endings_round_trip_in_both_scopes(self):
        for index, ending in enumerate(("\r\n", "\r")):
            with self.subTest(ending=repr(ending)):
                self.root = Path(self.temp.name) / f"amp-{index}"
                personal = f"Personal café{ending}Second line{ending}"
                shared = f"Shared guidance{ending}Different final line"
                self.live["settings"][2]["value"] = personal
                self.live["settings"][3]["value"] = shared
                self.run_sync("--export")
                self.assertEqual((self.root / "user/AGENTS.md").read_bytes(), personal.encode("utf-8"))
                self.assertEqual((self.root / "workspaces/team/AGENTS.md").read_bytes(), shared.encode("utf-8"))
                before = self.files()
                self.assertEqual(json.loads(self.run_sync("--plan").stdout), [])
                self.run_sync("--export")
                self.assertEqual(self.files(), before)

    def test_plan_scopes_changes_and_requires_approval_without_applying(self):
        (self.root / "workspaces/team/AGENTS.md").write_text("New shared instructions")
        (self.root / "user/prompts.json").write_text(json.dumps([
            {"name": "review", "title": "Review", "body": "New review instructions"},
            {"name": "release-notes", "title": "Release Notes", "body": "Describe user-facing changes"},
        ]))
        before = self.files()
        changes = json.loads(self.run_sync("--plan").stdout)
        self.assertCountEqual(changes, [
            {"topic": "settings", "operation": "update", "parameters": {
                "key": "workspace_global_agent_guidance", "workspace": "team",
                "value": "New shared instructions"}, "requires_approval": True},
            {"topic": "prompts", "operation": "set", "parameters": {
                "name": "release-notes", "title": "Release Notes", "body": "Describe user-facing changes"},
             "requires_approval": True},
            {"topic": "prompts", "operation": "set", "parameters": {
                "name": "review", "title": "Review", "body": "New review instructions"},
             "requires_approval": True},
        ])
        self.assertEqual(self.files(), before)
        self.assertIn("Unapplied local", self.run_sync("--export", success=False).stderr)
        self.assertEqual(self.files(), before)
        self.live["settings"][3]["value"] = "New shared instructions"
        self.live["prompts"]["user"] = json.loads((self.root / "user/prompts.json").read_text())
        self.run_sync("--export")
        self.assertEqual(json.loads(self.run_sync("--plan").stdout), [])

    def test_remote_drift_blocks_entire_plan_and_export_can_pull_it(self):
        (self.root / "user/AGENTS.md").write_text("Pending personal edit")
        self.live["settings"][3]["value"] = "An independent remote edit"
        before = self.files()
        result = self.run_sync("--plan", success=False)
        self.assertIn("Drift detected", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.files(), before)
        (self.root / "user/AGENTS.md").write_text("Personal guidance\n")
        self.run_sync("--export")
        self.assertEqual((self.root / "workspaces/team/AGENTS.md").read_text(), "An independent remote edit")

    def test_wrong_account_or_incomplete_snapshot_cannot_change_export(self):
        before = self.files()
        self.live["settings"][0]["value"] = "bob"
        for mode in ("--plan", "--export"):
            self.assertIn("different Amp account", self.run_sync(mode, success=False).stderr)
        self.live["settings"][0]["value"] = "alice"
        self.live["settings"].pop(3)
        for mode in ("--plan", "--export"):
            self.assertIn("Snapshot must include", self.run_sync(mode, success=False).stderr)
        self.assertEqual(self.files(), before)

    def test_prompt_removal_is_explicit_and_unmanaged_remote_prompts_are_preserved(self):
        self.live["prompts"]["user"].append({"name": "remote-only", "title": "Remote Only", "body": "Keep this"})
        (self.root / "user/prompts.json").write_text("[]\n")
        changes = json.loads(self.run_sync("--plan").stdout)
        self.assertEqual(changes, [{"topic": "prompts", "operation": "delete",
                                  "parameters": {"name": "review"}, "requires_approval": True}])
        self.assertIn("Unapplied local prompt edits", self.run_sync("--export", success=False).stderr)
        self.live["prompts"]["user"].pop(0)
        self.run_sync("--export")
        prompts = json.loads((self.root / "user/prompts.json").read_text())
        self.assertEqual([prompt["name"] for prompt in prompts], ["remote-only"])

    def test_null_and_empty_guidance_round_trip_and_scope_paths_are_checked(self):
        self.live["settings"][2]["value"] = None
        self.live["settings"][3]["value"] = ""
        self.run_sync("--export")
        self.assertFalse((self.root / "user/AGENTS.md").exists())
        self.assertEqual((self.root / "workspaces/team/AGENTS.md").read_text(), "")
        self.run_sync("--check")
        self.assertEqual(json.loads(self.run_sync("--plan").stdout), [])
        before = self.files()
        self.live["settings"][3]["workspaceName"] = "../outside"
        self.assertIn("Snapshot must include", self.run_sync("--export", success=False).stderr)
        self.assertEqual(self.files(), before)

    def test_workspace_prompt_changes_are_manual_and_do_not_touch_personal_prompts(self):
        (self.root / "workspaces/team/prompts.json").write_text("[]\n")
        changes = json.loads(self.run_sync("--plan").stdout)
        self.assertEqual(changes, [{"operation": "delete",
                                  "parameters": {"name": "review"}, "requires_approval": True,
                                  "manual": True, "workspace": "team"}])
        self.assertIn("Unapplied local prompt edits", self.run_sync("--export", success=False).stderr)
        self.live["prompts"]["workspace:team"][0]["body"] = "Independent workspace edit"
        self.assertIn("Drift detected in prompt: workspace:team/review",
                      self.run_sync("--plan", success=False).stderr)

    def test_unexported_prompts_are_not_empty_or_deletions(self):
        self.root = Path(self.temp.name) / "unexported"
        shared = self.live["prompts"]["workspace:team"]
        self.live["prompts"]["workspace:team"] = None
        self.run_sync("--export")
        path = self.root / "workspaces/team/prompts.json"
        self.assertIsNone(json.loads(path.read_text()))
        self.assertEqual(json.loads(self.run_sync("--plan").stdout), [])
        path.write_text("[]\n")
        self.assertIn("refresh prompts", self.run_sync("--check", success=False).stderr)
        path.write_text("null\n")
        self.live["prompts"]["workspace:team"] = shared
        self.run_sync("--export")
        self.assertEqual(json.loads(path.read_text()), shared)
        self.live["prompts"]["workspace:team"] = None
        self.assertIn("Incomplete snapshot", self.run_sync("--export", success=False).stderr)

    def test_configured_scopes_isolate_exports_and_plans(self):
        for scope, folder, excluded in (("user", "user", "workspaces"),
                                        ("workspace:team", "workspaces/team", "user")):
            with self.subTest(scope=scope):
                self.root = Path(self.temp.name) / scope.replace(":", "-")
                self.manifest.write_text(json.dumps({"repositories": {scope: {}}}))
                self.run_sync("--export")
                self.assertTrue((self.root / folder / "AGENTS.md").exists())
                self.assertFalse((self.root / excluded).exists())
                state = json.loads((self.root / ".sync-state.json").read_text())
                self.assertEqual(set(state["scopes"]), {scope})
                self.assertEqual(json.loads(self.run_sync("--plan").stdout), [])
                self.run_sync("--check")
                # A refresh with both live scopes still cannot import the excluded one.
                self.run_sync("--export")
                self.assertFalse((self.root / excluded).exists())
                if scope.startswith("workspace:"):
                    self.live["settings"].pop(2)
                    self.run_sync("--export")
                    self.assertFalse((self.root / "user").exists())

    def test_manifest_changes_require_an_explicit_baseline_split(self):
        before = self.files()
        self.manifest.write_text(json.dumps({"repositories": {"workspace:team": {}}}))
        for mode in ("--check", "--export", "--plan"):
            self.assertIn("Sync state scopes must match", self.run_sync(mode, success=False).stderr)
            self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
