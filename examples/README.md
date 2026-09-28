# Capture contract and CLI example

The converter is offline and accepts a local JSON capture, not a Figma URL fetch. A capture is either a REST node/document tree (`document`, `nodes`, or a node object) with child order preserved, or a normalized IR file. Nodes should include `id`, `type`, `name`, `children`, `absoluteBoundingBox`/`bounds`, and optional `style`, `fills`, `characters`, `imageRef`/`format`, and `reactions`/`prototypeReactions`.

Normalization extracts deterministic tokens (colors/fonts), assets, and interaction records. Unknown node types remain in the tree and produce diagnostics. SVG is only a diagnostic/asset reference: supply a PNG or PDF export for UIImage use. A URL JSON object is treated as a locator and fails with `url-not-fetched`; acquisition is intentionally left to an MCP/capture adapter.

```sh
python3 scripts/figma_to_uikit.py normalize --input examples/minimal-input.json --output /tmp/example.ir.json
python3 scripts/figma_to_uikit.py generate --input /tmp/example.ir.json --output-dir /tmp/example-generated
python3 scripts/figma_to_uikit.py validate --input /tmp/example.ir.json --swift-dir /tmp/example-generated
```

## Responsive constraint example

`examples/responsive-input.json` is a 390 × 844 frame at a nonzero canvas origin. Its children explicitly demonstrate Figma `MIN`, `MAX`, `CENTER`, `STRETCH`, and `SCALE` constraints on both axes. These are parent-relative resize rules, not Figma Auto Layout (`layoutMode`, hug/fill, padding or spacing).

```sh
python3 scripts/figma_to_uikit.py normalize --input examples/responsive-input.json --output /tmp/responsive.ir.json
python3 scripts/figma_to_uikit.py generate --input /tmp/responsive.ir.json --output-dir /tmp/responsive-generated
python3 scripts/figma_to_uikit.py validate --input /tmp/responsive.ir.json --swift-dir /tmp/responsive-generated
```

Use a fresh output directory. After integration, compare at 390 × 844 and another viewport: the header should keep 24-point side margins, the badge should stay centered, the proportional panel should retain its parent-relative position/size ratios, and the footer should keep 24-point right and 32-point bottom margins. The optional [UIKit smoke harness](../tests/ios-smoke/README.md) now verifies this fixture at 390 × 844, 430 × 932 and back on a real simulator, including UIKit pixel-edge alignment; this is geometry validation, not screenshot comparison or target-app acceptance. Font sizes and corner radii do not scale with the proportional panel.

## Multiple screens

For a multi-screen example, substitute `tests/fixtures/multi-screen.json` for the input above. The fixture exercises five screens, duplicate/case-variant/Chinese names, nested geometry, and cross-screen interactions. Expected output is in `tests/golden/multi-screen/`.

The generator descends through `DOCUMENT`, `CANVAS`, and `SECTION` containers and selects the first non-container nodes as screens. It stops there: frames nested inside a screen remain child views. A standalone node is one screen; an empty container produces no screen pair. Each selected screen receives a Controller/RootView pair. `manifest.json` maps source IDs to relative filenames through `screens` records containing `node_id`, `controller`, and `view`. Names are deterministic and case-insensitive collision-safe; do not guess filenames from design names. Tokens, interaction support, and packaged assets are shared across screens. A destination inside the capture is recognized, but navigation still needs host integration.

Templates are loaded from the Skill's `templates/` directory relative to its script, not the working directory. Copy that directory with the rest of the Skill.

Generation refuses to overwrite existing files unless `--overwrite` is explicit. Output contains separate UIViewController and RootView files, UIKit controls, fixed-geometry Auto Layout anchors, `DesignTokens.swift`, `Interactions.swift`, and a deterministic `manifest.json`. Click reactions bind to an `onInteraction` callback carrying source ID, trigger, action, and destination ID; the host must implement navigation. Other triggers produce diagnostics. Colors in `DesignTokens.swift` are observed constants, not resolved Figma variables.

Pass `generate --assets-dir /absolute/local/assets` to package PNG/JPEG/PDF resources into `Assets.xcassets` and emit `UIImage(named:)` references. Asset refs must be relative to that root; traversal and escaping symlinks are rejected. For Figma image hashes, the host should export files and rewrite refs to their local relative paths before normalization. No downloads, SVG conversion, or image decoding checks occur. Read the generated manifest for packaging and interaction diagnostics as well as the input IR diagnostics. Asset packaging does not prove Xcode asset compilation or rendering.

## Fixed-size Auto Layout

`auto-layout-input.json` adds a nonzero-origin screen with a horizontally STRETCH container, centered horizontal flow, MAX cross alignment and a nested vertical MAX/CENTER flow. Both containers explicitly declare FIXED sizing, asymmetric padding and 12pt spacing; children have unequal fixed dimensions. It does not replace `responsive-input.json`. Golden output is `tests/golden/auto-layout/`. Run normalize → validate → generate → validate as above; the sample has no diagnostics. Missing parent sizing or unsupported direct-child evidence falls back as documented in `references/input-contract.md`.
