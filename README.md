# Antigravity Pro Unlock

用标准 Agent Skill 启用 Antigravity 已随应用分发的本地能力：**Swarm、Boost、Teamwork、Orchestrator**。安装使用官方 [`skills` CLI](https://github.com/vercel-labs/skills)，支持 Codex、Claude Code、Cursor、OpenCode 等客户端。

版本：**1.4.0**。项目由 `enable-antigravity-swarm` 更名并独立维护。

## 安装

先列出技能：

```sh
npx skills add mapix/antigravity-pro-unlock --list
```

交互选择客户端和安装范围：

```sh
npx skills add mapix/antigravity-pro-unlock --skill antigravity-pro-unlock
```

全局安装到常用外部客户端：

```sh
npx skills add mapix/antigravity-pro-unlock --skill antigravity-pro-unlock -g -a codex -a claude-code -a cursor -a opencode -y
```

单个客户端，例如 Codex：

```sh
npx skills add mapix/antigravity-pro-unlock --skill antigravity-pro-unlock -g -a codex -y
```

默认使用 CLI 的标准链接安装；需要文件副本时加 `--copy`。客户端列表和目录由官方 CLI 维护，见[官方客户端文档](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)。CLI 当前要求 Node.js **22.20.0+**。

本地仓库也可以直接安装：

```sh
npx skills add ./antigravity-pro-unlock --skill antigravity-pro-unlock -g -a codex -a claude-code -a cursor -a opencode -y
```

以上命令安装技能。应用补丁由使用该技能的 agent 按检查、备份、安装、验证流程执行。

## 使用

在其他 harness 中输入：

> 使用 antigravity-pro-unlock 技能检查我的 Antigravity，并启用 Swarm、Boost 和 Teamwork。保留现有会话和 gateway 配置。

**从 Antigravity 之外执行补丁。** 完整退出目标应用会终止它自己的 agent；脚本会拒绝从 Antigravity 进程或 agent 环境执行修改。

手动运行时，在仓库根目录执行：

```sh
python3 skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py --version
python3 skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py inspect --features pro
python3 skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py prepare --features pro
# 完整退出 Antigravity 后，使用 prepare 返回的计划路径：
python3 skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py apply --plan /returned/plan.json --restart
python3 skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py verify --plan /returned/plan.json
```

若基于旧补丁增加能力，`prepare` 还需传入 `--base-plan /previous/verified/plan.json`。完整流程见 [SKILL.md](skills/antigravity-pro-unlock/SKILL.md)。

## 支持范围

| 能力 | 已验证 Antigravity 版本 | 验证范围 |
| --- | --- | --- |
| Swarm | 2.31.0、2.31.2 | 命令和原生 Board / Members / Graph |
| Boost | 2.31.2 | 原生命令入口 |
| Teamwork | 2.31.2 | 原生命令入口 |
| Orchestrator | 2.31.2 / gateway | Carbon → Hydrogen → Carbon 实际交接 |
| Carbon Direct | 2.31.2 / gateway 桌面 UI | 独立入口、固定 Carbon、按会话保存选择 |

补丁运行于 **macOS Apple Silicon**，需要 **Python 3.9+** 和 macOS 自带的 `codesign`、`ditto`、`ps`、`open`。跨客户端安装遵循 [Agent Skills 标准](https://agentskills.io/specification)；应用兼容性按上表限制。

“Pro Unlock” 是本项目对本地功能补丁的命名，不提供订阅或额度。账号认证、gateway、模型路由及管理员控制保留。Boost、Teamwork 的完整任务效果尚未进行基准测试。

## 一键启用与模型配置

`--features pro`（也可用 `all`）启用当前版本已适配的能力。未知版本仍会拒绝修改；这不是订阅、额度或所有实验功能的总开关。

Orchestrator 默认选择已配置的 Carbon 与 Hydrogen，自动读取现有 gateway 模型映射，不需要新增模型或 API key。Carbon 的现有选择器条目变为 **Orchestrator (Carbon) (Gateway)**；Argon 仍是单模型。Hydrogen 的 profile 同时注册交回规划的工具，因此单独选择 Hydrogen 时也会有同模型的规划/执行工具。

1.4.0 同时提供 **Gemini 4 Carbon (Direct) (Gateway)**。它使用原生 BYOM 会话身份及指向现有 Carbon 后端的请求配置，允许不同会话分别选择纯 Carbon 或 Orchestrator。虚拟菜单 ID 不会作为 API 模型名发给 gateway。已通过真实 UI 请求和旧 Orchestrator 会话的切换验证，Direct 请求均返回 `gemini-4-carbon`，不含规划／执行交接协议。

桌面适配使用应用已有的 HTTP RPC 回退，保留原来的 TLS、CSRF、权限和 gateway 认证。补丁会校验并更新 ASAR 完整性、签名及数据库快照。Direct 菜单目前仅适配所列桌面版本，不代表 CLI 或远程控制界面已增加同名入口。

两个模型的实际往返已在隔离目录完成文件创建、断言执行和 Carbon 复核。Argon 的共享 profile 较大，独立复制可能超过本版本的 native 字符串容量；脚本会保留原设置并拒绝该情况。

## 备份与升级

- 修改前保存完整应用、配置和会话数据库快照，检查原应用及 staging 指纹。
- 应用启动可能裁剪已完成的子 agent 轨迹；新版在启动后只从已校验快照恢复缺失数据库，不覆盖新数据。已有摘要不代表完整轨迹仍存在。
- 新计划位于 `~/.local/share/antigravity-pro-unlock/`；旧 `~/.local/share/antigravity-swarm-patch/` 计划可继续通过绝对路径使用。
- 原会话和配置目录保持不变。升级后先检查当前版本，再为支持的版本准备新补丁；不要复用旧偏移或直接应用旧计划。
- 修改原生二进制会使厂商签名失效；脚本对该应用进行本地签名。失败时使用计划中的源应用回滚。机制见 [mechanics.md](skills/antigravity-pro-unlock/references/mechanics.md)。

更新或卸载技能使用官方 CLI：

```sh
npx skills update antigravity-pro-unlock -g
npx skills remove antigravity-pro-unlock -g -y
```

卸载技能不会回滚已安装的应用补丁。应用回滚需按计划执行 `restore`。

## 开发与打包

```sh
npm ci --ignore-scripts
npm test
npm run test:install
npm run package
```

测试使用一次性应用 fixture 和项目安装目录。打包产物及 SHA-256 位于 `dist/`；包含技能及许可证，不包含应用、会话、配置、凭据或本机备份。
