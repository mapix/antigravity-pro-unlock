---
name: antigravity-pro-unlock
description: Expose shipped local Antigravity Pro features on macOS, including Swarm and its native UI, Boost, and Teamwork. Use when these commands are missing, when restoring a local patch, or when checking feature gates after an upgrade.
license: MIT
metadata:
  version: "1.2.0"
  platform: macos-arm64
  python: ">=3.9"
---

# Antigravity Pro Unlock

Enable the requested local feature gates in the installed Antigravity application. Preserve its data, gateway configuration, model selection, account authentication, quotas and administrator controls. “Pro Unlock” names this project's local feature patch; it does not grant a subscription.

Patching requires macOS Apple Silicon, Python 3.9+ and the macOS `codesign`, `ditto`, `ps`, and `open` commands.

## Supported features

| Feature | Verified application versions | What to observe |
| --- | --- | --- |
| Swarm | 2.31.0, 2.31.2 | `/swarm`, Open the Swarm UI, Board / Members / Graph |
| Boost | 2.31.2 | `/boost` in the command menu |
| Teamwork | 2.31.2 | `/teamwork` in the command menu |

Boost and Teamwork command visibility has been verified; their task effectiveness has not been benchmarked. They use separate native implementations.

## Execute from another harness

Use Codex, Claude Code, Cursor, OpenCode, another external harness, or a terminal. Do not execute this patch from an Antigravity task: quitting the app would terminate the patcher and its recovery channel. The script rejects Antigravity ancestors and agent environments for mutations.

Resolve `scripts/antigravity_pro_unlock.py` relative to this skill directory and use its absolute path when working elsewhere. The examples below assume this skill directory is the working directory.

## Workflow

1. Run `inspect` with the requested features. Check the application version, native contract, active tasks and flags. A matching version alone is insufficient.
2. Run `prepare` for the requested features. It backs up the complete source application and configurations, then signs a staged application. Save the returned plan path.
3. When tasks are active, use the user's existing restart authorization, or wait/ask before interrupting them. Quit the app completely from the external harness. `apply` refuses a running app.
4. Run `apply --plan PLAN --restart`. Source and staged fingerprints are checked before the transactional swap.
5. Run `verify --plan PLAN`. Check authentication, original config/data namespaces, requested flags and durable conversation-file identities. Observe the actual requested commands in the UI; do not submit paid test tasks merely to check a menu.
6. For Swarm, if the native panel is absent, run `panel` and verify **Open the Swarm UI** or **+ → Extensions → Swarm** opens Board, Members and Graph. A skill file or a running sidecar alone is insufficient.

```sh
python3 scripts/antigravity_pro_unlock.py inspect --features swarm,boost,teamwork
python3 scripts/antigravity_pro_unlock.py prepare --features swarm,boost,teamwork
python3 scripts/antigravity_pro_unlock.py apply --plan /returned/plan.json --restart
python3 scripts/antigravity_pro_unlock.py verify --plan /returned/plan.json
python3 scripts/antigravity_pro_unlock.py panel
```

For the Pro feature bundle, explicitly request `swarm,boost,teamwork`. For a specific feature, select only that feature. The script default remains Swarm; omitted features are preserved.

### Extend a previous patch

When adding features to a compact patch, supply its verified previous plan:

```sh
python3 scripts/antigravity_pro_unlock.py prepare --features swarm,boost,teamwork --base-plan /previous/verified/plan.json
```

The script validates the current fingerprint, source backup, saved defaults offset/length and whitespace-only padding before reusing capacity. A missing or stale plan requires investigation; do not bypass validation.

New plans use `~/.local/share/antigravity-pro-unlock/`. Existing plans under `~/.local/share/antigravity-swarm-patch/` remain usable by their absolute `--plan` or `--base-plan` paths. Do not relocate application data or legacy backup contents during this rename.

## Upgrade and recovery

Vendor upgrades usually replace patched application files. Inspect again, validate the new release and prepare a fresh plan if needed. Use vendor-enabled features when already available. Unsupported versions/features are refused; investigate their native contracts before extending the support table.

If startup or verification fails, quit the application and restore its verified source backup:

```sh
python3 scripts/antigravity_pro_unlock.py restore --plan /returned/plan.json --restart
```

An extension plan restores the previous working patch; an initial plan restores the vendor app. Do not restore an older application over a newer vendor update. Application rollback preserves existing conversation data.

After successful UI verification, retain the newest verified source backup and plan. Remove obsolete app backups or redundant staging/displaced copies only when requested; preserve unrelated configuration backups and recorded native hashes.

Read `references/mechanics.md` when adapting a release or diagnosing defaults capacity, signing, recovery or panel discovery. Report the actual verification boundary and recovery path.
