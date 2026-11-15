"""Disposable native-contract and legacy-plan regression checks; no real app/RPC."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/antigravity-pro-unlock/scripts/antigravity_pro_unlock.py"
spec = importlib.util.spec_from_file_location("unlock", SCRIPT)
unlock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unlock)


@contextlib.contextmanager
def selected(*features):
    flags, original = unlock.FLAGS, unlock.SELECTED_FEATURES
    unlock.SELECTED_FEATURES = tuple(features)
    unlock.FLAGS = tuple(dict.fromkeys(k for f in features for k in unlock.FEATURE_FLAGS[f]))
    try:
        yield
    finally:
        unlock.FLAGS, unlock.SELECTED_FEATURES = flags, original


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pro-unlock-unit-")
        self.root = Path(self.temp.name)
        self.app = self.root / "Antigravity.app"
        self.make_app(self.app)

    def tearDown(self):
        self.temp.cleanup()

    def make_app(self, app, version="2.31.2", base=None):
        contents = app / "Contents"
        contents.mkdir(parents=True)
        (contents / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "com.google.antigravity",
            "CFBundleShortVersionString": version,
            "CFBundleName": "Antigravity", "CFBundleExecutable": "Antigravity",
        }))
        obj = {"base": base if base is not None else {
            "enable-native-swarm": False, "enable-plugins": False,
            "enable-customization-kind-plugin": False, "unknown-option": {"keep": [1, 2]},
        }, "subclients": {}, "os": {}, "model_profiles": {}, "models": {}}
        header = b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x0100000c) + b"\0" * 24
        literals = b"assets/shared/plugins/swarm/\0" + b"\0".join(
            k.encode() for values in unlock.FEATURE_FLAGS.values() for k in values)
        binary = contents / "Resources/bin/language_server"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(header + literals + b"\0" + json.dumps(obj, indent=8).encode() + b"\0END")

    def repeat_plan(self):
        directory = self.root / "legacy-plan"
        original = directory / "original/Antigravity.app"
        original.parent.mkdir(parents=True)
        shutil.copytree(self.app, original)
        with selected("swarm"):
            contract = unlock.defaults_contract(self.app)
        binary = unlock.binary_path(self.app)
        raw = bytearray(binary.read_bytes())
        start, length = contract["offset"], contract["length"]
        raw[start:start + length] = contract["patched"]
        binary.write_bytes(raw)
        plan = {"schema": 1, "skill_version": "1.1.0", "state": "verified",
                "app": str(self.app), "identity": unlock.identity(self.app),
                "original_app": str(original), "staged_app": str(directory / "staged/Antigravity.app"),
                "original_fingerprint": unlock.fingerprint(original),
                "staged_fingerprint": unlock.fingerprint(self.app),
                "flags": list(unlock.FEATURE_FLAGS["swarm"]),
                "native_span": {"offset": start, "length": length}}
        path = directory / "plan.json"
        path.write_text(json.dumps(plan))
        return path, plan, contract

    def test_default_patch_preserves_unknown_settings_and_binary_span(self):
        before = unlock.binary_path(self.app).read_bytes()
        result = unlock.defaults_contract(self.app)
        obj = json.loads(result["patched"])
        self.assertEqual(obj["base"]["unknown-option"], {"keep": [1, 2]})
        self.assertTrue(all(obj["base"][k] is True for k in unlock.FEATURE_FLAGS["swarm"]))
        self.assertNotIn("enable-owl-slash-command", obj["base"])
        self.assertEqual(len(result["patched"]), result["length"])
        self.assertEqual(unlock.binary_path(self.app).read_bytes(), before)

    def test_requested_features_only(self):
        with selected("boost", "teamwork"):
            obj = json.loads(unlock.defaults_contract(self.app)["patched"])
        self.assertTrue(obj["base"]["enable-owl-slash-command"])
        self.assertTrue(obj["base"]["enable-teamwork-subagent"])
        self.assertFalse(obj["base"]["enable-native-swarm"])

    def test_unknown_version_refuses_before_external_commands(self):
        info = self.app / "Contents/Info.plist"
        data = plistlib.loads(info.read_bytes())
        data["CFBundleShortVersionString"] = "99.0.0"
        info.write_bytes(plistlib.dumps(data))
        before = unlock.fingerprint(self.app)
        with patch.object(unlock, "external_harness_guard"), patch.object(unlock, "run") as run:
            with self.assertRaisesRegex(unlock.PatchError, "Unverified"):
                unlock.prepare(self.app, self.root / "backups")
            run.assert_not_called()
        self.assertEqual(unlock.fingerprint(self.app), before)

    def test_optional_features_on_older_release_are_refused(self):
        older = self.root / "Older.app"
        self.make_app(older, version="2.31.0")
        with selected("boost"), patch.object(unlock, "external_harness_guard"):
            with self.assertRaisesRegex(unlock.PatchError, "Unverified"):
                unlock.prepare(older, self.root / "backups")

    def test_x86_mach_o_refused(self):
        binary = unlock.binary_path(self.app)
        data = bytearray(binary.read_bytes())
        data[4:8] = struct.pack("<I", 0x01000007)
        binary.write_bytes(data)
        with self.assertRaisesRegex(unlock.PatchError, "Apple Silicon"):
            unlock.defaults_contract(self.app)

    def test_already_enabled_is_noop(self):
        other = self.root / "Enabled.app"
        self.make_app(other, base={k: True for k in unlock.FEATURE_FLAGS["swarm"]})
        with patch.object(unlock, "external_harness_guard"), patch.object(unlock, "live_state", side_effect=unlock.PatchError("not running")), patch.object(unlock, "run") as run:
            result = unlock.prepare(other, self.root / "backups")
        self.assertEqual(result["action"], "noop")
        run.assert_not_called()
        self.assertFalse((self.root / "backups").exists())

    def test_legacy_schema_one_plan_reuses_verified_capacity(self):
        path, plan, first = self.repeat_plan()
        before = unlock.binary_path(self.app).read_bytes()
        with selected("swarm", "boost", "teamwork"):
            with self.assertRaisesRegex(unlock.PatchError, "base-plan"):
                unlock.defaults_contract(self.app)
            result = unlock.defaults_contract(self.app, path)
        self.assertEqual(result["offset"], first["offset"])
        self.assertEqual(result["length"], first["length"])
        self.assertTrue(json.loads(result["patched"])["base"]["enable-teamwork-subagent"])
        self.assertEqual(unlock.binary_path(self.app).read_bytes(), before)
        self.assertEqual(unlock.load_plan(path)[1]["skill_version"], "1.1.0")

    def test_changed_current_app_refuses_capacity_reuse(self):
        path, _, _ = self.repeat_plan()
        (self.app / "Contents/new-file").write_text("changed")
        with selected("swarm", "boost"), self.assertRaisesRegex(unlock.PatchError, "current patched application"):
            unlock.defaults_contract(self.app, path)

    def test_changed_backup_refuses_capacity_reuse(self):
        path, plan, _ = self.repeat_plan()
        (Path(plan["original_app"]) / "Contents/new-file").write_text("changed")
        with selected("swarm", "boost"), self.assertRaisesRegex(unlock.PatchError, "backup changed"):
            unlock.defaults_contract(self.app, path)

    def test_non_whitespace_tail_refuses_capacity_reuse(self):
        path, plan, first = self.repeat_plan()
        binary = unlock.binary_path(self.app)
        data = bytearray(binary.read_bytes())
        data[first["offset"] + first["length"] - 1] = ord("X")
        binary.write_bytes(data)
        plan["staged_fingerprint"] = unlock.fingerprint(self.app)
        path.write_text(json.dumps(plan))
        with selected("swarm", "boost"), self.assertRaisesRegex(unlock.PatchError, "not whitespace"):
            unlock.defaults_contract(self.app, path)

    def test_plan_paths_cannot_escape_backup_directory(self):
        path, plan, _ = self.repeat_plan()
        plan["original_app"] = str(self.app)
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(unlock.PatchError, "escapes"):
            unlock.load_plan(path)

    def test_running_app_refuses_apply(self):
        path, _, _ = self.repeat_plan()
        before = unlock.fingerprint(self.app)
        with patch.object(unlock, "external_harness_guard"), patch.object(unlock, "target_processes", return_value={42: "fixture"}):
            with self.assertRaisesRegex(unlock.PatchError, "Quit Antigravity"):
                unlock.apply_plan(path, False)
        self.assertEqual(unlock.fingerprint(self.app), before)


class RuntimeBoundaryTests(unittest.TestCase):
    def test_antigravity_ancestor_refused(self):
        table = {os.getpid(): (99, "python fixture"), 99: (0, "/Applications/Antigravity.app/Contents/MacOS/Antigravity")}
        with patch.object(unlock, "processes", return_value=table), self.assertRaisesRegex(unlock.PatchError, "another harness"):
            unlock.external_harness_guard()

    def test_antigravity_environment_refused(self):
        with patch.object(unlock, "processes", return_value={}), patch.dict(os.environ, {"ANTIGRAVITY_AGENTAPI_EXE": "fixture"}), self.assertRaisesRegex(unlock.PatchError, "agent environment"):
            unlock.external_harness_guard()

    def test_non_macos_cli_refuses_mutation(self):
        stderr = io.StringIO()
        with patch.object(unlock.sys, "argv", [str(SCRIPT), "prepare"]), patch.object(unlock.sys, "platform", "linux"), contextlib.redirect_stderr(stderr):
            self.assertEqual(unlock.main(), 1)
        self.assertIn("macOS only", json.loads(stderr.getvalue())["error"])

    def test_renamed_cli_reports_identity_without_inspecting_app(self):
        stdout = io.StringIO()
        with patch.object(unlock.sys, "argv", [str(SCRIPT), "inspect"]), patch.object(unlock.sys, "platform", "darwin"), patch.object(unlock, "inspect", return_value={"app": "fixture"}), contextlib.redirect_stdout(stdout):
            self.assertEqual(unlock.main(), 0)
        self.assertEqual(json.loads(stdout.getvalue())["skill_name"], "antigravity-pro-unlock")

    def test_verify_uses_plan_flags_and_durable_conversations(self):
        with tempfile.TemporaryDirectory(prefix="pro-unlock-rpc-") as directory:
            home = Path(directory)
            conv = "11111111-2222-3333-4444-555555555555"
            folder = home / ".gemini/antigravity/conversations"
            folder.mkdir(parents=True)
            (folder / (conv + ".db")).write_bytes(b"fixture")
            plan = {"schema": 1, "original_app": str(home / "original/app"), "staged_app": str(home / "staged/app"),
                    "flags": ["enable-owl-slash-command"],
                    "baseline": {"conversation_id_source": "conversation_files", "conversation_ids": [conv]}}
            path = home / "plan.json"
            path.write_text(json.dumps(plan))
            replies = {"GetAuthStatus": {"authResult": {"hasValidAuth": True, "authMode": "AUTH_MODE_ENTERPRISE_GATEWAY"}},
                       "GetMendelFlags": {"experimentConfig": {"experiments": [{"keyString": "enable-owl-slash-command"}]}},
                       "GetAllCascadeTrajectories": {"trajectorySummaries": {}}, "GetSidecars": {"sidecars": []}}
            with patch.object(unlock, "run", return_value=""), patch.object(unlock, "runtime", return_value={"config_dir": "config", "data_dir": "antigravity"}), patch.object(unlock, "rpc", side_effect=lambda rt, method: replies[method]), patch.object(unlock.Path, "home", return_value=home), patch.object(unlock, "identity", return_value={"version": "2.31.2"}):
                result = unlock.verify(home / "fixture.app", path)
                self.assertTrue(result["baseline_conversations_preserved"])
                self.assertEqual(result["conversation_count"], 1)
                self.assertEqual(result["flags"], ["enable-owl-slash-command"])
                replies["GetMendelFlags"]["experimentConfig"]["experiments"] = []
                with self.assertRaisesRegex(unlock.PatchError, "not active"):
                    unlock.verify(home / "fixture.app", path)


if __name__ == "__main__":
    unittest.main()
