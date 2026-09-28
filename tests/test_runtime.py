import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import figma_to_uikit as f
class RuntimeTests(unittest.TestCase):
 def setUp(self): self.data=json.loads((Path(__file__).parents[1]/'examples/minimal-input.json').read_text())
 def test_normalize_contract(self):
  ir=f.normalize(self.data); self.assertEqual(ir['ir_version'],f.IR_VERSION); self.assertEqual(len(ir['root']['children']),4); self.assertTrue(ir['interactions']); self.assertIn('svg-needs-rasterization',[x['code'] for x in ir['diagnostics']])
 def test_deterministic_and_safe(self):
  ir=f.normalize(self.data)
  with tempfile.TemporaryDirectory() as d:
   f.generate(ir,d); first={p.name:p.read_bytes() for p in Path(d).iterdir()};
   with self.assertRaises(FileExistsError): f.generate(ir,d)
   f.generate(ir,d,True); self.assertEqual(first,{p.name:p.read_bytes() for p in Path(d).iterdir()})
 def test_validate(self): self.assertEqual(f.validate(f.normalize(self.data))[0],[])
 def test_rgb_default_alpha(self): self.assertEqual(f.color({'r':1,'g':0,'b':0}), '#FF0000FF')
 def test_invalid_color(self): self.assertIsNone(f.color('#1234567'))
 def test_swift_escape(self):
  self.assertEqual(f.swift_string('\\(danger)\n'), '"\\\\(danger)\\u{a}"')
 def test_rest_nodes_wrapper(self):
  ir=f.normalize({'nodes':{'1':{'document':{'id':'1','type':'FRAME','name':'Screen'}}}})
  self.assertEqual(ir['root']['children'][0]['id'],'1')
 def test_url_fails_validation(self): self.assertTrue(f.validate(f.normalize({'url':'https://figma.com/design/example'}))[0])
 def test_explicit_semantics(self): self.assertEqual(f.ui_class({'type':'FRAME','name':'Button input'}),'UIView()')
 def test_parent_relative_layout(self):
  ir=f.normalize({'id':'r','type':'FRAME','name':'Screen','bounds':{'x':100,'y':200},'children':[{'id':'p','type':'FRAME','bounds':{'x':110,'y':220},'children':[{'id':'c','type':'TEXT','characters':'Hello','bounds':{'x':115,'y':225}}]}]})
  with tempfile.TemporaryDirectory() as d:
   text=f.generate(ir,d)['ScreenRootView.swift']
   self.assertIn('node0.addSubview(node1)',text)
   self.assertIn('equalTo: node0.leadingAnchor, constant: 5.0',text)
   self.assertNotIn('safeAreaLayoutGuide',text)
 def test_overwrite_preflight(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'DesignTokens.swift').write_text('handwritten')
   with self.assertRaises(FileExistsError): f.generate(f.normalize(self.data),d)
   self.assertEqual(list(Path(d).iterdir()),[Path(d)/'DesignTokens.swift'])

 def test_reaction_shapes_and_callbacks(self):
  data={'id':'r','type':'FRAME','name':'Screen','children':[{'id':'b','type':'BUTTON','reactions':[{'trigger':'ON_CLICK','actions':[{'type':'NODE','destinationId':'other'}]},{'trigger':{'type':'ON_HOVER'},'action':'BACK'}]}]}
  ir=f.normalize(data)
  with tempfile.TemporaryDirectory() as d:
   files=f.generate(ir,d)
   self.assertIn('addTarget(self, action: #selector(handleNode0Tap)',files['ScreenRootView.swift'])
   self.assertIn('destinationID: "other"',files['ScreenRootView.swift'])
   codes=[x['code'] for x in json.loads(files['manifest.json'])['diagnostics']]
   self.assertIn('external-interaction-destination',codes)
   self.assertIn('unsupported-trigger',codes)
 def test_root_fill(self):
  ir=f.normalize({'id':'r','type':'FRAME','name':'Screen','fills':[{'color':{'r':1,'g':0,'b':0}}]})
  with tempfile.TemporaryDirectory() as d:
   self.assertIn('self.backgroundColor = UIColor(red: 1.00000000',f.generate(ir,d)['ScreenRootView.swift'])

 def test_ir_passthrough(self):
  ir=f.normalize(self.data)
  self.assertEqual(f.normalize(ir),ir)
 def test_malformed_ir(self):
  for ir in [None,[],{'root':None},{'root':{'id':[],'children':'bad'}}]:
   self.assertTrue(f.validate(ir)[0])
 def test_support_filename_collision(self):
  ir=f.normalize({'id':'r','type':'FRAME','name':'DesignTokens'})
  with tempfile.TemporaryDirectory() as d:
   files=f.generate(ir,d)
   self.assertIn('DesignTokensScreenViewController.swift',files)
   self.assertIn('enum DesignTokens',files['DesignTokens.swift'])
 def test_image_fill(self):
  ir=f.normalize({'id':'r','type':'RECTANGLE','fills':[{'type':'IMAGE','imageRef':'logo.png'}]})
  self.assertEqual(ir['assets'],['logo.png'])
  self.assertEqual(f.ui_class(ir['root']),'UIImageView()')

 def test_asset_integration_and_symlink_preflight(self):
  ir=f.normalize({'id':'r','type':'FRAME','name':'Screen','children':[{'id':'i','type':'IMAGE','imageRef':'logo.png'}]})
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); assets=root/'assets'; assets.mkdir(); (assets/'logo.png').write_bytes(b'png fixture')
   out=root/'out'; files=f.generate(ir,out,assets_dir=assets)
   self.assertIn('UIImage(named:',files['ScreenRootView.swift'])
   self.assertTrue(list(out.glob('Assets.xcassets/*.imageset/Contents.json')))
   blocked=root/'blocked'; blocked.mkdir(); (blocked/'Assets.xcassets').symlink_to(assets,target_is_directory=True)
   with self.assertRaises(FileExistsError): f.generate(ir,blocked,assets_dir=assets)
   self.assertFalse((blocked/'ScreenRootView.swift').exists())

if __name__=='__main__': unittest.main()
