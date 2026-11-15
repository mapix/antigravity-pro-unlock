#!/usr/bin/env python3
"""Enable shipped local Antigravity Pro features with checked staging and recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

SKILL_NAME = "antigravity-pro-unlock"
SKILL_VERSION = "1.2.0"
SUPPORTED = {"2.31.0", "2.31.2"}
FEATURE_FLAGS = {
    "swarm": ("enable-native-swarm", "enable-plugins", "enable-customization-kind-plugin"),
    "boost": ("enable-owl-slash-command",),
    "teamwork": ("enable-teamwork-subagent",),
}
FEATURE_VERSIONS = {"swarm": {"2.31.0", "2.31.2"}, "boost": {"2.31.2"}, "teamwork": {"2.31.2"}}
SELECTED_FEATURES = ("swarm",)
FLAGS = FEATURE_FLAGS["swarm"]
DEFAULT_APP = Path("/Applications/Antigravity.app")
DEFAULT_ROOT = Path.home() / ".local/share/antigravity-pro-unlock"
MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe",
          b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}
SERVICE = "/exa.language_server_pb.LanguageServerService/"
SCHEMA = 1

class PatchError(RuntimeError):
    pass

def run(argv):
    p = subprocess.run([str(x) for x in argv], capture_output=True, text=True)
    if p.returncode:
        raise PatchError(f"{Path(str(argv[0])).name} failed: {p.stderr.strip()[:600]}")
    return p.stdout

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".swarm-patch-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if Path(tmp).exists():
            Path(tmp).unlink()

def identity(app):
    p = Path(app) / "Contents/Info.plist"
    if not p.is_file():
        raise PatchError(f"Missing app Info.plist: {p}")
    j = plistlib.loads(p.read_bytes())
    if not j.get("CFBundleIdentifier", "").startswith("com.google.antigravity"):
        raise PatchError("The target is not an identified Antigravity app")
    return {"version": j.get("CFBundleShortVersionString"),
            "bundle_id": j.get("CFBundleIdentifier"),
            "name": j.get("CFBundleName"),
            "executable": j.get("CFBundleExecutable")}

def binary_path(app):
    return Path(app) / "Contents/Resources/bin/language_server"

def fingerprint(app):
    records = {}
    for p in sorted(Path(app).rglob("*")):
        rel = str(p.relative_to(app))
        if p.is_symlink():
            records[rel] = {"link": os.readlink(p)}
        elif p.is_file():
            records[rel] = {"sha256": sha(p), "mode": p.stat().st_mode & 0o777}
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()

def processes():
    out = run(["ps", "-axo", "pid,ppid,command"])
    result = {}
    for line in out.splitlines()[1:]:
        pieces = line.strip().split(None, 2)
        if len(pieces) == 3 and pieces[0].isdigit():
            result[int(pieces[0])] = (int(pieces[1]), pieces[2])
    return result

def external_harness_guard():
    table = processes()
    pid = os.getpid()
    seen = set()
    while pid and pid not in seen:
        seen.add(pid)
        ppid, cmd = table.get(pid, (0, ""))
        if re.search(r"/Antigravity(?: [^/]*)?\.app/", cmd, re.I):
            raise PatchError("Run this mutation from another harness, not Antigravity")
        pid = ppid
    if any(os.environ.get(k) for k in
           ("ANTIGRAVITY_EXECUTABLE_DATA_DIR", "ANTIGRAVITY_AGENTAPI_EXE")):
        raise PatchError("Antigravity agent environment detected; use an external harness")

def target_processes(app):
    prefix = str(Path(app)) + "/Contents/"
    return {pid: cmd for pid, (_, cmd) in processes().items()
            if cmd.startswith(prefix)}

def require_closed(app):
    running = target_processes(app)
    if running:
        raise PatchError("Quit Antigravity completely from an external UI first; "
                         f"target PIDs still running: {sorted(running)}")

def runtime(app):
    prefix = str(binary_path(app))
    matches = [(pid, cmd) for pid, (_, cmd) in processes().items()
               if cmd.startswith(prefix)]
    if len(matches) != 1:
        raise PatchError("Expected exactly one running language server for this app")
    pid, cmd = matches[0]
    token = re.search(r"--csrf_token(?:=|\s+)(\S+)", cmd)
    config_dir = re.search(r"--config_dir(?:=|\s+)(\S+)", cmd)
    data_dir = re.search(r"--app_data_dir(?:=|\s+)(\S+)", cmd)
    name = identity(app)["name"]
    log = Path.home() / "Library/Logs" / name / "language_server.log"
    if not log.exists():
        raise PatchError("Language server startup log is not ready")
    text = log.read_text(errors="replace")
    if not re.search(r"with pid " + str(pid) + r"\b", text):
        raise PatchError("Startup log does not belong to the current language server")
    port = re.search(r"listening on \w+ port at (\d+) for HTTP\b", text)
    if not port:
        raise PatchError("Language server HTTP port is not ready")
    return {"pid": pid, "port": int(port.group(1)),
            "csrf": token.group(1) if token else "",
            "config_dir": config_dir.group(1) if config_dir else "config",
            "data_dir": data_dir.group(1) if data_dir else "antigravity"}

def rpc(rt, method, body=None):
    req = Request(f"http://127.0.0.1:{rt['port']}{SERVICE}{method}",
                  data=json.dumps(body or {}).encode(),
                  headers={"Content-Type": "application/json",
                           "X-Codeium-Csrf-Token": rt["csrf"]})
    try:
        with urlopen(req, timeout=12) as r:
            return json.load(r)
    except HTTPError as e:
        msg = e.read().decode(errors="replace")[:500]
        # Do not echo token-bearing URLs or credential fields.
        msg = re.sub(r"https?://\S+", "<url>", msg)
        raise PatchError(f"{method}: HTTP {e.code}: {msg}") from e

def live_state(app):
    rt = runtime(app)
    auth = rpc(rt, "GetAuthStatus").get("authResult", {})
    exps = rpc(rt, "GetMendelFlags").get("experimentConfig", {}).get("experiments", [])
    enabled = {x.get("keyString") for x in exps if not x.get("disabled", False)}
    summaries = rpc(rt, "GetAllCascadeTrajectories").get("trajectorySummaries", {})
    rows = list(summaries.values()) if isinstance(summaries, dict) else summaries
    # GetAllCascadeTrajectories is a resident/in-memory list. A fresh
    # restart can return zero even while hundreds of stored conversations exist.
    # Use the stable conversation file names for data-preservation checks.
    directory = Path.home() / ".gemini" / rt["data_dir"] / "conversations"
    ids = []
    if directory.exists():
        pattern = re.compile(r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:\.db|\.pb|\.pbtxt|\.json)?$")
        ids = sorted({match.group(1).lower() for p in directory.iterdir()
                      if (match := pattern.fullmatch(p.name)) and
                      (p.is_file() or p.is_dir())})
    active = [x for x in rows if x.get("status") not in
              (None, "CASCADE_RUN_STATUS_IDLE", "CASCADE_RUN_STATUS_UNSPECIFIED")]
    sidecars = rpc(rt, "GetSidecars").get("sidecars", [])
    ui = [x for x in sidecars if
          (x.get("sidecarId", "").endswith("/swarm_board") or
           x.get("sidecarId") == "swarm") and
          x.get("config", {}).get("hasWebUi")]
    return {"runtime": rt, "auth_valid": bool(auth.get("hasValidAuth")),
            "auth_mode": auth.get("authMode"), "enabled_flags": sorted(enabled),
            "conversation_ids": ids, "conversation_id_source": "conversation_files",
            "resident_trajectory_count": len(rows), "running_summaries": len(active),
            "swarm_panels": [{"id": x.get("sidecarId"), "status": x.get("status"),
                              "error": x.get("lastError")} for x in ui]}

def defaults_contract(app, base_plan=None):
    data = binary_path(app).read_bytes()
    if data[:4] != b"\xcf\xfa\xed\xfe":
        raise PatchError("Only the verified thin arm64 Mach-O layout is supported")
    if struct.unpack_from("<I", data, 4)[0] != 0x0100000c:
        raise PatchError("Only Apple Silicon is verified by this version of the script")
    for flag in FLAGS:
        if flag.encode() not in data:
            raise PatchError(f"Missing shipped feature contract: {flag}")
    if b"assets/shared/plugins/swarm/" not in data:
        raise PatchError("Missing shipped native Swarm viewer assets")
    found = []
    dec = json.JSONDecoder()
    for m in re.finditer(rb'\{\s*"base"\s*:', data):
        sample = data[m.start():m.start() + 512 * 1024].decode(
            "utf-8", errors="surrogateescape")
        try:
            obj, end = dec.raw_decode(sample)
        except ValueError:
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("base"), dict):
            continue
        if not {"subclients", "os", "model_profiles", "models"}.issubset(obj):
            continue
        original = sample[:end].encode("utf-8", errors="surrogateescape")
        found.append((m.start(), original, obj))
    if len(found) != 1:
        raise PatchError(f"Expected one complete defaults object, found {len(found)}")
    offset, original, obj = found[0]
    patched = json.loads(json.dumps(obj))
    for key in FLAGS:
        patched["base"][key] = True
    new = json.dumps(patched, separators=(",", ":"), ensure_ascii=False).encode()
    already = all(obj["base"].get(key) is True for key in FLAGS)
    if not already and len(new) > len(original):
        if not base_plan:
            raise PatchError("Compact prior patch needs --base-plan for verified capacity")
        _, base = load_plan(base_plan)
        if identity(app) != base["identity"] or fingerprint(app) != base["staged_fingerprint"]:
            raise PatchError("Base plan does not identify the current patched application")
        clean = Path(base["original_app"])
        if fingerprint(clean) != base["original_fingerprint"]:
            raise PatchError("Base plan backup changed")
        span = base["native_span"]
        if offset != span["offset"] or span["length"] < len(original):
            raise PatchError("Base plan native span does not match this defaults object")
        whole = data[offset:offset + span["length"]]
        if not whole.startswith(original) or any(c not in b" \t\r\n" for c in whole[len(original):]):
            raise PatchError("Verified prior string tail is not whitespace")
        original = whole
        if len(new) > len(original):
            raise PatchError("Requested features exceed the verified string capacity")
    return {"offset": offset, "length": len(original),
            "original": original, "patched": new.ljust(len(original), b" "),
            "flags_before": {k: obj["base"].get(k) for k in FLAGS},
            "already_patched": already}

def sign_debug_app(app):
    app = Path(app)
    machos = []
    for p in app.rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        with p.open("rb") as f:
            if f.read(4) in MAGICS:
                machos.append(p)
    for p in sorted(machos, key=lambda p: len(p.parts), reverse=True):
        run(["codesign", "--force", "--sign", "-",
             "--preserve-metadata=entitlements,flags", p])
    bundles = [p for p in app.rglob("*") if p.is_dir() and not p.is_symlink()
               and p.suffix in (".app", ".framework", ".xpc")]
    for p in sorted(bundles, key=lambda p: len(p.parts), reverse=True):
        run(["codesign", "--force", "--sign", "-",
             "--preserve-metadata=entitlements,flags", p])
    # Ad-hoc debug signatures have no Google Team ID. Scope the library
    # validation exception to the patched app and its Electron helper apps.
    apps = [p for p in bundles if p.suffix == ".app"] + [app]
    with tempfile.TemporaryDirectory(prefix="antigravity-swarm-sign-") as td:
        for i, p in enumerate(sorted(apps, key=lambda p: len(p.parts), reverse=True)):
            out = run(["codesign", "-d", "--entitlements", ":-", p])
            start, end = out.find("<?xml"), out.find("</plist>")
            if start < 0 or end < 0:
                raise PatchError(f"Could not recover existing entitlements for {p}")
            ent = plistlib.loads(out[start:end + 8].encode())
            ent["com.apple.security.cs.disable-library-validation"] = True
            ent_path = Path(td) / f"{i}.plist"
            ent_path.write_bytes(plistlib.dumps(ent))
            run(["codesign", "--force", "--sign", "-", "--options", "runtime",
                 "--entitlements", ent_path, p])
    run(["codesign", "--verify", "--deep", "--strict", app])

def inspect(app):
    info = identity(app)
    contract = defaults_contract(app)
    live = None
    try:
        live = live_state(app)
        live.pop("runtime", None)
        live["conversation_count"] = len(live.pop("conversation_ids"))
    except PatchError:
        pass
    return {"app": str(app), "identity": info, "verified_version": info["version"] in SUPPORTED,
            "flags_before": contract["flags_before"],
            "already_patched": contract["already_patched"], "live": live}

def prepare(app, backup_root, base_plan=None):
    external_harness_guard()
    info = identity(app)
    if info["version"] not in SUPPORTED or any(info["version"] not in FEATURE_VERSIONS[f] for f in SELECTED_FEATURES):
        raise PatchError(f"Unverified release/features {info['version']}; inspect/adapt first")
    contract = defaults_contract(app, base_plan)
    baseline = None
    try:
        baseline = live_state(app)
        baseline.pop("runtime", None)
    except PatchError:
        pass
    if contract["already_patched"]:
        return {"action": "noop", "reason": "All required defaults already enabled",
                "next": "Run verify, then panel if necessary"}
    if baseline and all(k in baseline["enabled_flags"] for k in FLAGS) and ("swarm" not in SELECTED_FEATURES or baseline["swarm_panels"]):
        return {"action": "noop", "reason": "Requested native features are already available"}
    run(["codesign", "--verify", "--deep", "--strict", app])
    before = fingerprint(app)
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path(tempfile.mkdtemp(prefix=f"{info['version']}-{stamp}-", dir=backup_root))
    os.chmod(folder, 0o700)
    original = folder / "original" / app.name
    staged = folder / "staged" / app.name
    original.parent.mkdir(mode=0o700)
    staged.parent.mkdir(mode=0o700)
    run(["ditto", app, original])
    if fingerprint(original) != before or fingerprint(app) != before:
        raise PatchError(f"Application changed while backing up. Keep backup at {folder}; retry.")
    config_dir = Path.home() / ".gemini/config"
    for label, p in (("config.json", config_dir / "config.json"),
                     ("legacy-settings.json", Path.home() / ".antigravity/settings.json")):
        if p.exists():
            q = folder / "config" / label
            q.parent.mkdir(exist_ok=True, mode=0o700)
            shutil.copy2(p, q)
            q.chmod(0o600)
    run(["ditto", original, staged])
    p = binary_path(staged)
    with p.open("r+b") as f:
        f.seek(contract["offset"])
        if f.read(contract["length"]) != contract["original"]:
            raise PatchError("Staged native defaults differ from the inspected source")
        f.seek(contract["offset"])
        f.write(contract["patched"])
        f.flush()
        os.fsync(f.fileno())
    (folder / "defaults-original.bin").write_bytes(contract["original"])
    sign_debug_app(staged)
    if identity(staged) != info:
        raise PatchError("Application identity changed unexpectedly")
    for rel in ("Contents/Info.plist", "Contents/Resources/app.asar",
                "Contents/Resources/default_app.asar"):
        if sha(staged / rel) != sha(original / rel):
            raise PatchError(f"Unexpected change to {rel}")
    if not defaults_contract(staged)["already_patched"]:
        raise PatchError("Staged flags failed verification")
    plan = {"schema": SCHEMA, "skill_version": SKILL_VERSION, "app": str(app), "identity": info,
            "original_app": str(original), "staged_app": str(staged),
            "original_fingerprint": before, "staged_fingerprint": fingerprint(staged),
            "flags": list(FLAGS), "features": list(SELECTED_FEATURES), "original_native_sha256": sha(binary_path(original)),
            "staged_native_sha256": sha(binary_path(staged)),
            "native_span": {"offset": contract["offset"],
            "length": contract["length"]}, "baseline": baseline,
            "config_dir": str(config_dir), "data_dir": str(Path.home() / ".gemini/antigravity"),
            "state": "prepared"}
    plan_path = folder / "plan.json"
    private_json(plan_path, plan)
    return {"action": "prepared", "plan": str(plan_path), "backup": str(original),
            "running_summaries": baseline["running_summaries"] if baseline else None,
            "requires_complete_app_exit": True}

def load_plan(path):
    path = Path(path).resolve()
    plan = json.loads(path.read_text())
    if plan.get("schema") != SCHEMA:
        raise PatchError("Unknown plan schema")
    for key in ("original_app", "staged_app"):
        q = Path(plan[key]).resolve()
        if path.parent not in q.parents:
            raise PatchError(f"Plan path escapes its backup directory: {key}")
    return path, plan

def install_candidate(app, candidate, archive_to):
    # Materialize on the destination filesystem so both swap renames are atomic.
    container = Path(tempfile.mkdtemp(prefix=".antigravity-swarm-install-", dir=app.parent))
    staged = container / app.name
    displaced = container / "displaced.app"
    run(["ditto", candidate, staged])
    run(["codesign", "--verify", "--deep", "--strict", staged])
    swapped = False
    try:
        if app.exists():
            app.rename(displaced)
        staged.rename(app)
        swapped = True
        run(["codesign", "--verify", "--deep", "--strict", app])
    except Exception:
        if swapped and app.exists():
            app.rename(container / "failed.app")
        if displaced.exists():
            displaced.rename(app)
        raise
    if displaced.exists():
        archive_to.parent.mkdir(exist_ok=True, mode=0o700)
        shutil.move(str(displaced), str(archive_to))
    container.rmdir()

def launch_and_wait(app):
    run(["open", "-n", app])
    deadline = time.monotonic() + 25
    error = None
    while time.monotonic() < deadline:
        try:
            return live_state(app)
        except PatchError as e:
            error = e
            time.sleep(0.5)
    raise PatchError(f"Startup verification failed: {error}. Quit the app and use restore.")

def apply_plan(path, restart):
    external_harness_guard()
    path, plan = load_plan(path)
    app, stage = Path(plan["app"]), Path(plan["staged_app"])
    require_closed(app)
    if identity(app) != plan["identity"] or fingerprint(app) != plan["original_fingerprint"]:
        raise PatchError("Live application changed after preparation; prepare a fresh plan")
    if fingerprint(stage) != plan["staged_fingerprint"]:
        raise PatchError("Staged application changed after validation")
    archive = path.parent / "displaced" / app.name
    if archive.exists():
        raise PatchError("This plan has already been applied")
    install_candidate(app, stage, archive)
    plan["state"] = "applied"
    private_json(path, plan)
    if restart:
        launch_and_wait(app)
    return {"action": "applied", "app": str(app), "plan": str(path),
            "backup": plan["original_app"], "next": "verify; then panel if absent"}

def verify(app, plan_path=None):
    run(["codesign", "--verify", "--deep", "--strict", app])
    state = live_state(app)
    rt = state.pop("runtime")
    if rt["config_dir"] != "config" or rt["data_dir"] != "antigravity":
        raise PatchError("The target is not using the original Antigravity data/config namespaces")
    required_flags = list(FLAGS)
    if plan_path:
        _, requested_plan = load_plan(plan_path)
        required_flags = requested_plan.get("flags", required_flags)
    missing = [k for k in required_flags if k not in state["enabled_flags"]]
    if missing:
        raise PatchError("Requested local features are not active: " + ", ".join(missing))
    before_ids = []
    if plan_path:
        _, plan = load_plan(plan_path)
        baseline = plan.get("baseline") or {}
        if plan.get("baseline") is not None and baseline.get("conversation_id_source") != "conversation_files":
            raise PatchError("Legacy plan used resident trajectory IDs; prepare a fresh plan for durable data verification")
        before_ids = baseline.get("conversation_ids", [])
        if not set(before_ids).issubset(state["conversation_ids"]):
            raise PatchError("One or more baseline conversation identities are missing")
    result = {"version": identity(app)["version"], "auth_valid": state["auth_valid"],
              "auth_mode": state["auth_mode"], "flags": [k for k in required_flags if k in state["enabled_flags"]],
              "conversation_count": len(state["conversation_ids"]),
              "baseline_conversations_preserved": bool(before_ids),
              "config_namespace": rt["config_dir"], "data_namespace": rt["data_dir"],
              "swarm_panels": state["swarm_panels"], "ui_observation_required": True}
    return result

def restore(path, restart):
    external_harness_guard()
    path, plan = load_plan(path)
    app, original = Path(plan["app"]), Path(plan["original_app"])
    require_closed(app)
    if fingerprint(original) != plan["original_fingerprint"]:
        raise PatchError("Clean backup fingerprint changed")
    if app.exists():
        try:
            current = identity(app)
        except (PatchError, OSError, ValueError):
            # A damaged Info.plist must not strand recovery. Identify the
            # release from native files of the verified clean/staged snapshots.
            known = {sha(binary_path(original))}
            if plan.get("staged_native_sha256"):
                known.add(plan["staged_native_sha256"])
            stage = Path(plan["staged_app"])
            if stage.exists() and fingerprint(stage) == plan["staged_fingerprint"]:
                known.add(sha(binary_path(stage)))
            native = binary_path(app)
            if not native.is_file() or sha(native) not in known:
                raise PatchError("Cannot identify this corrupt app's release; "
                                 "refusing to overwrite an unknown vendor upgrade")
        else:
            if current["version"] != plan["identity"]["version"]:
                raise PatchError("Refusing to restore an older backup over another vendor version")
        if fingerprint(app) == plan["original_fingerprint"]:
            if restart:
                run(["open", "-n", app])
            return {"action": "noop", "reason": "Verified clean app already present"}
    archive = path.parent / "restored-from" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".app")
    install_candidate(app, original, archive)
    plan["state"] = "restored"
    private_json(path, plan)
    if restart:
        run(["open", "-n", app])
    return {"action": "restored", "app": str(app), "data_and_gateway_config": "retained"}

def panel(app, backup_root=DEFAULT_ROOT):
    external_harness_guard()
    info = identity(app)
    if info["version"] not in SUPPORTED:
        raise PatchError(f"Unverified viewer release {info['version']}; inspect/adapt first")
    rt = runtime(app)
    records = rpc(rt, "GetSidecars").get("sidecars", [])
    native = [x for x in records if x.get("sidecarId", "").endswith("/swarm_board")
              and x.get("config", {}).get("hasWebUi")]
    if native:
        return {"action": "native_panel_available",
                "panels": [{"id": x["sidecarId"], "status": x.get("status")} for x in native]}
    cfgroot = Path.home() / ".gemini" / rt["config_dir"]
    data = Path.home() / ".gemini" / rt["data_dir"]
    source = data / "builtin/plugins/swarm/sidecars/swarm_board"
    if not (source / "main.mjs").is_file():
        raise PatchError("The running release has not populated the native Swarm viewer")
    root = cfgroot / "sidecars/swarm"
    target = cfgroot / "swarm-ui-local/native_ui"
    owner = target / ".enable-antigravity-swarm.json"
    existing = next((x for x in records if x.get("sidecarId") == "swarm"), None)
    owned = False
    if owner.is_file() and not target.is_symlink():
        try:
            marker = json.loads(owner.read_text())
            owned = isinstance(marker, dict) and marker.get("skill_name") == "enable-antigravity-swarm"
        except (OSError, ValueError):
            pass
    if target.is_symlink() or target.parent.is_symlink():
        raise PatchError("Refusing a symlinked viewer target")
    if (target.exists() or root.exists() or existing) and not owned:
        raise PatchError("An unowned Swarm sidecar/viewer exists; inspect it before overwriting")
    if existing:
        old_config = existing.get("config", {})
        if old_config.get("command") != "node" or old_config.get("args") != [str(target / "main.mjs")]:
            raise PatchError("The existing 'swarm' record runs unrelated code; preserve it")
    else:
        old_config = None

    # Validate a complete staged payload before changing any owned viewer.
    with tempfile.TemporaryDirectory(prefix=".swarm-ui-stage-", dir=cfgroot) as td:
        stage = Path(td) / "native_ui"
        shutil.copytree(source, stage)
        p = stage / "main.mjs"
        text = p.read_text()
        needle = "app.page('/', () => readFileSync(join(__dirname, 'index.html'), 'utf-8'));"
        if text.count(needle) != 1:
            raise PatchError("Native viewer route contract changed; existing viewer retained")
        p.write_text(text.replace(needle, needle + "\n// Local Swarm UI canonical link alias.\n"
                     "app.page('/swarm_board/', () => readFileSync(join(__dirname, 'index.html'), 'utf-8'));\n"))
        private_json(stage / ".enable-antigravity-swarm.json",
                     {"skill_name": "enable-antigravity-swarm", "skill_version": SKILL_VERSION,
                      "app_version": info["version"], "source_sha256": sha(source / "main.mjs")})

        parent = Path(backup_root) / "panel-backups"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"),
                                       dir=parent))
        backup.chmod(0o700)
        shutil.copy2(cfgroot / "config.json", backup / "config.json")
        (backup / "config.json").chmod(0o600)
        if root.exists():
            run(["ditto", root, backup / "sidecar-swarm"])
        if target.exists():
            run(["ditto", target, backup / "viewer-original"])

        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        displaced = Path(td) / "previous"
        if target.exists():
            target.rename(displaced)
        try:
            stage.rename(target)
        except Exception:
            if displaced.exists():
                displaced.rename(target)
            raise

        config = {"command": "node", "args": [str(target / "main.mjs")],
                  "restartPolicy": "always", "displayName": "Swarm",
                  "description": "Native current-conversation Swarm board.", "hasWebUi": True,
                  "env": {"SWARM_GRAPH_TAB": "true", "SWARM_OVERVIEW": "false", "SWARM_RAW_TAB": "false"},
                  "agentPermissions": {"allowsUserInteractions": False},
                  "uiConfig": {"displayName": "Swarm", "views": [{"path": "/swarm_board/",
                    "entrypoint": "SIDECAR_UI_ENTRYPOINT_AUX_PANE", "title": "Swarm"}]}}
        # Preserve existing user permissions when updating our owned record.
        if old_config and old_config.get("agentPermissions"):
            config["agentPermissions"] = old_config["agentPermissions"]
        # The manager supplies ANTIGRAVITY_EXECUTABLE_DATA_DIR; do not override it.
        try:
            rpc(rt, "ManageSidecar", {"sidecarId": "swarm", "action": 7 if existing else 5, "config": config})
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                record = next((x for x in rpc(rt, "GetSidecars").get("sidecars", [])
                               if x.get("sidecarId") == "swarm"), None)
                if record and record.get("status") == "SIDECAR_STATUS_RUNNING":
                    return {"action": "panel_registered", "id": "swarm", "route": "/swarm_board/",
                            "backup": str(backup), "ui_observation_required": True}
                time.sleep(0.3)
            raise PatchError("Viewer did not reach RUNNING")
        except Exception as error:
            if old_config:
                # Restore the previous bytes even if the server is unavailable.
                if target.exists():
                    shutil.rmtree(target)
                if displaced.exists():
                    displaced.rename(target)
                detail = "previous viewer bytes restored"
            else:
                # An RPC timeout may have committed the new registration.
                # Keep its complete payload so no possible record points at
                # deleted code, even if unregistering is unavailable.
                detail = f"new viewer files retained at {target}"
            try:
                current = next((x for x in rpc(rt, "GetSidecars").get("sidecars", [])
                                if x.get("sidecarId") == "swarm"), None)
                if current and current.get("config", {}).get("args") == config["args"]:
                    if old_config:
                        rpc(rt, "ManageSidecar", {"sidecarId": "swarm", "action": 7, "config": old_config})
                        detail += "; previous registration restored"
                    else:
                        rpc(rt, "ManageSidecar", {"sidecarId": "swarm", "action": 3})
                        detail += "; unregister request completed"
                elif current:
                    detail += "; changed registration preserved, cleanup not confirmed"
                else:
                    detail += "; registration absent in the current snapshot"
            except Exception as rollback_error:
                detail += f"; registration cleanup not confirmed: {rollback_error}"
            raise PatchError(f"{error}; {detail}; panel backup: {backup}") from error

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"{SKILL_NAME} {SKILL_VERSION}")
    parser.add_argument("action", choices=("inspect", "prepare", "apply", "verify", "restore", "panel"))
    parser.add_argument("--app", type=Path, default=DEFAULT_APP)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--features", default="swarm", help="comma-separated swarm,boost,teamwork; default swarm only")
    parser.add_argument("--base-plan", type=Path, help="verified prior plan when extending compact patched defaults")
    args = parser.parse_args()
    app = args.app.expanduser().absolute()
    global FLAGS, SELECTED_FEATURES
    SELECTED_FEATURES = tuple(dict.fromkeys(x.strip() for x in args.features.split(",") if x.strip()))
    if not SELECTED_FEATURES or any(f not in FEATURE_FLAGS for f in SELECTED_FEATURES):
        parser.error("features must be swarm,boost,teamwork")
    FLAGS = tuple(dict.fromkeys(k for f in SELECTED_FEATURES for k in FEATURE_FLAGS[f]))
    try:
        if sys.platform != "darwin":
            raise PatchError("This implementation supports macOS only")
        if args.action == "inspect":
            result = inspect(app)
        elif args.action == "prepare":
            result = prepare(app, args.backup_root.expanduser().absolute(), args.base_plan)
        elif args.action == "apply":
            if not args.plan:
                parser.error("apply requires --plan")
            result = apply_plan(args.plan, args.restart)
        elif args.action == "verify":
            result = verify(app, args.plan)
        elif args.action == "restore":
            if not args.plan:
                parser.error("restore requires --plan")
            result = restore(args.plan, args.restart)
        else:
            result = panel(app, args.backup_root.expanduser().absolute())
        print(json.dumps({"skill_name": SKILL_NAME, "skill_version": SKILL_VERSION, **result}, ensure_ascii=False, indent=2))
    except (PatchError, OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
