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
| OMP | 51609e8d-e4ce-4a8e-8a0d-f7c896c24842 / 4a870824-7894-4c4d-bfa5-c39c6b4c5219 | 直接CPython3.10扩展候选：native_release_wait_extension.c/.py/test；仅另可给原C的POSIX宏加ifndef，不改函数体。不编译/native/WSL，不接生产。 |
| Claude Code | e64514a6-77c2-4b27-91a7-896c92a361fd / d335c61d-1571-4faf-8fb9-37902133e73c | 只读核对最小等待接线/时间戳语义与#84证明绑定，唯一写native-wait-integration-contract-20260913.md，不改实现，不运行测试/native。 |

最新句柄在rolling-two-20260913-06.json。主会话现掌握基准/C库/适配器，OMP可改C宏guard但该未验证修改不可混入已执行版本；当前C/py已从bench02快照精确暂存为18bf382d…/17328f02…，不要盲目重新add正在修改的C文件。准备器已验收18测试，源码candidate0107001b…与成功实验逐字相同。

调度修复：已通过automation_update暂停同根任务每3分钟wksim heartbeat，Goal读回仍active；原prompt/周期/目标/名称/创建时间全部保留。证据native-release-wait-bench-20260913-02/scheduler-adjustment.json。只让Goal持续执行，避免双重唤醒；不要无故恢复重复heartbeat。OMP关于21ad94b2源调查未定位具体调用，其引用根turn时间早于该外部任务创建，heartbeat存在不是因果证明；来源仍unknown。21ad94b2已明确interrupted，两WSL当时无残留，未用该轮当受控native证据。两个子任务均无独立goal，Goal DB只读未改。

三个codebuddy因429不可用（2026-09-13 20:54:20 JST前不重投），DeepSeek后台仍待重启确认，Luna Fast未核验不替换用户选择。不虚报不可用席位。

## 已完成：#83

#83已CLOSED，#82已CLOSED。结果/修复/独立复核已推送至f6239b7：
- run joint-public-flight-1w6dru32，epoch a160e99bb6ac46b4a09f0b36b3daeed7，runner与完整raw PV审计PASS，无计时探针。
- tick116004，最坏迟到89299145ns；27493个10s、21245个60s完整滑窗与两栈两段各12001个1ms参考样本全部通过原门；PGID2060–2069独立全空。
- 原件在Linux validation/joint-public-flight-1w6dru32；选取包validation/33-final-combo-luna/pv-settle-1w6dru32。audit-v2 SHA8140d80e5695bb377dedaef7198cb67811456a2429bab005085b2a5926f0e8c4；全部302输入SHA另复核。
- 详见docs/2026-09-13-final-combo-pv-pass.md。v1因重复status失败保留；v2复用原mixed严格规则核验两条完整解码字段相同的状态，保留事件及真实负例。没有重跑PV，也没有改旧原件。
- Task的fresh/估计速度≤.4入场余量已实跑；原2s/.5m/s保持及全部物理门保留。

## 当前#84阻断与下一步

最新#84候选微基准：C最终1ms等待库真实构建，16个受控时钟C检查在UBSan下通过（含完整int64最后部分秒）；适配器14纯测试通过。bench01因.so和.py同名，Python误当扩展导入而失败，未产生样本；bench02改为libwksim_release_wait.so的同字节副本，真实3000样本成功，3种模式轮转各1000。Python返回延迟中位148.5ns/累计2.532098ms；CDLL2979ns/6.517725ms；PyDLL2424ns/5.822768ms。C内部7ns中位不能替代返回Python的实际时间，当前ctypes接法暂不接生产；下一步测直接CPython扩展是否消掉边界开销。详见docs/2026-09-13-native-release-wait-benchmark.md。不得据单进程基准称RateUnmet已修复。

库SHA b695fcc7c86ea0e3ad5c6b56bc4ba5055725fc24c6b83da784c2664da2da4145，私有/root/wksim-native-release-wait-20260913-01与-02。源C18bf382d…/适配器17328f02…，rows SHAe0742388ce82efd2a68200b8ed024526d4323c6d6950b226c27345c6129df7c8，已独立重算全部分布/时序。PGID666/811/948/1087/1228均空。keepalive session73427/PID590/start_ticks6815已按boot身份核验后终止且会话exit0、PID不存在。第一次库编译前检boot与编译不同，不以该前检声明隔离；之后unit和bench前检/执行均d2131159-199f-4795-9a65-cbd9846b0155。未来native入口必须复验boot与前检相同，不同则重做前检；库编译不构成性能证据。


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

spin v2已主审收口并完成下文0fsmugd1诊断：主会话去掉热路径仍存在的tuple，改为每组预分配slots并逐标量更新；CPython observe无BUILD_TUPLE/LIST/MAP字节码。新增前后时钟跨观测顺序检查。helper SHA d3115c140cc3b1fb2500d8fd7c78321c62a81bd2928dae00eb894e1334d3ec40，测试1f5c2741…，合并57passed/11subtests；私有提交ff389db，主仓库已同步这两个文件，receipt在validation/coordination/spin-v2-delivery-20260913。该版本实跑结果见下文；不得因旧检查点文字重复运行。

## G6与模型证据

主会话已在/root/wksim-first-step-diagonal-solve-20260913-01真实执行独立对角求解顺序实验：统一有限非零对角矩阵乘倒数，倒数非finite即回退原通用函数；原函数字节保留，不改正式模型。compile/run exit0，PGID669/678独立全空。候选首步240 major、13映射态及4级导数/末态、5次solve均与参考run05逐位相同；人工对照和自动比对一致。trace SHA5e89b720dac275a4980df1881aae2dfde76d223ad9a0bc8dbeba15edaa1e1d09，exe2b867710633e713db60c275fbbb1f356bd3c3c606d0162bae3252853cc251fb0。原archive/输入/builder/recorder/配方5项运行后SHA不变；证据g6-diagonal-solve-candidate-20260913，详见docs/2026-09-13-diagonal-solve-experiment.md。原件和正式模型未替换，不能据首步成功关闭R1/G6。

基础观测：目标trace03与参考run05的5次实际分子/矩阵全等，仅seq2 q结果差1ULP；参考实际连接穿过SubSystem/Reshape到Product2，Inputs=*/、Matrix(*)，2输入(1x3/3x3)、1输出(1x3)。参考run04在Reshape正确unavailable后补单输入/输出穿越；run05成功5条无丢弃，两次exit0/PID25320、71816退出无残留，37个使用冻结输入及源前后不变，240major和72积分器事件与run03完全相同。reference05 SHA72ff7d8eaeee7854bf026d19a7ee37f38c061764ce5369d0dd5845b1aa084c62；probe eb485804…，resolver d87e61d7…；完整证据见g6-reference-probe-20260913和docs/2026-09-13-first-step-solve-boundary.md。两次MATLAB不再运行。

比对器v3经主审补畸形容器、缺字段、端口数、bool冒充序号/时间、disabled optional兼容；30测试+8subtests通过。工具SHA569742b6a5c8219404441e8c34dbfddc7de27b5f7836f9c603368bbc90f0a632，测试75d5205ed2e4062e8c7e5971b7a29236397f69ed20c4cf98580a226e00b9e0d6。candidate comparator-result-v2与v1语义相同，差异列表为空；aligned只表示可对齐。旧main-review-v1中的未使用PostOutputs.derivatives dtype负例已由v2更正，真实使用的PostDerivatives坏dtype拒绝；历史报告保留。

另做同源边界核查：固定11.0与已生成11.8的实际mrdivide函数体1046字节完全相同，SHA7e0be87b4e760028fbd191e6be1011a67da749e6791f0b1ea06d0d63460dfcf9，见g6-solve-same-source-20260913/source-comparison-v2.json（v1误取前置声明已作废，不保留厂商正文）。复用既有11.8 C0 major和normal C0作纯离线60120值诊断，仍有Sensor30[10]在k153/k181两差异，无模型重跑，无预算赋值/改判；existing-c0-observation.json及脚本保留。不要追求旧R1全部零差异来代替Full真实要求；#59同源逐量物理预算仍缺依据，正式入口不得绕过。旧R1仍5684失败。

#26 current-wrapper-01仍为已完成4x1000/1ms冷重建/reset、480000值精确相同；wrapper150ddf3b…/library528db324…，docs/2026-09-12-current-wrapper-lifecycle.md。#9 DLL接口仍缺厂商C原型/所有权/授权样本，环境合同已批准不等于DLL ABI获证；#73/#74/#76/#77/#78不可按ready标签猜接口执行。#102仍依赖#29/#33和真实公开绕障闭环，#62失败后#63/#64未解锁；当前并未全局blocked。

## 运行资源与必须保持的规则

- 当前冻结组合：AP /root/wksim-ap-mixed-fhuf05l9/mixed-build.json SHA1e6250ef…；Control /root/wksim-joint-control-c2IXOr/build.json SHA6fe8c0b3…；Message /root/wksim-ros2-Rzj3Pf/message-build.json SHA29969da0…。完整SHA和精确命令见当前final-combo合同及最近launch.sh。ZlTVa4是旧构建，已失配8份当前支持模块。
- 保持固定PX4 /root/wksim-px4-state-ONa1Kw/wksim-build.json（d7e905b3…）与本场模型库e59ab914…的原准入链；不要给PV/MIXED传PX4 override。两native参数必须同时启用。
- 新native前分别完成并检查两WSL进程扫描，再在另一调用启动；收口/暂停重负载代理，并以read确认终态。禁止终止用户进程或改全局内核/调度。当前无native活跃，最近31209/19042/46644均终态，不再poll/restart这些场。
- WSL空闲连接保持进程session12541/PID605已按15分钟到期exit0并读回终态，不是活跃任务；无需再次取消。保留历史身份boot a295410e-b29d-4d4a-aadb-9bf16f4652df/start_ticks336。
- 使用干净env；ROS离线审计需要/opt/ros/humble、DDS、AP消息与Rzj3Pf环境。Bash脚本用Python写入并清除CR；不要重犯PowerShell管道在末行追加CR。
- 已通过飞行不重跑。审计变化复核原件，保留失败报告，全部原AC证明后才关闭对应票；#33/#84/Full仍未完成，Goal不可complete。只精确git add，禁止发布厂商源码或.so。

## 仍待用户确认的恢复操作

用户指定卡死任务34386db2-17a1-425b-a102-f910451c5c63：原受管DSH日志turn10缺turn/end，已备份且停止确认无其它活跃任务的受管PID58652；用户独立DeepSeek桌面PID31408未动。适配器仍缓存故障和会话cookie，手动起同端口不能假定可恢复。重启Codex应用的确认尚未收到，不执行C:/Users/PC/.codex/repair-backups/ds-b-stuck-20260912/restart-codex-after-approval.ps1，不补写turn/end或Goal数据库。若用户明确批准，先重新核验进程身份再操作；不要重复提问。
