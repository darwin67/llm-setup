# Personal Amp content

This repository manages darwin67's **personal** guidance, prompts, skills, and
plugins. The LLC's workspace configuration is maintained separately in
[chaba-dev/llm-setup](https://github.com/chaba-dev/llm-setup).

| Content | Location |
| --- | --- |
| Guidance | `user/AGENTS.md` |
| Prompts | `user/prompts.json` (confirmed empty at the original export) |
| Skills | `user/skills/` |
| Plugins | Shopify source, tests, and bundled instructions in `user/plugins/` |

`amp-sync.json` selects only the `user` scope. Exports and update plans ignore
workspace guidance and prompts even if they appear in a live snapshot.
Preferences, model pins, and other `settings.json` content are never exported.

## Guidance and prompts

`scripts/sync_amp.py` exports tool snapshots and prints guarded update plans;
it never writes account settings. `.sync-state.json` preserves account identity
and baseline hashes from the original export, split without changing those hashes.

To refresh, ask an Amp agent to:

1. Read `manage_amp` settings help, then get only `username` and
   `global_agent_guidance` for the user scope. Keep `key`, `scope`, `value`,
   `editable`, and `risky`.
2. Read personal prompts through `manage_amp` prompts help/list. A failed read
   is not an empty prompt list.
3. Save a temporary snapshot outside tracked files in this shape:

   ```json
   {
     "settings": ["the actual username and personal guidance tool records"],
     "prompts": {"user": []}
   }
   ```

4. Run `nix develop --command python scripts/sync_amp.py --export <snapshot>`,
   review the diff for private content, and delete the temporary snapshot.

Guidance preserves exact text and line endings. A missing `AGENTS.md` means null
(clear guidance); an empty file means an empty string. These are exported global
instructions, not development instructions for this repository. Prompts use
`name`, `title`, and `body`; `[]` means confirmed empty, while `null` means not
exported and not managed. Once exported, prompts cannot be disabled with null.

To apply edits, get a fresh snapshot and run
`nix develop --command python scripts/sync_amp.py --plan <snapshot>`. The script
rejects conflicting Amp edits and exports that would erase pending local work,
and preserves unmanaged prompts. All live writes require explicit user approval.
After applying, re-read live state, confirm the plan is empty, and export to
refresh the baseline. Inspect live state after failed writes before retrying.
Never change hashes to bypass conflicts.

## Skills and plugins

Discover the destinations with `amp skills repositories` and
`amp plugins repositories`. Use the User repository clone commands and canonical
cache locations documented by the building-skills/building-plugins skills.
Refresh clean clones with fetch and fast-forward before copying live edits here;
preserve bundled resources and review diffs. Never overwrite pending source
edits or copy destination `.llm-*-sync.json` files into the source.

`scripts/sync_repositories.py --check` validates selected packages. To prepare
a clean destination clone, use `--scope user`, `--kind skills` or `--kind plugins`,
and `--target <clone>`. Only selected committed packages are copied to the target
root. Unmanaged content stays untouched; removed manifest entries delete only
previously managed packages. Source identity, scope, ancestry, collision, and
drift guards run before any writes. See the root README for the pinned source
handoff used on the first publication.

On `master`, CI publishes personal skills and plugins using the `AMP_API_KEY`
GitHub Actions secret. Guidance and prompts remain agent-assisted. The Shopify
plugin reads credentials from Amp Secrets & Env Vars; only source, tests, and
instructions are tracked. Never export tokens, cookies, credentials, secret
values, or raw machine-local configuration.
