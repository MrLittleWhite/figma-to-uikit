import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import figma_to_uikit as f

HERE = Path(__file__).parent


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class MultiScreenTests(unittest.TestCase):
    def setUp(self):
        self.ir = f.normalize(json.loads((HERE / 'fixtures/multi-screen.json').read_text()))

    def test_complete_golden_output(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            f.generate(self.ir, out)
            self.assertEqual(snapshot(out), snapshot(HERE / 'golden/multi-screen'))

    def test_select_wrappers_but_keep_nested_frames(self):
        screens = f.select_screens(self.ir['root'])
        self.assertEqual([n['id'] for n in screens], [f'screen-{i}' for i in range(1, 6)])
        self.assertEqual(screens[0]['children'][0]['id'], 'panel')
        files = f.plan_output(self.ir)
        self.assertEqual(len([p for p in files if p.endswith('ViewController.swift')]), 5)
        view = files['HomeRootView.swift']
        self.assertIn('self.addSubview(node0)', view)
        self.assertIn('node0.addSubview(node1)', view)
        self.assertIn('equalTo: self.leadingAnchor, constant: 16.0', view)
        self.assertIn('equalTo: node0.leadingAnchor, constant: 12.0', view)
        self.assertIn('equalTo: node0.topAnchor, constant: 16.0', view)

    def test_case_insensitive_duplicate_and_chinese_names(self):
        names = f.screen_names(f.select_screens(self.ir['root']))
        self.assertEqual(names['screen-1'], ('HomeViewController', 'HomeRootView'))
        flat = [name.casefold() for pair in names.values() for name in pair]
        self.assertEqual(len(flat), len(set(flat)))
        for pair in names.values():
            for name in pair:
                self.assertRegex(name, r'^[A-Za-z_][A-Za-z0-9_]*$')
        self.assertEqual(names, f.screen_names(list(reversed(f.select_screens(self.ir['root'])))))

    def test_manifest_and_capture_wide_destinations(self):
        files = f.plan_output(self.ir)
        manifest = json.loads(files['manifest.json'])
        self.assertEqual(len(manifest['screens']), 5)
        for screen in manifest['screens']:
            self.assertEqual(set(screen), {'node_id', 'controller', 'view'})
            self.assertIn(screen['controller'], files)
            self.assertIn(screen['view'], files)
        external = [d for d in manifest['diagnostics'] if d['code'] == 'external-interaction-destination']
        self.assertEqual([d['node_id'] for d in external], ['outside'])
        self.assertIn('destinationID: "screen-2"', files['HomeRootView.swift'])

    def test_shared_support_and_assets_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'logo.png').write_bytes(b'fixture png')
            files = f.generate(self.ir, root / 'out', assets_dir=root)
            self.assertEqual(len([p for p in files if p.endswith('.png')]), 1)
            self.assertEqual(len([p for p in files if p == 'DesignTokens.swift']), 1)
            self.assertEqual(len([p for p in files if p == 'Interactions.swift']), 1)
            self.assertIn('UIImage(named:', files['HomeRootView.swift'])

    def test_deterministic_repeat_and_no_ir_mutation(self):
        before = copy.deepcopy(self.ir)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = f.generate(self.ir, root / 'first')
            second = f.generate(self.ir, root / 'second')
            self.assertEqual(first, second)
            self.assertEqual(snapshot(root / 'first'), snapshot(root / 'second'))
            self.assertEqual(first, f.generate(self.ir, root / 'first', overwrite=True))
        self.assertEqual(self.ir, before)

    def test_late_screen_conflict_writes_nothing(self):
        files = f.plan_output(self.ir)
        last = json.loads(files['manifest.json'])['screens'][-1]['controller']
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / last).write_text('hand-written')
            before = snapshot(out)
            with self.assertRaises(FileExistsError):
                f.generate(self.ir, out)
            self.assertEqual(snapshot(out), before)

    def test_manifest_directory_conflict_even_with_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / 'manifest.json').mkdir()
            with self.assertRaises(FileExistsError):
                f.generate(self.ir, out, overwrite=True)
            self.assertEqual(list(out.iterdir()), [out / 'manifest.json'])

    def test_asset_parent_file_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'logo.png').write_bytes(b'fixture')
            out = root / 'out'
            out.mkdir()
            (out / 'Assets.xcassets').write_text('not a directory')
            with self.assertRaises(FileExistsError):
                f.generate(self.ir, out, assets_dir=root)
            self.assertEqual(snapshot(out), {'Assets.xcassets': b'not a directory'})

    def test_template_failure_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(f, 'TEMPLATE_DIR', root):
                with self.assertRaises(FileNotFoundError):
                    f.generate(self.ir, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_templates_resolve_without_working_directory(self):
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as td:
            try:
                os.chdir(td)
                files = f.generate(self.ir, Path(td) / 'out')
                self.assertIn('HomeRootView.swift', files)
            finally:
                os.chdir(old)

    def test_single_root_and_existing_controller_suffix(self):
        screen = copy.deepcopy(f.select_screens(self.ir['root'])[0])
        screen['name'] = 'ExampleViewController'
        single = dict(self.ir, root=screen)
        files = f.plan_output(single)
        self.assertIn('ExampleViewController.swift', files)
        self.assertIn('ExampleRootView.swift', files)
        self.assertEqual(len(json.loads(files['manifest.json'])['screens']), 1)

    def test_empty_wrapper_has_no_fake_screen(self):
        files = f.plan_output(f.normalize({'id': 'doc', 'type': 'DOCUMENT'}))
        self.assertEqual(json.loads(files['manifest.json'])['screens'], [])
        self.assertEqual(set(files), {'DesignTokens.swift', 'Interactions.swift', 'manifest.json'})

    def test_existing_case_variant_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / 'homerootview.swift').write_text('hand-written')
            with self.assertRaises(FileExistsError):
                f.generate(self.ir, out, overwrite=True)
            self.assertEqual(snapshot(out), {'homerootview.swift': b'hand-written'})


if __name__ == '__main__':
    unittest.main()
