import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import avatars as a

MAPPING = '''<actor>
  <a zh_cn="明里紬" zh_tw="明里䌷" jp="明里つむぎ" keyword="明里䌷,明里つむぎ,つむつむ" />
  <a zh_cn="甲" zh_tw="甲" jp="甲" keyword="甲,共用" />
  <a zh_cn="乙" zh_tw="乙" jp="乙" keyword="乙,共用" />
</actor>'''
TREE = {'Content': {
    'z-low': {'明里つむぎ.jpg': '明里つむぎ.jpg?t=1', '共用.jpg': '共用.jpg?t=1'},
    '0-Hand-Storage': {'明里つむぎ.jpg': 'AI-Fix-明里つむぎ.jpg?t=2', 'bad.jpg': '../x.jpg'}}}


class AvatarTests(unittest.TestCase):
    def test_japanese_name_bridges_to_chinese_and_last_group_wins(self):
        entries = a.build_index(TREE, MAPPING)
        self.assertEqual(entries, [{'zh_cn': '明里紬', 'zh_tw': '明里䌷', 'jp': '明里つむぎ', 'matched': '明里つむぎ',
                                    'path': 'Content/0-Hand-Storage/AI-Fix-明里つむぎ.jpg?t=2'}])

    def test_shared_alias_never_attaches_a_face(self):
        names = {e['zh_cn'] for e in a.build_index(TREE, MAPPING)}
        self.assertNotIn('甲', names)
        self.assertNotIn('乙', names)

    def test_unsafe_filenames_rejected(self):
        self.assertEqual(a.safe_filename('明里紬'), '明里紬.jpg')
        for bad in ('', '..', 'a/b', 'a\\b', 'a:b'):
            self.assertIsNone(a.safe_filename(bad))

    def test_repository_index_is_present(self):
        base, table = a.load_index()
        self.assertTrue(base.startswith('https://raw.githubusercontent.com/gfriends/'))
        self.assertIn(a.norm('明里紬'), table)


if __name__ == '__main__':
    unittest.main()
