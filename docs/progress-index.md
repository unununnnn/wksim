# 进度导航

| 事项 | 报告 | 证据 | Commit | 现状与结论 | 入口 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 全球航点 | [2026-09-10-global-flight-report.md](2026-09-10-global-flight-report.md) | [final-matrix.json](../validation/47-global-flight/final-matrix.json) | `ff63c72` | 两栈v2全球航点、明确高度基准、真实home修改撤权、旧命令拒绝、新请求恢复和降落，在实验候选中通过。默认生产未提升；G6与倍率未因此通过。 | [run-global-flight.sh](../tools/run-global-flight.sh) |
| G6材料 | [g6-material-index.md](g6-material-index.md) | [index.json](../validation/g6-material-index-01/index.json) | `35728b1` | 索引23份PDF/773页及48个文件，找到厂家开发/生成说明和教学标定材料；当前e0全量精度预算仍未建立，未据此推定再分发权或新模型通过。 | - |
| 倍率诊断 | [joint-scheduler-diagnostic-report.md](joint-scheduler-diagnostic-report.md) | [archives.json](../validation/rate-remediation-ff63c72/archives.json)<br>[analysis-detail.json](../validation/rate-remediation-ff63c72/probe-03/analysis-detail.json) | `26182df` | 修复WSL PID映射及空采集误判，完成10秒地面窗口、39736对write和13项检查。未完成1x三epoch/60秒空中验收。最长12.00962ms组中AP输入等待8.098026ms，飞控各线程和主机根因尚未确认。 | [profile_joint_scheduler.py](../tools/profile_joint_scheduler.py)<br>[analyze_joint_scheduler.py](../tools/analyze_joint_scheduler.py) |

完整目标见 [plan/goal-objective.md](plan/goal-objective.md)，整体工具链仍未完成，旧报告“提交后停止”是历史状态，用户现在明确要求本会话继续推进。
