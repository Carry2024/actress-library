#!/usr/bin/env python3
"""Actor profiles for Emby: XSlist in bulk, official pages on top.

collect  look up each Emby person's Japanese name (via mapping_actor.xml) on XSlist and cache
         birthday, height, measurements, cup and birthplace in profiles-cache/xslist.json.
plan     merge the cache with the verified data in data/actors (official values win and are
         marked as such) and write profiles-plan.json; read-only for Emby.
apply    write the planned profile block into each person's Overview (and an empty birthday),
         keeping the rest of the Overview, with a JSON backup per person.

Runs where Emby and XSlist are reachable. Python 3.11+, standard library only.
"""
import argparse
import datetime as dt
import getpass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import emby_sync  # noqa: E402

CACHE = Path('profiles-cache/xslist.json')
XSLIST = 'https://xslist.org'
START, END = '【演员资料】', '【演员资料结束】'
LABELS = {'birthday': '生日', 'height_cm': '身高（cm）', 'measurements_cm': '三围（胸/腰/臀，cm）', 'cup': '罩杯',
          'birthplace': '出生地'}
AGENT = {'User-Agent': 'Mozilla/5.0 (ActressLibrary profile lookup; personal media library)'}


def norm(value):
    return ''.join(unicodedata.normalize('NFKC', value or '').split()).casefold()


def today():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


# ---------- name resolution ----------

def mapping_rows():
    rows = []
    for node in ET.parse(ROOT / 'mapping_actor.xml').getroot():
        names = [node.get('zh_cn'), node.get('zh_tw'), node.get('jp'),
                 *[k for k in (node.get('keyword') or '').split(',') if k.strip()]]
        rows.append({'zh_cn': node.get('zh_cn'), 'zh_tw': node.get('zh_tw'), 'jp': node.get('jp'), 'names': names})
    return rows


def name_resolver():
    """Display name (any of the three output names) -> row, only when unambiguous."""
    owners = {}
    rows = mapping_rows()
    for i, row in enumerate(rows):
        for n in {norm(row['zh_cn']), norm(row['zh_tw']), norm(row['jp'])}:
            owners.setdefault(n, set()).add(i)
    return lambda name: rows[next(iter(owners[norm(name)]))] if len(owners.get(norm(name), ())) == 1 else None


# ---------- XSlist ----------

class Page(HTMLParser):
    """Collects result links (search page) and visible text lines (detail page)."""

    def __init__(self):
        super().__init__()
        self.links, self.lines, self.title = [], [], ''
        self._href, self._text, self._skip, self._in_h1, self._buf = None, [], 0, False, []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip += 1
        if tag == 'a':
            self._href, self._text = dict(attrs).get('href'), []
        if tag == 'h1':
            self._in_h1 = True
        if tag in ('br', 'p', 'li', 'div', 'tr', 'h1', 'h2', 'h3', 'dd', 'dt'):
            self._flush()

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self._skip = max(0, self._skip - 1)
        if tag == 'a' and self._href:
            self.links.append((self._href, ''.join(self._text).strip()))
            self._href = None
        if tag == 'h1':
            self._in_h1 = False
        if tag in ('p', 'li', 'div', 'tr', 'h1', 'h2', 'h3', 'dd', 'dt'):
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._href is not None:
            self._text.append(data)
        if self._in_h1:
            self.title += data
        self._buf.append(data)

    def _flush(self):
        line = re.sub(r'\s+', ' ', ''.join(self._buf)).strip()
        if line:
            self.lines.append(line)
        self._buf = []

    def close(self):
        super().close()
        self._flush()


def parse(html_text):
    page = Page()
    page.feed(html_text)
    page.close()
    return page


def search_result(html_text, jp):
    """The detail URL whose link text is exactly the Japanese name; several or none -> None."""
    hits = {urllib.parse.urljoin(XSLIST, href) for href, text in parse(html_text).links
            if '/model/' in href and norm(text) == norm(jp)}
    return hits.pop() if len(hits) == 1 else None


def parse_detail(html_text, jp):
    page = parse(html_text)
    text = unicodedata.normalize('NFKC', '\n'.join(page.lines))
    if norm(jp) not in norm(page.title) and norm(jp) not in norm(text[:2000]):
        raise ValueError('详情页没有预期姓名')
    fields = {}
    m = re.search(r'(?:出生|生日|誕生日|生年月日)\s*[:：]\s*(\d{4})\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})', text)
    if m:
        born = dt.date(*map(int, m.groups()))
        if (dt.date.today() - born).days >= 18 * 365.25:
            fields['birthday'] = born.isoformat()
    m = re.search(r'(?:身高|身長)\s*[:：]\s*(\d{3})\s*cm', text)
    if m and 130 <= int(m[1]) <= 200:
        fields['height_cm'] = int(m[1])
    m = re.search(r'(?:三围|三圍|スリーサイズ)\s*[:：]\s*B\s*(\d{2,3})\D{0,6}W\s*(\d{2,3})\D{0,6}H\s*(\d{2,3})', text)
    if m:
        bust, waist, hip = map(int, m.groups())
        if all(40 <= v <= 150 for v in (bust, waist, hip)):
            fields['measurements_cm'] = {'bust': bust, 'waist': waist, 'hip': hip}
    m = re.search(r'(?:罩杯|カップ)\s*[:：]\s*([A-Z])\b', text)
    if m:
        fields['cup'] = m[1]
    m = re.search(r'(?:出生地|出身地|出身)\s*[:：]\s*([^\n:：]{1,30})', text)
    if m and m[1].strip().lower() not in ('n/a', '-', ''):
        fields['birthplace'] = m[1].strip()
    if not fields:
        raise ValueError('详情页格式无法识别')
    return fields


def get(url):
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(3_000_000).decode('utf-8', 'replace')


def collect_one(jp):
    url = search_result(get(f'{XSLIST}/search?lg=zh&query={urllib.parse.quote(jp)}'), jp)
    if not url:
        return {'status': 'not_found', 'checked_at': today()}
    time.sleep(1)
    return {'status': 'ok', 'url': url, 'checked_at': today(), 'fields': parse_detail(get(url), jp)}


def load_cache():
    return json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}


def save_cache(cache):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix('.tmp')
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(CACHE)


# ---------- official data ----------

def official_profiles():
    """Japanese name/alias -> (profile, sources) from data/actors."""
    result = {}
    for path in (ROOT / 'data/actors').glob('*.json'):
        actor = json.loads(path.read_text(encoding='utf-8'))
        for n in [actor['name'], *actor['aliases']]:
            result[norm(n)] = actor
    return result


def merged(row, cache, official):
    entry = cache.get(row['jp']) or {}
    fields = {k: {'value': v, 'source': 'XSlist', 'url': entry['url'], 'checked_at': entry['checked_at']}
              for k, v in (entry.get('fields') or {}).items()}
    actor = next((official[norm(n)] for n in row['names'] if norm(n) in official), None)
    if actor:
        for key, claim in actor['profile'].items():
            if claim:
                source = actor['sources'][claim['source']]
                fields[key] = {'value': claim['value'], 'source': source['title'], 'url': source['url'],
                               'checked_at': claim['checked_at'], 'official': True}
    return fields


def block(fields):
    lines = [START]
    for key, label in LABELS.items():
        f = fields.get(key)
        if not f:
            continue
        v = f['value']
        if key == 'measurements_cm':
            v = '/'.join(str(v[k]) for k in ('bust', 'waist', 'hip'))
        tag = '官方' if f.get('official') else f['source']
        lines.append(f'{label}：{v}（{tag}，{f["checked_at"]}）')
    for url in sorted({f['url'] for f in fields.values()}):
        lines.append('来源：' + url)
    lines.append(END)
    return '\n'.join(lines)


def new_overview(old, fields):
    old = old or ''
    if old.count(START) != old.count(END) or old.count(START) > 1:
        raise ValueError('简介中的资料标记异常，请人工核对')
    rest = re.sub(re.escape(START) + '.*?' + re.escape(END), '', old, flags=re.S).strip()
    return (rest + '\n\n' if rest else '') + block(fields)


# ---------- Emby ----------

def connect(args):
    url = args.emby or input('主 Emby 地址（如 http://NAS地址:8096/emby）：').strip()
    key = os.environ.get('EMBY_API_KEY') or getpass.getpass('Emby API Key（不显示、不保存）：').strip()
    client = emby_sync.Client(url, key)
    users = [u for u in client.request('/Users') if u.get('Policy', {}).get('IsAdministrator')]
    if len(users) != 1:
        raise ValueError('需要恰好一个管理员账号；多个时请先用 emby_sync.py 确认 User ID')
    return client, users[0]['Id']


def collect(args):
    resolve = name_resolver()
    if args.names_file:
        names = [n.strip() for n in Path(args.names_file).read_text(encoding='utf-8').splitlines() if n.strip()]
    else:
        client, _ = connect(args)
        names = [p['Name'] for p in emby_sync.all_people(client)]
    cache = load_cache()
    jps = []
    for name in names:
        row = resolve(name)
        if row and row['jp'] not in jps:
            jps.append(row['jp'])
    todo = [jp for jp in jps if args.refresh or jp not in cache][:args.limit]
    print(f'人员 {len(names)}，映射到日文名 {len(jps)}，本次查询 {len(todo)}（每次约 2 秒）。')
    for i, jp in enumerate(todo, 1):
        try:
            cache[jp] = collect_one(jp)
        except Exception as error:  # noqa: BLE001 - recorded and retried next run
            cache[jp] = {'status': 'error', 'error': str(error)[:200], 'checked_at': today()}
        if i % 20 == 0:
            save_cache(cache)
            print(f'  {i}/{len(todo)}')
        time.sleep(1)
    save_cache(cache)
    counts = {}
    for jp in jps:
        s = cache.get(jp, {}).get('status', 'pending')
        counts[s] = counts.get(s, 0) + 1
    print('结果：', counts, '；缓存：', CACHE.resolve())


def plan(args):
    client, user = connect(args)
    resolve, cache, official = name_resolver(), load_cache(), official_profiles()
    changes, skipped = [], 0
    for person in emby_sync.all_people(client):
        row = resolve(person['Name'])
        fields = merged(row, cache, official) if row else {}
        if not fields:
            skipped += 1
            continue
        before = client.item(user, person['Id'])
        wanted = {'Overview': new_overview(before.get('Overview'), fields)}
        b = fields.get('birthday')
        if b and not before.get('PremiereDate'):
            wanted['PremiereDate'] = b['value'] + 'T00:00:00.0000000Z'
        delta = {k: v for k, v in wanted.items() if before.get(k) != v}
        if delta:
            changes.append({'id': person['Id'], 'name': person['Name'], 'fingerprint': emby_sync.fingerprint(before),
                            'set': delta, 'official': any(f.get('official') for f in fields.values())})
    result = {'base_url': client.url, 'user_id': user, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'changes': changes}
    emby_sync.save(args.plan, result)
    print(f'拟更新 {len(changes)} 人（含官方资料 {sum(c["official"] for c in changes)} 人），无资料 {skipped} 人。预览：{args.plan}')
    for c in changes[:5]:
        print('---', c['name'], '\n' + c['set']['Overview'].split(START)[-1][:200])


def apply(args):
    client, user = connect(args)
    data = emby_sync.read(args.plan)
    if data['base_url'] != client.url or data['user_id'] != user:
        raise ValueError('Emby 地址或管理员与预览不一致')
    rows = data['changes'][:args.limit]
    done = 0
    for r in rows:
        before = client.item(user, r['id'])
        if emby_sync.fingerprint(before) != r['fingerprint']:
            print('跳过（预览后资料已变化）：', r['name'])
            continue
        if set(r['set']) - {'Overview', 'PremiereDate'}:
            raise ValueError('预览包含不允许的字段')
        emby_sync.save(Path(args.backups) / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{r['id']}.json", before)
        after = dict(before)
        after.update(r['set'])
        client.request('/Items/' + r['id'], 'POST', after)
        check = client.item(user, r['id'])
        if check.get('Overview') != r['set']['Overview']:
            raise ValueError('写入后校验失败：' + r['name'])
        done += 1
    print(f'已写入 {done}/{len(rows)} 人，备份在 {args.backups}/。剩余请重新 plan 后继续。')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--emby', help='主 Emby 地址；不填则运行时询问')
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--names-file', help='不连 Emby，改用每行一个演员名的文本文件')
    c.add_argument('--limit', type=int, default=300, help='本次最多查询人数，默认 300')
    c.add_argument('--refresh', action='store_true', help='已缓存的也重新查询')
    p = sub.add_parser('plan')
    p.add_argument('--plan', default='profiles-plan.json')
    a = sub.add_parser('apply')
    a.add_argument('--plan', default='profiles-plan.json')
    a.add_argument('--limit', type=int, default=20, help='本次最多写入人数，默认 20')
    a.add_argument('--backups', default='emby-backups')
    t = sub.add_parser('test-page', help='用保存的 XSlist 详情页检查解析结果')
    t.add_argument('file')
    t.add_argument('jp')
    args = parser.parse_args()
    if args.command == 'collect':
        collect(args)
    elif args.command == 'plan':
        plan(args)
    elif args.command == 'apply':
        apply(args)
    else:
        print(json.dumps(parse_detail(Path(args.file).read_text(encoding='utf-8'), args.jp), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # noqa: BLE001
        print('停止：' + str(error), file=sys.stderr)
        sys.exit(1)
