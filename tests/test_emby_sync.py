import sys, unittest, copy, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import emby_sync as s
class SyncTests(unittest.TestCase):
 def test_overview_preserves_old_content_and_is_idempotent(self):
  actor=s.read(s.ROOT/'data/actors/miru.json')
  text=s.overview(actor,'原有中文简介')
  self.assertTrue(text.startswith('原有中文简介'))
  self.assertEqual(s.overview(actor,text),text)
 def test_unbalanced_marker_rejected(self):
  with self.assertRaises(ValueError):s.overview({},s.START)
 def test_key_not_serialized(self):
  c=s.Client('http://localhost:8096/emby','secret')
  self.assertNotIn('secret',c.url)
 def test_redirect_rejected(self):
  with self.assertRaises(ValueError):s.NoRedirect().redirect_request(None,None,None,None,None,None)
 def test_wrong_server_blocks_all_writes(self):
  class Fake:
   url='http://localhost:8096/emby'
   def request(self,path,*args):
    if path!='/System/Info':raise AssertionError('Unexpected write')
    return {'Id':'wrong'}
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'plan.json';s.save(p,{'server_id':'correct','base_url':Fake.url})
   with self.assertRaises(ValueError):s.apply(Fake(),SimpleNamespace(plan=p))
 def test_fingerprint_detects_changes(self):
  a={'Name':'one','Overview':'old'};b=copy.deepcopy(a);b['Overview']='new'
  self.assertNotEqual(s.fingerprint(a),s.fingerprint(b))
if __name__=='__main__':unittest.main()
