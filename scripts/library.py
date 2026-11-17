#!/usr/bin/env python3
"""Public actor metadata, source provenance and Gfriends portrait references.

Python 3.11+, standard library only. No media-server credentials required.
"""
import argparse
import copy
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TREE_URL = 'https://raw.githubusercontent.com/gfriends/gfriends/master/Filetree.json'
IMAGE_BASE = 'https://raw.githubusercontent.com/gfriends/gfriends/master/Content/'
PROFILE_HOSTS = {'cmore.jp', 'www.t-powers.co.jp'}


def today():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def https_url(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('来源地址必须是无凭据的 HTTPS URL')
    return value


def fetch(url, max_bytes=25_000_000):
    https_url(url)
    request = urllib.request.Request(url, headers={'User-Agent': 'ActressLibrary/0.1 (public profile metadata)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        https_url(response.geturl())
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError('响应超过大小限制')
        return body.decode('utf-8-sig')


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('br', 'p', 'div', 'dd', 'dt'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        self.parts.append(' ')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalize(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).casefold()


def parse_profile(body, expected_name):
    parser = Text()
    parser.feed(body)
    text = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', ' '.join(parser.parts)))
    if normalize(expected_name) not in normalize(text):
        raise ValueError('页面未找到预期姓名，可能为拦截页或页面已更名')
    birth = re.search(r'生年月日[】\s:]*([0-9]{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日', text)
    if not birth:
        raise ValueError('未找到完整生日；不覆盖已有数据')
    birthday = dt.date(*map(int, birth.groups()))
    if (dt.date.fromisoformat(today()) - birthday).days < 18 * 365.25:
        raise ValueError('仅收录已成年公众人物的公开资料')
    section = text[birth.end():birth.end()+220]
    height = re.search(r'(?:T\s*:|身長\s*)([0-9]{3})', section)
    measurements = re.search(r'(?:B\s*:|スリーサイズ\s*)([0-9]{2,3})\s*\(([A-Z]+)\)\s*W\s*:\s*([0-9]{2,3})\s*H\s*:\s*([0-9]{2,3})', section)
    if not height or not measurements:
        raise ValueError('身高/三围页面格式改变；不覆盖已有数据')
    bust, cup, waist, hip = measurements.groups()
    return {'birthday': birthday.isoformat(), 'height_cm': int(height[1]),
            'measurements_cm': {'bust': int(bust), 'waist': int(waist), 'hip': int(hip)}, 'cup': cup}


def check_actor(actor):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,79}', actor['id']):
        raise ValueError('不合法的演员 ID')
    if not isinstance(actor['name'], str) or not actor['name'].strip():
        raise ValueError('姓名不能为空')
    if not all(isinstance(x, str) and x.strip() for x in actor['aliases']):
        raise ValueError('别名必须是非空字符串')
    sources = actor['sources']
    for source in sources.values():
        https_url(source['url'])
        dt.date.fromisoformat(source['checked_at'])
    for key, claim in actor['profile'].items():
        if claim is None:
            continue
        if claim['source'] not in sources:
            raise ValueError(f'{key} 缺少来源')
        dt.date.fromisoformat(claim['checked_at'])
        value = claim['value']
        if key == 'birthday':
            born = dt.date.fromisoformat(value)
            if (dt.date.fromisoformat(today())-born).days < 18*365.25:
                raise ValueError('生日不是已成年日期')
        elif key == 'height_cm' and (type(value) is not int or not 100 <= value <= 230):
            raise ValueError('身高单位/范围不正确')
        elif key == 'measurements_cm':
            if set(value) != {'bust', 'waist', 'hip'} or not all(type(v) is int and 30 <= v <= 180 for v in value.values()):
                raise ValueError('三围单位/范围不正确')
    for item in actor['career']:
        if item['source'] not in sources or not item['summary'].strip():
            raise ValueError('履历缺少来源或内容')
        date = item['date']
        if not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', date):
            raise ValueError('履历日期格式不正确')
        dt.date.fromisoformat(date + {4:'-01-01',7:'-01',10:''}[len(date)])
    for image in actor.get('portraits', []):
        https_url(image['url'])
    return actor


def actors():
    return [check_actor(read(p)) for p in sorted((ROOT/'data/actors').glob('*.json'))]


def check_board(board, ids):
    if board['kind'] not in ('personal', 'external'):
        raise ValueError('榜单类型错误')
    if not re.fullmatch(r'[a-z0-9-]+', board['id']):
        raise ValueError('榜单 ID 错误')
    dt.date.fromisoformat(board['as_of'])
    if not board['title'].strip() or not board['metric'].strip():
        raise ValueError('榜单必须注明名称和排名指标')
    if board['kind'] == 'external':
        https_url(board['source_url'])
        if not board['period'].strip():
            raise ValueError('外部榜单必须注明统计周期')
    ranks, seen = set(), set()
    for item in board['entries']:
        if type(item['rank']) is not int or item['rank'] < 1 or item['rank'] in ranks:
            raise ValueError('排名必须为不重复的正整数')
        if item['actor_id'] not in ids or item['actor_id'] in seen:
            raise ValueError('演员 ID 未收录或在榜单重复')
        ranks.add(item['rank'])
        seen.add(item['actor_id'])
    return board


def validate():
    records = actors()
    ids = {a['id'] for a in records}
    if len(ids) != len(records):
        raise ValueError('重复演员 ID')
    boards = [check_board(read(p), ids) for p in sorted((ROOT/'data/rankings').glob('*.json'))]
    print(f'校验通过：{len(records)} 位演员，{len(boards)} 份榜单（空榜不代表已取得排名）')
    return records, boards


def match_portraits(tree, names):
    """Exact normalized-name lookup; never infer identity from portrait filenames."""
    wanted = {normalize(n) for n in names}
    found = {}
    for group, files in tree['Content'].items():
        for name, target in files.items():
            stem = re.sub(r'-\d+$', '', Path(name).stem)
            if normalize(stem) not in wanted:
                continue
            parts = urllib.parse.urlsplit(target)
            if parts.scheme or parts.netloc or '/' in parts.path or '\\' in parts.path:
                continue
            url = IMAGE_BASE + urllib.parse.quote(group, safe='') + '/' + urllib.parse.quote(parts.path, safe='')
            if parts.query:
                url += '?' + parts.query
            found[url] = {'url': url, 'group': group, 'matched_name': name,
                          'identity_status': 'name_match_only', 'source': TREE_URL}
    # Upstream insertion order is low to high quality; last groups take precedence.
    return list(reversed(list(found.values())))[:20]


def refresh(tree_file=None):
    records, _ = validate()
    raw_tree = Path(tree_file).read_text(encoding='utf-8') if tree_file else fetch(TREE_URL)
    tree = json.loads(raw_tree)
    if not isinstance(tree.get('Content'), dict) or not tree['Content']:
        raise ValueError('Gfriends 索引为空/格式异常')
    changed = []
    failures = []
    for original in records:
        actor = copy.deepcopy(original)
        source_id = actor.get('refresh_source')
        if source_id:
            try:
                source = actor['sources'][source_id]
                if urllib.parse.urlsplit(source['url']).hostname not in PROFILE_HOSTS:
                    raise ValueError('来源尚无受支持的解析器')
                body = fetch(source['url'], 2_000_000)
                values = parse_profile(body, actor['name'])
                for key, value in values.items():
                    old = actor['profile'].get(key)
                    if old and old.get('locked'):
                        continue
                    if old and old['value'] != value:
                        actor['history'].append({'field': key, 'previous': old, 'changed_at': today()})
                    actor['profile'][key] = {'value': value, 'source': source_id, 'checked_at': today()}
                source['checked_at'] = today()
                source['response_sha256'] = hashlib.sha256(body.encode()).hexdigest()
                time.sleep(1)
            except Exception as error:
                failures.append({'actor_id': actor['id'], 'error': str(error)})
        actor['portraits'] = match_portraits(tree, [actor['name']] + actor['aliases'])
        check_actor(actor)
        changed.append(actor)
    # No dataset write on ANY failure. Old profiles and images remain intact.
    if failures:
        write(ROOT/'reports/refresh-errors.json', failures)
        raise ValueError('刷新失败，所有现有资料保持原样；详见 reports/refresh-errors.json')
    for actor in changed:
        write(ROOT/'data/actors'/f"{actor['id']}.json", actor)
    write(ROOT/'data/upstream.json', {'repository':'https://github.com/gfriends/gfriends',
        'index_url': TREE_URL, 'checked_at': today(), 'information': tree['Information'],
        'sha256': hashlib.sha256(raw_tree.encode()).hexdigest(),
        'note':'TotalNum 是上游图片数量，不是本库已核对演员数量；图片只保存引用链接。'})
    print(f'刷新成功：{len(changed)} 位演员。履历和排行榜需来源核对后另行更新。')


def build():
    records, boards = validate()
    write(ROOT/'docs/catalog.json', {'actors': records, 'rankings': boards})
    lines = ['# 演员目录', '', '可在 GitHub 点击演员姓名查看资料。空字段表示尚未核实。', '', '| 姓名 | 生日 | 身高 cm | 三围 cm |', '| --- | --- | --- | --- |']
    for actor in records:
        p = actor['profile']
        v = lambda k: p[k]['value'] if p.get(k) else '待补充'
        m = v('measurements_cm')
        sizes = '/'.join(str(m[k]) for k in ('bust','waist','hip')) if isinstance(m,dict) else m
        lines.append(f"| [{actor['name']}](actors/{actor['id']}.md) | {v('birthday')} | {v('height_cm')} | {sizes} |")
        detail = [f"# {actor['name']}", '', f"稳定 ID：`{actor['id']}`", '', '别名：'+'、'.join(actor['aliases']), '', '## 公开资料', '']
        labels = {'birthday':'生日','height_cm':'身高（cm）','measurements_cm':'三围（cm）','cup':'罩杯','birthplace':'出生地'}
        for key, claim in p.items():
            if claim:
                source = actor['sources'][claim['source']]
                value = json.dumps(claim['value'],ensure_ascii=False) if isinstance(claim['value'],dict) else str(claim['value'])
                detail.append(f"- {labels.get(key,key)}：{value}；[来源]({source['url']})；核对：{claim['checked_at']}")
        detail += ['', '## 履历', '']
        for event in actor['career']:
            detail.append(f"- {event['date']}：{event['summary']} [来源]({actor['sources'][event['source']]['url']})")
        if not actor['career']:
            detail.append('尚未核实，暂不填充。')
        detail += ['', '## 头像候选', '', '以下由 Gfriends 姓名精确匹配得到，图片仍属原权利人；匹配不等于人工确认。', '']
        for image in actor.get('portraits',[])[:5]:
            detail.append(f"- [{image['group']}]({image['url']})")
        path = ROOT/'docs/actors'/f"{actor['id']}.md"
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('\n'.join(detail)+'\n',encoding='utf-8')
    (ROOT/'docs/CATALOG.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('已生成 docs/catalog.json、docs/CATALOG.md 和演员资料页。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    sub.add_parser('build')
    r = sub.add_parser('refresh')
    r.add_argument('--tree-file', help='使用本地 Gfriends 索引，仍从官网更新已配置资料')
    b = sub.add_parser('import-ranking')
    b.add_argument('file')
    args = parser.parse_args()
    if args.command == 'validate':
        validate()
    elif args.command == 'build':
        build()
    elif args.command == 'refresh':
        refresh(args.tree_file)
        build()
    elif args.command == 'import-ranking':
        board = check_board(read(args.file), {a['id'] for a in actors()})
        destination = ROOT/'data/rankings'/f"{board['id']}-{board['as_of']}.json"
        if destination.exists():
            raise ValueError('该榜单快照已存在；请核对后手动编辑，不静默覆盖历史')
        write(destination, board)
        build()


if __name__ == '__main__':
    main()
