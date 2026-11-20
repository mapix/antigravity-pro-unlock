# Antigravity Pro Unlock

为 Mac 上的 Antigravity 启用本地功能。Gateway 用户可以在同一个模型菜单中选择 **Carbon Direct** 或 **Orchestrator**，并按需提高会话的 checkpoint 上限。当前技能版本为 **1.5.0**。

| 功能 | 用法 |
| --- | --- |
| Swarm | 用 `/swarm` 组织多个 agent，在看板查看任务和成员。 |
| Boost、Teamwork | 在支持的版本中启用 `/boost` 和 `/teamwork`。 |
| Carbon Direct | 整个会话使用 Carbon。 |
| Orchestrator | Carbon 规划，Hydrogen 执行，再由 Carbon 复核。 |
| 长上下文 | 用 `--checkpoint-limit` 设置 Carbon Direct 和 Orchestrator 各阶段的 checkpoint 上限。 |

补丁针对应用内置功能，使用现有账号和 Gateway 模型配置。订阅权益、配额和上游模型限制仍由服务端决定。

## 安装技能

用 [skills CLI](https://github.com/vercel-labs/skills) 安装到 Codex、Claude Code、Cursor 和 OpenCode。CLI 需要 Node.js 22.20.0 或更高版本。

```sh
npx skills add mapix/antigravity-pro-unlock --skill antigravity-pro-unlock -g -a codex -a claude-code -a cursor -a opencode -y
```

只装给 Codex 时，保留 `-a codex` 即可。省略客户端参数可交互选择。安装技能后，在 Antigravity 之外的客户端里提出请求，例如：

> 用 antigravity-pro-unlock 检查我的 Antigravity，启用 Orchestrator 和 Carbon Direct，并把 checkpoint 上限设为 512,000 token。当前任务结束后再重启应用。

## 兼容性与验证

应用补丁支持 **Apple Silicon Mac**，需要 **Python 3.9+** 以及 macOS 自带的 `codesign`、`ditto`、`ps`、`open`。

| Antigravity 版本 | 支持与验证范围 |
| --- | --- |
| 2.31.0 | Swarm 命令和看板。 |
| 2.31.2 | Swarm 看板、Boost 和 Teamwork 命令。Gateway 下已验证 Carbon Direct 和 Orchestrator 实际交接。 |
| 2.33.0 | 已确认 Swarm、Boost、Teamwork 功能开关及桌面双模型入口。隔离环境通过模拟网关验证了 Carbon Direct 和 Orchestrator 往返，并读回 512,000 token 的 checkpoint 上限。 |

Carbon Direct 的独立入口适用于桌面模型菜单。2.33.0 在 Gateway 只配置 Hydrogen Medium 时，可以用该入口作为执行模型。实际网关对接近 512K token 请求的承载能力尚未测试。

## 手动应用补丁

从仓库根目录运行以下命令。先检查和准备补丁，等正在运行的 Antigravity 任务结束后再退出应用并应用。请从外部终端执行，退出 Antigravity 会中断它自己的 agent。

```sh
SCRIPT=skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py
python3 "$SCRIPT" inspect --features pro
python3 "$SCRIPT" prepare --features pro
# 完全退出 Antigravity 后，把下面的路径替换为 prepare 返回的计划路径。
python3 "$SCRIPT" apply --plan /returned/plan.json --restart
python3 "$SCRIPT" verify --plan /returned/plan.json
```

`--features pro` 和 `--features all` 选择当前版本已适配的功能。也可以单选 `--features orchestrator`，它会同时提供 Carbon Direct。省略 `--features` 时默认选择 Swarm。

在 2.33.0 上将 Carbon Direct、Carbon 规划和 Hydrogen 执行的 checkpoint 上限设为 **512,000 token**：

```sh
python3 "$SCRIPT" inspect --features orchestrator --checkpoint-limit 512000
python3 "$SCRIPT" prepare --features orchestrator --checkpoint-limit 512000
```

准备好的计划会记录上限，后续 `apply` 和 `verify` 使用同一份计划。首次安装时省略该参数会沿用应用默认值。实际可用空间还受模型上下文、输出预留和请求配置约束。

## 备份、升级与回滚

准备阶段会备份应用、配置和会话数据库。新版启动时可能清理旧轨迹，脚本会从已校验的快照补回缺失数据库，保留已存在的文件。计划和备份默认存放在 `~/.local/share/antigravity-pro-unlock/`。

升级 Antigravity 后，请针对新版本重新检查并准备补丁。若在同一版本的已有补丁上增加功能，准备时传入 `--base-plan /previous/verified/plan.json`，以检查旧补丁和备份是否匹配。旧版技能留下的计划可以继续用绝对路径引用。

要回滚某次补丁，先退出 Antigravity，再使用那次的计划：

```sh
python3 "$SCRIPT" restore --plan /returned/plan.json --restart
```

技能和应用补丁分别管理。更新或卸载技能可用 `npx skills update antigravity-pro-unlock -g` 或 `npx skills remove antigravity-pro-unlock -g -y`。补丁的详细流程和验证边界见[技能说明](skills/antigravity-pro-unlock/SKILL.md)及[实现说明](skills/antigravity-pro-unlock/references/mechanics.md)。

## 开发与打包

```sh
npm ci --ignore-scripts
npm test
npm run test:install
npm run package
```

测试使用一次性应用和安装目录。技能 ZIP 和 SHA-256 位于 `dist/`，用于单独分发技能及许可证。应用、会话、配置和凭据不打包。
