#!/usr/bin/env python3
"""主 Emby 人员资料：只读预览、限定 ID 写入与备份。Python 3.11+。"""
import argparse, base64, copy, getpass, hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
import urllib.request, urllib.parse

ROOT=Path(__file__).resolve().parents[1]
START='【女友资料库】'
END='【资料库结束】'
FIELDS=('Name','Overview','PremiereDate','LockedFields')
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError('拒绝重定向，避免把认证信息发送到其他地址')

def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
    os.chmod(path,0o600)

def read(path): return json.loads(Path(path).read_text())
def norm(s): return re.sub(r'\s+','',s).casefold()
def fingerprint(item):
    x={k:item.get(k) for k in FIELDS};x['ImageTags']=item.get('ImageTags',{})
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class Client:
    def __init__(self,url,key):
        self.url=url.rstrip('/')
        p=urllib.parse.urlsplit(self.url)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment: raise ValueError('Emby 地址不合法')
        self.key=key;self.open=urllib.request.build_opener(NoRedirect()).open
    def request(self,path,method='GET',data=None,content_type='application/json',raw=False):
        headers={'X-Emby-Token':self.key,'Accept':'application/json'}
        if data is not None:
            if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
            headers['Content-Type']=content_type
        req=urllib.request.Request(self.url+path,data=data,headers=headers,method=method)
        with self.open(req,timeout=45) as r:
            body=r.read(20_000_001)
            if len(body)>20_000_000: raise ValueError('响应过大')
            if raw:return body,r.headers.get_content_type()
            return json.loads(body) if body else None
    def item(self,user,ident):
        if not re.fullmatch(r'[a-zA-Z0-9-]+',str(ident)):raise ValueError('ID 格式异常')
        x=self.request(f'/Users/{user}/Items/{ident}')
        if x.get('Type')!='Person':raise ValueError('只允许人员条目')
        return x

def overview(actor,old):
    if old.count(START)!=old.count(END) or old.count(START)>1:raise ValueError('简介标记异常，人工核对')
    old=re.sub(re.escape(START)+'.*?'+re.escape(END),'',old,flags=re.S).strip()
    labels={'birthday':'生日','height_cm':'身高（cm）','measurements_cm':'三围（胸/腰/臀，cm）','cup':'罩杯','birthplace':'出生地'}
    lines=[START,'公开艺名：'+actor['name']]
    used=set()
    for key,label in labels.items():
        c=actor['profile'].get(key)
        if not c:continue
        v=c['value']
        if key=='measurements_cm':v='/'.join(str(v[k]) for k in ('bust','waist','hip'))
        lines.append(f'{label}：{v}（核对 {c["checked_at"]}）');used.add(c['source'])
    for e in actor['career']:
        lines.append(e['date']+'：'+e['summary']);used.add(e['source'])
    for source in sorted(used):lines.append('资料来源：'+actor['sources'][source]['url'])
    lines.append(END)
    return (old+'\n\n' if old else '')+'\n'.join(lines)

def all_people(client):
    items=[];seen=set();start=0
    while True:
        page=client.request('/Persons?'+urllib.parse.urlencode({'StartIndex':start,'Limit':200,'Fields':'Overview,ProviderIds','EnableImages':'true'}))
        batch=page.get('Items',[])
        if not batch:break
        for item in batch:
            if item['Id'] in seen:raise ValueError('人员分页重复，停止扫描')
            seen.add(item['Id']);items.append(item)
        start+=len(batch)
        if start>=page.get('TotalRecordCount',start):break
    return items

def create_plan(client,user,out):
    server=client.request('/System/Info');people=all_people(client)
    mappings=read(ROOT/'data/emby-names.json')
    actor_map={p.stem:read(p) for p in (ROOT/'data/actors').glob('*.json')}
    index={}
    for aid,m in mappings.items():
        for n in [m['display_name'],*m['match_names']]:index.setdefault(norm(n),set()).add(aid)
    groups={};unmatched=[];ambiguous=[]
    for item in people:
        match=index.get(norm(item['Name']),set())
        if len(match)==1:groups.setdefault(next(iter(match)),[]).append(item)
        elif match:ambiguous.append({'id':item['Id'],'name':item['Name'],'reason':'别名冲突'})
        else:unmatched.append({'id':item['Id'],'name':item['Name'],'has_image':bool(item.get('ImageTags',{}).get('Primary'))})
    changes=[]
    for aid,items in groups.items():
        if len(items)!=1:
            ambiguous.extend({'id':i['Id'],'name':i['Name'],'reason':'同一演员存在多个人员 ID，暂不合并'} for i in items);continue
        before=client.item(user,items[0]['Id']);actor=actor_map[aid];mapping=mappings[aid]
        wanted={'Name':mapping['display_name'],'Overview':overview(actor,before.get('Overview') or '')}
        birthday=actor['profile'].get('birthday')
        if birthday and not before.get('PremiereDate'):wanted['PremiereDate']=birthday['value']+'T00:00:00.0000000Z'
        wanted['LockedFields']=sorted(set(before.get('LockedFields') or [])|set(wanted))
        delta={k:v for k,v in wanted.items() if before.get(k)!=v}
        image=mapping.get('portrait_url') if not before.get('ImageTags',{}).get('Primary') else None
        if delta or image:changes.append({'id':before['Id'],'actor_id':aid,'before_name':before['Name'],'fingerprint':fingerprint(before),'set':delta,'image_url':image})
    plan={'server_id':server['Id'],'server_name':server.get('ServerName'),'base_url':client.url,'user_id':user,'created_at':datetime.now(timezone.utc).isoformat(),'changes':changes,'ambiguous':ambiguous,'unmatched':unmatched}
    save(out,plan)
    print(f'服务器：{plan["server_name"]} / {plan["server_id"]}\n扫描 {len(people)} 人，拟更新 {len(changes)} 人，重复/冲突 {len(ambiguous)} 人，缺少资料 {len(unmatched)} 人。\n预览文件：{out}')
    for x in changes:print(x['id'],x['before_name'],'→',x['set'].get('Name',x['before_name']),'补头像' if x['image_url'] else '保留头像')

def image_bytes(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname not in ('cmore.jp','raw.githubusercontent.com'):raise ValueError('头像来源不在支持名单')
    req=urllib.request.Request(url,headers={'User-Agent':'ActressLibrary/0.2'})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as r:
        b=r.read(10_000_001);mime=r.headers.get_content_type()
    jpeg=b.startswith(b'\xff\xd8\xff');png=b.startswith(b'\x89PNG\r\n\x1a\n')
    if len(b)>10_000_000 or not (jpeg or png):raise ValueError('头像不是支持的 JPEG/PNG')
    return b,'image/jpeg' if jpeg else 'image/png'

def apply(client,args):
    plan=read(args.plan);server=client.request('/System/Info')
    if server['Id']!=plan['server_id'] or client.url!=plan['base_url']:raise ValueError('服务器与预览不一致')
    selected=set(args.ids.split(','));rows=[r for r in plan['changes'] if r['id'] in selected]
    if len(rows)!=len(selected):raise ValueError('ID 不在预览或存在重复')
    if len(rows)>args.limit:raise ValueError('超过本次数量上限')
    for r in rows:
        before=client.item(plan['user_id'],r['id'])
        if fingerprint(before)!=r['fingerprint']:raise ValueError('资料已变化，请重新预览：'+r['id'])
        if set(r['set'])-set(FIELDS):raise ValueError('计划包含不允许更新的字段')
        image=image_bytes(r['image_url']) if r['image_url'] else None
        after=copy.deepcopy(before);after.update(r['set'])
        backup=Path(args.backups)/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+r['id']+'.json')
        record={'server_id':server['Id'],'user_id':plan['user_id'],'before':before,'intended':r['set'],'image_added':False,'state':'prepared'};save(backup,record)
        client.request('/Items/'+r['id'],'POST',after)
        record['state']='metadata_written';save(backup,record)
        if image:
            # Mark intent before network write, so timeout still leaves a recovery record.
            record['image_added']=True;save(backup,record)
            client.request('/Items/'+r['id']+'/Images/Primary','POST',base64.b64encode(image[0]),image[1])
        verified=client.item(plan['user_id'],r['id'])
        if any(verified.get(k)!=v for k,v in r['set'].items()):raise ValueError('写入后字段校验失败，备份：'+str(backup))
        if image and not verified.get('ImageTags',{}).get('Primary'):raise ValueError('头像上传后未确认，备份：'+str(backup))
        record['state']='verified';record['after_fingerprint']=fingerprint(verified);save(backup,record)
        print('已验证：',r['id'],verified['Name'],'备份：',backup)

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',help='主 Emby 地址，例如 http://NAS:端口/emby');p.add_argument('--user-id',help='主 Emby 管理员 User ID')
    s=p.add_subparsers(dest='mode',required=True)
    q=s.add_parser('plan');q.add_argument('--out',default='emby-plan.json')
    a=s.add_parser('apply');a.add_argument('--plan',default='emby-plan.json');a.add_argument('--ids',required=True);a.add_argument('--limit',type=int,default=3);a.add_argument('--backups',default='emby-backups')
    args=p.parse_args()
    if args.user_id and not re.fullmatch(r'[a-zA-Z0-9-]+',args.user_id):raise ValueError('用户 ID 格式错误')
    if not args.url:args.url=input('主 Emby 地址（含协议和端口，如 http://NAS:端口/emby）：').strip()
    key=os.environ.get('EMBY_API_KEY') or getpass.getpass('主 Emby API Key（隐藏输入，不写入文件）：')
    client=Client(args.url,key)
    if not args.user_id:
        users=client.request('/Users')
        admins=[u for u in users if u.get('Policy',{}).get('IsAdministrator')]
        if len(admins)==1:args.user_id=admins[0]['Id']
        else:
            for u in users:print(u['Id'],u['Name'])
            args.user_id=input('输入主 Emby 管理员 User ID：').strip()
        if not re.fullmatch(r'[a-zA-Z0-9-]+',args.user_id):raise ValueError('用户 ID 格式错误')
    if args.mode=='plan':create_plan(client,args.user_id,args.out)
    else:
        if read(args.plan)['user_id']!=args.user_id:raise ValueError('用户与预览不一致')
        apply(client,args)
if __name__=='__main__':
    try:main()
    except Exception as e:print('停止：'+str(e),file=sys.stderr);sys.exit(1)
