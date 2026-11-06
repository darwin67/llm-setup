import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_repositories.py"


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.target = Path(self.temp.name) / "target"
        for repo in (self.source, self.target):
            repo.mkdir()
            self.git(repo, "init", "-q")
            self.git(repo, "config", "user.name", "Publishing test")
            self.git(repo, "config", "user.email", "test@example.invalid")
            self.git(repo, "config", "commit.gpgsign", "false")
            self.skill(repo, "alpha-skill", "Alpha original")
            self.skill(repo, "beta-skill", "Beta original")
        (self.target / "unmanaged.txt").write_text("Keep this unrelated file\n")
        self.skill(self.target, "unmanaged-skill", "Keep this unrelated skill")
        self.commit(self.target)
        config = {
            "source_repository": "test/skills",
            "repositories": {"workspace:team": {"skills": {
                "alpha-skill": "skills/alpha-skill", "beta-skill": "skills/beta-skill",
            }, "plugins": {}}, "user": {"skills": {}, "plugins": {}}},
        }
        (self.source / "amp-sync.json").write_text(json.dumps(config))
        self.commit(self.source)

    def git(self, repo, *args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    def commit(self, repo):
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-qm", "Fixture change")

    def skill(self, repo, name, body):
        if repo == self.source:
            repo = repo / "skills"
        directory = repo / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: A test skill.\n---\n\n{body}\n"
        )

    def sync(self, success=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--target", str(self.target),
             "--scope", "workspace:team", "--kind", "skills"],
            cwd=self.source, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def bootstrap(self):
        self.sync()
        self.commit(self.target)

    def test_first_publish_can_add_listed_skills_to_a_new_destination(self):
        for name in ("alpha-skill", "beta-skill"):
            shutil.rmtree(self.target / name)
        self.commit(self.target)
        self.sync()
        self.assertIn("Alpha original", (self.target / "alpha-skill/SKILL.md").read_text())
        self.assertIn("Beta original", (self.target / "beta-skill/SKILL.md").read_text())
        self.assertIn("Keep this unrelated skill", (self.target / "unmanaged-skill/SKILL.md").read_text())

    def test_bootstrap_update_resources_and_noop_preserve_unmanaged_content(self):
        self.bootstrap()
        self.skill(self.source, "alpha-skill", "Alpha updated independently")
        resource = self.source / "skills/alpha-skill/reference/guide.md"
        resource.parent.mkdir()
        resource.write_text("Nested supporting content\n")
        self.commit(self.source)
        self.sync()
        self.assertEqual((self.target / "alpha-skill/SKILL.md").read_bytes(),
                         (self.source / "skills/alpha-skill/SKILL.md").read_bytes())
        self.assertEqual((self.target / "alpha-skill/reference/guide.md").read_text(),
                         "Nested supporting content\n")
        self.assertEqual((self.target / "unmanaged.txt").read_text(), "Keep this unrelated file\n")
        self.assertIn("Keep this unrelated skill", (self.target / "unmanaged-skill/SKILL.md").read_text())
        self.assertIn("Beta original", (self.target / "beta-skill/SKILL.md").read_text())
        self.commit(self.target)
        self.sync()
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")

    def test_ignored_local_files_are_not_published(self):
        (self.source / ".gitignore").write_text("local-notes.txt\n")
        (self.source / "skills/alpha-skill/local-notes.txt").write_text("Private local notes\n")
        self.commit(self.source)
        self.sync()
        self.assertFalse((self.target / "alpha-skill/local-notes.txt").exists())
        self.assertEqual((self.target / "alpha-skill/SKILL.md").read_bytes(),
                         (self.source / "skills/alpha-skill/SKILL.md").read_bytes())

    def test_source_cannot_be_its_own_destination(self):
        self.target = self.source
        self.assertIn("different checkouts", self.sync(success=False).stderr)
        self.assertEqual(self.git(self.source, "status", "--porcelain"), "")
        self.assertIn("Alpha original", (self.source / "skills/alpha-skill/SKILL.md").read_text())

    def test_manifest_controls_added_and_removed_skills(self):
        self.bootstrap()
        self.skill(self.source, "gamma-skill", "New skill")
        self.commit(self.source)
        self.sync()
        self.assertFalse((self.target / "gamma-skill").exists())
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        manifest["repositories"]["workspace:team"]["skills"] = {
            "beta-skill": "skills/beta-skill", "gamma-skill": "skills/gamma-skill",
        }
        config.write_text(json.dumps(manifest))
        self.commit(self.source)
        self.sync()
        self.assertFalse((self.target / "alpha-skill").exists())
        self.assertTrue((self.source / "skills/alpha-skill").exists())
        self.assertIn("New skill", (self.target / "gamma-skill/SKILL.md").read_text())
        state = json.loads((self.target / ".llm-skills-sync.json").read_text())
        self.assertEqual(set(state["skills"]), {"beta-skill", "gamma-skill"})
        self.assertEqual(state["source_commit"], self.git(self.source, "rev-parse", "HEAD"))

    def test_missing_listed_skill_does_not_delete_published_content(self):
        self.bootstrap()
        shutil.rmtree(self.source / "skills/alpha-skill")
        self.commit(self.source)
        self.assertIn("Missing package", self.sync(success=False).stderr)
        self.assertIn("Alpha original", (self.target / "alpha-skill/SKILL.md").read_text())
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")

    def test_invalid_names_and_paths_fail_without_destination_writes(self):
        self.bootstrap()
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        for entries in ([], {"../outside": "skills/alpha-skill"},
                        {"alpha-skill": "../skills/alpha-skill"},
                        {"alpha-skill": "skills/beta-skill"}):
            with self.subTest(entries=entries):
                manifest["repositories"]["workspace:team"]["skills"] = entries
                config.write_text(json.dumps(manifest))
                self.commit(self.source)
                self.sync(success=False)
                self.assertEqual(self.git(self.target, "status", "--porcelain"), "")

    def test_remote_drift_blocks_all_changes(self):
        self.bootstrap()
        self.skill(self.target, "alpha-skill", "Independent remote edit")
        self.commit(self.target)
        before = self.git(self.target, "rev-parse", "HEAD")
        self.skill(self.source, "beta-skill", "This must not be copied")
        self.commit(self.source)
        self.assertIn("Drift detected", self.sync(success=False).stderr)
        self.assertEqual(self.git(self.target, "rev-parse", "HEAD"), before)
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")
        self.assertIn("Beta original", (self.target / "beta-skill/SKILL.md").read_text())

    def test_first_publish_refuses_existing_content_that_differs_from_source(self):
        self.skill(self.target, "beta-skill", "Remote edit before first publish")
        self.commit(self.target)
        self.assertIn("Drift detected", self.sync(success=False).stderr)
        self.assertFalse((self.target / ".llm-skills-sync.json").exists())
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")

    def test_unmanaged_name_collision_is_not_overwritten(self):
        self.bootstrap()
        self.skill(self.source, "unmanaged-skill", "Must not replace the destination")
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        manifest["repositories"]["workspace:team"]["skills"]["unmanaged-skill"] = "skills/unmanaged-skill"
        config.write_text(json.dumps(manifest))
        self.commit(self.source)
        self.assertIn("unmanaged package", self.sync(success=False).stderr)
        self.assertIn("Keep this unrelated skill", (self.target / "unmanaged-skill/SKILL.md").read_text())
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")

    def test_older_source_revision_cannot_roll_back_a_newer_publish(self):
        self.bootstrap()
        older = self.git(self.source, "rev-parse", "HEAD")
        self.skill(self.source, "alpha-skill", "Newer deployed content")
        self.commit(self.source)
        self.sync()
        self.commit(self.target)
        self.git(self.source, "checkout", "-q", older)
        self.assertIn("older or unrelated", self.sync(success=False).stderr)
        self.assertIn("Newer deployed content", (self.target / "alpha-skill/SKILL.md").read_text())

    def test_source_repository_identity_must_match(self):
        self.bootstrap()
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        manifest["source_repository"] = "test/llm-setup"
        config.write_text(json.dumps(manifest))
        self.commit(self.source)
        self.assertIn("another source", self.sync(success=False).stderr)
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")

    def test_pinned_source_handoff_preserves_packages_and_drift_guards(self):
        self.bootstrap()
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        baseline = json.loads((self.target / ".llm-skills-sync.json").read_text())
        previous = {key: baseline[key] for key in ("source_repository", "source_commit")}
        manifest["source_repository"] = "personal/llm-setup"
        manifest["migrate_from"] = {**previous, "source_commit": "0" * 40}
        config.write_text(json.dumps(manifest))
        self.commit(self.source)
        self.assertIn("another source", self.sync(success=False).stderr)
        manifest["migrate_from"] = previous
        config.write_text(json.dumps(manifest))
        self.skill(self.source, "alpha-skill", "Cannot change content during handoff")
        self.commit(self.source)
        self.assertIn("preserve every managed package", self.sync(success=False).stderr)
        self.skill(self.source, "alpha-skill", "Alpha original")
        self.commit(self.source)
        self.skill(self.target, "beta-skill", "Independent edit")
        self.commit(self.target)
        self.assertIn("Drift detected", self.sync(success=False).stderr)
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")
        self.skill(self.target, "beta-skill", "Beta original")
        self.commit(self.target)
        before = {name: self.git(self.target, "rev-parse", f"HEAD:{name}")
                  for name in ("alpha-skill", "beta-skill", "unmanaged-skill", "unmanaged.txt")}
        # The personal repository starts fresh, without the LLC's history.
        self.git(self.source, "checkout", "--orphan", "personal-source")
        self.commit(self.source)
        self.sync()
        updated = json.loads((self.target / ".llm-skills-sync.json").read_text())
        self.assertEqual(updated["source_repository"], "personal/llm-setup")
        self.assertEqual(updated["source_commit"], self.git(self.source, "rev-parse", "HEAD"))
        self.assertEqual(updated["skills"], baseline["skills"])
        self.commit(self.target)
        self.assertEqual(before, {name: self.git(self.target, "rev-parse", f"HEAD:{name}") for name in before})
        self.sync()
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")
        self.skill(self.source, "alpha-skill", "Normal update after handoff")
        self.commit(self.source)
        self.sync()
        self.assertIn("Normal update after handoff", (self.target / "alpha-skill/SKILL.md").read_text())

    def test_user_publish_cannot_adopt_workspace_managed_state(self):
        self.bootstrap()
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        manifest["repositories"]["user"]["skills"] = manifest["repositories"]["workspace:team"]["skills"]
        config.write_text(json.dumps(manifest))
        self.commit(self.source)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--target", str(self.target), "--scope", "user", "--kind", "skills"],
            cwd=self.source, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another scope", result.stderr)
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")

    def test_configuration_is_never_published_with_skills(self):
        (self.source / "amp").mkdir()
        (self.source / "amp/prompts.json").write_text('[]')
        self.commit(self.source)
        self.sync()
        self.assertFalse((self.target / "amp").exists())
        self.assertFalse((self.target / "skills").exists())
        self.assertIn("Alpha original", (self.target / "alpha-skill/SKILL.md").read_text())
        self.assertIn("Keep this unrelated skill", (self.target / "unmanaged-skill/SKILL.md").read_text())

    def test_personal_skill_variant_and_plugins_publish_only_to_selected_scope(self):
        personal = self.source / "amp/user/skills/alpha-skill"
        personal.mkdir(parents=True)
        (personal / "SKILL.md").write_text(
            "---\nname: alpha-skill\ndescription: Personal variant.\n---\nPersonal content\n"
        )
        plugin = self.source / "amp/user/plugins/shopify"
        (plugin / "skills/read-shop/reference").mkdir(parents=True)
        (plugin / "index.ts").write_text("export default function () {}\n")
        (plugin / "skills/read-shop/SKILL.md").write_text("Bundled instructions\n")
        (plugin / "skills/read-shop/reference/setup.md").write_text("Supporting setup\n")
        single = self.source / "amp/user/plugins/standalone.ts"
        single.write_text("export default function () {}\n")
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        manifest["repositories"]["user"] = {
            "skills": {"alpha-skill": "amp/user/skills/alpha-skill"},
            "plugins": {"shopify": "amp/user/plugins/shopify", "standalone.ts": "amp/user/plugins/standalone.ts"},
        }
        config.write_text(json.dumps(manifest))
        self.commit(self.source)
        self.sync()
        self.assertIn("Alpha original", (self.target / "alpha-skill/SKILL.md").read_text())
        for kind in ("skills", "plugins"):
            destination = Path(self.temp.name) / kind
            destination.mkdir()
            self.git(destination, "init", "-q")
            self.git(destination, "config", "user.name", "Publishing test")
            self.git(destination, "config", "user.email", "test@example.invalid")
            self.git(destination, "config", "commit.gpgsign", "false")
            (destination / "unmanaged.txt").write_text("Keep me\n")
            self.commit(destination)
            command = [sys.executable, str(SCRIPT), "--target", str(destination),
                       "--scope", "user", "--kind", kind]
            result = subprocess.run(command, cwd=self.source, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            if kind == "skills":
                self.assertIn("Personal content", (destination / "alpha-skill/SKILL.md").read_text())
                self.assertFalse((destination / "beta-skill").exists())
                self.assertFalse((destination / "shopify").exists())
            else:
                self.assertEqual((destination / "shopify/skills/read-shop/reference/setup.md").read_text(),
                                 "Supporting setup\n")
                self.assertEqual((destination / "standalone.ts").read_bytes(), single.read_bytes())
                self.assertFalse((destination / "alpha-skill").exists())
            self.assertFalse((destination / "amp").exists())
            self.assertEqual((destination / "unmanaged.txt").read_text(), "Keep me\n")
            self.commit(destination)
            result = subprocess.run(command, cwd=self.source, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.git(destination, "status", "--porcelain"), "")
            if kind == "plugins":
                (destination / "shopify/index.ts").write_text("Independent live edit\n")
                self.commit(destination)
                result = subprocess.run(command, cwd=self.source, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Drift detected", result.stderr)
                self.assertEqual((destination / "shopify/index.ts").read_text(), "Independent live edit\n")

    def test_empty_selection_does_not_publish_the_entire_source_tree(self):
        config = self.source / "amp-sync.json"
        manifest = json.loads(config.read_text())
        manifest["repositories"]["workspace:team"]["skills"] = {}
        config.write_text(json.dumps(manifest))
        self.commit(self.source)
        self.sync()
        self.assertFalse((self.target / "amp-sync.json").exists())
        self.assertIn("Alpha original", (self.target / "alpha-skill/SKILL.md").read_text())

    def test_invalid_skill_and_dirty_target_fail_without_writes(self):
        self.bootstrap()
        (self.target / "local.txt").write_text("Do not discard local work")
        self.assertIn("must be clean", self.sync(success=False).stderr)
        self.assertEqual((self.target / "local.txt").read_text(), "Do not discard local work")
        (self.target / "local.txt").unlink()
        (self.source / "skills/alpha-skill/SKILL.md").write_text("Missing metadata")
        self.commit(self.source)
        self.assertIn("missing YAML frontmatter", self.sync(success=False).stderr)
        self.assertIn("Alpha original", (self.target / "alpha-skill/SKILL.md").read_text())
        (self.source / "skills/alpha-skill/SKILL.md").write_text("---\n- invalid\n---\n")
        self.commit(self.source)
        self.assertIn("invalid or mismatched skill name", self.sync(success=False).stderr)
        self.assertEqual(self.git(self.target, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
