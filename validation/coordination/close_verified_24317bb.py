"""Close only the explicitly parent-reviewed tickets, checking native blockers first."""
import hashlib
import json
from pathlib import Path
import subprocess
import datetime

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'validation/coordination/closures-24317bb.json'
REPO='unununnnn/wksim'
BASE='https://github.com/unununnnn/wksim/blob/24317bb/'
groups=[
    ([99,38], 'RC', 'docs/2026-09-10-rc-flight-report.md',
     '双栈 movement/recenter/yaw/stream-stall/mode-out/new-takeover 六场景、12场最终原始审计均通过；记录撤权后的实际原生行为，不宣称断流自动悬停。'),
    ([105,106,107,108,44], '单电机效率', 'docs/2026-09-10-motor-efficiency-flight-report.md',
     '单旋翼效率进入真实 ODE4 力/力矩，无 PWM 缩放替代；双栈 baseline/fault/repeat 六场通过，新进程/新控制 epoch 与相同初始随机状态、效率重置已核实。'),
    ([118,119,120,47], '全球航点', 'docs/2026-09-10-global-flight-report.md',
     '双栈实际全球航点与明确 datum/home/origin，真实 home 改动撤权、旧命令拒绝、新请求恢复和落地均通过。OMP 从最终 PX4/AP 原始目录重审计复现通过。'),
    ([121,111,112], 'GNSS 运行子票', 'docs/2026-09-10-gnss-flight-report.md',
     '双栈传感器链注入、运行器、原始审计与最终两场运行已交付；OMP 重算复现通过。runbook 已明确历史边界；原始最终审计 JSON 已复制并与矩阵逐项核对。父 #45 的 GNSS 专属策略批准出处尚未定位，因此 #45 保持开放，本次不补造批准。'),
    ([103], 'ArUco 地面场景', 'docs/2026-09-10-aruco-scene-report.md',
     '真实 UE 39帧：外观8、运动7、遮挡8、恢复16；原门槛下最大角点误差0.487px、平移误差4.30mm；实际材质/组件/相机/身份读回通过，35项相关测试通过。仅 #103 场景标定完成，#104 与父 #40 的双栈跟踪继续实施。'),
]


def gh(*args):
    return subprocess.check_output(['gh',*map(str,args)],cwd=ROOT,text=True,encoding='utf-8')


if OUT.exists():raise SystemExit('Closure record already exists; inspect it instead of repeating comments')
records=[]
for numbers,label,report,summary in groups:
    for number in numbers:
        before=json.loads(gh('issue','view',number,'--repo',REPO,'--json','state,title,body'))
        blockers=json.loads(gh('api',f'repos/{REPO}/issues/{number}/dependencies/blocked_by','--jq','[.[] | {number,state}]'))
        if any(row['state']!='closed' for row in blockers):raise RuntimeError(f'#{number} still blocked: {blockers}')
        record=dict(number=number,title=before['title'],before=before['state'],blockers=blockers,
            reviewed_body_sha256=hashlib.sha256(before['body'].encode()).hexdigest())
        if before['state']=='OPEN':
            body=(f'<!-- main-acceptance-24317bb -->\n主会话复核收口：{label}。\n\n{summary}\n\n'
                f'实现及证据：[{report}]({BASE+report})。本轮复核：[parent-acceptance-514743f.md]({BASE}docs/coordination/parent-acceptance-514743f.md)。\n\n'
                '用户持续推进授权覆盖原目标实施及相应文件预约；既有统一验证目录被接受为实际证据位置，不复制成虚构新场次。'
                '父/子票按真实依赖顺序关闭；保留历史失败、实验候选与默认生产配置的区别。此次不表示 Full、G6、倍率或其它未验收模式完成。\n')
            path=ROOT/f'validation/coordination/closure-{number}-24317bb.md'
            path.write_text(body,encoding='utf-8')
            record['comment_url']=gh('issue','comment',number,'--repo',REPO,'--body-file',path).strip()
            gh('issue','close',number,'--repo',REPO,'--reason','completed')
        record['after']=json.loads(gh('issue','view',number,'--repo',REPO,'--json','state'))['state']
        assert record['after']=='CLOSED'
        records.append(record)
        OUT.write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),records=records),indent=2),encoding='utf-8')
        print(f'#{number} CLOSED',flush=True)
