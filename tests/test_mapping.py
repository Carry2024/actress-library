import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mapping as m

BASE = '''<?xml version="1.0" encoding="UTF-8"?>
<actor>
  <a zh_cn="明里䌷" zh_tw="明里䌷" jp="明里つむぎ" keyword="明里䌷,明里つむぎ,明里紬" />
  <a zh_cn="甲" zh_tw="甲" jp="甲" keyword="甲,共用" />
  <a zh_cn="乙" zh_tw="乙" jp="乙" keyword="乙,共用" />
  <a zh_cn="丙&amp;丁" zh_tw="丙" jp="丙" keyword="" />
</actor>
'''


class MappingTests(unittest.TestCase):
    def test_round_trip_keeps_base_bytes(self):
        self.assertEqual(m.render(m.parse(BASE)), BASE)

    def test_override_display_name_keeps_aliases(self):
        rows, report = m.merge(m.parse(BASE), {'a': {'display_name': '明里紬', 'match_names': ['明里つむぎ']}})
        self.assertEqual(rows[0]['zh_cn'], '明里紬')
        self.assertEqual(rows[0]['zh_tw'], '明里䌷')
        self.assertEqual(rows[0]['keyword'], '明里䌷,明里つむぎ,明里紬')
        self.assertEqual(len(report), 1)

    def test_shared_alias_alone_is_rejected(self):
        with self.assertRaises(ValueError):
            m.merge(m.parse(BASE), {'x': {'display_name': '新名', 'match_names': ['共用']}})

    def test_unknown_actor_is_appended(self):
        rows, _ = m.merge(m.parse(BASE), {'n': {'display_name': '新人', 'match_names': ['しんじん']}})
        self.assertEqual(rows[-1], {'zh_cn': '新人', 'zh_tw': '新人', 'jp': 'しんじん', 'keyword': '新人,しんじん'})

    def test_bad_structure_rejected(self):
        for text in ['<actors><a zh_cn="a" zh_tw="a" jp="a" keyword="a"/></actors>',
                     '<actor><a zh_cn="a" zh_tw="a" keyword="a"/></actor>', '<actor></actor>', '<actor><a']:
            with self.assertRaises(Exception):
                m.parse(text)

    def test_repository_file_is_in_sync(self):
        m.check()


if __name__ == '__main__':
    unittest.main()
