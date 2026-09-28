#!/usr/bin/env python3
"""Portable offline Figma to UIKit pipeline (Python standard library only)."""
from __future__ import annotations
import argparse, hashlib, json, math, re, sys
import auto_layout
from string import Template
from pathlib import Path
from typing import Any
IR_VERSION = "figma-uikit-ir/1"
GENERATOR_VERSION = "figma-to-uikit/1"
CONSTRAINT_MODES = {'MIN', 'MAX', 'CENTER', 'STRETCH', 'SCALE'}
KNOWN_TYPES = {"DOCUMENT","CANVAS","FRAME","GROUP","SECTION","COMPONENT","INSTANCE","TEXT","RECTANGLE","ELLIPSE","VECTOR","BOOLEAN_OPERATION","STAR","LINE","POLYGON","SLICE","COMPONENT_SET","CODE_BLOCK","STAMP","HIGHLIGHT","WASHI_TAPE","TABLE","TABLE_CELL","SWITCH","BUTTON","INPUT","IMAGE","SVG","SCROLL_CONTAINER"}

def swift_name(s: str, fallback="Node") -> str:
    words = re.findall(r"[A-Za-z0-9]+", s or "")
    n = "".join(w[:1].upper()+w[1:] for w in words) or fallback
    if n[0].isdigit(): n = "N"+n
    return n + "View" if n in {"View","UIView","UILabel","Button"} else n

def color(v):
    if isinstance(v, dict):
        if "color" in v: return color(v["color"])
        if all(k in v for k in ("r","g","b")):
            return "#%02X%02X%02X%02X"%tuple(max(0,min(255,round(float(v.get(k,1))*255))) for k in ("r","g","b","a"))
    if isinstance(v,str):
        x=v.strip().upper(); return x if re.fullmatch(r"#(?:[0-9A-F]{6}|[0-9A-F]{8})",x) else None
    return None

def bounds(n):
    b=n.get("absoluteBoundingBox") or n.get("bounds") or {}
    for key in ("x", "y", "width", "height"):
        if not auto_layout.finite(b.get(key, 0)): raise ValueError("bounds." + key + ": must be a finite number")
    return {k: float(b.get(k,0)) for k in ("x","y","width","height")}

def paint(n):
    fills=n.get("fills") or []
    for f in fills:
        if isinstance(f,dict) and (not f.get('visible',True) or f.get('type','SOLID')!='SOLID'): continue
        c=color(f)
        if c: return c
    return None

def normalize_node(n, diagnostics, order=0):
    typ=str(n.get("type","UNKNOWN")).upper(); nid=str(n.get("id") or f"generated-{order}")
    name=str(n.get("name") or typ.title())
    if typ not in KNOWN_TYPES: diagnostics.append({"level":"warning","code":"unknown-node-type","node_id":nid,"message":f"Preserved raw node type {typ}; no UIKit mapping."})
    for field in ('effects','boundVariables','strokes','characterStyleOverrides'):
        if n.get(field) and n.get(field)!='NONE': diagnostics.append({'level':'warning','code':'unsupported-'+field,'node_id':nid,'message':field+' is not resolved by the fixed-geometry generator; host adaptation required.'})
    style=n.get("style") or {}; bb=bounds(n)
    fills=n.get("fills") or []
    image_fill=next((f for f in fills if isinstance(f,dict) and f.get('type')=='IMAGE' and f.get('visible',True)),{})
    if image_fill: n=dict(n,imageRef=n.get('imageRef') or image_fill.get('imageRef') or image_fill.get('imageHash'))
    node={"id":nid,"type":typ,"name":name,"swift_name":swift_name(name),"order":0,"bounds":bb,"visible":n.get("visible",True),"layout":{"mode":str(n.get("layoutMode") or "NONE"),"padding":n.get("paddingTop",0) or 0,"item_spacing":n.get("itemSpacing",0) or 0},"style":{},"children":[],"raw_type":typ}
    auto_layout.capture(n, node)
    # Keep absent constraints absent for backwards-compatible IR/output bytes.
    if 'constraints' in n:
        rules = n['constraints']
        if (not isinstance(rules, dict) or any(key not in ('horizontal', 'vertical') for key in rules)
                or any(not isinstance(value, str) or value not in CONSTRAINT_MODES for value in rules.values())):
            raise ValueError(f'Node {nid}: constraints must be an object with horizontal/vertical MIN, MAX, CENTER, STRETCH, or SCALE values')
        node['constraints'] = dict(rules)
    if paint(n): node["style"]["fill"] = paint(n)
    if n.get("cornerRadius") is not None: node["style"]["corner_radius"] = float(n["cornerRadius"])
    if typ=="TEXT" or "characters" in n: node["text"]={"value":str(n.get("characters",n.get("text", ""))),"font_family":style.get("fontFamily","System"),"font_size":float(style.get("fontSize",16) or 16),"font_weight":style.get("fontWeight","regular"),"color":paint(n)}
    if typ in {"IMAGE","SVG","VECTOR"} or n.get("imageRef") or n.get("imageHash"):
        node["asset"]={"ref":str(n.get("imageRef") or n.get("imageHash") or ""),"format":str(n.get("format") or ("svg" if typ in {"SVG","VECTOR"} else "png")).lower()}
        if node["asset"]["format"]=="svg": diagnostics.append({"level":"warning","code":"svg-needs-rasterization","node_id":nid,"message":"SVG is not used directly as UIImage; provide PNG/PDF export."})
    reactions=n.get("reactions") or n.get("prototypeReactions") or []
    if reactions:
        node["interactions"] = []
        for r in reactions:
            if not isinstance(r,dict):
                diagnostics.append({"level":"warning","code":"unsupported-reaction","node_id":nid,"message":"Reaction must be an object."})
                continue
            trigger = r.get("trigger") or "tap"
            trigger = trigger.get("type","tap") if isinstance(trigger,dict) else str(trigger)
            actions = r.get("actions")
            if actions is None: actions = [r.get("action") or {}]
            if not isinstance(actions,list): actions = [actions]
            for action in actions:
                if not isinstance(action,dict): action = {"type":str(action)}
                node["interactions"].append({"trigger":trigger,"action":str(action.get("type","unknown")),"destination":str(action.get("destinationId") or r.get("destinationId") or "")})
    node["children"]=[normalize_node(c,diagnostics,f"{order}-{i}") for i,c in enumerate(n.get("children") or [])]
    return node

def normalize(data):
    diagnostics=[]
    if not isinstance(data,dict): raise ValueError('capture must be a JSON object')
    if 'ir_version' in data:
        errors,_=validate(data)
        if errors: raise ValueError('; '.join(errors))
        return data
    if isinstance(data,dict) and data.get("url") and not data.get("document") and not data.get("nodes"):
        diagnostics.append({"level":"error","code":"url-not-fetched","message":"URL is a locator only; provide captured REST/MCP JSON locally. No network acquisition performed."}); root={"id":"url-root","type":"DOCUMENT","name":"URL Input","children":[]}
    else:
        rootdata=data.get("document",data.get("root",data)) if isinstance(data,dict) else data
        if isinstance(rootdata,dict) and "nodes" in rootdata and "type" not in rootdata: rootdata={"id":"document","type":"DOCUMENT","name":"Document","children":[v.get("document",v) for v in rootdata["nodes"].values() if v is not None] if isinstance(rootdata["nodes"],dict) else rootdata["nodes"]}
        root=normalize_node(rootdata,diagnostics)
    diagnostics = auto_layout.merge_diagnostics(diagnostics, auto_layout.diagnostics(root))
    result = {"ir_version":IR_VERSION,"source":{"kind":"local-json"},"root":root,"diagnostics":diagnostics,"tokens":extract_tokens(root),"interactions":extract_interactions(root),"assets":extract_assets(root)}
    return result

def walk(n):
    yield n
    for c in n.get("children",[]): yield from walk(c)
def extract_tokens(root):
    colors=sorted({n.get("style",{}).get("fill") for n in walk(root) if n.get("style",{}).get("fill")})
    fonts=sorted({(n.get("text") or {}).get("font_family") for n in walk(root) if n.get("text")})
    return {"version":1,"colors":{"color"+str(i+1):c for i,c in enumerate(colors)},"fonts":{"font"+str(i+1):f for i,f in enumerate(fonts)},"spacing":{},"radii":{}}
def extract_interactions(root): return [dict(x,source=n["id"]) for n in walk(root) for x in n.get("interactions",[])]
def extract_assets(root): return sorted({n["asset"]["ref"] for n in walk(root) if n.get("asset",{}).get("ref")})

def swift_string(s):
    result = '"'
    for c in str(s):
        if c == '\\': result += '\\\\'
        elif c == '"': result += '\\"'
        elif ord(c) < 32 or ord(c) == 127: result += '\\u{' + format(ord(c), 'x') + '}'
        else: result += c
    return result + '"'

def swift_color(value):
    value = value.lstrip('#')
    if len(value) == 6: value += 'FF'
    channels = [int(value[i:i+2],16)/255 for i in range(0,8,2)]
    return 'UIColor(red: %.8f, green: %.8f, blue: %.8f, alpha: %.8f)' % tuple(channels)

def ui_class(n):
    t=n["type"]
    if t=="TEXT": return "UILabel()"
    if t == "BUTTON": return "UIButton(type: .system)"
    if t == "INPUT": return "UITextField()"
    if t in {"IMAGE","SVG","VECTOR"} or n.get('asset'): return "UIImageView()"
    return "UIView()"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
WRAPPER_TYPES = {"DOCUMENT", "CANVAS", "SECTION"}


def select_screens(root):
    """Unwrap capture containers, stopping at each actual screen (not its children)."""
    if root['type'] not in WRAPPER_TYPES:
        return [root]
    return [screen for child in root.get('children', []) for screen in select_screens(child)]


def screen_names(screens):
    """Allocate stable Swift/file names, independent of capture traversal order."""
    used = {'designtokens', 'interactions', 'generatedinteraction'}
    result = {}
    for root in sorted(screens, key=lambda n: n['id']):
        base = swift_name(root.get('name', 'FigmaScreen'))
        if base.casefold() in used: base += 'Screen'
        if base.endswith('ViewController'): base = base[:-len('ViewController')]
        candidate = base
        suffix = hashlib.sha256(root['id'].encode('utf-8')).hexdigest()
        counter = 0
        while any((candidate + ending).casefold() in used for ending in ('ViewController', 'RootView')):
            counter += 1
            candidate = base + '_' + suffix + ('_' + str(counter) if counter > 1 else '')
        page, view = candidate + 'ViewController', candidate + 'RootView'
        used.update([page.casefold(), view.casefold()])
        result[root['id']] = (page, view)
    return result


def constraint_geometry(child, parent, axis, mode):
    """Resolve captured absolute geometry into a parent-local axis equation."""
    coordinate, dimension = ('x', 'width') if axis == 'horizontal' else ('y', 'height')
    offset = child[coordinate] - parent[coordinate]
    size, extent = child[dimension], parent[dimension]
    if mode in {'MAX', 'STRETCH'}: return offset + (size - extent), size
    if mode == 'CENTER': return offset + (size / 2 - extent / 2), size
    if mode == 'SCALE' and extent != 0: return offset / extent, size / extent
    return offset, size


def render_axis_constraints(n, parent, var, owner, axis, setup, diagnostics):
    mode = n['constraints'].get(axis, 'MIN')
    start, end, center, dimension = (('leading', 'trailing', 'centerX', 'width') if axis == 'horizontal'
                                    else ('top', 'bottom', 'centerY', 'height'))
    coordinate = 'x' if axis == 'horizontal' else 'y'
    offset = n['bounds'][coordinate] - parent['bounds'][coordinate]
    position, size = constraint_geometry(n['bounds'], parent['bounds'], axis, mode)
    def number(value): return format(value, '.17g')
    def anchor(name, target, constant=0):
        return f'        {var}.{name}Anchor.constraint(equalTo: {target}, constant: {number(constant)}).isActive = true'
    fixed = f'        {var}.{dimension}Anchor.constraint(equalToConstant: {number(size)}).isActive = true'
    if mode == 'SCALE' and parent['bounds'][dimension] == 0:
        diagnostics.append({'level': 'warning', 'code': 'undefined-scale-constraint', 'node_id': n['id'],
                            'message': f'{axis} SCALE has zero captured parent {dimension} ({parent["id"]}); using fixed MIN offset and size on this axis. Supply a nonzero parent {dimension} to enable proportional layout.'})
        mode = 'MIN'
    if mode == 'MIN': return [anchor(start, f'{owner}.{start}Anchor', position), fixed]
    if mode == 'MAX': return [anchor(end, f'{owner}.{end}Anchor', position), fixed]
    if mode == 'CENTER': return [anchor(center, f'{owner}.{center}Anchor', position), fixed]
    if mode == 'STRETCH':
        return [anchor(start, f'{owner}.{start}Anchor', offset), anchor(end, f'{owner}.{end}Anchor', position)]
    # UIKit location anchors cannot have multipliers. A nonnegative-length guide
    # represents the proportional offset; reverse its endpoints for negative offsets.
    result = []
    target = f'{owner}.{start}Anchor'
    if position != 0:
        guide = var + ('Horizontal' if axis == 'horizontal' else 'Vertical') + 'ScaleGuide'
        setup.extend([f'        let {guide} = UILayoutGuide()', f'        {owner}.addLayoutGuide({guide})'])
        near, far = (start, end) if position > 0 else (end, start)
        result.extend([f'        {guide}.{near}Anchor.constraint(equalTo: {target}).isActive = true',
                       f'        {guide}.{dimension}Anchor.constraint(equalTo: {owner}.{dimension}Anchor, multiplier: {number(abs(position))}).isActive = true'])
        # Fully determine the guide on the other axis as well.
        cross_start, cross_size = ('top', 'height') if axis == 'horizontal' else ('leading', 'width')
        result.extend([f'        {guide}.{cross_start}Anchor.constraint(equalTo: {owner}.{cross_start}Anchor).isActive = true',
                       f'        {guide}.{cross_size}Anchor.constraint(equalToConstant: 0).isActive = true'])
        target = f'{guide}.{far}Anchor'
    result.append(anchor(start, target))
    result.append(f'        {var}.{dimension}Anchor.constraint(equalTo: {owner}.{dimension}Anchor, multiplier: {number(size)}).isActive = true' if size != 0 else fixed)
    return result


def render_screen(root, page, view_name, asset_names, diagnostics, templates):
    nodes = list(walk(root))[1:]
    interactions = extract_interactions(root)
    decl=[]; setup=[]; constraints=[]; handlers=[]
    if interactions:
        decl.append('    var onInteraction: ((GeneratedInteraction) -> Void)?')
    names = {n['id']: 'node'+str(i) for i,n in enumerate(nodes)}
    parents = {c['id']: p for p in walk(root) for c in p.get('children',[])}
    flow = {}
    for parent in walk(root):
        if auto_layout.analyze(parent)[0]:
            for cid, anchor, target, target_anchor, constant in auto_layout.equations(parent):
                var = names[cid]
                expression = (f'equalTo: {names.get(target, "self")}.{target_anchor}Anchor, constant: {constant:.17g}'
                              if target is not None else f'equalToConstant: {constant:.17g}')
                flow.setdefault(cid, []).append(f'        {var}.{anchor}Anchor.constraint({expression}).isActive = true')
    for i,n in enumerate(nodes):
        var="node"+str(i); decl.append(f"    private let {var} = {ui_class(n)}")
        setup.append(f"        {var}.translatesAutoresizingMaskIntoConstraints = false")
        asset_name=asset_names.get(n.get('asset',{}).get('ref'))
        if asset_name and ui_class(n)=='UIImageView()':
            setup.append(f'        {var}.image = UIImage(named: {swift_string(asset_name)})')
            setup.append(f'        {var}.contentMode = .scaleAspectFit')
        if n['type'] == 'TEXT': setup.append(f"        {var}.text = {swift_string(n['text']['value'])}; {var}.numberOfLines = 0")
        if n["type"]=="INPUT": setup.append(f"        {var}.borderStyle = .roundedRect; {var}.placeholder = {swift_string(n.get('name', 'Input'))}")
        parent = parents[n['id']]
        owner = names.get(parent['id'], 'self')
        setup.append(f"        {owner}.addSubview({var})")
        taps=[]
        for action in n.get('interactions',[]):
            if action.get('trigger','').upper() in {'TAP','ON_CLICK','ON_TAP'}: taps.append(action)
            else: diagnostics.append({'level':'warning','code':'unsupported-trigger','node_id':n['id'],'message':'No UIKit binding for trigger: '+action.get('trigger','')})
        if taps:
            method=f'handleNode{i}Tap'
            if n['type'] in {'BUTTON','INPUT'}:
                setup.append(f'        {var}.addTarget(self, action: #selector({method}), for: .touchUpInside)')
            else:
                setup.append(f'        {var}.isUserInteractionEnabled = true')
                setup.append(f'        {var}.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector({method})))')
            calls=[]
            for action in taps:
                args=', '.join(label+': '+swift_string(value) for label,value in [('sourceID',n['id']),('trigger',action['trigger']),('action',action['action']),('destinationID',action.get('destination',''))])
                calls.append(f'        onInteraction?(GeneratedInteraction({args}))')
            handlers.append(f'    @objc private func {method}() {{\n'+ '\n'.join(calls)+'\n    }')
        setup.append(f"        {var}.isHidden = {str(not n.get('visible', True)).lower()}")
        fill = n.get('style',{}).get('fill')
        if fill:
            prop = 'textColor' if n['type'] == 'TEXT' else 'backgroundColor'
            setup.append(f"        {var}.{prop} = {swift_color(fill)}")
        if n['type'] == 'TEXT':
            text = n.get('text',{})
            size = text.get('font_size',16)
            setup.append(f"        {var}.font = UIFont(name: {swift_string(text.get('font_family','System'))}, size: {size}) ?? UIFont.systemFont(ofSize: {size})")
        if 'corner_radius' in n.get('style',{}):
            setup.append(f"        {var}.layer.cornerRadius = {n['style']['corner_radius']}")
        if n['id'] in flow:
            constraints.extend(flow[n['id']])
        elif 'constraints' in n:
            for axis in ('horizontal', 'vertical'):
                constraints.extend(render_axis_constraints(n, parent, var, owner, axis, setup, diagnostics))
        else:
            b=dict(n["bounds"]); b["x"]-=parent["bounds"]["x"]; b["y"]-=parent["bounds"]["y"]; constraints += [f"        {var}.leadingAnchor.constraint(equalTo: {owner}.leadingAnchor, constant: {b['x']:.1f}).isActive = true",f"        {var}.topAnchor.constraint(equalTo: {owner}.topAnchor, constant: {b['y']:.1f}).isActive = true",f"        {var}.widthAnchor.constraint(equalToConstant: {max(0,b['width']):.1f}).isActive = true",f"        {var}.heightAnchor.constraint(equalToConstant: {max(0,b['height']):.1f}).isActive = true"]
    root_fill = root.get('style', {}).get('fill')
    root_body = templates['RootView'].substitute(
        view_name=view_name,
        declarations="\n".join(decl) or '    // Empty Figma page',
        background=swift_color(root_fill) if root_fill else '.systemBackground',
        setup="\n".join(setup), constraints="\n".join(constraints),
        handlers="\n\n".join(handlers))
    callback = ''
    if interactions:
        callback = '    var onInteraction: ((GeneratedInteraction) -> Void)? {\n        didSet { contentView.onInteraction = onInteraction }\n    }\n'
    controller = templates['Controller'].substitute(controller_name=page, view_name=view_name, callback=callback)
    return {f'{view_name}.swift': root_body, f'{page}.swift': controller}


def plan_output(ir, assets_dir=None):
    """Render the complete capture in memory; no output filesystem mutations."""
    errors, warnings = validate(ir)
    if errors: raise ValueError('; '.join(errors))
    templates = {name: Template((TEMPLATE_DIR / (name + '.swift.template')).read_text(encoding='utf-8'))
                 for name in ('Controller', 'RootView')}
    root = ir['root']; files = {}; diagnostics = list(warnings)
    asset_names = {}
    if assets_dir is not None:
        from emit_assets import plan_assets
        asset_files, asset_names, asset_diagnostics = plan_assets(ir, assets_dir)
        files.update(asset_files)
        diagnostics.extend(asset_diagnostics)
        if any(d['code']=='unsafe-asset-ref' for d in asset_diagnostics): raise ValueError('Unsafe asset reference')
    elif extract_assets(root):
        diagnostics.append({'level':'warning','code':'assets-not-packaged','message':'Supply --assets-dir to package local image resources.'})
    ids = {n['id'] for n in walk(root)}
    for interaction in extract_interactions(root):
        destination = interaction.get('destination', '')
        if destination and destination not in ids:
            diagnostics.append({'level':'warning','code':'external-interaction-destination','node_id':interaction['source'],'message':'Destination is outside this capture: '+destination})
    screens = select_screens(root)
    names = screen_names(screens)
    manifest_screens = []
    for screen in screens:
        page, view_name = names[screen['id']]
        files.update(render_screen(screen, page, view_name, asset_names, diagnostics, templates))
        manifest_screens.append({'node_id': screen['id'], 'controller': page + '.swift', 'view': view_name + '.swift'})
    files["DesignTokens.swift"]="import UIKit\n\nenum DesignTokens {\n"+"".join(f"    static let color{i} = {swift_color(v)}\n" for i,v in enumerate(ir.get("tokens",{}).get("colors",{}).values()))+"}\n"
    files["Interactions.swift"]="import UIKit\n\n// Host callback payload; navigation/business logic remains the host app's responsibility.\nstruct GeneratedInteraction {\n    let sourceID: String\n    let trigger: String\n    let action: String\n    let destinationID: String\n}\n"
    files['manifest.json'] = json.dumps({'generator': GENERATOR_VERSION, 'files': sorted(files), 'screens': manifest_screens,
                                      'assets': ir.get('assets', []), 'diagnostics': diagnostics}, indent=2, sort_keys=True) + '\n'
    return files


def preflight_output(out, files, overwrite):
    """Check every file and ancestor before creating directories or writing bytes."""
    planned = set()
    for rel in files:
        relative = Path(rel)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe output path: ' + rel)
        folded = rel.casefold()
        if folded in planned: raise ValueError('Duplicate output path: ' + rel)
        planned.add(folded)
        p = out / relative
        for parent in p.parents:
            # System ancestors may legitimately be symlinks (e.g. macOS /var).
            if parent == out or out in parent.parents:
                if parent.is_symlink(): raise FileExistsError(f'Refusing symlink output path: {parent}')
            if parent.exists() and not parent.is_dir(): raise FileExistsError(f'Output parent is not a directory: {parent}')
        if p.is_symlink(): raise FileExistsError(f'Refusing symlink output path: {p}')
        if p.exists() and (not overwrite or not p.is_file()): raise FileExistsError(f'Refusing to overwrite {p}')
        if p.parent.is_dir():
            for sibling in p.parent.iterdir():
                if sibling.name.casefold() == p.name.casefold() and sibling.name != p.name:
                    raise FileExistsError(f'Case-insensitive output collision: {sibling}')


def generate(ir,out,overwrite=False,assets_dir=None):
    files = plan_output(ir, assets_dir)
    out = Path(out)
    preflight_output(out, files, overwrite)
    out.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes): p.write_bytes(text)
        else: p.write_text(text, encoding='utf-8')
    return files

def validate(ir, swift_dir=None):
    """Check JSON-shaped IR before rendering or accessing templates/assets."""
    errors = []; warnings = []; seen = set()
    def error(path, message): errors.append(path + ': ' + message)
    def obj(value, path):
        if not isinstance(value, dict):
            error(path, 'must be an object'); return False
        return True
    def array(value, path):
        if not isinstance(value, list):
            error(path, 'must be an array'); return False
        return True
    def string(value, path, nonempty=False):
        if not isinstance(value, str) or (nonempty and not value):
            error(path, 'must be a ' + ('nonempty ' if nonempty else '') + 'string'); return False
        # JSON can contain escaped lone surrogates, which cannot be written as UTF-8.
        try: value.encode('utf-8')
        except UnicodeEncodeError:
            error(path, 'must be valid UTF-8 text'); return False
        return True
    def number(value, path, minimum=None, positive=False):
        valid = not isinstance(value, bool) and isinstance(value, (int, float))
        if valid:
            try: valid = math.isfinite(float(value))
            except OverflowError: valid = False
        if not valid:
            error(path, 'must be a finite representable number'); return False
        if (minimum is not None and value < minimum) or (positive and value <= 0):
            error(path, 'must be positive' if positive else 'must be nonnegative'); return False
        return True
    def hex_color(value, path):
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?', value):
            error(path, 'must be a #RRGGBB or #RRGGBBAA string')
    def interactions(value, path, source=False):
        if not array(value, path): return
        for i, action in enumerate(value):
            here = f'{path}[{i}]'
            if not obj(action, here): continue
            for key in ('trigger', 'action', 'destination'):
                string(action.get(key), here + '.' + key)
            if source or 'source' in action:
                string(action.get('source'), here + '.source', nonempty=True)
    def node(n, path, parent=None, capture_container=True, in_flow=False):
        if not obj(n, path): return
        if string(n.get('id'), path + '.id', nonempty=True):
            if n['id'] in seen: error(path + '.id', 'duplicate node id: ' + n['id'])
            seen.add(n['id'])
        string(n.get('type'), path + '.type')
        if 'name' in n: string(n['name'], path + '.name')
        if 'visible' in n and not isinstance(n['visible'], bool): error(path + '.visible', 'must be a boolean')
        errors.extend(auto_layout.validate_node(n, path))
        b = n.get('bounds'); valid_bounds = {}
        if obj(b, path + '.bounds'):
            for key in ('x', 'y', 'width', 'height'):
                if number(b.get(key), path + '.bounds.' + key, minimum=0 if key in ('width', 'height') else None):
                    valid_bounds[key] = b[key]
            for key in ('x', 'y'):
                if not in_flow and parent is not None and key in parent and key in valid_bounds:
                    # Match rendering arithmetic, including int/int subtraction.
                    number(valid_bounds[key] - parent[key], path + '.bounds.' + key + ' (parent-relative)')
        if 'constraints' in n and obj(n['constraints'], path + '.constraints'):
            rules = n['constraints']
            for key in rules:
                if key not in ('horizontal', 'vertical'): error(path + '.constraints', 'unknown field: ' + str(key))
            for axis in ('horizontal', 'vertical'):
                mode = rules.get(axis, 'MIN')
                here = path + '.constraints.' + axis
                if not isinstance(mode, str) or mode not in CONSTRAINT_MODES:
                    error(here, 'must be MIN, MAX, CENTER, STRETCH, or SCALE')
                elif (not in_flow and parent is not None and not capture_container
                      and len(valid_bounds) == 4 and len(parent) == 4):
                    for value in constraint_geometry(valid_bounds, parent, axis, mode):
                        number(value, here + ' (derived geometry)')
        if 'style' in n and obj(n['style'], path + '.style'):
            if 'fill' in n['style']: hex_color(n['style']['fill'], path + '.style.fill')
            if 'corner_radius' in n['style']: number(n['style']['corner_radius'], path + '.style.corner_radius', minimum=0)
        if 'text' in n or n.get('type') == 'TEXT':
            text = n.get('text')
            if obj(text, path + '.text'):
                string(text.get('value'), path + '.text.value')
                number(text.get('font_size'), path + '.text.font_size', positive=True)
                if 'font_family' in text: string(text['font_family'], path + '.text.font_family')
                if text.get('color') is not None: hex_color(text['color'], path + '.text.color')
        if 'asset' in n and obj(n['asset'], path + '.asset'):
            for key in ('ref', 'format'): string(n['asset'].get(key), path + '.asset.' + key)
        if 'interactions' in n: interactions(n['interactions'], path + '.interactions')
        supported = False
        if not errors:
            supported = auto_layout.analyze(n)[0]
        if array(n.get('children'), path + '.children'):
            for i, child in enumerate(n['children']):
                node(child, f'{path}.children[{i}]', valid_bounds,
                     capture_container and isinstance(n.get('type'), str) and n['type'] in WRAPPER_TYPES, supported)
    if not obj(ir, '$'): return errors, warnings
    if ir.get('ir_version') != IR_VERSION: error('$.ir_version', 'unsupported or missing ir_version')
    node(ir.get('root'), '$.root')
    if 'diagnostics' in ir and array(ir['diagnostics'], '$.diagnostics'):
        for i, diagnostic in enumerate(ir['diagnostics']):
            path = f'$.diagnostics[{i}]'
            if not obj(diagnostic, path): continue
            before = len(errors)
            if diagnostic.get('level') not in ('warning', 'error', 'info'): error(path + '.level', 'must be warning, error, or info')
            for key in ('code', 'message'): string(diagnostic.get(key), path + '.' + key)
            for key in ('node_id', 'asset_ref'):
                if key in diagnostic: string(diagnostic[key], path + '.' + key)
            if len(errors) == before:
                warnings.append(diagnostic)
                if diagnostic['level'] == 'error': error(path + '.message', diagnostic['message'])
    if 'assets' in ir and array(ir['assets'], '$.assets'):
        for i, ref in enumerate(ir['assets']): string(ref, f'$.assets[{i}]')
    if 'interactions' in ir: interactions(ir['interactions'], '$.interactions', source=True)
    if 'tokens' in ir and obj(ir['tokens'], '$.tokens'):
        tokens = ir['tokens']
        if isinstance(tokens.get('version'), bool) or tokens.get('version') != 1: error('$.tokens.version', 'must be 1')
        for key in ('colors', 'fonts', 'spacing', 'radii'):
            path = '$.tokens.' + key
            if obj(tokens.get(key), path):
                for name, value in tokens[key].items():
                    here = path + '[' + json.dumps(name) + ']'
                    if key == 'colors': hex_color(value, here)
                    elif key == 'fonts': string(value, here)
                    else: number(value, here, minimum=0 if key == 'radii' else None)
    if not errors:
        warnings = auto_layout.merge_diagnostics(warnings, auto_layout.diagnostics(ir['root']))
        for current in walk(ir['root']):
            if auto_layout.analyze(current)[0]:
                try: auto_layout.equations(current)
                except (ValueError, OverflowError) as exc: error(current['id'], str(exc))
    if swift_dir and not errors:
        for p in Path(swift_dir).glob('*.swift'):
            txt = p.read_text(errors='replace')
            if 'private let node' in txt and 'translatesAutoresizingMaskIntoConstraints = false' not in txt:
                warnings.append({'level':'warning','code':'no-autolayout','message':str(p)})
    return errors, warnings

def main(argv=None):
    ap=argparse.ArgumentParser(description="Offline Figma JSON to UIKit converter")
    sub=ap.add_subparsers(dest="cmd",required=True)
    n=sub.add_parser("normalize"); n.add_argument("--input",required=True); n.add_argument("--output",required=True)
    g=sub.add_parser("generate"); g.add_argument("--input",required=True); g.add_argument("--output-dir",required=True); g.add_argument("--overwrite",action="store_true"); g.add_argument('--assets-dir',help='Explicit local root for PNG/JPEG/PDF assets; never downloads resources')
    v=sub.add_parser("validate"); v.add_argument("--input",required=True); v.add_argument("--swift-dir")
    t=sub.add_parser("test"); t.add_argument("--start-dir",default=".")
    a=ap.parse_args(argv)
    if a.cmd=="test":
        import unittest
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / "tests"))
        if not suite.countTestCases(): raise ValueError("No tests discovered")
        return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if a.input=="-": data=json.load(sys.stdin)
    else: data=json.loads(Path(a.input).read_text())
    if a.cmd=="normalize":
        ir=normalize(data)
        errors, _ = validate(ir)
        if errors: raise ValueError("; ".join(errors))
        Path(a.output).write_text(json.dumps(ir,indent=2,sort_keys=True)+"\n")
        return not validate(ir)[0]
    elif a.cmd=="generate": generate(data,a.output_dir,a.overwrite,a.assets_dir)
    else:
        e,w=validate(data,a.swift_dir); print(json.dumps({"errors":e,"warnings":w},indent=2)); return not e
    return True
if __name__ == "__main__":
    try:
        sys.exit(0 if main() else 1)
    except (ValueError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(1)
