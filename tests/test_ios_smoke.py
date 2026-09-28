"""Offline runner regression: mock all process/environment access, never run Xcode."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import run_ios_smoke as smoke

RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-18-0"


def device(udid="AAAA", state="Shutdown", name="iPhone 16"):
    return {"udid": udid, "state": state, "name": name, "isAvailable": True}


def results(status="Passed"):
    return {"testNodes": [{"nodeType": "Test Suite", "children": [
        {"nodeType": "Test Case", "nodeIdentifier": name, "result": status}
        for name in sorted(smoke.EXPECTED)]}]}


class DeviceTests(unittest.TestCase):
    def test_prefers_booted_and_is_deterministic(self):
        a, b = device("A"), device("B", "Booted")
        for values in ([a, b], [b, a]):
            self.assertEqual(smoke.select_device({"devices": {RUNTIME: values}})["udid"], "B")

    def test_explicit_device(self):
        value = smoke.select_device({"devices": {RUNTIME: [device()]}}, "aaaa")
        self.assertEqual(value["udid"], "AAAA")
        with self.assertRaises(smoke.InvocationError):
            smoke.select_device({"devices": {RUNTIME: [device()]}}, "missing")

    def test_unavailable_or_non_ios_or_old_not_selected(self):
        for payload in ({"devices": {}}, {"devices": {"watchOS": [device()]}},
                        {"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-14-0": [device()]}},
                        {"devices": {RUNTIME: [dict(device(), isAvailable=False)]}},
                        {"devices": {RUNTIME: [device(state="Booting")]}}):
            with self.assertRaises(smoke.Unavailable):
                smoke.select_device(payload)

    def test_malformed_discovery_is_failure(self):
        for payload in ({}, {"devices": []}, {"devices": {RUNTIME: {}}}, {"devices": {RUNTIME: [{}]}}):
            with self.assertRaises(ValueError):
                smoke.select_device(payload)


class StagingTests(unittest.TestCase):
    def test_combined_pipeline_and_project_references(self):
        with tempfile.TemporaryDirectory() as td:
            project = smoke.stage(Path(td))
            ir = json.loads((Path(td) / "ir.json").read_text())
            self.assertEqual(ir["root"]["type"], "DOCUMENT")
            self.assertEqual(len(ir["root"]["children"][0]["children"]), 4)
            generated = project / "Generated"
            self.assertEqual(len(list(generated.glob("*.swift"))), 8)
            self.assertTrue((generated / "Assets.xcassets/Contents.json").is_file())
            image = next(generated.glob("Assets.xcassets/*/*.png"))
            self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertIn("UIImage(named:", (generated / "AssetExampleRootView.swift").read_text())

    def test_manifest_mismatch_fails(self):
        real_generate = smoke.generate
        def extra(ir, output, **kwargs):
            real_generate(ir, output, **kwargs)
            (output / "Unexpected.swift").write_text("import UIKit")
        with tempfile.TemporaryDirectory() as td, patch.object(smoke, "generate", side_effect=extra):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                smoke.stage(Path(td))

    def test_command_uses_isolated_paths_and_no_parallel_clones(self):
        command = smoke.test_command(Path("/tmp/a space/project"), Path("/tmp/a space"), device())
        self.assertIn("/tmp/a space/project/UIKitSmoke.xcodeproj", command)
        self.assertEqual(command[command.index("-parallel-testing-enabled") + 1], "NO")
        self.assertIn("CODE_SIGNING_ALLOWED=NO", command)
        self.assertIn("platform=iOS Simulator,id=AAAA", command)
        self.assertIn("/tmp/a space/Tests.xcresult", command)


class EvidenceTests(unittest.TestCase):
    def test_named_tests_pass(self):
        self.assertEqual(set(smoke.verify_results(results())), smoke.EXPECTED)

    def test_zero_missing_failed_skipped_not_pass(self):
        missing = results()
        missing["testNodes"][0]["children"].pop()
        for value in ({"testNodes": []}, missing, results("Failed"), results("Skipped"), {}, []):
            with self.assertRaises(ValueError):
                smoke.verify_results(value)

    def test_failure_attempt_not_hidden_by_pass(self):
        value = results()
        value["testNodes"][0]["children"].extend(results("Failed")["testNodes"][0]["children"])
        with self.assertRaises(ValueError):
            smoke.verify_results(value)


class CommandTests(unittest.TestCase):
    def test_subprocess_is_grouped_and_logged(self):
        with tempfile.TemporaryDirectory() as td, patch.object(smoke.subprocess, "Popen") as popen:
            process = popen.return_value
            process.wait.return_value = 0
            summary = {"commands": []}
            smoke.Commands(Path(td), summary).run("sample", ["fake", "a b"], timeout=9)
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            self.assertNotIn("shell", popen.call_args.kwargs)
            self.assertEqual(summary["commands"][0]["returncode"], 0)
            process.wait.assert_called_once_with(timeout=9)

    def test_timeout_and_interrupt_cleanup(self):
        for error in (subprocess.TimeoutExpired("fake", 1), KeyboardInterrupt()):
            with tempfile.TemporaryDirectory() as td, patch.object(smoke.subprocess, "Popen") as popen, patch.object(smoke, "stop_group") as stop:
                popen.return_value.wait.side_effect = error
                with self.assertRaises(type(error)):
                    smoke.Commands(Path(td), {"commands": []}).run("fake", ["fake"])
                stop.assert_called_once_with(popen.return_value)

    def test_nonzero_is_failure(self):
        with tempfile.TemporaryDirectory() as td, patch.object(smoke.subprocess, "Popen") as popen:
            popen.return_value.wait.return_value = 65
            with self.assertRaisesRegex(RuntimeError, "exited 65"):
                smoke.Commands(Path(td), {"commands": []}).run("fake", ["fake"])

    def test_cleanup_targets_only_own_group(self):
        process = MagicMock(pid=4321)
        process.wait.side_effect = [subprocess.TimeoutExpired("fake", 5), 0]
        with patch.object(smoke.os, "killpg") as kill:
            smoke.stop_group(process)
        self.assertEqual(kill.call_args_list[0].args, (4321, signal.SIGTERM))
        self.assertEqual(kill.call_args_list[1].args, (4321, signal.SIGKILL))


class RunnerTests(unittest.TestCase):
    def run_main(self, error=None, state="Booted", require=False):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "new"
            selected = dict(device(state=state), runtime=RUNTIME)
            calls = []
            def preflight(commands, summary, requested):
                if error and isinstance(error, (smoke.Unavailable, smoke.InvocationError)):
                    raise error
                summary["device"] = dict(selected, initial_state=state, boot_requested_by_runner=False)
                return selected
            def run(commands, name, args, timeout=60):
                calls.append(args)
                if error:
                    raise error
                return json.dumps(results())
            with patch.object(smoke, "preflight", side_effect=preflight), patch.object(smoke, "stage", return_value=out / "project"), patch.object(smoke.Commands, "run", new=run):
                code = smoke.main(["--output-dir", str(out)] + (["--require-simulator"] if require else []))
            return code, json.loads((out / "summary.json").read_text()), calls

    def test_booted_is_never_booted_again_or_shutdown(self):
        code, summary, calls = self.run_main()
        self.assertEqual(code, 0)
        self.assertFalse(summary["device"]["boot_requested_by_runner"])
        self.assertFalse(any("boot" in c for c in calls))
        self.assertFalse(any(verb in c for c in calls for verb in ("shutdown", "delete", "erase", "create")))

    def test_shutdown_boots_and_is_left_running(self):
        code, summary, calls = self.run_main(state="Shutdown")
        self.assertEqual(code, 0)
        self.assertTrue(summary["device"]["boot_requested_by_runner"])
        self.assertTrue(summary["device"]["left_running"])
        self.assertEqual(sum("boot" in c for c in calls), 1)
        self.assertFalse(any(verb in c for c in calls for verb in ("shutdown", "delete", "erase", "create")))

    def test_unavailable_codes(self):
        self.assertEqual(self.run_main(smoke.Unavailable("no Xcode"))[0], 77)
        self.assertEqual(self.run_main(smoke.Unavailable("no Xcode"), require=True)[0], 1)

    def test_explicit_device_invocation_error(self):
        self.assertEqual(self.run_main(smoke.InvocationError("unknown device"))[0], 2)

    def test_failure_timeout_interrupt_reported(self):
        for error, expected in ((RuntimeError("build failed"), 1),
                                (subprocess.TimeoutExpired("xcodebuild", 1200), 1),
                                (ValueError("bad JSON"), 1), (KeyboardInterrupt(), 130)):
            code, summary, _ = self.run_main(error)
            self.assertEqual(code, expected)
            self.assertEqual(summary["exit_code"], expected)
            self.assertTrue(summary["reason"])

    def test_existing_directory_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td, patch.object(smoke, "preflight") as preflight:
            path = Path(td)
            (path / "keep").write_text("untouched")
            self.assertEqual(smoke.main(["--output-dir", td]), 2)
            link = path / "link"
            link.symlink_to(path / "absent")
            self.assertEqual(smoke.main(["--output-dir", str(link)]), 2)
            preflight.assert_not_called()
            self.assertEqual((path / "keep").read_text(), "untouched")

    def test_non_macos_is_unavailable_without_commands(self):
        commands = MagicMock()
        with patch.object(smoke.platform, "system", return_value="Linux"):
            with self.assertRaises(smoke.Unavailable):
                smoke.preflight(commands, {}, None)
        commands.run.assert_not_called()

    def test_preflight_old_xcode_and_malformed_json(self):
        commands = MagicMock()
        with patch.object(smoke.platform, "system", return_value="Darwin"), patch.object(smoke.shutil, "which", return_value="/fake/tool"), patch.object(Path, "is_dir", return_value=True):
            commands.run.side_effect = ["/fake/Xcode/Contents/Developer", "Xcode 15.0"]
            with self.assertRaises(smoke.Unavailable):
                smoke.preflight(commands, {}, None)
            commands.run.side_effect = ["/fake/Xcode/Contents/Developer", "Xcode 16.0", "iphonesimulator18.0", "18.0", "not json"]
            with self.assertRaises(ValueError):
                smoke.preflight(commands, {}, None)


if __name__ == "__main__":
    unittest.main()
