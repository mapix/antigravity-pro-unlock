---
name: antigravity-pro-unlock
description: Expose shipped local Antigravity Pro features on macOS, including Swarm, Boost, Teamwork, and Orchestrator, with a separate fixed Carbon choice. Use when commands are missing, when separating Carbon session modes, restoring a patch, or checking gates after an upgrade.
license: MIT
metadata:
  version: "1.5.0"
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
| Orchestrator | 2.31.2 / gateway | Carbon planning → Hydrogen execution → Carbon review |
| Carbon Direct | 2.31.2 / gateway / desktop UI | Separate picker entry; actual Carbon requests without phase handoffs |
| 2.33.0 Gateway | 2.33.0 / isolated language server | Carbon Direct and Orchestrator round trip with a local mock Gateway |

Boost and Teamwork command visibility has been verified; their task effectiveness has not been benchmarked. They use separate native implementations.

`--features pro` (or `all`) selects every inspected feature for the detected release. This is a local preset; account subscriptions and quota enforcement remain authoritative. Defaults still select Swarm only.

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
python3 scripts/antigravity_pro_unlock.py inspect --features pro
python3 scripts/antigravity_pro_unlock.py prepare --features pro
python3 scripts/antigravity_pro_unlock.py apply --plan /returned/plan.json --restart
python3 scripts/antigravity_pro_unlock.py verify --plan /returned/plan.json
python3 scripts/antigravity_pro_unlock.py panel
```

For the Pro feature bundle, explicitly request `pro`. For a specific feature, select only that feature. The script default remains Swarm; omitted features are preserved.

## Orchestrator model requirements

Resolve existing models from the authenticated gateway catalog. On 2.31.2 Carbon is M349, Hydrogen M340, and Argon M418. On 2.33.0 the inspected pair is Carbon M437 and Hydrogen M462. If the default Hydrogen ID is absent on 2.33.0, the script checks the configured Hydrogen Medium entry against M462. Reject missing, disabled, or differently mapped models.

The default prefers Carbon as planner and uses Hydrogen as executor. `--planner-models gemini-4-carbon` selects Carbon explicitly. Carbon → Hydrogen → Carbon was verified on an isolated file-edit/test task; it is not an efficiency benchmark. Cloning the larger shared Argon profile can exceed the verified native string capacity and is refused.

Set owned profiles through both `models` and `model_profiles`, preserving the original profile features, and add the structured `plan-execute-config`. Hydrogen also needs an execution profile to register `enter_plan_mode`; without it, the first handoff works but handback is an unknown-tool error. The Hydrogen profile exposes same-model plan/execute tools when selected directly.

Relabel the existing Carbon picker entry **Orchestrator (Carbon) (Gateway)**. Model IDs, endpoint, credentials and defaultModelId are retained; do not create duplicate IDs. Argon remains a standalone entry. Application restore reverts only owned display-name changes.

Carbon Direct is installed with `--features orchestrator`; it is not a separate flag name. The desktop picker exposes **Gemini 4 Carbon (Direct) (Gateway)**. It uses the inspected native BYOM identity `326` and a request-local `customModelInfoOverride` pointing at the existing `gemini-4-carbon` backend. The virtual picker ID is not a gateway API model alias. The native model identity is persisted with the conversation, so sessions can choose Direct or Orchestrator independently. Direct was verified through the actual UI and on an existing Orchestrator trajectory; all observed Direct requests returned Carbon and omitted the phase protocol.

The owned Electron preload bridge selects the application's built-in HTTP RPC fallback before the UI initializes, then adapts its `GetUserStatus` catalog and outgoing configuration. It preserves TLS, CSRF headers, account fields and other BYOM overrides. Prepare updates the ASAR entry and Electron header integrity, and signs the staged app. This adapter is scoped to the inspected local desktop release; do not claim the Direct picker exists in the CLI or remote-control UI.

Equivalent duplicate Carbon config rows are backed up and normalized to one Orchestrator row. Rows with different capability settings are refused. Rollback restores only matching owned rows and labels.

If the user authorizes restoring interrupted sessions, record the active roots and their children before quitting, snapshot databases again after a normal exit, and preserve their goals and permission settings. Resume only the specified sessions and avoid redoing completed side effects. If the user elects to resume manually, stop automatic continuation and keep the recovery manifest.

### Optional checkpoint window

Add `--checkpoint-limit 512000` to `inspect` and `prepare` with `--features orchestrator` or `--features pro` when the user asks for a larger context. Fresh installs without the option use the shipped limits. The plan records the chosen cap, and the patched app applies it to Carbon planning, Hydrogen execution, and new Carbon Direct requests. The effective cap remains subject to the model context window, output reservation, and explicit request configuration. Restore the plan to undo the change. The isolated 2.33.0 test read back 512,000 across Direct and every Orchestrator phase using a local mock Gateway. Upstream capacity for requests near that size remains unverified.

### Extend a previous patch

When adding features to a compact patch, supply its verified previous plan:

```sh
python3 scripts/antigravity_pro_unlock.py prepare --features pro --base-plan /previous/verified/plan.json
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

Preparation snapshots conversation databases into the private plan directory and checkpoints only the owned copies. After restart or restore, copy back verified missing databases without overwriting newer live files. The vendor may prune completed subagent trajectories on restart; summary records do not prove the trajectory payload exists. Report pre-snapshot losses accurately.

Read `references/mechanics.md` when adapting a release or diagnosing defaults capacity, signing, recovery or panel discovery. Report the actual verification boundary and recovery path.
