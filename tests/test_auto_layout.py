import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import figma_to_uikit as f
import auto_layout as a


def fixture():
    return json.loads((ROOT / 'examples/auto-layout-input.json').read_text())


def flow():
    return fixture()['children'][0]


class AutoLayoutTests(unittest.TestCase):
    def test_capture_version_and_independent_item(self):
        raw = flow(); raw['children'][0]['layoutSizingHorizontal'] = 'FILL'
        ir = f.normalize(raw)
        self.assertEqual(ir['root']['layout']['version'], 1)
        self.assertEqual(ir['root']['children'][0]['layout_item'], {'version': 1, 'horizontal_sizing': 'FILL'})
        self.assertFalse(a.analyze(ir['root'])[0])

    def test_all_alignment_pairs_both_axes(self):
        for mode in ('HORIZONTAL', 'VERTICAL'):
            for primary in ('MIN', 'CENTER', 'MAX'):
                for cross in ('MIN', 'CENTER', 'MAX'):
                    with self.subTest(mode=mode, primary=primary, cross=cross):
                        raw = flow(); raw.update(layoutMode=mode, primaryAxisAlignItems=primary, counterAxisAlignItems=cross)
                        n = f.normalize(raw)['root']; rows = a.equations(n)
                        # Independently computed fixture constants, not a second implementation.
                        main = {'HORIZONTAL': {'MIN': 40, 'CENTER': -86, 'MAX': -212},
                                'VERTICAL': {'MIN': 10, 'CENTER': -126, 'MAX': -262}}[mode]
                        side = {'HORIZONTAL': {'MIN': 10, 'CENTER': -10, 'MAX': -30},
                                'VERTICAL': {'MIN': 40, 'CENTER': 10, 'MAX': -20}}[mode]
                        self.assertEqual(rows[0][-1], main[primary]); self.assertEqual(rows[1][-1], side[cross])
                        self.assertEqual(rows[4][-1], 12)
                        self.assertFalse(f.validate(f.normalize(raw))[0])

    def test_empty_single_and_zero_spacing(self):
        for count in (0, 1, 2):
            raw = flow(); raw['children'] = raw['children'][:count]; raw['itemSpacing'] = 0
            n = f.normalize(raw)['root']; self.assertEqual(len(a.equations(n)), count * 4)
            swift = f.plan_output(f.normalize(raw))['AutoRowRootView.swift']
            self.assertNotIn('UIStackView', swift)

    def test_flow_overrides_constraints_even_overflowing_scale(self):
        raw = flow(); raw['bounds']['width'] = 1e-300
        raw['children'][0]['bounds']['x'] = 1e300
        raw['children'][0]['constraints'] = {'horizontal': 'SCALE'}
        ir = f.normalize(raw); self.assertEqual(f.validate(ir)[0], [])
        self.assertNotIn('ScaleGuide', f.plan_output(ir)['AutoRowRootView.swift'])
        raw['children'][0]['constraints']['horizontal'] = 'INVALID'
        with self.assertRaises(ValueError): f.normalize(raw)

    def test_whole_direct_child_fallback_and_nested_independence(self):
        raw = flow(); raw['children'][0]['layoutPositioning'] = 'ABSOLUTE'
        n = f.normalize(raw)['root']
        self.assertFalse(a.analyze(n)[0]); self.assertTrue(a.analyze(n['children'][1])[0])
        swift = f.plan_output(f.normalize(raw))['AutoRowRootView.swift']
        self.assertIn('node0.leadingAnchor.constraint(equalTo: self.leadingAnchor, constant: -24.0)', swift)
        self.assertIn('node3.topAnchor.constraint(equalTo: node2.bottomAnchor, constant: 12)', swift)

    def test_each_unsupported_signal(self):
        signals = [('primaryAxisSizingMode', 'AUTO'), ('counterAxisSizingMode', 'HUG'),
                   ('primaryAxisAlignItems', 'SPACE_BETWEEN'), ('counterAxisAlignItems', 'BASELINE'),
                   ('layoutWrap', 'WRAP'), ('itemSpacing', -1), ('strokesIncludedInLayout', True),
                   ('itemReverseZIndex', True), ('layoutMode', 'GRID'), ('type', 'GROUP')]
        for key, value in signals:
            with self.subTest(key=key):
                raw = flow(); raw[key] = value; n = f.normalize(raw)['root']
                self.assertFalse(a.analyze(n)[0]); self.assertTrue(a.analyze(n)[1])
        for key, value in [('layoutSizingHorizontal', 'FILL'), ('layoutSizingVertical', 'HUG'),
                           ('layoutGrow', 1), ('layoutAlign', 'STRETCH'), ('layoutPositioning', 'ABSOLUTE'),
                           ('minWidth', 0), ('maxWidth', 100), ('minHeight', 1), ('maxHeight', 100), ('visible', False)]:
            with self.subTest(key=key):
                raw = flow(); raw['children'][0].update(layoutSizingHorizontal='FIXED'); raw['children'][0][key] = value
                self.assertFalse(a.analyze(f.normalize(raw)['root'])[0])

    def test_missing_sizing_is_unknown(self):
        raw = flow(); del raw['primaryAxisSizingMode']
        n = f.normalize(raw)['root']; self.assertEqual(n['layout']['primary_sizing'], 'UNKNOWN')
        self.assertFalse(a.analyze(n)[0])

    def test_legacy_none_missing_and_version(self):
        ir = f.normalize(flow())
        for layout, supported in [({'mode': 'HORIZONTAL', 'padding': 10, 'item_spacing': 2}, False), ({'mode': 'NONE'}, False), ({}, False)]:
            ir['root']['layout'] = layout
            self.assertEqual(f.validate(ir)[0], []); self.assertEqual(a.analyze(ir['root'])[0], supported)
        del ir['root']['layout']; self.assertFalse(f.validate(ir)[0])
        ir['root']['layout'] = {'version': 2}; self.assertTrue(f.validate(ir)[0])

    def test_diagnostics_shared_deduplicated_and_validation_immutable(self):
        raw = flow(); raw['layoutWrap'] = 'WRAP'; ir = f.normalize(raw); before = copy.deepcopy(ir)
        errors, warnings = f.validate(ir); self.assertFalse(errors); self.assertEqual(ir, before)
        manifest = json.loads(f.plan_output(ir)['manifest.json'])
        self.assertEqual(manifest['diagnostics'], warnings)
        ir.pop('diagnostics'); self.assertEqual(f.validate(ir)[1], warnings)
        self.assertEqual(len(warnings), len({json.dumps(d, sort_keys=True) for d in warnings}))

    def test_malformed_capture_numbers(self):
        for field in ('paddingTop', 'itemSpacing', 'layoutGrow', 'minWidth'):
            for value in (True, None, '2', float('nan'), float('inf'), 10**400):
                with self.subTest(field=field, value=str(value)[:20]):
                    raw = flow(); raw[field] = value
                    with self.assertRaises(ValueError): f.normalize(raw)
        raw = flow(); raw['bounds']['x'] = True
        with self.assertRaises(ValueError): f.normalize(raw)

    def test_malformed_ir_precedes_template_asset_access(self):
        ir = f.normalize(flow())
        for field, value in [('version', True), ('padding', {'top': 1}), ('mode', []), ('item_spacing', float('nan')), ('wrap', 'BAD'), ('other', 3)]:
            bad = copy.deepcopy(ir); bad['root']['layout'][field] = value
            with patch.object(Path, 'read_text', side_effect=AssertionError('template access')):
                with self.assertRaises(ValueError): f.plan_output(bad, assets_dir='/missing')
        bad = copy.deepcopy(ir); bad['root']['children'][0]['layout_item'] = {'version': 1, 'grow': []}
        self.assertTrue(f.validate(bad)[0])

    def test_flow_arithmetic_overflow_no_writes(self):
        ir = f.normalize(flow())
        for c in ir['root']['children']: c['bounds']['width'] = 1e308
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'absent'
            with self.assertRaises(ValueError): f.generate(ir, out)
            self.assertFalse(out.exists())

    def test_golden_repeat_and_overwrite_protection(self):
        ir = f.normalize(fixture()); files = f.plan_output(ir)
        self.assertEqual(files, f.plan_output(ir))
        golden = ROOT / 'tests/golden/auto-layout'
        self.assertEqual(files, {str(p.relative_to(golden)): p.read_text() for p in golden.rglob('*') if p.is_file()})
        with tempfile.TemporaryDirectory() as tmp:
            f.generate(ir, tmp); p = Path(tmp) / 'AutoLayoutExampleRootView.swift'; p.write_text('// edited')
            with self.assertRaises(FileExistsError): f.generate(ir, tmp)
            self.assertEqual(p.read_text(), '// edited')

    def test_style_text_asset_and_interaction_preserved(self):
        raw = flow(); child = raw['children'][0]
        child.update(type='TEXT', characters='Keep me', fills=['#123456'], reactions=[{'trigger': 'tap', 'action': {'type': 'BACK'}}])
        swift = f.plan_output(f.normalize(raw))['AutoRowRootView.swift']
        self.assertIn('Keep me', swift); self.assertIn('textColor', swift); self.assertIn('onInteraction?', swift)
        child.update(type='IMAGE', imageRef='local.png')
        self.assertEqual(f.normalize(raw)['assets'], ['local.png'])


if __name__ == '__main__': unittest.main()
