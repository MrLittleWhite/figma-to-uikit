"""Regression coverage for the JSON IR validation boundary (stdlib only)."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import figma_to_uikit as f

MISSING = object()


def base_ir():
    return f.normalize({'id': 'root', 'type': 'FRAME', 'name': 'Screen',
                        'children': [{'id': 'input', 'type': 'INPUT', 'name': 'Email'}]})


def malformed_cases():
    cases = []
    def add(path, values):
        for value in values: cases.append((path, value))
    add(('ir_version',), [MISSING, None, [], 'old'])
    add(('root',), [MISSING, None, [], 'root'])
    add(('root', 'id'), [MISSING, None, [], '', 1])
    add(('root', 'type'), [MISSING, None, [], 1])
    add(('root', 'name'), [None, [], 1, chr(0xd800)])
    add(('root', 'visible'), [None, [], 0, 'false'])
    add(('root', 'children'), [MISSING, None, {}, 'children', [None]])
    add(('root', 'bounds'), [MISSING, None, [], {}])
    bad_numbers = [MISSING, None, True, '1', [], float('nan'), float('inf'), -float('inf'), 10**400]
    for key in ('x', 'y', 'width', 'height'):
        add(('root', 'bounds', key), bad_numbers)
    for key in ('width', 'height'): add(('root', 'bounds', key), [-1])
    add(('root', 'layout'), [None, [], {'version': True}, {'version': 2}, {'version': 1, 'mode': []},
                            {'version': 1, 'padding': {'top': 0}}, {'version': 1, 'unknown': 0},
                            {'version': 1, 'item_spacing': True}, {'version': 1, 'item_spacing': float('inf')}])
    add(('root', 'layout_item'), [None, [], {}, {'version': True}, {'version': 1, 'grow': []},
                                 {'version': 1, 'horizontal_sizing': 'BAD'}, {'version': 1, 'max_width': float('nan')}])
    add(('root', 'style'), [None, [], 'style'])
    add(('root', 'style', 'fill'), [None, {}, {'r': []}, [], 1, '#12345', ' #FFFFFF', '#FFFFFF\n'])
    add(('root', 'style', 'corner_radius'), bad_numbers[1:] + [-1])
    add(('root', 'text'), [None, [], {}, {'value': 'hello'}, {'value': 1, 'font_size': 12}])
    for value in bad_numbers[1:] + [0, -1]:
        add(('root', 'text'), [{'value': 'hello', 'font_size': value}])
    for key in ('font_family', 'color'):
        add(('root', 'text'), [{'value': 'hello', 'font_size': 12, key: []}])
    add(('root', 'asset'), [None, [], {}, {'ref': []}, {'ref': '', 'format': []}, {'ref': 1, 'format': 'png'}])
    for prefix in [(), ('root',)]:
        add(prefix + ('interactions',), [None, {}, [None], [{}], [{'trigger': [], 'action': 1, 'destination': None}]])
        for key in ('trigger', 'action', 'destination', 'source'):
            action = dict(trigger='TAP', action='NODE', destination='', source='root')
            action[key] = []
            add(prefix + ('interactions',), [[action]])
    add(('interactions',), [[{'trigger': 'TAP', 'action': 'NODE', 'destination': ''}],
                            [{'trigger': 'TAP', 'action': 'NODE', 'destination': '', 'source': ''}]])
    add(('assets',), [None, {}, [None], [[]], [1]])
    add(('diagnostics',), [None, {}, [None], [{}], [{'level': [], 'code': 'x', 'message': 'x'}]])
    for key in ('level', 'code', 'message', 'node_id', 'asset_ref'):
        diagnostic = dict(level='warning', code='x', message='x')
        diagnostic[key] = []
        add(('diagnostics',), [[diagnostic]])
    add(('tokens',), [None, [], {}])
    add(('tokens', 'version'), [MISSING, None, True, 2, []])
    for key in ('colors', 'fonts', 'spacing', 'radii'):
        add(('tokens', key), [MISSING, None, []])
    add(('tokens', 'colors'), [{'bad': v} for v in [None, {}, '#12345', ' #FFFFFF', '#FFFFFF\n', 1]])
    add(('tokens', 'fonts'), [{'bad': []}, {'bad': None}])
    for key in ('spacing', 'radii'):
        add(('tokens', key), [{'bad': v} for v in bad_numbers[1:]])
    add(('tokens', 'radii'), [{'bad': -1}])
    return cases


def mutate(path, value):
    ir = base_ir()
    target = ir
    for key in path[:-1]: target = target[key]
    if value is MISSING: target.pop(path[-1], None)
    else: target[path[-1]] = value
    return ir


class ValidationTests(unittest.TestCase):
    def test_malformed_field_matrix(self):
        for path, value in malformed_cases():
            with self.subTest(path=path, value=value):
                ir = mutate(path, value)
                errors, _ = f.validate(ir)
                self.assertTrue(errors)
                self.assertTrue(all(e.startswith('$.') for e in errors))
                self.assertEqual(errors, f.validate(ir)[0])
                with tempfile.TemporaryDirectory() as temp:
                    out = Path(temp) / 'output'
                    # No template or asset reads should occur on malformed IR.
                    with patch.object(Path, 'read_text', side_effect=AssertionError('template read')), patch('emit_assets.plan_assets', side_effect=AssertionError('asset read')):
                        with self.assertRaises(ValueError): f.generate(ir, out, assets_dir=temp)
                    self.assertFalse(out.exists())

    def test_nonobject_ir(self):
        for value in (None, [], 1, 'ir'):
            self.assertEqual(f.validate(value)[0], ['$: must be an object'])

    def test_duplicate_and_text_required(self):
        ir = base_ir()
        ir['root']['children'][0].update(id='root', type='TEXT')
        errors, _ = f.validate(ir)
        self.assertTrue(any('$.root.children[0].id: duplicate' in e for e in errors))
        self.assertTrue(any('$.root.children[0].text:' in e for e in errors))

    def test_relative_coordinate_overflow(self):
        for magnitude in (1e308, 10**308):
            ir = base_ir()
            ir['root']['bounds']['x'] = -magnitude
            ir['root']['children'][0]['bounds']['x'] = magnitude
            self.assertIn('parent-relative', '; '.join(f.validate(ir)[0]))
            with tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / 'out'
                with self.assertRaises(ValueError): f.generate(ir, out)
                self.assertFalse(out.exists())

    def test_optional_fields_and_valid_values(self):
        ir = base_ir()
        for key in ('tokens', 'diagnostics', 'assets', 'interactions'): ir.pop(key)
        for node in f.walk(ir['root']):
            for key in ('name', 'visible', 'style'): node.pop(key)
        self.assertEqual(f.validate(ir)[0], [])
        files = f.plan_output(ir)
        self.assertIn('placeholder = "Input"', files['FigmaScreenRootView.swift'])
        ir['tokens'] = dict(version=1, colors={'a': '#aAbBcC', 'b': '#aAbBcCdd'}, fonts={'body': 'System'}, spacing={'overlap': -2.5}, radii={'zero': 0})
        ir['root']['children'][0]['visible'] = False
        self.assertEqual(f.validate(ir)[0], [])
        self.assertIn('isHidden = true', f.plan_output(ir)['FigmaScreenRootView.swift'])

    def test_error_diagnostic_blocks_generation(self):
        ir = base_ir()
        ir['diagnostics'] = [{'level': 'error', 'code': 'blocked', 'message': 'Capture incomplete'}]
        errors, warnings = f.validate(ir)
        self.assertEqual(errors, ['$.diagnostics[0].message: Capture incomplete'])
        self.assertEqual(warnings, ir['diagnostics'])
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'
            with self.assertRaisesRegex(ValueError, 'Capture incomplete'): f.generate(ir, out)
            self.assertFalse(out.exists())

    def test_validation_does_not_mutate(self):
        ir = base_ir(); original = copy.deepcopy(ir)
        before = f.plan_output(ir)
        self.assertEqual(f.validate(ir)[0], [])
        self.assertEqual(ir, original)
        self.assertEqual(before, f.plan_output(ir))

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/figma_to_uikit.py'), *args], capture_output=True, text=True)

    def test_cli_validation_and_generate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'ir.json'; out = root / 'out'
            source.write_text(json.dumps(mutate(('tokens', 'colors'), {'bad': {}})))
            result = self.cli('validate', '--input', str(source))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('$.tokens.colors["bad"]', json.loads(result.stdout)['errors'][0])
            result = self.cli('generate', '--input', str(source), '--output-dir', str(out))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('error: $.tokens.colors', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(out.exists())

    def test_cli_expected_input_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'bad.json'
            for contents in (None, '{'):
                if contents is not None: source.write_text(contents)
                for command in ('validate', 'generate'):
                    args = [command, '--input', str(source)]
                    if command == 'generate': args += ['--output-dir', str(Path(temp) / 'out')]
                    result = self.cli(*args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(result.stderr.startswith('error: '))
                    self.assertNotIn('Traceback', result.stderr)

    def test_programming_errors_propagate(self):
        with patch.object(f, 'render_screen', side_effect=TypeError('implementation bug')):
            with self.assertRaisesRegex(TypeError, 'implementation bug'): f.plan_output(base_ir())


if __name__ == '__main__': unittest.main()
