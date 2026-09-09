"""Read-only one-ticket dispatcher for the published Luna backlog."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPO='unununnnn/wksim'


def gh(*arguments):
    result=subprocess.run(['gh',*arguments],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
    if result.returncode:raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def candidates(plan, issued, states, tier):
    ready=[];blocked=[]
    for row in sorted(plan['children'],key=lambda x:(x['priority'],x['key'])):
        if row['tier']!=tier:continue
        receipt=issued.get(row['key'])
        if not receipt:
            blocked.append({'key':row['key'],'reason':'not published'});continue
        current=states.get(receipt['number'])
        if current is None:
            blocked.append({'key':row['key'],'reason':'live issue missing'});continue
        if current['state'].lower()=='closed':continue
        labels={x['name'] if isinstance(x,dict) else x for x in current['labels']}
        required_label='ready-for-human' if tier=='decision' else 'ready-for-agent'
        if required_label not in labels:
            blocked.append({'key':row['key'],'issue':receipt['number'],'reason':'triage/decision hold'});continue
        if any(k not in issued for k in row['prerequisite_keys']):
            blocked.append({'key':row['key'],'issue':receipt['number'],'reason':'dependency not published'});continue
        deps=list(dict.fromkeys([issued[k]['number'] for k in row['prerequisite_keys']]+row.get('blocking_issue_numbers',[])))
        waiting=[n for n in deps if n not in states or states[n]['state'].lower()!='closed']
        if waiting:
            blocked.append({'key':row['key'],'issue':receipt['number'],'blocked_by':waiting});continue
        ready.append((row,receipt))
    return ready,blocked


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('next','list','inspect'))
    parser.add_argument('key',nargs='?')
    parser.add_argument('--tier',choices=('luna','astra','decision'),default='luna')
    args=parser.parse_args()
    plan=json.loads((ROOT/'docs/plan/lunar-backlog.json').read_text(encoding='utf-8'))
    path=ROOT/'docs/plan/lunar-issued.json'
    if not path.exists():raise RuntimeError('Backlog has not been published')
    receipt=json.loads(path.read_text(encoding='utf-8'));issued=receipt['issues']
    if args.command=='inspect':
        row=next((x for x in plan['children'] if x['key']==args.key),None)
        if row is None:raise ValueError('Unknown stable key')
        print(json.dumps({'definition':row,'published':issued.get(row['key'])},ensure_ascii=False,indent=2));return 0
    raw=gh('issue','list','--repo',REPO,'--state','all','--limit','500','--json','number,title,state,labels')
    states={x['number']:x for x in raw}
    ready,blocked=candidates(plan,issued,states,args.tier)
    verified=[]
    for row,item in ready:
        native=gh('api',f'repos/{REPO}/issues/{item["number"]}/dependencies/blocked_by')
        pending=[x['number'] for x in native if x['state'].lower()!='closed']
        if pending:
            blocked.append({'key':row['key'],'issue':item['number'],'native_blocked_by':pending});continue
        verified.append((row,item))
        if args.command=='next':break
    if args.command=='list':
        print(json.dumps({'ready':[{'key':r['key'],'number':i['number'],'title':r['title']} for r,i in verified],
                          'blocked':blocked},ensure_ascii=False,indent=2));return 0
    if not verified:
        print(json.dumps({'status':'no_ready_'+args.tier+'_ticket','blocked':blocked,
                          'action':'保留阻塞；查看Astra/decision前置。不要改预算或重复失败运行。'},ensure_ascii=False,indent=2));return 3
    row,item=verified[0]
    current=gh('issue','view',str(item['number']),'--repo',REPO,'--json','number,title,state,body')
    if f'<!-- lunar-slice:{row["key"]}:v1 -->' not in current['body']:
        raise RuntimeError('Live ticket stable identity changed')
    print(json.dumps({'status':'ready','number':item['number'],'url':item['url'],'key':row['key'],
        'tier':row['tier'],'working_directory':str(ROOT),'title':current['title'],'definition':row,
        'next_action':'先完整读取此GitHub子票；只做本票写入范围。真实运行使用新ID/目录，完成后再取下一票。'},
        ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
