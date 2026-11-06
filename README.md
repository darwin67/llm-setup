# Personal LLM setup

Personal LLM setup, skills, and configuration used across tools.

The layout is unchanged:

- `amp/user/AGENTS.md` and `amp/user/prompts.json`: personal guidance and prompts.
- `amp/user/skills/`: personal skills and supporting resources.
- `amp/user/plugins/`: personal plugins, tests, and bundled skills.
- `scripts/` and `tests/`: validation and guarded sync tools.
- `.agents/`: orb setup and resume hooks.

## Amp sync

On pushes to `master`, GitHub Actions validates the setup and publishes only the
packages selected in `amp-sync.json` to `darwin67/-/skills` and
`darwin67/-/plugins`. No workspace packages are published. Guidance and prompts
remain agent-assisted, not automatically applied by CI; account preferences and
other `settings.json` content are excluded. See [Amp content](amp/README.md).

Before the first push to `master`, add the GitHub Actions repository secret
[`AMP_API_KEY`](https://github.com/darwin67/llm-setup/settings/secrets/actions)
with an Amp access token permitted to write your User Skills and User Plugins
repositories. Do not put the token in this repository or a conversation.

The manifest pins a one-time handoff from the former source repository and its
published revision. The first sync changes ownership metadata only: every
managed package must match both the old baseline and the new source. Destination
drift, wrong scopes, and any other source revision are rejected. Later publishes
use the normal source ancestry and drift checks. Remove `migrate_from` after both
user repositories have successfully migrated; do not update its pin to bypass
unexpected live changes.

## Development

Dependencies come from the locked Nix development environment. `.agents/setup`
installs upstream Nix when needed and caches the environment; `.agents/resume`
activates cached inputs without installing anything. Run:

```sh
nix develop --command python scripts/sync_repositories.py --check
nix develop --command python scripts/sync_amp.py --check
nix develop --command python -m unittest discover -s tests -v
nix develop --command bun test amp/user/plugins
nix develop --command actionlint
bash -n .agents/setup .agents/resume
```
