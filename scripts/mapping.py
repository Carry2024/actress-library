#!/usr/bin/env python3
"""Build the NGi-compatible mapping_actor.xml at the repository root.

The output is a full actor table: a base table (by default the condensed table from
li-peifeng/Jav-Actors-Mapping) plus the Chinese display names in data/emby-names.json.
NGi reads only this file once the custom repository is enabled, so it must stay complete.

Python 3.11+, standard library only.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/mapping/source.json'
BASE = ROOT / 'data/mapping/base_mapping_actor.xml'
NAMES = ROOT / 'data/emby-names.json'
OUTPUT = ROOT / 'mapping_actor.xml'
ATTRS = ('zh_cn', 'zh_tw', 'jp', 'keyword')


def norm(value):
    return ''.join(unicodedata.normalize('NFKC', value).split()).casefold()


def split_keywords(value):
    return [k.strip() for k in value.split(',') if k.strip()]


def parse(text):
    """Parse and check structure: <actor> root, only <a> children with the four attributes."""
    root = ET.fromstring(text.encode('utf-8'))
    if root.tag != 'actor':
        raise ValueError('根节点必须是 <actor>')
    rows = []
    for index, node in enumerate(root, 1):
        if node.tag != 'a':
            raise ValueError(f'第 {index} 条不是 <a> 节点')
        # keyword may be empty (the base table has a few such rows); the three names may not.
        missing = [k for k in ATTRS if node.get(k) is None or (k != 'keyword' and not node.get(k).strip())]
        if missing:
            raise ValueError(f'第 {index} 条缺少属性或为空：{",".join(missing)}')
        rows.append({k: node.get(k) for k in ATTRS})
    if not rows:
        raise ValueError('映射表为空')
    return rows


def escape(value):
    return (value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def render(rows):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<actor>']
    for row in rows:
        lines.append('  <a ' + ' '.join(f'{k}="{escape(row[k])}"' for k in ATTRS) + ' />')
    lines.append('</actor>')
    return '\n'.join(lines) + '\n'


def names_of(row):
    return {norm(row['zh_cn']), norm(row['zh_tw']), norm(row['jp'])} | {norm(k) for k in split_keywords(row['keyword'])}


def find_row(rows, actor_id, names):
    wanted = {norm(n) for n in names}
    hits = [i for i, row in enumerate(rows) if names_of(row) & wanted]
    if len(hits) > 1:
        # Prefer rows whose output names (not just aliases) match; shared aliases are common.
        strict = [i for i in hits if {norm(rows[i][k]) for k in ('zh_cn', 'zh_tw', 'jp')} & wanted]
        hits = strict or hits
    if len(hits) > 1:
        detail = '；'.join(rows[i]['jp'] for i in hits[:5])
        raise ValueError(f'{actor_id} 匹配到多条映射（{detail}），请在 match_names 中去掉共用别名')
    return hits[0] if hits else None


def merge(base_rows, mappings):
    rows = [dict(r) for r in base_rows]
    report = []
    for actor_id, item in mappings.items():
        display = item['display_name'].strip()
        names = [display, *item['match_names']]
        index = find_row(rows, actor_id, names)
        if index is None:
            jp = (item.get('jp') or item['match_names'][0]).strip()
            rows.append({'zh_cn': display, 'zh_tw': (item.get('zh_tw') or display).strip(), 'jp': jp,
                         'keyword': ','.join(dict.fromkeys([display, jp, *item['match_names']]))})
            report.append(f'新增 {actor_id}：{display}')
            continue
        row = rows[index]
        before = dict(row)
        row['zh_cn'] = display
        if item.get('zh_tw'):
            row['zh_tw'] = item['zh_tw'].strip()
        if item.get('jp'):
            row['jp'] = item['jp'].strip()
        keywords = split_keywords(row['keyword'])
        known = {norm(k) for k in keywords}
        for name in [row['zh_cn'], row['zh_tw'], row['jp'], *item['match_names']]:
            if norm(name) not in known:
                keywords.append(name.strip())
                known.add(norm(name))
        row['keyword'] = ','.join(keywords)
        if row != before:
            report.append(f'修改 {actor_id}：{before["zh_cn"]} → {row["zh_cn"]}')
    return rows, report


def conflicts(rows):
    """Aliases claimed by more than one row; the base table already has some, so this only reports."""
    owner = {}
    shared = set()
    for i, row in enumerate(rows):
        for key in names_of(row):
            if key in owner and owner[key] != i:
                shared.add(key)
            owner.setdefault(key, i)
    return shared


def load_mappings():
    data = json.loads(NAMES.read_text(encoding='utf-8'))
    for actor_id, item in data.items():
        if not item.get('display_name', '').strip() or not item.get('match_names'):
            raise ValueError(f'{actor_id} 缺少 display_name 或 match_names')
        if any(',' in n for n in [item['display_name'], *item['match_names']]):
            raise ValueError(f'{actor_id} 的名字不能包含英文逗号')
    return data


def build_text():
    rows, report = merge(parse(BASE.read_text(encoding='utf-8')), load_mappings())
    return render(rows), rows, report


def build():
    text, rows, report = build_text()
    OUTPUT.write_text(text, encoding='utf-8')
    for line in report:
        print(line)
    print(f'已生成 mapping_actor.xml：{len(rows)} 条，其中 {len(report)} 条来自 data/emby-names.json。')


def check():
    text, rows, _ = build_text()
    if not OUTPUT.exists():
        raise ValueError('缺少根目录 mapping_actor.xml，请运行 python3 scripts/mapping.py build')
    current = OUTPUT.read_text(encoding='utf-8')
    parse(current)
    if current != text:
        raise ValueError('mapping_actor.xml 与底表/emby-names.json 不同步，请运行 python3 scripts/mapping.py build')
    print(f'映射表校验通过：{len(rows)} 条，共用别名 {len(conflicts(rows))} 个（多来自底表，仅提示）。')


def update_base(file=None):
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    if file:
        text = Path(file).read_text(encoding='utf-8-sig')
        origin = str(Path(file).name)
    else:
        url = source['url']
        if urllib.parse.urlsplit(url).scheme != 'https':
            raise ValueError('底表地址必须是 HTTPS')
        request = urllib.request.Request(url, headers={'User-Agent': 'ActressLibrary/0.3'})
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read(50_000_001).decode('utf-8-sig')
        if len(text.encode('utf-8')) > 50_000_000:
            raise ValueError('底表超过大小限制')
        origin = url
    rows = parse(text)
    old_rows = parse(BASE.read_text(encoding='utf-8')) if BASE.exists() else []
    if old_rows and len(rows) < len(old_rows) * 0.9:
        raise ValueError(f'新底表条数从 {len(old_rows)} 降到 {len(rows)}，疑似异常，未覆盖')
    BASE.parent.mkdir(parents=True, exist_ok=True)
    BASE.write_text(render(rows), encoding='utf-8')
    source.update({'checked_at': dt.datetime.now(dt.timezone.utc).date().isoformat(), 'last_origin': origin,
                   'records': len(rows), 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()})
    SOURCE.write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'底表已更新：{len(rows)} 条（来源 {origin}）。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('build', help='由底表和 data/emby-names.json 生成根目录 mapping_actor.xml')
    sub.add_parser('check', help='校验 mapping_actor.xml 格式并确认已同步')
    u = sub.add_parser('update-base', help='更新底表；默认从 data/mapping/source.json 的地址下载')
    u.add_argument('--file', help='改用本地文件作为底表，例如从 NGi 容器 /data 拷出的默认 mapping_actor.xml')
    args = parser.parse_args()
    if args.command == 'build':
        build()
    elif args.command == 'check':
        check()
    else:
        update_base(args.file)
        build()


if __name__ == '__main__':
    main()
