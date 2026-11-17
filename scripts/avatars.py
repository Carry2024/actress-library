#!/usr/bin/env python3
"""Chinese-name avatars from Gfriends.

index  build data/avatars/index.json: every mapping_actor.xml row whose names (Chinese,
       Japanese or an alias unique to that row) have a Gfriends image, with the image path.
fetch  on the machine that reaches Emby: download avatars for people who have none into a
       folder named by their Emby name, for Gfriends Inputer's Local_Path to import.

Python 3.11+, standard library only.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import getpass
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / 'mapping_actor.xml'
INDEX = ROOT / 'data/avatars/index.json'
GFRIENDS = 'https://raw.githubusercontent.com/gfriends/gfriends/master/'
TREE_URL = GFRIENDS + 'Filetree.json'
AGENT = {'User-Agent': 'ActressLibrary/0.4'}


def norm(value):
    return ''.join(unicodedata.normalize('NFKC', value).split()).casefold()


def split_keywords(value):
    return [k.strip() for k in (value or '').split(',') if k.strip()]


def tree_lookup(tree):
    """Name -> image path. Groups are listed low to high quality, so later groups win (as Inputer does)."""
    found = {}
    for group, files in tree['Content'].items():
        for name, target in files.items():
            if not name.lower().endswith('.jpg') or '/' in target or '\\' in target:
                continue
            found[norm(name[:-4])] = f'Content/{group}/{target}'
    return found


def build_index(tree, mapping_text):
    rows = ET.fromstring(mapping_text.encode('utf-8'))
    entries = []
    for node in rows:
        names = [node.get('zh_cn'), node.get('jp'), node.get('zh_tw'), *split_keywords(node.get('keyword'))]
        entries.append((node.get('zh_cn'), node.get('zh_tw'), node.get('jp'), [n for n in names if n]))
    owners = {}
    for i, (_, _, _, names) in enumerate(entries):
        for n in {norm(x) for x in names}:
            owners.setdefault(n, set()).add(i)
    lookup = tree_lookup(tree)
    result = []
    for i, (zh_cn, zh_tw, jp, names) in enumerate(entries):
        for name in names:
            key = norm(name)
            # A name shared by two actors could attach the wrong face, so it is never used.
            if len(owners[key]) == 1 and key in lookup:
                result.append({'zh_cn': zh_cn, 'zh_tw': zh_tw, 'jp': jp, 'matched': name, 'path': lookup[key]})
                break
    return result


def fetch_text(url, limit=50_000_000):
    request = urllib.request.Request(url, headers={**AGENT, 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError('响应超过大小限制')
    return body.decode('utf-8-sig')


def index(tree_file=None):
    raw = Path(tree_file).read_text(encoding='utf-8') if tree_file else fetch_text(TREE_URL)
    tree = json.loads(raw)
    if not isinstance(tree.get('Content'), dict) or not tree['Content']:
        raise ValueError('Gfriends 索引为空或格式异常')
    entries = build_index(tree, MAPPING.read_text(encoding='utf-8'))
    old = json.loads(INDEX.read_text(encoding='utf-8')) if INDEX.exists() else None
    if old and len(entries) < len(old['entries']) * 0.9:
        raise ValueError(f'可配头像演员从 {len(old["entries"])} 降到 {len(entries)}，疑似异常，未覆盖')
    data = {'generated_at': dt.datetime.now(dt.timezone.utc).date().isoformat(),
            'gfriends': {'base_url': GFRIENDS, 'information': tree.get('Information'),
                         'sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest()},
            'mapping_rows': len(ET.fromstring(MAPPING.read_bytes())),
            'note': '每条演员只用其独有名字匹配 Gfriends；共用别名不参与，宁缺勿错。path 拼在 base_url 后即为下载地址。',
            'entries': entries}
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=0) + '\n', encoding='utf-8')
    print(f'头像对照表：映射表 {data["mapping_rows"]} 位，其中 {len(entries)} 位可配 Gfriends 头像。')


def load_index():
    data = json.loads(INDEX.read_text(encoding='utf-8'))
    table = {}
    for e in data['entries']:
        for name in (e['zh_cn'], e['zh_tw'], e['jp']):
            table.setdefault(norm(name), e)
    return data['gfriends']['base_url'], table


def safe_filename(name):
    if not name or name in ('.', '..') or re.search(r'[\\/:*?"<>|\x00-\x1f]', name):
        return None
    return name + '.jpg'


def emby_people(url, key):
    sys.path.insert(0, str(ROOT / 'scripts'))
    import emby_sync
    client = emby_sync.Client(url, key)
    return emby_sync.all_people(client)


def download(url, path, retries=3):
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=AGENT)
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(10_000_001)
            if len(body) > 10_000_000 or not body.startswith(b'\xff\xd8\xff'):
                raise ValueError('不是 JPEG 或超过 10 MB')
            tmp = path.with_suffix('.part')
            tmp.write_bytes(body)
            tmp.replace(path)
            return None
        except Exception as error:  # noqa: BLE001 - reported per file
            last = error
            time.sleep(2 * (attempt + 1))
    return str(last)


def fetch(args):
    base, table = load_index()
    if args.names_file:
        people = [{'Name': n.strip(), 'ImageTags': {}} for n in Path(args.names_file).read_text(encoding='utf-8').splitlines() if n.strip()]
    else:
        url = args.emby or input('主 Emby 地址（如 http://NAS地址:8096/emby）：').strip()
        key = getpass.getpass('Emby API Key（不显示、不保存）：').strip()
        people = emby_people(url, key)
    out = Path(args.out)
    todo, missing, skipped = [], [], 0
    for person in people:
        name = person.get('Name') or ''
        if person.get('ImageTags', {}).get('Primary') and not args.include_existing:
            skipped += 1
            continue
        filename = safe_filename(name)
        entry = table.get(norm(name))
        if not entry or not filename:
            missing.append(name)
            continue
        if (out / filename).exists():
            skipped += 1
            continue
        path = entry['path'] if args.ai_fix else entry['path'].replace('/AI-Fix-', '/')
        todo.append((name, base + urllib.parse.quote(path, safe='/?=&'), out / filename))
    print(f'人员 {len(people)}：待下载 {len(todo)}，已有头像或已下载 {skipped}，Gfriends 无匹配 {len(missing)}。')
    if args.dry_run:
        for name, url, _ in todo[:20]:
            print(' ', name, '←', url)
        return
    out.mkdir(parents=True, exist_ok=True)
    errors = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.threads, 8))) as pool:
        for (name, url, path), error in zip(todo, pool.map(lambda t: download(t[1], t[2]), todo)):
            if error:
                errors[name] = error
    report = out / 'avatar-report.json'
    report.write_text(json.dumps({'downloaded': len(todo) - len(errors), 'failed': errors, 'no_match': sorted(missing)},
                                 ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'完成：下载 {len(todo) - len(errors)}，失败 {len(errors)}。明细：{report}')
    print(f'下一步：Gfriends Inputer 的 Local_Path 设为 {out.resolve()}/ 后运行。')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    i = sub.add_parser('index', help='生成 data/avatars/index.json')
    i.add_argument('--tree-file', help='使用本地 Gfriends Filetree.json')
    f = sub.add_parser('fetch', help='按 Emby 缺头像演员下载头像到本地文件夹')
    f.add_argument('--emby', help='主 Emby 地址；不填则运行时询问')
    f.add_argument('--names-file', help='不连 Emby，改用每行一个演员名的文本文件')
    f.add_argument('--out', default='Avatar', help='保存目录，默认 ./Avatar')
    f.add_argument('--include-existing', action='store_true', help='已有头像的演员也下载')
    f.add_argument('--no-ai-fix', dest='ai_fix', action='store_false', help='使用未经 AI 放大的原图')
    f.add_argument('--threads', type=int, default=4, help='下载线程，默认 4，最多 8')
    f.add_argument('--dry-run', action='store_true', help='只统计，不下载')
    args = parser.parse_args()
    if args.command == 'index':
        index(args.tree_file)
    else:
        fetch(args)


if __name__ == '__main__':
    main()
