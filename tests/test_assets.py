import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from emit_assets import plan_assets


class AssetPackagingTests(unittest.TestCase):
    def test_packages_supported_assets_and_contents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "hero image.png").write_bytes(b"png")
            (root / "photo.jpg").write_bytes(b"jpg")
            (root / "doc.pdf").write_bytes(b"pdf")
            ir = {"assets": ["photo.jpg", "hero image.png", "doc.pdf"]}
            files, catalog, diagnostics = plan_assets(ir, root)
            self.assertFalse(diagnostics)
            self.assertEqual(set(catalog), set(ir["assets"]))
            self.assertEqual(len(catalog), 3)
            self.assertEqual(json.loads(files["Assets.xcassets/Contents.json"]),
                             {"info": {"author": "xcode", "version": 1}})
            for ref, name in catalog.items():
                contents = json.loads(files[f"Assets.xcassets/{name}.imageset/Contents.json"])
                filename = contents["images"][0]["filename"]
                self.assertEqual(files[f"Assets.xcassets/{name}.imageset/{filename}"], (root / ref).read_bytes())
                self.assertEqual(contents["info"], {"author": "xcode", "version": 1})

    def test_no_assets_has_no_empty_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(plan_assets({"assets": []}, td), ({}, {}, []))

    def test_all_failed_assets_has_no_root_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            files, catalog, diagnostics = plan_assets({"assets": ["missing.png"]}, td)
            self.assertEqual(files, {})
            self.assertEqual(catalog, {})
            self.assertEqual(diagnostics[0]["code"], "missing-asset")

    def test_node_asset_format_is_consumed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "icon.png").write_bytes(b"x")
            ir = {"assets": [], "root": {"children": [{"asset": {"ref": "icon.png", "format": "png"}}]}}
            files, catalog, diagnostics = plan_assets(ir, root)
            self.assertFalse(diagnostics)
            self.assertIn("icon.png", catalog)
            self.assertTrue(files)

    def test_deterministic_name_and_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "A B.PNG").write_bytes(b"bytes")
            ir = {"assets": ["A B.PNG"]}
            first = plan_assets(ir, root)
            second = plan_assets(ir, root)
            self.assertEqual(first, second)
            self.assertEqual(next(iter(first[1].values())), "A_B_" + __import__("hashlib").sha256(b"A B.PNG").hexdigest()[:8])

    def test_rejects_absolute_traversal_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            root, other = Path(td), Path(outside)
            (other / "secret.png").write_bytes(b"secret")
            (root / "link.png").symlink_to(other / "secret.png")
            refs = ["/tmp/secret.png", "../secret.png", "link.png"]
            files, catalog, diagnostics = plan_assets({"assets": refs}, root)
            self.assertFalse(files)
            self.assertFalse(catalog)
            self.assertEqual([d["code"] for d in diagnostics], ["unsafe-asset-ref", "unsafe-asset-ref", "unsafe-asset-ref"])

    def test_missing_and_unsupported_are_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "vector.svg").write_text("<svg/>")
            refs = ["missing.png", "vector.svg", "thing.gif"]
            files, catalog, diagnostics = plan_assets({"assets": refs}, root)
            self.assertFalse(files)
            self.assertFalse(catalog)
            by_ref = {d["asset_ref"]: d["code"] for d in diagnostics}
            self.assertEqual(by_ref, {"missing.png": "missing-asset", "vector.svg": "unsupported-asset-format", "thing.gif": "unsupported-asset-format"})


if __name__ == "__main__":
    unittest.main()
