import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import figma_to_uikit as f


def capture(horizontal='MIN', vertical='MIN'):
    return {'id': 'r', 'type': 'FRAME', 'name': 'Responsive',
            'bounds': {'x': 100, 'y': 200, 'width': 400, 'height': 600},
            'children': [{'id': 'p', 'type': 'FRAME',
                          'bounds': {'x': 140, 'y': 260, 'width': 200, 'height': 300},
                          'children': [{'id': 'c', 'type': 'RECTANGLE',
                                        'bounds': {'x': 170, 'y': 310, 'width': 80, 'height': 60},
                                        'constraints': {'horizontal': horizontal, 'vertical': vertical}}]}]}


def rendered(data):
    return f.plan_output(f.normalize(data))


class ConstraintTests(unittest.TestCase):
    def test_preserves_constraints_and_ir_roundtrip(self):
        for mode in sorted(f.CONSTRAINT_MODES):
            ir = f.normalize(capture(mode, mode))
            self.assertEqual(ir['root']['children'][0]['children'][0]['constraints'],
                             {'horizontal': mode, 'vertical': mode})
            self.assertEqual(f.normalize(ir), ir)
            self.assertFalse(f.validate(ir)[0])

    def test_nested_parent_geometry(self):
        expected = {
            'MIN': ['node1.leadingAnchor.constraint(equalTo: node0.leadingAnchor, constant: 30)',
                    'node1.topAnchor.constraint(equalTo: node0.topAnchor, constant: 50)'],
            'MAX': ['node1.trailingAnchor.constraint(equalTo: node0.trailingAnchor, constant: -90)',
                    'node1.bottomAnchor.constraint(equalTo: node0.bottomAnchor, constant: -190)'],
            'CENTER': ['node1.centerXAnchor.constraint(equalTo: node0.centerXAnchor, constant: -30)',
                       'node1.centerYAnchor.constraint(equalTo: node0.centerYAnchor, constant: -70)'],
        }
        for mode, lines in expected.items():
            swift = rendered(capture(mode, mode))['ResponsiveRootView.swift']
            for line in lines: self.assertIn(line, swift)
            self.assertIn('node1.widthAnchor.constraint(equalToConstant: 80)', swift)
            self.assertIn('node1.heightAnchor.constraint(equalToConstant: 60)', swift)
        swift = rendered(capture('STRETCH', 'STRETCH'))['ResponsiveRootView.swift']
        for line in expected['MIN'] + expected['MAX']: self.assertIn(line, swift)
        self.assertNotIn('node1.widthAnchor.constraint', swift)
        self.assertNotIn('node1.heightAnchor.constraint', swift)

    def test_scale_guide_legal_equations(self):
        data = capture('SCALE', 'SCALE')
        child = data['children'][0]['children'][0]
        child['bounds'].update(x=90, y=185, width=100, height=75)
        swift = rendered(data)['ResponsiveRootView.swift']
        self.assertIn('node0.addLayoutGuide(node1HorizontalScaleGuide)', swift)
        self.assertIn('node1HorizontalScaleGuide.trailingAnchor.constraint(equalTo: node0.leadingAnchor)', swift)
        self.assertIn('node1HorizontalScaleGuide.widthAnchor.constraint(equalTo: node0.widthAnchor, multiplier: 0.25)', swift)
        self.assertIn('node1.leadingAnchor.constraint(equalTo: node1HorizontalScaleGuide.leadingAnchor, constant: 0)', swift)
        self.assertIn('node1VerticalScaleGuide.bottomAnchor.constraint(equalTo: node0.topAnchor)', swift)
        self.assertIn('node1.heightAnchor.constraint(equalTo: node0.heightAnchor, multiplier: 0.25)', swift)
        self.assertNotIn('multiplier: -', swift)
        child['bounds'].update(x=190, y=335)
        swift = rendered(data)['ResponsiveRootView.swift']
        self.assertIn('node1HorizontalScaleGuide.leadingAnchor.constraint(equalTo: node0.leadingAnchor)', swift)
        self.assertIn('node1.leadingAnchor.constraint(equalTo: node1HorizontalScaleGuide.trailingAnchor, constant: 0)', swift)

    def test_zero_offset_and_size_scale(self):
        data = capture('SCALE', 'SCALE')
        data['children'][0]['children'][0]['bounds'].update(x=140, y=260, width=0, height=0)
        swift = rendered(data)['ResponsiveRootView.swift']
        self.assertNotIn('ScaleGuide', swift)
        self.assertIn('node1.widthAnchor.constraint(equalToConstant: 0)', swift)
        self.assertNotIn('multiplier: 0)', swift)

    def test_undefined_scale_axis_falls_back_and_is_deterministic(self):
        data = capture('SCALE', 'SCALE')
        data['children'][0]['bounds']['width'] = 0
        files = rendered(data)
        self.assertEqual(files, rendered(data))
        swift = files['ResponsiveRootView.swift']
        self.assertIn('node1.leadingAnchor.constraint(equalTo: node0.leadingAnchor, constant: 30)', swift)
        self.assertIn('node1.widthAnchor.constraint(equalToConstant: 80)', swift)
        self.assertIn('VerticalScaleGuide', swift)
        diagnostics = json.loads(files['manifest.json'])['diagnostics']
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]['code'], 'undefined-scale-constraint')
        self.assertIn('nonzero parent width', diagnostics[0]['message'])

    def test_invalid_raw_and_ir_constraints(self):
        invalid = [None, [], 'MIN', 7, {'horizontal': None}, {'vertical': ['MAX']},
                   {'horizontal': 'LEFT'}, {'horizontal': 'min'}, {'typo': 'MIN'}]
        for rules in invalid:
            with self.subTest(rules=rules):
                data = capture()
                data['children'][0]['children'][0]['constraints'] = rules
                with self.assertRaisesRegex(ValueError, 'constraints'): f.normalize(data)
                ir = f.normalize(capture())
                ir['root']['children'][0]['children'][0]['constraints'] = rules
                self.assertTrue(any('constraints' in e for e in f.validate(ir)[0]))
                with self.assertRaises(ValueError): f.plan_output(ir)

    def test_partial_axes_default_min_and_no_mutation(self):
        data = capture()
        data['children'][0]['children'][0]['constraints'] = {'horizontal': 'MAX'}
        ir = f.normalize(data)
        before = copy.deepcopy(ir)
        swift = f.plan_output(ir)['ResponsiveRootView.swift']
        self.assertEqual(before, ir)
        self.assertIn('node1.trailingAnchor.constraint(equalTo: node0.trailingAnchor, constant: -90)', swift)
        self.assertIn('node1.topAnchor.constraint(equalTo: node0.topAnchor, constant: 50)', swift)
        data['children'][0]['children'][0]['constraints'] = {}
        self.assertFalse(f.validate(f.normalize(data))[0])

    def test_nonfinite_derived_geometry_rejected(self):
        for mode in ('SCALE', 'MAX', 'CENTER', 'STRETCH'):
            data = capture(mode)
            parent = data['children'][0]
            child = parent['children'][0]
            parent['bounds'].update(x=0, width=1e-308 if mode == 'SCALE' else 0)
            child['bounds'].update(x=1.7e308, width=1.7e308)
            ir = f.normalize(data)
            self.assertTrue(any('derived geometry' in e for e in f.validate(ir)[0]))
            with self.assertRaises(ValueError): f.plan_output(ir)

    def test_screen_root_constraints_have_no_parent(self):
        data = capture()
        data['constraints'] = {'horizontal': 'SCALE', 'vertical': 'SCALE'}
        data['bounds'].update(width=0, height=0)
        files = rendered(data)
        self.assertNotIn('undefined-scale-constraint', files['manifest.json'])
        del data['constraints']
        self.assertEqual(files, rendered(data))

    def test_unwrapped_screen_does_not_derive_wrapper_ratios(self):
        screen = capture()
        screen['constraints'] = {'horizontal': 'SCALE'}
        data = {'id': 'doc', 'type': 'DOCUMENT',
                'bounds': {'x': 0, 'y': 0, 'width': 1e-308, 'height': 0},
                'children': [screen]}
        ir = f.normalize(data)
        self.assertFalse(f.validate(ir)[0])
        self.assertEqual(rendered(data), rendered(screen))

    def test_auto_layout_missing_sizing_falls_back(self):
        data = capture('STRETCH', 'CENTER')
        data['layoutMode'] = 'HORIZONTAL'
        self.assertIn('auto-layout-fallback', rendered(data)['manifest.json'])


if __name__ == '__main__':
    unittest.main()
