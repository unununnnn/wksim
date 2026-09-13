"""Publish the reviewed Luna slices through gh; resume by stable marker/receipt.

Dry-run by default. --publish creates issues and native parent/dependency links.
Original parent AC/dependencies are retained; #1/#9/#10 get comments only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
REPO='unununnnn/wksim'
PLAN=ROOT/'docs/plan/lunar-backlog.json'
RECEIPT=ROOT/'docs/plan/lunar-issued.json'
SNAPSHOTS=ROOT/'docs/plan/lunar-parent-snapshots.json'
GUIDE='https://github.com/'+REPO+'/blob/codex/independent-rgb-integration/lunar%E6%A8%A1%E5%9E%8B%E5%AE%8C%E6%95%B4%E6%8E%A8%E8%BF%9B%E6%8C%87%E5%8D%97.md'


def save(path,value):
    data=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_bytes(data);temporary.replace(path)


def api(path, method='GET', body=None):
    command=['gh','api','repos/'+REPO+'/'+path,'-H','X-GitHub-Api-Version: 2026-03-10']
    if method!='GET':command+=['--method',method]
    temporary=None
    try:
        if body is not None:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.json',delete=False) as stream:
                json.dump(body,stream,ensure_ascii=False);temporary=Path(stream.name)
            command+=['--input',str(temporary)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
        if result.returncode:
            raise RuntimeError(f'{method} {path}: '+result.stderr.strip())
        return json.loads(result.stdout) if result.stdout.strip() else None
    finally:
        if temporary:temporary.unlink(missing_ok=True)


def ordered(rows):
    result=[];done=set()
    while len(result)<len(rows):
        ready=[r for r in rows if r['key'] not in done and set(r['prerequisite_keys'])<=done]
        if not ready:raise ValueError('Cyclic/unknown dependency keys')
        row=min(ready,key=lambda x:(x['priority'],x['key']))
        result.append(row);done.add(row['key'])
    return result


def issue_body(row, issued):
    key=row['key'];tier={'luna':'Luna 主任务','astra':'Astra 设计/审查','decision':'具体决策/资源确认'}[row['tier']]
    lines=[f'<!-- lunar-slice:{key}:v1 -->',f'原验收父票：#{row["parent"]}。执行层：**{tier}**。稳定键：`{key}`。',
        f'先读 [lunar模型完整推进指南.md]({GUIDE})。本票只完成下面限定切片，原父票验收标准不变。',
        '## 写入范围']
    lines += ['- `'+p+'`' for p in row['owned_files']]
    lines += ['','## 先读输入']+['- `'+p+'`' for p in row['known_input_reports']]
    deps=[issued[k]['number'] for k in row['prerequisite_keys']]+row.get('blocking_issue_numbers',[])
    lines+=['','## 本票前置']
    lines+=['- '+', '.join('#'+str(n) for n in dict.fromkeys(deps))] if deps else ['无本票额外开放依赖；运行前仍须完成脚本资源/身份检查。']
    if row.get('parent_dependencies'):
        lines+=['原父票依赖仍为 '+', '.join('#'+str(n) for n in row['parent_dependencies'])+'。本子票仅按自身真实前置派发，父票关闭规则不变。']
    lines+=['','## 操作步骤']+[f'{i}. {a}' for i,a in enumerate(row['concrete_actions'],1)]
    lines+=['','## 完成条件','- [ ] '+row['verifiable_completion'],
        '- [ ] 交付源码/配置身份、准确命令、原始结果和失败边界；仅关闭本子票。']
    command=row.get('targeted_test_command')
    if command:
        lines+=['','## 已有命令（WSL 仓库根目录）','```bash',command,'```',
            '运行标识/输出目录按指南生成新值；先核对当前 --help。']
    elif row['tier']=='luna' and row['command_status']=='predecessor_must_supply_exact_command':
        lines+=['','## 命令入口','前置票必须已经交付可执行脚本、完整命令、固定输入/预算与输出schema。缺一项即保持阻塞，不自行编造运行命令。']
    else:
        lines+=['','## 命令入口','这是实现/契约切片。新增入口、测试命令和输出schema属于交付物；当前不宣称尚未创建的脚本可以运行。']
    lines+=['','## 失败处理',
        '保存本次新证据，保持票据 OPEN，移到 needs-triage 并写清实际错误。源码身份、物理预算或写入范围变化交 Astra 复核；已授权的普通读写/检查不反复请求用户许可。',
        '父票关闭另核对原AC、原依赖和全部必要证明。子票通过不等于物理/Full通过；R1、RateUnmet与旧失败记录保持原状。']
    return '\n\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    plan=json.loads(PLAN.read_text(encoding='utf-8'));rows=ordered(plan['children'])
    if not args.publish:
        print(json.dumps({'children':len(rows),'parents':len(plan['parents']),'acyclic':True,
            'tiers':{t:sum(r['tier']==t for r in rows) for t in ('luna','astra','decision')}}));return
    receipt=json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {'schema_version':1,'repository':REPO,'issues':{},'parents_updated':[]}
    issued=receipt['issues']
    existing=api('issues?state=all&per_page=100')
    by_number={x['number']:x for x in existing if 'pull_request' not in x}
    if SNAPSHOTS.exists():snapshots=json.loads(SNAPSHOTS.read_text(encoding='utf-8'))
    else:
        snapshots={}
        for p in plan['parents']:
            n=p['number'];value=by_number.get(n) or api(f'issues/{n}')
            snapshots[str(n)]={'id':value['id'],'title':value['title'],'body':value.get('body') or '',
                'body_sha256':hashlib.sha256((value.get('body') or '').encode()).hexdigest(),
                'blocked_by':[x['number'] for x in api(f'issues/{n}/dependencies/blocked_by')]}
        save(SNAPSHOTS,snapshots)
    # Canonical triage labels only; do not invent a competing Luna label system.
    labels={x['name'] for x in api('labels?per_page=100')}
    for name,color,description in [('needs-triage','ededed','Needs scoped triage before another attempt'),
            ('needs-info','d876e3','Missing concrete information or resources'),
            ('ready-for-human','fbca04','Concrete human decision or resource action needed')]:
        if name not in labels:api('labels','POST',{'name':name,'color':color,'description':description});time.sleep(.7)
    for index,row in enumerate(rows,1):
        key=row['key'];marker=f'<!-- lunar-slice:{key}:v1 -->'
        if key not in issued:
            found=next((x for x in existing if marker in (x.get('body') or '')),None)
            if found is None:
                tier={'luna':'Luna','astra':'Astra','decision':'决策'}[row['tier']]
                label='ready-for-human' if row['tier']=='decision' else 'ready-for-agent'
                found=api('issues','POST',{'title':f'[{tier}] {row["title"]}',
                    'body':issue_body(row,issued),'labels':[label,'wayfinder:task'],
                    'parent_issue_id':snapshots[str(row['parent'])]['id']})
                time.sleep(1)
            issued[key]={'number':found['number'],'id':found['id'],'url':found['html_url'],'parent':row['parent'],'tier':row['tier']}
            save(RECEIPT,receipt)
        item=issued[key];n=item['number']
        if not item.get('parent_verified'):
            try:parent=api(f'issues/{n}/parent')
            except RuntimeError:parent=None
            if not parent or parent['number']!=row['parent']:
                api(f'issues/{row["parent"]}/sub_issues','POST',{'sub_issue_id':item['id']});time.sleep(.8)
                parent=api(f'issues/{n}/parent')
            if parent['number']!=row['parent']:raise ValueError('Wrong native parent')
            item['parent_verified']=True;save(RECEIPT,receipt)
        dependencies=list(dict.fromkeys([issued[k]['number'] for k in row['prerequisite_keys']]+row.get('blocking_issue_numbers',[])))
        if not item.get('dependencies_verified'):
            actual={x['number'] for x in api(f'issues/{n}/dependencies/blocked_by')}
            for dep in dependencies:
                if dep in actual:continue
                target=next((v for v in issued.values() if v['number']==dep),None)
                target_id=target['id'] if target else (by_number.get(dep) or api(f'issues/{dep}'))['id']
                api(f'issues/{n}/dependencies/blocked_by','POST',{'issue_id':target_id});time.sleep(.8)
            actual={x['number'] for x in api(f'issues/{n}/dependencies/blocked_by')}
            if not set(dependencies)<=actual:raise ValueError('Dependency readback differs')
            item['blocked_by']=sorted(actual);item['dependencies_verified']=True;save(RECEIPT,receipt)
        print(json.dumps({'published':index,'total':len(rows),'key':key,'issue':n}),flush=True)
    for p in plan['parents']:
        n=p['number']
        if n in receipt['parents_updated']:continue
        children=[x for x in rows if x['parent']==n]
        block='<!-- lunar-container:v1 -->\n本票保留为原验收容器；从下列子票执行，每次一个切片。原AC与原Blocked by不变。\n\n'
        block+=f'[完整推进指南]({GUIDE})\n\n'
        block+='\n'.join(f'- [ ] #{issued[x["key"]]["number"]} · {x["title"]}（{x["tier"]}）' for x in children)
        block+='\n\n子票仅保留各自真实前置以便并行推进；关闭本父票仍需原依赖和原AC全部满足。\n<!-- /lunar-container:v1 -->'
        original=snapshots[str(n)]['body']
        current=api(f'issues/{n}')
        if n in (1,9,10):
            comments=api(f'issues/{n}/comments?per_page=100')
            if not any('<!-- lunar-container:v1 -->' in (x.get('body') or '') for x in comments):
                api(f'issues/{n}/comments','POST',{'body':block});time.sleep(1)
        else:
            desired=block+'\n\n'+original
            if current.get('body') not in (original,desired):raise ValueError(f'Concurrent parent edit #{n}')
            if current.get('body')!=desired:api(f'issues/{n}','PATCH',{'body':desired});time.sleep(1)
        current=api(f'issues/{n}')
        if original not in (current.get('body') or ''):raise ValueError('Original parent body changed')
        deps=[x['number'] for x in api(f'issues/{n}/dependencies/blocked_by')]
        if set(deps)!=set(snapshots[str(n)]['blocked_by']):raise ValueError('Original parent dependencies changed')
        receipt['parents_updated'].append(n);save(RECEIPT,receipt)
        print(json.dumps({'parent_verified':n,'children':len(children)}),flush=True)
    receipt['complete']=True;save(RECEIPT,receipt)


if __name__=='__main__':main()
