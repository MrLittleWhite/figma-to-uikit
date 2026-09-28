#!/usr/bin/env python3
"""Optional real UIKit smoke; standard library only, Xcode 16+ JSON evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile

from figma_to_uikit import normalize, validate, generate

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "GeneratedLayoutTests/testResponsiveLayoutRoundTrip()",
    "GeneratedLayoutTests/testPackagedImageDecodes()",
    "GeneratedLayoutTests/testAutoLayoutRoundTrip()",
}


class Unavailable(Exception):
    pass


class InvocationError(Exception):
    pass


def stop_group(process):
    """Stop only our newly-created process group, never simulator services."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # A parent can exit while its descendants still hold the group alive.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


class Commands:
    def __init__(self, output, summary):
        self.output = output
        self.summary = summary

    def run(self, name, args, timeout=60):
        log = self.output / (name + ".log")
        record = {"stage": name, "argv": [str(a) for a in args], "log": str(log), "timeout_seconds": timeout}
        self.summary["commands"].append(record)
        with log.open("wb") as stream:
            process = subprocess.Popen(record["argv"], stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                record["returncode"] = process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                stop_group(process)
                raise
        if record["returncode"]:
            raise RuntimeError(f"{name} exited {record['returncode']}; see {log}")
        return log.read_text(encoding="utf-8", errors="replace")


def select_device(payload, requested=None):
    if not isinstance(payload, dict) or not isinstance(payload.get("devices"), dict):
        raise ValueError("Invalid simctl devices JSON")
    eligible = []
    for runtime, devices in payload["devices"].items():
        if not isinstance(devices, list):
            raise ValueError("Invalid simctl device list")
        for device in devices:
            if not isinstance(device, dict) or not all(k in device for k in ("udid", "name", "state", "isAvailable")):
                raise ValueError("Invalid simctl device entry")
            match = re.fullmatch(r"com\.apple\.CoreSimulator\.SimRuntime\.iOS-(\d+)(?:-\d+)*", runtime)
            if match and int(match[1]) >= 15 and device["isAvailable"] is True:
                if device["state"] in ("Booted", "Shutdown"):
                    eligible.append(dict(device, runtime=runtime))
    if requested:
        matches = [d for d in eligible if d["udid"].lower() == requested.lower()]
        if not matches:
            raise InvocationError("Requested UDID is not an available iOS 15+ device in Booted/Shutdown state")
        return matches[0]
    phones = [d for d in eligible if d.get("deviceTypeIdentifier", "").startswith("com.apple.CoreSimulator.SimDeviceType.iPhone-")
              or d["name"].startswith("iPhone")]
    if not phones:
        raise Unavailable("No available iOS 15+ iPhone simulator")
    return sorted(phones, key=lambda d: (d["state"] != "Booted", d["runtime"], d["name"], d["udid"]))[0]


def preflight(commands, summary, requested):
    if platform.system() != "Darwin":
        raise Unavailable("macOS with full Xcode 16+ is required")
    for tool in ("xcode-select", "xcodebuild", "xcrun"):
        if shutil.which(tool) is None:
            raise Unavailable(f"Missing {tool}")
    developer = commands.run("developer-directory", ["xcode-select", "-p"]).strip()
    if not (Path(developer) / "Platforms/iPhoneSimulator.platform").is_dir():
        raise Unavailable("Selected developer directory has no Simulator platform; select full Xcode")
    version = commands.run("xcode-version", ["xcodebuild", "-version"])
    summary["xcode"] = version.strip()
    match = re.search(r"^Xcode (\d+)", version, re.MULTILINE)
    if not match:
        raise ValueError("Unrecognized xcodebuild version output")
    if int(match[1]) < 16:
        raise Unavailable("Xcode 16+ is required for xcresulttool test-results JSON")
    sdks = commands.run("sdk-list", ["xcodebuild", "-showsdks"])
    if "iphonesimulator" not in sdks:
        raise Unavailable("No iOS Simulator SDK installed")
    summary["sdk"] = commands.run("sdk-version", ["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"]).strip()
    devices = json.loads(commands.run("devices-before", ["xcrun", "simctl", "list", "devices", "--json"]))
    device = select_device(devices, requested)
    summary["device"] = {k: device[k] for k in ("udid", "name", "state", "runtime")}
    summary["device"]["initial_state"] = device["state"]
    summary["device"]["boot_requested_by_runner"] = False
    return device


def stage(output):
    template = ROOT / "tests/ios-smoke"
    project = output / "project"
    shutil.copytree(template, project)
    responsive = json.loads((ROOT / "examples/responsive-input.json").read_text())
    asset = json.loads((template / "Fixtures/asset-input.json").read_text())
    auto = json.loads((ROOT / "examples/auto-layout-input.json").read_text())
    capture = {"id": "smoke:document", "type": "DOCUMENT", "name": "Smoke", "children": [responsive, asset, auto]}
    (output / "capture.json").write_text(json.dumps(capture, indent=2) + "\n")
    ir = normalize(capture)
    errors, _ = validate(ir)
    if errors:
        raise ValueError("Invalid smoke IR: " + "; ".join(errors))
    (output / "ir.json").write_text(json.dumps(ir, indent=2) + "\n")
    generated = project / "Generated"
    generate(ir, generated, assets_dir=project / "Fixtures")
    manifest = json.loads((generated / "manifest.json").read_text())
    if any(d.get("level") == "error" for d in manifest["diagnostics"]):
        raise ValueError("Asset generation reported errors")
    project_text = (project / "UIKitSmoke.xcodeproj/project.pbxproj").read_text()
    references = set(re.findall(r"path = Generated/([^;]+\.swift);", project_text))
    declared = {p for p in manifest["files"] if p.endswith(".swift")}
    actual = {str(p.relative_to(generated)) for p in generated.rglob("*.swift")}
    if not references or references != declared or actual != declared:
        raise ValueError(f"Generated Swift/project mismatch: refs={references}, manifest={declared}, actual={actual}")
    if not (generated / "Assets.xcassets/Contents.json").is_file():
        raise ValueError("Missing compiled catalog input")
    return project


def test_command(project, output, device):
    return ["xcodebuild", "test", "-project", str(project / "UIKitSmoke.xcodeproj"),
            "-scheme", "UIKitSmoke", "-configuration", "Debug", "-sdk", "iphonesimulator",
            "-destination", f"platform=iOS Simulator,id={device['udid']}",
            "-destination-timeout", "120", "-derivedDataPath", str(output / "DerivedData"),
            "-resultBundlePath", str(output / "Tests.xcresult"), "-parallel-testing-enabled", "NO",
            "-maximum-concurrent-test-simulator-destinations", "1", "-disable-concurrent-destination-testing",
            "-test-timeouts-enabled", "YES", "-default-test-execution-time-allowance", "60",
            "-maximum-test-execution-time-allowance", "120", "CODE_SIGNING_ALLOWED=NO"]


def verify_results(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("testNodes"), list):
        raise ValueError("Invalid xcresult test-results tests JSON")
    results = {}
    def visit(node):
        if not isinstance(node, dict):
            raise ValueError("Invalid xcresult test node")
        if node.get("nodeType") == "Test Case":
            identifier = node.get("nodeIdentifier", "")
            results.setdefault(identifier, []).append(node.get("result"))
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError("Invalid xcresult children")
        for child in children:
            visit(child)
    for node in payload["testNodes"]:
        visit(node)
    if not EXPECTED.issubset(results) or any(r != "Passed" for statuses in results.values() for r in statuses):
        raise ValueError(f"Expected named tests did not all pass: {results}")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="Existing available iOS simulator UDID")
    parser.add_argument("--output-dir", type=Path, help="New retained directory; existing paths are refused")
    parser.add_argument("--require-simulator", action="store_true", help="Convert environment-unavailable exit 77 to failure 1")
    args = parser.parse_args(argv)
    try:
        if args.output_dir is None:
            output = Path(tempfile.mkdtemp(prefix="figma-uikit-smoke-"))
        else:
            output = args.output_dir.expanduser().absolute()
            output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(f"Invalid output directory: {error}", file=sys.stderr)
        return 2
    summary = {"status": "running", "commands": [], "output_dir": str(output),
               "expected_tests": sorted(EXPECTED), "simulator_policy": "Never create, delete, erase or shutdown; leave booted devices running"}
    print(f"Retained smoke evidence: {output}", flush=True)
    commands = Commands(output, summary)
    code = 1
    try:
        device = preflight(commands, summary, args.device)
        project = stage(output)
        summary["project"] = str(project)
        if device["state"] != "Booted":
            summary["device"]["boot_requested_by_runner"] = True
            commands.run("boot", ["xcrun", "simctl", "boot", device["udid"]], timeout=120)
        commands.run("boot-ready", ["xcrun", "simctl", "bootstatus", device["udid"], "-b"], timeout=300)
        summary["device"]["left_running"] = True
        commands.run("xcodebuild-test", test_command(project, output, device), timeout=1200)
        result = output / "Tests.xcresult"
        raw = commands.run("xcresult-tests", ["xcrun", "xcresulttool", "get", "test-results", "tests", "--path", str(result), "--format", "json"])
        payload = json.loads(raw)
        (output / "test-results.json").write_text(json.dumps(payload, indent=2) + "\n")
        summary["tests"] = verify_results(payload)
        summary["xcresult"] = str(result)
        summary["status"], summary["reason"], code = "passed", "All expected XCTest cases passed", 0
    except Unavailable as error:
        code = 1 if args.require_simulator else 77
        summary["status"], summary["reason"] = ("failed" if code == 1 else "unavailable"), str(error)
    except InvocationError as error:
        code = 2
        summary["status"], summary["reason"] = "invocation-error", str(error)
    except KeyboardInterrupt:
        code = 130
        summary["status"], summary["reason"] = "interrupted", "Interrupted; runner process group stopped, evidence retained"
    except Exception as error:
        summary["status"], summary["reason"] = "failed", f"{type(error).__name__}: {error}"
    finally:
        summary["exit_code"] = code
        summary["evidence"] = sorted(str(p) for p in output.iterdir())
        (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"{summary['status']}: {summary['reason']}\nSummary: {output / 'summary.json'}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
