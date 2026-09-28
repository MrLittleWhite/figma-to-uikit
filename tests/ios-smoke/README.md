# Optional UIKit simulator smoke

Requires macOS, full selected Xcode 16+, an installed Simulator SDK, and an existing available iOS 15+ simulator. Newer Xcode releases may impose a newer XCTest runtime minimum. No third-party dependencies are used.

```sh
python3 scripts/figma_to_uikit.py test
python3 scripts/run_ios_smoke.py --output-dir /tmp/my-new-uikit-smoke
python3 scripts/run_ios_smoke.py --device EXISTING-UDID --require-simulator
```

Paths are resolved from the script, not the current directory. `--output-dir` must not exist (including dangling symlinks); otherwise the runner refuses it. Without that option, a fresh temporary directory is created and its path printed. Outputs are retained, not automatically removed.

## What runs

The static `UIKitSmoke.xcodeproj` and shared `UIKitSmoke` scheme are copied into the retained directory. The unchanged `examples/responsive-input.json` `examples/auto-layout-input.json` and independent `Fixtures/asset-input.json` are combined into one DOCUMENT. Existing normalize, validate, generate and asset-packaging code generates three controllers, three root views and one copy each of shared support. Generated Swift manifest entries and actual files must match the project references. The committed `Fixtures/smoke.png` is a real 2×3 opaque red PNG.

An app-hosted XCTest runs three named tests:

- `GeneratedLayoutTests/testResponsiveLayoutRoundTrip()`: real window/controller containment with a fixed child root, explicitly sized 390×844 → 430×932 → 390×844. Checks four fixture-owned children, finite frames, no ambiguous layout, STRETCH/MIN header, CENTER badge, SCALE panel and MAX footer. Expected edges are independently rounded to the real hosting screen's pixel grid, then compared with 0.1pt tolerance. A separate UIKit view constrained with constant values verifies pixel-edge rounding without using generated SCALE guides. System control implementation subviews are not inspected.
- `GeneratedLayoutTests/testPackagedImageDecodes()`: generated UIImageView loads the compiled catalog image, checks 2×3 dimensions, draws CGImage pixels into a bitmap and checks red/alpha values.

The runner invokes `xcodebuild test` with isolated DerivedData and result bundle, signing disabled, parallel testing disabled and bounded test execution. Xcode's JSON `xcresulttool get test-results tests` output must show both named tests passed; an exit-zero build with no/missing/skipped/failed tests is not accepted.

## Device lifecycle and evidence

Default selection is deterministic and prefers already booted eligible iPhones. `--device` accepts an available existing iOS simulator UDID. A shutdown selection is booted and awaited. The runner **never creates, deletes, erases or shuts down simulators**; any device it boots remains running. Tests install/launch the smoke app on that selected device. Avoid selecting a device busy with another task.

Discovery commands have 60-second limits, boot 120 seconds, readiness 300 seconds and build/test 1200 seconds. Timeout or Ctrl-C stops the runner's own process group, not CoreSimulator services. Each stage has a retained combined stdout/stderr log. `summary.json` records status, reason, exit code, version, device initial state, boot request, commands and evidence paths. Generated capture/IR/project, build products and `.xcresult` remain available even after failure. Successful runs also retain `test-results.json`. Argument parsing errors and refused output paths cannot write a summary into the refused directory.

| Exit | Meaning |
| --- | --- |
| 0 | Both expected XCTest cases passed |
| 1 | Generation, command, build, runtime, evidence or timeout failure; also unavailable environment with `--require-simulator` |
| 2 | Invalid invocation/output path/explicit device |
| 77 | Supported simulator environment unavailable |
| 130 | Interrupted |

Ordinary Python tests mock process/environment access; they never start Xcode or a simulator. This smoke is not screenshot comparison, a complete constraint-conflict proof, RTL/Dynamic Type coverage or target-app integration acceptance. Inspect retained logs and still run the real application's scheme. The project targets iOS 15; the verified runtime need not be iOS 15.

## Initial real-run finding

The first real run built and decoded the image but exposed pixel alignment in the layout assertion: at 3× scale, ideal panel y=168.8 / height=168.8 becomes y=168.6667 / height=169.0. Rounding independent minimum/maximum edges (maxY=337.6 → 337.6667), rather than rounding height, handles UIKit behavior while retaining a 0.1pt comparison tolerance. The revised test obtains scale from its real window and checks an independent constant-constraint UIKit control. This changes smoke assertions only, not generator semantics.


- `GeneratedLayoutTests/testAutoLayoutRoundTrip()`: nested horizontal/vertical fixed flow, asymmetric padding, unequal child sizes, CENTER/MAX alignment, 12pt sibling gaps and a STRETCH container. Checks 390×844 → 430×932 → 390×844 against independently written expected rectangles; finite frames and no ambiguity. Runner requires all three named tests to be Passed (missing/skipped fails).

Verified 2026-09-28: 96 Python tests passed; real build, link, asset catalog compilation and all 3 app-hosted XCTest cases passed on existing booted iPhone 17 / iOS 26.5, Xcode 27.0 SDK 27.0. Run started from `/tmp` using the absolute runner path. Evidence retained at `/tmp/figma-uikit-auto-layout-smoke-20260928/`: `summary.json`, `test-results.json`, `Tests.xcresult`, `xcodebuild-test.log` and staged generated files. No simulator was created, erased, deleted or shut down; existing booted device was left running.

Build warnings remain: manual target order deprecation, UIApplication.windows deprecation, skipped AppIntents metadata and XCTest libraries targeting iOS 17 while project target is iOS 15. This is not iOS 15 runtime evidence, Figma screenshot comparison, Dynamic Type/RTL validation or a full hug/fill engine.
