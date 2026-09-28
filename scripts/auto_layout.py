"""Versioned fixed-size Auto Layout evidence, validation and anchor equations."""
import math

CONTAINER = {
    'layoutMode': ('mode', 'NONE'), 'primaryAxisSizingMode': ('primary_sizing', 'UNKNOWN'),
    'counterAxisSizingMode': ('counter_sizing', 'UNKNOWN'),
    'primaryAxisAlignItems': ('primary_align', 'MIN'), 'counterAxisAlignItems': ('counter_align', 'MIN'),
    'layoutWrap': ('wrap', 'NO_WRAP'), 'itemSpacing': ('item_spacing', 0),
    'strokesIncludedInLayout': ('stroke_inclusive', False), 'itemReverseZIndex': ('reverse_stacking', False),
}
ITEM = {'layoutSizingHorizontal': 'horizontal_sizing', 'layoutSizingVertical': 'vertical_sizing',
        'layoutGrow': 'grow', 'layoutAlign': 'align', 'layoutPositioning': 'positioning',
        'minWidth': 'min_width', 'maxWidth': 'max_width', 'minHeight': 'min_height', 'maxHeight': 'max_height'}
SIDES = ('top', 'right', 'bottom', 'left')
ENUMS = {'primary_sizing': {'FIXED', 'AUTO', 'HUG', 'FILL', 'UNKNOWN'},
         'counter_sizing': {'FIXED', 'AUTO', 'HUG', 'FILL', 'UNKNOWN'},
         'primary_align': {'MIN', 'CENTER', 'MAX', 'SPACE_BETWEEN'},
         'counter_align': {'MIN', 'CENTER', 'MAX', 'BASELINE'},
         'wrap': {'NO_WRAP', 'WRAP'}, 'horizontal_sizing': {'FIXED', 'HUG', 'FILL', 'UNKNOWN'},
         'vertical_sizing': {'FIXED', 'HUG', 'FILL', 'UNKNOWN'},
         'align': {'INHERIT', 'STRETCH', 'MIN', 'CENTER', 'MAX'}, 'positioning': {'AUTO', 'ABSOLUTE'}}


def finite(value):
    try: return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))
    except OverflowError: return False


def capture(n, node):
    if any(k in n for k in CONTAINER) or any('padding' + s.title() in n for s in SIDES):
        node['layout'] = dict(version=1, **{key: n.get(raw, default) for raw, (key, default) in CONTAINER.items()})
        node['layout']['padding'] = {s: n.get('padding' + s.title(), 0) for s in SIDES}
    if any(k in n for k in ITEM):
        node['layout_item'] = dict(version=1, **{key: n[raw] for raw, key in ITEM.items() if raw in n})
    errors = validate_node(node)
    if errors: raise ValueError('; '.join(errors))


def validate_node(n, node_path=None):
    errors = []
    for field in ('layout', 'layout_item'):
        if field not in n: continue
        value = n[field]; path = (node_path or str(n.get('id'))) + '.' + field
        def error(key, message): errors.append(path + '.' + key + ': ' + message)
        if not isinstance(value, dict):
            error('', 'must be an object'); continue
        legacy = field == 'layout' and 'version' not in value
        if not legacy and (type(value.get('version')) is not int or value['version'] != 1): error('version', 'must be integer 1')
        allowed = {'mode', 'padding', 'item_spacing'} if legacy else ({key for key, _ in CONTAINER.values()} | {'version', 'padding'} if field == 'layout' else set(ITEM.values()) | {'version'})
        for key, val in value.items():
            if key not in allowed: error(key, 'unknown field'); continue
            if key == 'version': continue
            if key == 'mode':
                if not isinstance(val, str): error(key, 'must be a string')
            elif key == 'padding' and not legacy:
                if not isinstance(val, dict) or set(val) != set(SIDES): error(key, 'must contain exactly top/right/bottom/left')
                else:
                    for side, amount in val.items():
                        if not finite(amount) or amount < 0: error(key + '.' + side, 'must be a finite nonnegative number')
            elif key in ENUMS:
                if not isinstance(val, str) or val not in ENUMS[key]: error(key, 'invalid enum value')
            elif key in ('stroke_inclusive', 'reverse_stacking'):
                if not isinstance(val, bool): error(key, 'must be boolean')
            elif not finite(val) or (key != 'item_spacing' and val < 0): error(key, 'must be a finite ' + ('' if key == 'item_spacing' else 'nonnegative ') + 'number')
    return errors


def analyze(n):
    """One decision for all direct children; descendants decide independently."""
    children = n.get('children', [])
    if not isinstance(children, list) or any(not isinstance(c, dict) or validate_node(c) for c in children):
        return False, []
    layout = n.get('layout', {})
    mode = layout.get('mode', 'NONE')
    if mode == 'NONE': return False, []
    reasons = []
    def reason(node, field, value):
        reasons.append({'level': 'warning', 'code': 'auto-layout-fallback', 'node_id': node['id'],
                        'message': f'Container {n["id"]}: {field}={value!r} is unsupported or incomplete; all direct children use captured geometry/constraints.'})
    if layout.get('version') != 1: reason(n, 'layout.version', 'legacy evidence; recapture required')
    elif mode not in ('HORIZONTAL', 'VERTICAL'): reason(n, 'layout.mode', mode)
    else:
        if n['type'] not in {'FRAME', 'COMPONENT', 'INSTANCE'}: reason(n, 'type', n['type'])
        for key, allowed, default in [('primary_sizing', {'FIXED'}, 'UNKNOWN'), ('counter_sizing', {'FIXED'}, 'UNKNOWN'),
                                      ('primary_align', {'MIN', 'CENTER', 'MAX'}, 'MIN'), ('counter_align', {'MIN', 'CENTER', 'MAX'}, 'MIN'),
                                      ('wrap', {'NO_WRAP'}, 'NO_WRAP'), ('stroke_inclusive', {False}, False), ('reverse_stacking', {False}, False)]:
            if layout.get(key, default) not in allowed: reason(n, 'layout.' + key, layout.get(key, default))
        if layout.get('item_spacing', 0) < 0: reason(n, 'layout.item_spacing', layout['item_spacing'])
        for item in [n] + n.get('children', []):
            for key, value in item.get('layout_item', {}).items():
                if key == 'version' or (item is n and key in {'grow', 'align', 'positioning'}): continue
                allowed = {'horizontal_sizing': {'FIXED'}, 'vertical_sizing': {'FIXED'}, 'grow': {0}, 'align': {'INHERIT'}, 'positioning': {'AUTO'}}.get(key, set())
                if value not in allowed: reason(item, 'layout_item.' + key, value)
            if item is not n and not item.get('visible', True): reason(item, 'visible', False)
    return not reasons, reasons


def equations(parent):
    """Return (child ID, anchor, target ID, target anchor, constant) tuples."""
    layout = parent['layout']; horizontal = layout['mode'] == 'HORIZONTAL'
    start, end, center, size = ('leading', 'trailing', 'centerX', 'width') if horizontal else ('top', 'bottom', 'centerY', 'height')
    cross_start, cross_end, cross_center, cross_size = ('top', 'bottom', 'centerY', 'height') if horizontal else ('leading', 'trailing', 'centerX', 'width')
    p = layout.get('padding', dict.fromkeys(SIDES, 0)); gap = layout.get('item_spacing', 0)
    before, after = (p['left'], p['right']) if horizontal else (p['top'], p['bottom'])
    cross_before, cross_after = (p['top'], p['bottom']) if horizontal else (p['left'], p['right'])
    children = parent.get('children', [])
    if not children: return []
    total = sum(c['bounds'][size] for c in children) + gap * (len(children) - 1)
    if not finite(total): raise ValueError(parent['id'] + ': nonfinite flow total')
    align = layout.get('primary_align', 'MIN'); cross = layout.get('counter_align', 'MIN')
    target, offset = (start, before) if align == 'MIN' else ((end, -after - total) if align == 'MAX' else (center, (before - after) / 2 - total / 2))
    result = []
    for i, child in enumerate(children):
        cid = child['id']; pid = parent['id']
        result.append((cid, start, children[i-1]['id'] if i else pid, end if i else target, gap if i else offset))
        cross_anchor, cross_offset = (cross_start, cross_before) if cross == 'MIN' else ((cross_end, -cross_after) if cross == 'MAX' else (cross_center, (cross_before - cross_after) / 2))
        result.append((cid, cross_anchor, pid, cross_anchor, cross_offset))
        result.extend((cid, dimension, None, None, child['bounds'][dimension]) for dimension in ('width', 'height'))
    if any(not finite(row[-1]) for row in result): raise ValueError(parent['id'] + ': nonfinite flow offset')
    return result


def diagnostics(root):
    result = []
    def visit(n):
        result.extend(analyze(n)[1])
        for c in n.get('children', []): visit(c)
    visit(root)
    return result


def merge_diagnostics(*groups):
    result = []; seen = set()
    for group in groups:
        for d in group:
            key = (d.get('node_id'), d.get('code'), d.get('message'))
            if key not in seen: result.append(d); seen.add(key)
    return result
