# Public velocity/yaw 独立结束审计（WIP）

修复正式入口把所有 initial 任务送入位置窗口的分派缺陷。原证据
`validation/joint-velocity-yaw-nnh00wfp/run/epochs/ecd4969e2100465283e4f421054cf4e1`
在旧 `verify_tasks` 离线重放稳定抛出 `KeyError: 'waypoint_reached'`。
新分派显式传配置 `task`，位置任务默认行为保留。

新 `velocity_evidence.py` 从连续的 1 ms 原始 120 维物理状态重算窗口，
沿用 #22 冻结门槛：ENU (0.8,0.4,0) 逐轴误差≤0.3 持续3 s；零保持
速度模≤0.25、相对阶跃结束原始位置漂移≤1 m 持续4 s；ENU 0.5 rad/s
偏航积分误差≤0.35 持续4 s；AP 无效组合拒绝后速度模≤0.25 持续2 s。
NED速度轴转换为ENU，NED原始偏航逐毫秒解缠并反号；不使用任务记录的pass充当物理证明。
同时检查请求序号/载荷/控制代次、命令身份、对应受理或精确拒绝、setup与LAND原生ACK、
场景时间和车辆身份及结束阶段。外层离线工具另核对task配置/ready/go、启动停止动作、
任务子进程正常退出；物理窗口和完整运行分别给出结论。

原样本物理结果：AP速度最大轴误差0.02556 m/s、零保持漂移0.57223 m、
yaw积分误差0.14328 rad；PX4分别0.08669、0.62529、0.11362；全部窗口满足门槛。
**整个运行仍为failed**：保留原 RateUnmet 和旧结束审计错误，不修改旧结果，
不宣称新版本真实全场景验收通过，也不关闭 #22。

离线命令：

```powershell
python -B -m unittest validation.test_joint_velocity_evidence -v
python -B tools/audit_joint_velocity_yaw.py validation/joint-velocity-yaw-nnh00wfp/run/epochs/ecd4969e2100465283e4f421054cf4e1 --output validation/joint-velocity-yaw-nnh00wfp/independent-velocity-audit.json
```

四项测试含真实分派回归及10个单字段负例（速度、零速度、漂移、yaw、拒绝静止、
请求身份、缺ACK、拒绝改受理、缩短持续窗口、错车辆）；全部通过。
第二条命令预期退出1：physical_windows=pass，但status=failed。
测试明确依赖上述保留的真实日志，不生成虚假的成功飞行。

主代理复核又发现全运行归约原先只看flight_completed+stopped，可能把仍有活动fault
的落地后运行提升为pass。本轮受权修改该归约：有完成飞行但最后authority.fault仍在→failed，
并在顶层保留原fault字符串；无完成飞行的故障停止仍为stopped。历史faults不一刀切拒绝，
已显式恢复且当前fault清空可通过。以封存健康`joint-rate-flow-82p4pbu7`、恢复后
`joint-rate-flow-4kt7s0ei`及原nnh样本内存重放作回归，原始文件均未更改。

发现路径：实际诊断literal→runtime调用→原生CBM index_status与精确verify_tasks查询
（1项，has_more=false）→读取实际joint_evidence源码；没有依赖修改后的结构查询。
本代理JSONL实际核验 model=gpt-6-astra、effort=low；没有嵌套代理、飞控/UE启动或构建。

主代理真实复跑：x8mozm0m仍在61172步发生既定RateUnmet，停止动作已无waypoint_reached审计错误，任务未全部完成所以物理成功证据为空；场景退场为stopped、验证器为failed，两者不混淆。#32保持OPEN。构建/生命周期/整体测试收口见2026-09-08-depth-lifecycle-closure-report.md。
