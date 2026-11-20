# Antigravity Pro Unlock

Enable built-in Antigravity features on Mac. Gateway users can choose **Carbon Direct** or **Orchestrator** from the same model menu and optionally raise the session checkpoint limit. The current skill version is **1.5.0**.

| Feature | What it does |
| --- | --- |
| Swarm | Use `/swarm` to coordinate multiple agents and review tasks and members on the board. |
| Boost and Teamwork | Enable `/boost` and `/teamwork` on supported versions. |
| Carbon Direct | Use Carbon throughout a session. |
| Orchestrator | Let Carbon plan, Hydrogen execute, and Carbon review. |
| Longer context | Set the checkpoint limit for Carbon Direct and each Orchestrator phase with `--checkpoint-limit`. |

The patch uses your existing account and Gateway model configuration. The service still controls subscription access, quotas, and upstream model limits.

## Install the skill

Use the [skills CLI](https://github.com/vercel-labs/skills) to install the skill for Codex, Claude Code, Cursor, or OpenCode. The CLI requires Node.js 22.20.0 or later.

```sh
npx skills add mapix/antigravity-pro-unlock --skill antigravity-pro-unlock -g -a codex -a claude-code -a cursor -a opencode -y
```

For Codex only, keep `-a codex`. Omit the client flags to select clients interactively. After installing the skill, ask for the patch from a client outside Antigravity. For example:

> Use antigravity-pro-unlock to inspect my Antigravity installation, enable Orchestrator and Carbon Direct, and set the checkpoint limit to 512,000 tokens. Wait for my current tasks to finish before restarting the app.

## Compatibility and verification

The app patch supports **Apple Silicon Macs** and requires **Python 3.9 or later** along with the macOS tools `codesign`, `ditto`, `ps`, and `open`.

| Antigravity version | What was verified |
| --- | --- |
| 2.31.0 | The Swarm command and board. |
| 2.31.2 | The Swarm board and the Boost and Teamwork commands. Carbon Direct and Orchestrator handoffs were verified with Gateway. |
| 2.33.0 | The Swarm, Boost, and Teamwork feature flags and both entries in the desktop model menu. An isolated test with a mock Gateway verified Carbon Direct, the full Orchestrator round trip, and a 512,000-token checkpoint limit. |

The separate Carbon Direct entry is available in the desktop model menu. On 2.33.0, Orchestrator can use a configured Hydrogen Medium entry when the base Hydrogen model is absent. Requests near 512,000 tokens have yet to be tested against the upstream Gateway.

## Apply the patch manually

Run the following commands from a terminal outside Antigravity, starting at the repository root. Inspect and prepare the patch first. Wait for active Antigravity tasks to finish before quitting the app and applying the patch.

```sh
SCRIPT=skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py
python3 "$SCRIPT" inspect --features pro
python3 "$SCRIPT" prepare --features pro
# Quit Antigravity completely, then replace this path with the plan returned by prepare.
python3 "$SCRIPT" apply --plan /returned/plan.json --restart
python3 "$SCRIPT" verify --plan /returned/plan.json
```

Both `--features pro` and `--features all` select the features supported on the installed version. Use `--features orchestrator` to enable Orchestrator and Carbon Direct together. If you omit `--features`, the script selects Swarm.

To set the checkpoint limit to **512,000 tokens** for Carbon Direct and the Carbon and Hydrogen phases of Orchestrator on 2.33.0, run these commands instead of the inspection and preparation commands above:

```sh
python3 "$SCRIPT" inspect --features orchestrator --checkpoint-limit 512000
python3 "$SCRIPT" prepare --features orchestrator --checkpoint-limit 512000
```

The plan records the limit. Use the same plan for `apply` and `verify`. Omitting the option on a fresh install uses the app defaults. The effective limit also depends on the model's context window, output reservation, and request settings.

## Back up, upgrade, and roll back

Preparation backs up the app, configuration, and conversation databases. A newer release may prune old conversation data on startup. The script restores missing database files from the verified snapshot and keeps any files that already exist. Plans and backups are stored in `~/.local/share/antigravity-pro-unlock/` by default.

After upgrading Antigravity, inspect the new version and prepare a new patch. To add features to an existing patch on the same app version, pass `--base-plan /previous/verified/plan.json` to `prepare` so it can check the patch and backup. Plans created by earlier skill versions can still be referenced by their absolute paths.

To roll back a patch, quit Antigravity and use the plan for that patch:

```sh
python3 "$SCRIPT" restore --plan /returned/plan.json --restart
```

Manage the skill with `npx skills update antigravity-pro-unlock -g` or `npx skills remove antigravity-pro-unlock -g -y`. Use `restore` to roll back the app patch. See the [skill instructions](skills/antigravity-pro-unlock/SKILL.md) and [implementation notes](skills/antigravity-pro-unlock/references/mechanics.md) for details and verification limits.

## Develop and package

```sh
npm ci --ignore-scripts
npm test
npm run test:install
npm run package
```

Tests use disposable app fixtures and installation directories. The skill ZIP and SHA-256 checksum go to `dist/`. The ZIP contains the skill and its license. It excludes the app, conversations, configuration, and credentials.
