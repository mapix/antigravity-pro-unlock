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
        literals = b"assets/shared/plugins/swarm/\0plan-execute-config\0enter_plan_mode\0exit_plan_mode\0" + b"\0".join(
            k.encode() for values in unlock.FEATURE_FLAGS.values() for k in values)
        binary = contents / "Resources/bin/language_server"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(header + literals + b"\0" + json.dumps(obj, indent=32).encode() + b"\0END")

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


class CarbonArchiveTests(unittest.TestCase):
    def test_preload_patch_preserves_unrelated_payload_and_checks_integrity(self):
        import hashlib
        with tempfile.TemporaryDirectory(prefix="carbon-archive-test-") as td:
            app = Path(td) / "Antigravity.app"
            resources = app / "Contents/Resources"
            resources.mkdir(parents=True)
            preload = b"function installCustomFlagOverridesSync() {}\ninstallCustomFlagOverridesSync();\n"
            other = b"export default 42;"
            def entry(data, offset):
                digest = hashlib.sha256(data).hexdigest()
                return {"size": len(data), "offset": str(offset), "integrity": {
                    "algorithm": "SHA256", "hash": digest, "blockSize": 4194304, "blocks": [digest]}}
            tree = {"files": {"dist": {"files": {"preload.js": entry(preload, 0),
                                                   "other.js": entry(other, len(preload))}}}}
            header = json.dumps(tree).encode()
            padded = header + b"\0" * (-len(header) % 4)
            archive = struct.pack("<IIII", 4, len(padded) + 8, len(padded) + 4, len(header)) + padded + preload + other
            (resources / "app.asar").write_bytes(archive)
            info = {"CFBundleIdentifier": "com.google.antigravity", "keep": "unchanged",
                    "ElectronAsarIntegrity": {"Resources/app.asar": {
                        "algorithm": "SHA256", "hash": hashlib.sha256(header).hexdigest()}}}
            (app / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
            unlock.patch_carbon_bridge(app)
            self.assertTrue(unlock.carbon_bridge_contract(app))
            self.assertEqual(unlock.asar_entry(app, "dist/other.js")[-1], other)
            patched = unlock.asar_entry(app)
            self.assertTrue(patched[1][8 + patched[2]:].startswith(preload + other))
            self.assertIn(b"injectCarbonModesEarly", patched[-1])
            asset = resources / "antigravity-pro-unlock/carbon_modes_bridge.js"
            asset.write_text("changed independently")
            self.assertFalse(unlock.carbon_bridge_contract(app))

    def test_duplicate_model_normalization_is_reversible_and_rejects_different_settings(self):
        requested = {"planners": [{"model_id": "gemini-4-carbon", "orchestrator_label": "Orchestrator (Carbon) (Gateway)"}]}
        config = {"models": {"defaultModelId": "gemini-4-carbon", "list": [
            {"modelId": "gemini-4-carbon", "displayName": "Orchestrator (Carbon) (Gateway)", "maxTokens": 100},
            {"modelId": "gemini-4-carbon", "displayName": "Carbon", "maxTokens": 100},
            {"modelId": "gemini-4-hydrogen", "keep": True}]}, "unknown": {"keep": [1, 2]}}
        original = json.loads(json.dumps(config))
        changes = unlock.model_row_normalization(requested, config)
        unlock.normalize_model_config(config, changes)
        self.assertEqual(len(config["models"]["list"]), 2)
        self.assertEqual(config["unknown"], original["unknown"])
        unlock.normalize_model_config(config, changes, restore=True)
        self.assertEqual(config, original)
        config["models"]["list"][1]["maxTokens"] = 200
        with self.assertRaisesRegex(unlock.PatchError, "differ"):
            unlock.model_row_normalization(requested, config)


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

    def test_runtime_excludes_language_server_multicall_commands(self):
        with tempfile.TemporaryDirectory(prefix="pro-unlock-runtime-") as directory:
            home = Path(directory)
            log = home / "Library/Logs/Antigravity/language_server.log"
            log.parent.mkdir(parents=True)
            log.write_text("language server started with pid 42\nlistening on local port at 1234 for HTTP\n")
            app = Path("/Applications/Antigravity.app")
            binary = str(unlock.binary_path(app))
            table = {42: (1, binary + " --csrf_token fixture --config_dir config --app_data_dir antigravity"),
                     43: (1, binary + " multicall schedule fixture")}
            with patch.object(unlock, "processes", return_value=table), patch.object(unlock.Path, "home", return_value=home), patch.object(unlock, "identity", return_value={"name": "Antigravity"}):
                self.assertEqual(unlock.runtime(app)["pid"], 42)

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


class OrchestratorTests(unittest.TestCase):
    setUp = NativeContractTests.setUp
    tearDown = NativeContractTests.tearDown
    make_app = NativeContractTests.make_app
    repeat_plan = NativeContractTests.repeat_plan
    def requested(self):
        return {"feature_key": unlock.ORCHESTRATOR_KEY,
                "value": {"execution_model": "MODEL_PLACEHOLDER_M340"},
                "execution": {"model_id": "gemini-4-hydrogen", "enum": "MODEL_PLACEHOLDER_M340", "label": "Hydrogen"},
                "planners": [{"model_id": "gemini-4-argon", "enum": "MODEL_PLACEHOLDER_M418", "label": "Argon",
                              "profile": unlock.ORCHESTRATOR_PROFILE_PREFIX + "MODEL_PLACEHOLDER_M418",
                              "orchestrator_label": "Orchestrator (Argon) (Gateway)"}],
                "scope": "model_profiles"}

    def test_profile_mapping_clones_original_and_preserves_other_models(self):
        obj = {"base": {"unknown": True}, "models": {"MODEL_PLACEHOLDER_M418": "existing", "MODEL_PLACEHOLDER_M340": "fast"},
               "model_profiles": {"existing": {"keep": "value"}, "fast": {"fast-option": True}}}
        requested = self.requested()
        self.assertFalse(unlock.orchestrator_defaults(obj, requested))
        unlock.orchestrator_defaults(obj, requested, write=True)
        self.assertTrue(unlock.orchestrator_defaults(obj, requested))
        profile = requested["planners"][0]["profile"]
        self.assertEqual(obj["model_profiles"][profile]["keep"], "value")
        execution_profile = unlock.ORCHESTRATOR_PROFILE_PREFIX + "executor/MODEL_PLACEHOLDER_M340"
        self.assertEqual(obj["models"]["MODEL_PLACEHOLDER_M340"], execution_profile)
        self.assertTrue(obj["model_profiles"][execution_profile]["fast-option"])
        self.assertNotIn(unlock.ORCHESTRATOR_KEY, obj["base"])

    def test_orchestrator_capacity_reuses_legacy_plan(self):
        path, _, first = self.repeat_plan()
        before = unlock.binary_path(self.app).read_bytes()
        with selected("orchestrator"), patch.object(unlock, "ORCHESTRATOR", self.requested()):
            with self.assertRaisesRegex(unlock.PatchError, "base-plan"):
                unlock.defaults_contract(self.app)
            inspected = unlock.defaults_contract(self.app, inspect_only=True)
            self.assertFalse(inspected["orchestrator_before"])
            result = unlock.defaults_contract(self.app, path)
        self.assertEqual(result["length"], first["length"])
        obj = json.loads(result["patched"])
        self.assertTrue(unlock.orchestrator_defaults(obj, self.requested()))
        self.assertEqual(unlock.binary_path(self.app).read_bytes(), before)

    def test_bad_mapping_and_profile_refused(self):
        for obj in [
            {"models": {"MODEL_PLACEHOLDER_M418": {}}, "model_profiles": {}},
            {"models": {}, "model_profiles": {self.requested()["planners"][0]["profile"]: []}},
        ]:
            with self.subTest(obj=obj), self.assertRaises(unlock.PatchError):
                unlock.orchestrator_defaults(obj, self.requested(), write=True)

    def catalog(self):
        return [dict(self.requested()["execution"]), dict(self.requested()["planners"][0])]

    def test_resolve_existing_gateway_pair(self):
        with patch.object(unlock, "model_catalog", return_value=("AUTH_MODE_ENTERPRISE_GATEWAY", self.catalog())):
            result = unlock.resolve_orchestrator(self.app)
        self.assertEqual(result["value"], {"execution_model": "MODEL_PLACEHOLDER_M340"})
        self.assertEqual(result["planners"][0]["model_id"], "gemini-4-argon")

    def test_missing_execution_mapping_refused(self):
        with patch.object(unlock, "model_catalog", return_value=("AUTH_MODE_ENTERPRISE_GATEWAY", self.catalog()[1:])), self.assertRaisesRegex(unlock.PatchError, "available planner"):
            unlock.resolve_orchestrator(self.app)

    def test_unknown_enum_refused(self):
        rows = self.catalog(); rows[0]["enum"] = "MODEL_PLACEHOLDER_M999"
        with patch.object(unlock, "model_catalog", return_value=("AUTH_MODE_ENTERPRISE_GATEWAY", rows)), self.assertRaisesRegex(unlock.PatchError, "Uninspected"):
            unlock.resolve_orchestrator(self.app)

    def test_non_gateway_pair_refused(self):
        with patch.object(unlock, "model_catalog", return_value=("AUTH_MODE_GOOGLE", self.catalog())), self.assertRaisesRegex(unlock.PatchError, "gateway mode"):
            unlock.resolve_orchestrator(self.app)

    def test_same_model_pair_refused(self):
        with patch.object(unlock, "model_catalog", return_value=("AUTH_MODE_ENTERPRISE_GATEWAY", self.catalog())), self.assertRaisesRegex(unlock.PatchError, "different"):
            unlock.resolve_orchestrator(self.app, "gemini-4-argon", "gemini-4-argon")

    def test_model_labels_preserve_routing_unknown_settings_and_restore(self):
        path = self.root / "config.json"
        config = {"gateway": {"url": "https://example.invalid", "apiKey": "fixture"},
                  "models": {"defaultModelId": "gemini-4-argon", "list": [{"modelId": "gemini-4-argon", "displayName": "Argon", "unknown": 7}]},
                  "userSettings": {"keep": True}}
        path.write_text(json.dumps(config))
        plan = {"config_dir": str(self.root), "model_label_patches": unlock.model_label_patches(self.requested(), path)}
        unlock.apply_model_labels(plan)
        changed = json.loads(path.read_text())
        self.assertEqual(changed["gateway"], config["gateway"])
        self.assertEqual(changed["userSettings"], config["userSettings"])
        self.assertEqual(changed["models"]["list"][0]["modelId"], "gemini-4-argon")
        self.assertEqual(changed["models"]["list"][0]["unknown"], 7)
        unlock.apply_model_labels(plan, restore=True)
        self.assertEqual(json.loads(path.read_text()), config)

    def test_changed_model_label_refused_without_writes(self):
        path = self.root / "config.json"
        path.write_text(json.dumps({"models": {"list": [{"modelId": "gemini-4-argon", "displayName": "Argon"}]}}))
        changes = unlock.model_label_patches(self.requested(), path)
        path.write_text(json.dumps({"models": {"list": [{"modelId": "gemini-4-argon", "displayName": "User choice"}]}}))
        before = path.read_bytes()
        with self.assertRaisesRegex(unlock.PatchError, "independently"):
            unlock.apply_model_labels({"config_dir": str(self.root), "model_label_patches": changes})
        self.assertEqual(path.read_bytes(), before)

    def test_restore_native_pruned_data_only_restores_missing_files(self):
        directory = self.root / "plan"
        snapshot = directory / "data-original/conversations"
        snapshot.mkdir(parents=True)
        data = self.root / "live-data/conversations"
        data.mkdir(parents=True)
        names = ["11111111-2222-3333-4444-555555555555.db", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.db"]
        for name in names:
            (snapshot / name).write_bytes(b"original")
        (data / names[1]).write_bytes(b"newer-live-data")
        plan = {"original_app": str(directory / "original/Antigravity.app"), "data_dir": str(self.root / "live-data"),
                "conversation_snapshot": {"directory": str(snapshot), "files": {name: unlock.sha(snapshot / name) for name in names}}}
        restored = unlock.restore_pruned_conversation_files(plan)
        self.assertEqual(restored, [names[0][:-3]])
        self.assertEqual((data / names[1]).read_bytes(), b"newer-live-data")
        (data / names[0]).unlink()
        (snapshot / names[0]).write_bytes(b"tampered")
        with self.assertRaisesRegex(unlock.PatchError, "changed"):
            unlock.restore_pruned_conversation_files(plan)

    def test_pro_preset_resolves_only_verified_release_features(self):
        with patch.object(unlock.sys, "argv", [str(SCRIPT), "inspect", "--features", "pro"]), patch.object(unlock.sys, "platform", "darwin"), patch.object(unlock, "identity", return_value={"version": "2.31.0"}), patch.object(unlock, "inspect", return_value={"fixture": True}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(unlock.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["selected_features"], ["swarm"])
        unlock.SELECTED_FEATURES = ("swarm",)
        unlock.FLAGS = unlock.FEATURE_FLAGS["swarm"]


if __name__ == "__main__":
    unittest.main()
