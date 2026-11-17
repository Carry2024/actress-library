import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import library as lib


class LibraryTests(unittest.TestCase):
    def test_profile_unicode_and_real_units(self):
        values = lib.parse_profile('<h1>Example</h1>【生年月日】１９９９年１１月２９日<br>【サイズ】T:157 B:82(E) W:54 H:84', 'Example')
        self.assertEqual(values['birthday'], '1999-11-29')
        self.assertEqual(values['measurements_cm'], {'bust':82,'waist':54,'hip':84})

    def test_failure_page_cannot_become_empty_profile(self):
        with self.assertRaises(ValueError):
            lib.parse_profile('<h1>Site Unavailable</h1>', 'miru')

    def test_wrong_person_rejected(self):
        with self.assertRaises(ValueError):
            lib.parse_profile('Wrong person 生年月日 1990年1月1日 T:155 B:80(B) W:58 H:83', 'miru')

    def test_image_priority_aliases_unicode_and_numbered_images(self):
        tree = {'Content': {'z-source': {'miru.jpg': 'miru.jpg?t=1'}, '0-Hand-Storage': {'miru-1.jpg':'miru-1.jpg?t=2', 'Another.jpg':'another.jpg'}}}
        images = lib.match_portraits(tree, ['miru'])
        self.assertEqual(len(images), 2)
        self.assertIn('0-Hand-Storage',images[0]['url'])
        self.assertEqual(images[0]['identity_status'], 'name_match_only')

    def test_external_rank_requires_provenance_and_known_actor(self):
        board = {'id':'test','title':'test','kind':'external','as_of':'2026-11-17','period':'2026-11','metric':'votes','source_url':'https://example.org/rank','entries':[{'rank':1,'actor_id':'missing'}]}
        with self.assertRaises(ValueError):lib.check_board(board, {'miru'})
        board['entries'][0]['actor_id']='miru'
        lib.check_board(board, {'miru'})
        board['entries'].append({'rank':1,'actor_id':'miru'})
        with self.assertRaises(ValueError):lib.check_board(board, {'miru'})

    def test_failed_refresh_preserves_entire_dataset(self):
        actor = copy.deepcopy(lib.actors()[0])
        actor['refresh_source']='official'
        tree = {'Content':{'test':{}},'Information':{}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(lib, 'ROOT', Path(tmp)):
            path = Path(tmp)/'data/actors'/f"{actor['id']}.json"
            lib.write(path,actor)
            before=path.read_bytes()
            with patch.object(lib,'fetch',side_effect=[__import__('json').dumps(tree),'Site Unavailable']):
                with self.assertRaises(ValueError):lib.refresh()
            self.assertEqual(path.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
