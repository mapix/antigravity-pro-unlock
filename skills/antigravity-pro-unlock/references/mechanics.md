# Patch mechanics and recovery

## Verified boundary

The workflow contracts were checked on Antigravity 2.31.0 and 2.31.2, arm64 macOS. It changes local application defaults for a user-authorized debugging setup. It does not replace authentication, invent a subscription, alter quota enforcement, or change gateway model routing.

The application contains both a native Swarm agent variant and native viewer assets. Read the running `GetMendelFlags`, `GetSlashCommands`, and `GetSidecars` results before concluding what is missing. A bundled file or a skill entry is not evidence that the viewer is registered or visible.

## Persistent data verification

The runtime GetAllCascadeTrajectories response is a resident/in-memory list, not the complete stored history; it may return zero immediately after a restart while conversation files remain on disk. Collect durable identities from the UUID-named conversation files under the original appData directory. Do not compare resident trajectoryId values against stored conversation IDs; old resident-only plans need fresh preparation for data verification.

## Application patch

The language-server Mach-O contains a JSON defaults object with `base`, `subclients`, `os`, `model_profiles`, and `models`. Find one unambiguous complete object, parse it, set the necessary local flags, reserialize compactly, and pad within the same original string span. Reject an absent/ambiguous object, an unsupported layout, or a replacement that exceeds that span.

The relevant flags are:
- `enable-native-swarm`: native swarm skill/variant and its gated bundled plugin.
- `enable-plugins` and `enable-customization-kind-plugin`: separate plugin UI/discovery gates. These may already be enabled; preserve their values when they are already true.

On inspected 2.31.2, Boost uses `enable-owl-slash-command` and Teamwork uses `enable-teamwork-subagent`. Recovered registration predicates require an enabled boolean and a Conversational or Google planner configuration; administrator disable controls remain authoritative. The actual UI commands are `/boost` and `/teamwork` (the native binary also contains `teamwork-preview`). These are separate native implementations. UI exposure is verified, but full task effectiveness is not established by this patch.

Default feature selection remains Swarm only. Use `--features` for explicitly requested optional gates. To extend compact JSON from a previous patch, supply that verified `--base-plan`: capacity reuse validates the current fingerprint, the previous backup, the exact saved offset/length and whitespace-only tail. Reject a stale or absent contract.

Never use an old release's byte offset. Keep a native-binary backup/fingerprint and derive the span from the selected shipped artifact. Do not enable `enable-developer-mode` merely to force an RPC: `SetMendelFlagOverrides` returned a developer-mode permission error in the investigated setup.

The official app's identity, ASAR, updater code, and namespaces stay unchanged. Preserve:
- `/Applications/Antigravity.app`
- `~/Library/Application Support/Antigravity`
- `~/.gemini/antigravity`
- `~/.gemini/config`

## macOS signing

Modifying the native binary invalidates its vendor signature. A recoverable source application backup is necessary because subsequent local signing changes multiple nested signatures.

Re-sign all Mach-O components, nested bundles, and then the outer app consistently. Ad-hoc signatures have no Google Team ID. The debug workflow scopes the library-validation exception to this app and its Electron helpers, retaining their other original entitlements. Do not change system-wide Gatekeeper, SIP, certificate validation, or application approval settings.

Keep the original application/helper names and bundle identity when patching the installed app. Renaming only the main app caused Electron's “Unable to find helper app” failure in the earlier separate-copy experiment. No rename is required for this workflow.

The script does not edit ASAR. If a later release genuinely requires an ASAR change, re-evaluate the package contract and Electron integrity metadata: the observed `ElectronAsarIntegrity` hash covers the ASAR header JSON, not the entire archive. Do not add an ASAR modification to this workflow without new evidence.

## Native viewer fallback

If no usable bundled Swarm sidecar appears:
1. Preserve current configuration before adding the local viewer.
2. Copy the shipped `builtin/plugins/swarm/sidecars/swarm_board` viewer into owned, persistent configuration storage.
3. Register a flat user-sidecar ID `swarm`. User-sidecar discovery scans one directory level; creating a user-sidecar ID `swarm/swarm_board` produced an unregistered nested directory.
4. Add the page alias `/swarm_board/` and declare that one AUX_PANE view. This resolves the native `sidecar://swarm/swarm_board/` button while using the original Board/Members/Graph implementation.
5. Let the manager supply `ANTIGRAVITY_EXECUTABLE_DATA_DIR`. The viewer derives appData by walking upward through `sidecar_data`; overriding this variable with the appData root made that derivation invalid.
6. Wait for RUNNING, then observe the UI. A pane's conversation ID is passed by the host; do not hardcode a previous swarm's ID.

The recorded local RPC shapes are `ManageSidecar` action 5 (create), action 7 (update), and `GetSidecars`. The configuration has `command`, `args`, `env`, `restartPolicy`, `hasWebUi`, `agentPermissions`, and `uiConfig.views`. Recheck this schema before adapting to another release.

Use **Open the Swarm UI**, or **+ → Extensions → Swarm**. A submenu may require keyboard navigation or hover rather than AXPress on its label. “No swarm in this conversation” is the expected state before a swarm is created there.

## Upgrade and recovery

A vendor update may overwrite the patched binary and local signatures. Inspect the new release afresh; if it exposes Swarm natively, no patch is needed. Otherwise validate the new defaults and viewer/RPC contracts, extend the tested-version set deliberately, and create a fresh backup.

The copied viewer can remain after an application upgrade. Compare its recorded release/source hash with the new shipped viewer before keeping it. Replace only viewer files owned by this skill.

Restore the source app from its verified plan. The application rollback retains existing conversation data and gateway configuration. Refuse to overwrite a newer vendor version with an older backup. Never delete unrelated user sidecars or projects to make the UI appear.

After successful UI acceptance, obsolete app-version backups can be removed when requested. Retain the newest verified original application, its plan, and the recorded original/staged native hashes. Staging and displaced copies are redundant after a verified install; the recorded hash supports damaged-Info.plist recovery without retaining another full app copy.
