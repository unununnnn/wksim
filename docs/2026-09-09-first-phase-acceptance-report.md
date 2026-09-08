# #48 首期SITL产品流程集成验收

票据于2026-09-08 17:35:14 UTC关闭并读回CLOSED/COMPLETED：[主代理验收评论](https://github.com/unununnnn/wksim/issues/48#issuecomment-5589276925)。

2026-09-09，主代理按[已批准首期矩阵](plan/2026-09-07-first-phase-batch-proposal.md)及[批准记录](2026-09-08-five-decisions-accepted.md)，完成跨切片集成复核。已验证项按批准要求保留真实运行并重新审计/回归，没有为累计次数重复飞行。#48的全部原生前置#6/#11/#13/#15/#16/#17/#18/#22/#42均已读回CLOSED；状态快照在validation/first-phase-acceptance-20260909/issues.json。

首期范围为固定四旋翼X、自有独立物理、真实PX4/ArduCopter、正式配置/任务入口和UE5.5 P450视觉资产；P450显示不等于实机动力学标定。联合profile的最小权威时间/显示/断连恢复已有独立已验切片，#20的持续1×及其他尚未完成联合能力仍开放。这里不将首期通过提升为G2/G6或Full完成，也不删改原Wayfinder父图。

## 按用户流程复核

| 用户步骤 / 首期条件 | 实际证据与本次复核 |
| --- | --- |
| 选择PX4/AP、保存配置、预检、正式启动 | #18真实内置浏览器完整操作；非法frame、保存重载、默认profile与每次新运行身份已验，HTTP原始动作与正式job/run再次逐项对应。#11/#12预检/启动前置关闭。 |
| 起飞、悬停、三航点、降落 | 五场UI运行保留4 pass/1 cancelled，所有公开信封与正式结果一致，物理驻留按0.5m/0.5m·s⁻¹/0.15rad原门槛重算，无事后改容差。 |
| 同一任务版本再次运行 | 两场PX4保存版本相同、run/mission身份不同，真实三航点均完成。 |
| 取消与拒绝过期决定 | AP首次取消确认过晚，未发cancel；同一10秒驻留配置再次运行，第三点驻留中取消并落地，只有前两点完成。事件/取消文件/HTTP身份仍一致。 |
| UE实时模型、位置和状态 | 五场共61张原生UE LIVE帧，5,560条Actor回读，与同run物理输出及既有坐标/姿态/时间差限再次核对；原PNG/JPEG未修改。 |
| 停止、结果与离线回看 | 真实页面结果读取、Truth分页、服务/查看器正常关闭；#16离线回看、#13独立实验隔离、#14旧控制epoch及#22断连/显式恢复保留各自已验报告与回归。 |
| 地面站观察和控制权交接 | #42本轮真实GUI双栈Hold/Brake、原生包、旧输出撤销、不自动抢回、新请求接管和落地已收口。用户最新授权助手全程确认，执行者并非人工点击。 |
| 核心不依赖外部闭源仿真运行时 | 两个独立默认准入实飞的FC/physics/Control/Agent当时加载映射和hash重新审计；无libgz-/libgazebo/libignition/libmwmcr/libmatlab/CopterSim.exe，实际加载钉定自编译libwksim_model.so。可读生成源码构建的库不是原版闭源模型DLL；不因此宣称资源可任意再分发。 |
| MATLAB按首期约定可选 | 两场真实R2022b六航点、暂停/继续、退出后自主推进、只读重连及AP的UE对应再次审计；真实MATLAB退出/私有startup标记、请求文件、结果原文、物理窗口均核对。未增加MATLAB控制范围或冒称它是物理/保活必需组件。 |

UI五场job为1262ff4465594257a9dde1d80d42ce80、160de7e1123e4b438e987b6ce703c710、a4b5e4d570214a5888dd1e5a5ac72fee、b27686cb10084d32bbfe67228587d763、bb5eef99eb9a4b3bab5473ea27914f62；每场8个公开请求、30个runtime/Control源码绑定。完整run、配置版本、任务ID、物理窗口、Actor回读和帧摘要在[UI收口报告](2026-09-08-console-ui-closure-report.md)及本次matrix-audit.json中逐行对应。独立FC动作/物理/UE是同一运行的证据链，不用另一个示例的画面拼接任务完成。

## 精确版本与历史证据

当前独立固件仍为PX4 d6f12ad1c4f70ad3230afd7d86e971421e02fef4加准入修改，二进制SHA93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a；AP 1511f27194f1dcc3728270883047bdf022b3fd53加准入修改，SHA083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de。加载映射、具体模型SHA、消息/控制包身份来自原始准入实飞及本轮#42结果。

运行器后来新增了显式参数存储、仅实验task_factory选择的较长物理寿命和GCS逐包摘要。默认任务行为有本轮回归；这些源码不能倒替历史UI/MATLAB版本。本次对UI逐源以记录SHA匹配当前字节，只有不同时才取git 1fdf273中的确切历史字节，另存ui-sources/manifest.json。对MATLAB从当前文件或本项目已存在Git对象恢复与原记录SHA完全相等的字节，共31个唯一来源绑定，建立正式retained-source-audit清单，再调用既有审计器。恢复的是确切字节，不猜测运行commit，也不改变原始结果。

MATLAB两场为matlab-flight-px4-bb855f5e07和matlab-flight-arducopter-9519837b8b；独立加载映射两场为gcs-px4-3b6b7dd16e20和gcs-arducopter-d1e5ae0f14d2。原有失败样本、条件跳过和主机墙钟回拨未被删除。第一次从WSL调用MATLAB历史审计因Windows路径不匹配失败，改在原Windows宿主运行后通过，没有放宽审计。

## 可复跑审计与入口

在Windows项目根：

```powershell
python -X utf8 -B validation/first-phase-acceptance-20260909/audit_matrix.py
python -X utf8 -B tools/audit_matlab_flight.py validation/matlab-independent-px4-20260907-run2 validation/matlab-independent-ap-20260907-run1 --source-archive validation/first-phase-acceptance-20260909/matlab-sources --output NEW_MATLAB_AUDIT.json
python -X utf8 -B tools/audit_independent_profile.py validation/gcs-bridge-20260908/live-px4-run4/formal validation/gcs-bridge-20260908/live-arducopter-run2/formal --source-archive validation/promotion-flight-20260908/independent-candidate/flown-source --output NEW_INDEPENDENT_AUDIT.json
```

正式交互从[工作台操作说明](wksim-console.md)选择PX4/AP mission配置；命令行仍用 `tools/run-wksim.sh` 和 `Simulator/wksim_runtime/examples/*-mission.json`，每次新run/output。联合入口另按[joint操作说明](joint-product-entry.md)及其未完成倍率约束。参数和GCS可选流程分别见[#43](2026-09-09-parameter-maintenance-closure-report.md)与[#42](2026-09-09-gcs-handoff-closure-report.md)。

本次matrix-audit.json和两次标准输出字节一致，SHAa5f5047154f7429e56ab8c3a0aaa8d73ed136b95e8c949992d5887f3ada83c25。MATLAB保留源审计SHAc8051b245b032a59cd71ebaf7cf3ac073ebdf1edaaf6ffbbc9d17a9381657b5b；独立加载审计SHA7ffbdd39096cec0c4f7e837a7fd0b20814c90a1dd846d9e2e1f00275fb93c6b1。原UI审计SHA63a454b01c03aa0bb4ffbef4d9541602d1092e3abfde2bfdef3ecf4c37aee186保持不变。

最终代码回归465项：436通过/29既有条件跳过，旧预检11通过。复核未启动新的FC/UE/MATLAB或改写旧证据，当前受控实验已结束。#48所需首期流程证据齐全；#20/#32倍率、#23数值预算、后续控制/模型/故障/ABI/硬件及Full扩展账本均保持各自未完成义务，持续目标不标完成。
