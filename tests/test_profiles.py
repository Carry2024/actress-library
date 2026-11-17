import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import profiles as p

SEARCH = '''<html><body><ul>
<li><h3><a href="https://xslist.org/zh/model/1.html">明里つむぎ</a></h3></li>
<li><h3><a href="https://xslist.org/zh/model/2.html">明里つむぎ似</a></h3></li>
</ul></body></html>'''
DETAIL = '''<html><body><h1>明里つむぎ (Tsumugi Akari)</h1><div><p>
出生: 1998年03月31日<br>三围: B80 / W58 / H83<br>罩杯: B Cup<br>身高: 157 cm<br>出生地: 東京都<br>国籍: 日本</p></div>
<script>var x="身高: 999 cm";</script></body></html>'''


class ProfileTests(unittest.TestCase):
    def test_search_requires_exact_name(self):
        self.assertEqual(p.search_result(SEARCH, '明里つむぎ'), 'https://xslist.org/zh/model/1.html')
        self.assertIsNone(p.search_result(SEARCH, '明里'))

    def test_detail_fields(self):
        self.assertEqual(p.parse_detail(DETAIL, '明里つむぎ'), {
            'birthday': '1998-03-31', 'height_cm': 157, 'measurements_cm': {'bust': 80, 'waist': 58, 'hip': 83},
            'cup': 'B', 'birthplace': '東京都'})

    def test_wrong_person_or_blank_page_rejected(self):
        for page in (DETAIL.replace('明里つむぎ', '別人'), '<html><h1>明里つむぎ</h1></html>'):
            with self.assertRaises(ValueError):
                p.parse_detail(page, '明里つむぎ')

    def test_official_overrides_xslist_and_overview_is_idempotent(self):
        row = {'zh_cn': '明里紬', 'zh_tw': '明里䌷', 'jp': '明里つむぎ', 'names': ['明里紬', '明里つむぎ']}
        cache = {'明里つむぎ': {'status': 'ok', 'url': 'https://xslist.org/zh/model/1.html', 'checked_at': '2026-11-17',
                               'fields': {'height_cm': 160, 'birthplace': '東京都'}}}
        fields = p.merged(row, cache, p.official_profiles())
        self.assertEqual(fields['height_cm']['value'], 157)
        self.assertTrue(fields['height_cm']['official'])
        self.assertEqual(fields['birthplace']['source'], 'XSlist')
        text = p.new_overview('原有简介', fields)
        self.assertTrue(text.startswith('原有简介'))
        self.assertEqual(p.new_overview(text, fields), text)

    def test_resolver_uses_output_names_only(self):
        resolve = p.name_resolver()
        self.assertEqual(resolve('明里紬')['jp'], '明里つむぎ')
        self.assertIsNone(resolve('つむつむ'))


if __name__ == '__main__':
    unittest.main()
