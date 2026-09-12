# 当前 Goal 执行检查点

2026-09-13。Goal active，createdAt=1789219780；Full/G0–G6原范围和原AC不变。上一轮与本轮均有真实运行、代码修复和新证据，不是全局blocked。历史明细保留于[8f726ca检查点](https://github.com/unununnnn/wksim/blob/8f726ca/docs/coordination/short-cycle-goal.md)，本页只描述当前状态。

## 工作区与所有权

- 主仓库：C:/Users/PC/Documents/odid编译/wksim，分支codex/independent-rgb-integration，remote unununnnn/wksim。大量controller/runtime/UE/rover他方修改保留，禁止git add全库或覆盖。
- 主会话独占native、正式profile/catalog和joint_profile.py接线。Linux执行检出：Ubuntu-22.04 /root/wksim-release-acceptance-fe3，分支codex/planner-release-validation；第二发行版RflySim-20.04。
- Windows tools/run_joint_flight.py属于其它工作；实验runner只在上述Linux检出修改，并保留实际源SHA快照。最新主仓库joint_profile.py修复尚未同步到该Linux检出。
- 队列JSON是交接记录，不是后台自动调度程序。先读精确thread终态再续派；THREAD_BUSY不算送达，cancel ack不算终态。

## 当前两个可用外部任务

| 席位 | thread / 当前turn | 独占交付 |
| --- | --- | --- |
| OMP | 6deb2e40-2240-4db2-8c7f-c06bf6724048 / 40cb9045-ae4a-461b-b3fc-8bc91d9840a4 | Linux spin probe v2：给CPU读取加同域wall前后边界，计算间隔上下界；热路径只更新标量，字典推迟到begin结束；不改runner/父pacer/调度，不跑native。v1已实跑，旧源/原件不动。 |
| Claude Code | 48faf2f5-f74a-4ba4-ac85-4ae4d05c5801 / ed15fcb7-debf-4154-9377-123ce8a84e05 | 参考端包已交，主会话尚未审阅/实跑：probe_reference_first_step.m a719e7dd…、map_reference_blocks.py bc81f851…、纯测试5项。现在独占新build_first_step_trace.py/必要recorder及instrumentation测试，准备目标ODE4四级只读trace；不编译、不运行模型、不改旧builder/冻结源，不把trace当G6通过。 |

OMP旧数值报告出现过把2墙秒当500组，以及将sleep_max总和减出“残余归因”的错误，均不采用。现有分类仅能定位阶段边界，不能证明OS/FC或纯off-CPU原因。新helper须先读源、核对真实父类行为与测试再接线。

三个codebuddy均因429终态，返回的恢复时间为2026-09-13 20:54:20 JST；此时前不重复投递。DeepSeek受管后台仍故障，不计作运行席位。原Luna Fast未能核验，不替换成未获授权的速度/模型。

## 已完成：#83

#83已CLOSED，#82已CLOSED。结果/修复/独立复核已推送至f6239b7：
- run joint-public-flight-1w6dru32，epoch a160e99bb6ac46b4a09f0b36b3daeed7，runner与完整raw PV审计PASS，无计时探针。
- tick116004，最坏迟到89299145ns；27493个10s、21245个60s完整滑窗与两栈两段各12001个1ms参考样本全部通过原门；PGID2060–2069独立全空。
- 原件在Linux validation/joint-public-flight-1w6dru32；选取包validation/33-final-combo-luna/pv-settle-1w6dru32。audit-v2 SHA8140d80e5695bb377dedaef7198cb67811456a2429bab005085b2a5926f0e8c4；全部302输入SHA另复核。
- 详见docs/2026-09-13-final-combo-pv-pass.md。v1因重复status失败保留；v2复用原mixed严格规则核验两条完整解码字段相同的状态，保留事件及真实负例。没有重跑PV，也没有改旧原件。
- Task的fresh/估计速度≤.4入场余量已实跑；原2s/.5m/s保持及全部物理门保留。

## 当前#84阻断与下一步

同一当前组合mixed首次新场oxv29042失败：
- epoch18c96a7e0af9477092aa87e18239c23c；Linux raw validation/joint-public-flight-oxv29042，live /root/wksim-joint-flight-8rmtytx5；收据validation/current-mixed-20260913-01。
- tick131760、LAND下降中，RateUnmet100034744ns；wall313.978032933s，source_unchanged=true、cleanup_errors=[]、PGID2023–2032独立全空且boot与前检相同。Task未完成，不计整场通过。
- 115732+99780808+138204=100034744ns；creep=15139984 work-over+84640824 release-excess。
- 正确墙钟分区：249 early/975731ns、1 crossing/4ns、32679 steady/98805073ns。开始相对earliest的中位超额19ns、p95=38ns；这包括前组工作超额，不能统称调度延迟。
- 选取包validation/33-formal-promotion/current-mixed-oxv29042约2.43MB；完整raw留Linux。原mixed审计拒绝failed run，下游检查不接受。不要盲重跑同配置。

正式接线准备：
1. OMP提供的readiness包确认正式行仍0DQQz9/evidence=[]。只找到已通过的当前PV一行；未找到同组合mixed整场PASS，不能复制PV凑两行。
2. 主会话已修joint_profile._control：current分支复用未修改的完整joint_control_candidate.check；sealed历史分支核验声明资产。真实c2的current/sealed均通过，Linux21passed/46subtests。before/after在validation/33-formal-promotion/20260913-readiness。原7模块检查曾拒绝真实15模块+2资产；旧默认行未改。
3. _mixed_proofs已支持Control封存的显式message：flight/admission/identities/保留message-build与审计摘要严格同绑，只覆写两个指定消息包，其余原生包仍按baseline/index匹配。真实1w6dru32消息证明及Rzj3Pf当前overlay通过，MUlZd0旧overlay实际拒绝；Linux24passed/52subtests。catalog仍缺mixed证明，ok=false、children=0、capabilities=[]；证据在20260913-readiness/message-*.json。
4. spin v1已修四项并实跑：helper c6f37ab4…、测试738d1b12…，main合并验证53passed/11subtests，私有提交c6983e3（runner+helper+两测试）。入口--rate-spin-cpu-timing仅PV/MIXED且需原RATE_TIMING_PROBE=1，提前导入核验、源封存、结束后记录器错误汇总；默认路径与父pacer不改。

最新诊断vnv58upp（epoch3649e119e5544199b406645610e258b5）在tick91504以RateUnmet100515303ns失败，wall234.990319751s；无记录器/CPU采样错误、source_unchanged=true，PGID2373–2382独立全空。Linux原件validation/joint-public-flight-vnv58upp，live /root/wksim-joint-flight-k607mi42，收据validation/spin-cpu-mixed-20260913-01。22,866条父/子记录逐组对应，22,848组有跨释放pair。765个>=10us迟到pair合计58.696388ms迟到，CPU/wall比值有高低两类；记录到的79个GC事件与这765个pair重叠0。CPU读取自身成本未被v1独立括住，因此不能把比值直接当原pacer的on/off-CPU或OS/FC因果证据。v2必须先剥离读取窗口不确定性，不盲改睡眠余量。选取包validation/33-formal-promotion/spin-vnv58upp约6.6MB，保留失败与测量局限，不能作正式通过。

## G6与模型证据

- 已交付G6 first-divergence工具、测试与v1/v2/v3保留报告。主会话修read-once、数值/hex与manifest绑定、独占输出，并补拒绝相同值/正负零、非finite、bool假失败；实际重算与v3一致。
- 当前工具SHA75e97e3c3188dd8982c769e1287b188dad9127385ce45302899ab751b8a04e00，测试61904a4e602eb357470c8dffe385b1c6b50a6ba470cdf6a110009b2d80cb28b4。Windows30passed/1已由先前Linux覆盖的symlink skip/5subtests；最终记录见validation/coordination/g6-first-divergence-20260913/main-verification-final.json。
- 仍有5684个R1零预算失败；最早C3G/k1/Vehicle60[3]为2ULP。小误差不能排除全部合同问题，精确浮点运算原因未证。修正后的静态doc SHA3b0de981…/source-index e852aa6b…保留原ODE4括号顺序，sqrt输入未观测仍未证，历史二进制缺失/FMA判断前提明确；参考端事件粒度需要实际新诊断验证，不能假定每步4次。
- #26 current-wrapper-01已完成4×1000/1ms冷重建与reset：wrapper150ddf3b…，library528db324…，480000值精确相同。详见docs/2026-09-12-current-wrapper-lifecycle.md；不要重跑。#9接口/环境反馈依赖仍OPEN，#26不能关闭，G6未完成。

## 运行资源与必须保持的规则

- 当前冻结组合：AP /root/wksim-ap-mixed-fhuf05l9/mixed-build.json SHA1e6250ef…；Control /root/wksim-joint-control-c2IXOr/build.json SHA6fe8c0b3…；Message /root/wksim-ros2-Rzj3Pf/message-build.json SHA29969da0…。完整SHA和精确命令见当前final-combo合同及最近launch.sh。ZlTVa4是旧构建，已失配8份当前支持模块。
- 保持固定PX4 /root/wksim-px4-state-ONa1Kw/wksim-build.json（d7e905b3…）与本场模型库e59ab914…的原准入链；不要给PV/MIXED传PX4 override。两native参数必须同时启用。
- 新native前分别完成并检查两WSL进程扫描，再在另一调用启动；收口/暂停重负载代理，并以read确认终态。禁止终止用户进程或改全局内核/调度。当前无native活跃，最近31209/19042/46644均终态，不再poll/restart这些场。
- WSL空闲连接保持进程session12541/PID605已按15分钟到期exit0并读回终态，不是活跃任务；无需再次取消。保留历史身份boot a295410e-b29d-4d4a-aadb-9bf16f4652df/start_ticks336。
- 使用干净env；ROS离线审计需要/opt/ros/humble、DDS、AP消息与Rzj3Pf环境。Bash脚本用Python写入并清除CR；不要重犯PowerShell管道在末行追加CR。
- 已通过飞行不重跑。审计变化复核原件，保留失败报告，全部原AC证明后才关闭对应票；#33/#84/Full仍未完成，Goal不可complete。只精确git add，禁止发布厂商源码或.so。

## 仍待用户确认的恢复操作

用户指定卡死任务34386db2-17a1-425b-a102-f910451c5c63：原受管DSH日志turn10缺turn/end，已备份且停止确认无其它活跃任务的受管PID58652；用户独立DeepSeek桌面PID31408未动。适配器仍缓存故障和会话cookie，手动起同端口不能假定可恢复。重启Codex应用的确认尚未收到，不执行C:/Users/PC/.codex/repair-backups/ds-b-stuck-20260912/restart-codex-after-approval.ps1，不补写turn/end或Goal数据库。若用户明确批准，先重新核验进程身份再操作；不要重复提问。
