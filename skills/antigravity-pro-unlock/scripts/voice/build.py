"""Build a separate Antigravity 2.33.0 dictation preview on macOS."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import plistlib
import struct
import sys

HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / "antigravity_pro_unlock.py"
SPEC = importlib.util.spec_from_file_location("unlock", HELPER)
unlock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(unlock)


def replace_once(source, original, replacement):
    if source.count(original) != 1:
        raise ValueError(f"Unexpected Antigravity desktop code: {original}")
    return source.replace(original, replacement)


def patch_archive(app, home, app_name, bundle_id, *, sidecars):
    archive, data, size, tree, _, _ = unlock.asar_entry(app)
    assets = app / "Contents/Resources/voice-preview"
    assets.mkdir()
    (assets / "gateway.cjs").write_bytes((HERE / "gateway.cjs").read_bytes())
    edits = {}
    for name in ("dist/main.js", "dist/languageServer.js", "dist/preload.js"):
        edits[name] = unlock.asar_entry(app, name)[-1].decode()
    main = edits["dist/main.js"]
    marker = "const gotTheLock = electron_1.app.requestSingleInstanceLock();"
    main = replace_once(main, marker, f"""
const previewHome = {json.dumps(str(home))};
process.env.HOME = previewHome;
for (const [name, dir] of [['userData', 'desktop'], ['logs', 'logs'], ['sessionData', 'desktop']]) {{
    const folder = path.join(previewHome, dir);
    fs.mkdirSync(folder, {{ recursive: true, mode: 0o700 }});
    electron_1.app.setPath(name, folder);
}}
const setupPreviewDictationMenu = require(path.join(process.resourcesPath, 'voice-preview/gateway.cjs')).register({{
    ipcMain: electron_1.ipcMain,
    configPath: path.join(previewHome, '.gemini/config/config.json'),
    modePath: path.join(previewHome, 'dictation-backend'),
    getPort: languageServer_1.getLsPort,
}});
{marker}""")
    main = replace_once(main, "electron_1.app.setAsDefaultProtocolClient(PROTOCOL, ...protocolClientArgs);",
                        "// Keep the production app as the default protocol handler.")
    main = replace_once(main, "await (0, ideInstall_1.maybeShowIdeInstallWizard)(storageManager);",
                        "// The preview skips IDE installation.")
    main = replace_once(main, "(0, updater_1.initAutoUpdater)(HEADLESS, settingsService);",
                        "// Rebuild the preview from a supported source to update it.")
    main = replace_once(main, "(0, menu_1.setupApplicationMenu)(url);",
                        "(0, menu_1.setupApplicationMenu)(url);\n        setupPreviewDictationMenu(electron_1);")
    edits["dist/main.js"] = main
    ls = edits["dist/languageServer.js"]
    sidecar_arg = "\n            '--enable_sidecars'," if sidecars else ""
    ls = replace_once(ls, "'--enable_sidecars',", f"'--gemini_dir', {json.dumps(str(home / '.gemini'))},\n            '--disable_telemetry',{sidecar_arg}")
    ls = replace_once(ls, "const env = { ...process.env, ...loginShellEnv };",
                      f"const env = {{ ...process.env, ...loginShellEnv, HOME: {json.dumps(str(home))} }};")
    edits["dist/languageServer.js"] = ls
    preload = edits["dist/preload.js"]
    js = json.dumps((HERE / "renderer.js").read_text())
    edits["dist/preload.js"] = preload + f"""
if (window.top === window && location.hostname === '127.0.0.1' && location.protocol === 'https:') {{
    electron_1.contextBridge.exposeInMainWorld('agVoicePreview', {{
        transcribe: pcm => electron_1.ipcRenderer.invoke('ag-voice-preview:transcribe', pcm),
        mode: () => electron_1.ipcRenderer.sendSync('ag-voice-preview:mode'),
        onModeChange: cb => {{ electron_1.ipcRenderer.on('ag-voice-preview:mode-changed', (_event, mode) => cb(mode)); }},
    }});
    const injectVoicePreview = () => {{
        if (!document.documentElement) return false;
        const script = document.createElement('script');
        script.textContent = {js};
        document.documentElement.appendChild(script);
        script.remove();
        return true;
    }};
    if (!injectVoicePreview()) {{
        const observer = new MutationObserver(() => {{ if (injectVoicePreview()) observer.disconnect(); }});
        observer.observe(document, {{childList: true, subtree: true}});
    }}
}}
"""
    payload = bytearray(data[8 + size:])
    for name, source in edits.items():
        entry = tree
        for part in name.split("/"):
            entry = entry["files"][part]
        blob = source.encode()
        block_size = entry["integrity"]["blockSize"]
        digest = lambda value: hashlib.sha256(value).hexdigest()
        entry.update(offset=str(len(payload)), size=len(blob), integrity={
            "algorithm": "SHA256", "hash": digest(blob), "blockSize": block_size,
            "blocks": [digest(blob[i:i + block_size]) for i in range(0, len(blob), block_size)],
        })
        payload.extend(blob)
    header = json.dumps(tree, separators=(",", ":"), ensure_ascii=False).encode()
    padded = header + bytes(-len(header) % 4)
    archive.write_bytes(struct.pack("<IIII", 4, len(padded)+8, len(padded)+4, len(header)) + padded + payload)
    info_path = app / "Contents/Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info.update(CFBundleIdentifier=bundle_id, CFBundleDisplayName=app_name, CFBundleName=app_name)
    info.pop("CFBundleURLTypes", None)
    info["ElectronAsarIntegrity"]["Resources/app.asar"]["hash"] = hashlib.sha256(header).hexdigest()
    info_path.write_bytes(plistlib.dumps(info))
    for name in edits:
        unlock.asar_entry(app, name)


def isolate_helpers(app, name, bundle_id):
    for helper in (app / "Contents/Frameworks").glob("Antigravity Helper*.app"):
        info_path = helper / "Contents/Info.plist"
        info = plistlib.loads(info_path.read_bytes())
        old = info["CFBundleExecutable"]
        new = old.replace("Antigravity Helper", name + " Helper", 1)
        tools = helper / "Contents/MacOS"
        (tools / old).rename(tools / new)
        info.update(CFBundleExecutable=new, CFBundleDisplayName=new, CFBundleName=new,
                    CFBundleIdentifier=info["CFBundleIdentifier"].replace(
                        "com.google.antigravity.helper", bundle_id + ".helper", 1))
        info_path.write_bytes(plistlib.dumps(info))
        helper.rename(helper.with_name(new + ".app"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path.home() / ".gemini/config/config.json")
    parser.add_argument("--reuse-data", action="store_true", help="Reuse the existing isolated preview data")
    parser.add_argument("--pro", action="store_true", help="Retain the verified Pro patch and Swarm sidecars")
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != "arm64":
        parser.error("The voice preview requires macOS on Apple Silicon")
    unlock.external_harness_guard()
    source = args.source.expanduser().resolve()
    source_id = unlock.identity(source)
    if source_id["bundle_id"] != "com.google.antigravity":
        raise ValueError("Use the main Antigravity bundle as the source")
    if source_id["version"] != "2.33.0":
        raise ValueError("Preview supports Antigravity 2.33.0 only")
    home = args.data.expanduser().resolve()
    app = args.app.expanduser().resolve()
    name = "Antigravity Pro Voice" if args.pro else "Antigravity Voice Preview"
    bundle_id = "com.google.antigravity." + ("provoice" if args.pro else "voicepreview")
    if home == Path.home().resolve():
        raise ValueError("Choose an isolated preview profile")
    if any(a == b or a in b.parents or b in a.parents
           for a, b in ((home, app), (source, app), (source, home))):
        raise ValueError("The source, preview app, and preview data must have separate paths")
    if app.exists():
        raise FileExistsError("Choose a new destination for the preview bundle")
    cfg_path = home / ".gemini/config/config.json"
    if args.reuse_data:
        if not cfg_path.is_file() or not (home / "desktop").is_dir():
            raise ValueError("The data destination is not an existing preview profile")
    elif home.exists():
        raise FileExistsError("Choose a new destination for preview data")
    unlock.run(["codesign", "--verify", "--deep", "--strict", source])
    if args.pro:
        unlock.FLAGS = tuple(dict.fromkeys(flag for flags in unlock.FEATURE_FLAGS.values() for flag in flags))
        requested = unlock.resolve_orchestrator(source, "gemini-4-carbon", "gemini-4-hydrogen")
        cap = unlock.installed_checkpoint_limit(source)
        if cap is not None:
            requested["checkpoint_limit"] = cap
        contract = unlock.defaults_contract(source, orchestrator=requested, inspect_only=True)
        if not contract["already_patched"] or not unlock.carbon_bridge_contract(source, cap):
            raise ValueError("The source bundle must already contain the inspected Pro patch")
    if not args.reuse_data:
        try:
            cfg = json.loads(args.config.expanduser().read_text())
            local_config = {k: cfg[k] for k in ("gateway", "models")}
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("Could not read gateway and models from the source config") from None
        home.mkdir(mode=0o700, parents=True)
        unlock.private_json(cfg_path, local_config)
    app.parent.mkdir(parents=True, exist_ok=True)
    unlock.run(["ditto", source, app])
    patch_archive(app, home, name, bundle_id, sidecars=args.pro)
    isolate_helpers(app, name, bundle_id)
    unlock.sign_debug_app(app)
    for expected in (name + " Helper", name + " Helper (Renderer)"):
        if not (app / "Contents/Frameworks" / (expected + ".app") / "Contents/MacOS" / expected).is_file():
            raise ValueError("Electron helper naming does not match the application bundle")
    if unlock.identity(app)["name"] != name:
        raise ValueError("Unexpected name in the signed application")
    print(app)


if __name__ == "__main__":
    main()
