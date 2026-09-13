# 当前 Goal 执行检查点

2026-09-13。Goal active，createdAt=1789219780；Full/G0–G6原范围和原AC不变。上一轮与本轮均有真实运行、代码修复和新证据，不是全局blocked。历史明细保留于[8f726ca检查点](https://github.com/unununnnn/wksim/blob/8f726ca/docs/coordination/short-cycle-goal.md)，本页只描述当前状态。

## 工作区与所有权

- 主仓库：C:/Users/PC/Documents/odid编译/wksim，分支codex/independent-rgb-integration，remote unununnnn/wksim。大量controller/runtime/UE/rover他方修改保留，禁止git add全库或覆盖。
- 主会话独占native、正式profile/catalog和joint_profile.py接线。Linux执行检出：Ubuntu-22.04 /root/wksim-release-acceptance-fe3，分支codex/planner-release-validation；第二发行版RflySim-20.04。
- Windows tools/run_joint_flight.py属于其它工作；实验runner只在上述Linux检出修改，并保留实际源SHA快照。最新主仓库joint_profile.py修复尚未同步到该Linux检出。
- 队列JSON是交接记录，不是后台自动调度程序。先读精确thread终态再续派；THREAD_BUSY不算送达，cancel ack不算终态。

## 当前运行与模块负责人

当前5个外部执行端为3 DeepSeek、Claude、OMP。codebuddy三席均429结束，重置提示2026-09-13 20:54:20 JST；不把它们计入活跃数量，也不循环重试。根Goal仍active，三分钟heartbeat保持PAUSED。

| 负责人 | thread / turn | 当前交付 |
| --- | --- | --- |
| DS-1 | 45decda4-b315-42b3-b7da-2b724dabfd4f / 05d6825f-f7af-4058-a707-8ce06d96acaf | 核验同源11.8 major的sensor_time/gps_time单位与表达链 |
| DS-2 | e2a62dda-d7fa-43f0-bfdb-c62eb13ac86c / 425d33b6-1464-4c64-8084-83d110068b0a | 退役错误的重复调度读取器，修正源码路径与实际运行的界限 |
| DS-3 | 7849b551-87ef-4dd7-8322-cd7e72ea241d / 955fa6c5-c75f-4aaf-a729-c2ffecc3fd68 | 独立复核11.8 major vehicle_time绑定 |
| Claude | e64514a6-77c2-4b27-91a7-896c92a361fd / 73f6801a-7122-4fba-b71e-37ef3dbe627f | 复用已有调度捕获工具，准备诊断runner接线与生命周期验证 |
| OMP | 51609e8d-e4ce-4a8e-8a0d-f7c896c24842 / 63da7482-132b-4937-a2f6-45a47f069ba6 | 独立核对PX4编译/启动覆盖和自有线程快照方案 |

最新接线检查点：validation/coordination/last-callbacks-run-20260913-01/checkpoint.json。快照runner v1/v2因boot/取消/元数据及成功路径手工模型拆除问题被拒；v3(1c600d7f…)通过主会话WSL Python3.10的16项测试及DS真实控制流复核。私有parent已暂存7855409d…，runner已暂存1c600d7f…，helper为a3f3badd…；主仓库parent仍a8bac9ac…，Windows runner他方修改保留。旧private08e20642/a8仅为历史基线，不再是当前私有字节。OMP最新审查turn91a6f251仍running，定点wait超时不算完成或卡死。当前无飞行、无keeper；待最终审查及两WSL新前检后才启动。

现有helper已对主会话自身/短命子进程实测，并对仅自有短命FIFO1子进程验证非零RT字段（stat.policy=1、rt_priority=1与系统调用一致），全部已退出，不改全局/他方设置。G6三时间量主审直接读取已钉f64：三参考首列product501/501、division429/501，输出分别vehicle72处、sensor/GPS61处与division形式不同；已以1de316d推送，预算与物理结论未改。作者此前参考版本/索引/首列描述错误已纠正，不能凭旧绿色报告跳过来源解码。

实时接续句柄与交付范围以validation/coordination/next-native-observation-20260913-01/dispatches.json为准。模块负责人负责内部测试/修复；交付稳定SHA后独立复核、批量集成。审计器5项缺口已修复，主会话独立反例7/7符合预期、20份交付哈希一致，5165781已推送；旧错误报告明确被v2替代。G6严格hex/目标序号修复经过52项作者检查及10项独立复核、15个输入/源码/回放哈希复验，13cf154已推送。aligned仍仅表示结构对齐，不能忽略numerator_equal/matrix_equal或据此宣称G6通过。

已推送ffb48b5、c1bfd42：准入独立测试与证据包10项检查、计时记录器/producer/独立对抗53项合并检查全部通过。G6合同已纠正旧“入口不存在”说法，当前缺口仍为有依据且approved的逐量预算。

最新无探针MIXED l6bxh4tn失败：epoch26acf41ac8904593a93427d530e59879，tick28604，迟到104381463ns，wall112.660268145s，未起飞。7141组、12工作超额组；工作超额合计18492055ns，start22420单次释放超额61209261ns，待独立定位，不能归因OS或缓存编码器。无诊断标记，source_unchanged=true，cleanup_errors=[]；同boot9f076946-7482-45bb-9188-a75badaa1958下PGID2210–2219独立全空。Keeper683/start147141按身份核验后SIGTERM且session69716终态；flight session31296终态，禁止再poll/restart这两个句柄。

本场唯一运行候选是worker.py缓存JSONEncoder：原0becd1f3…→38f34a8f…；主仓库与私有检出已接线，真实worker协议/日志测试Windows和WSL各18项通过，OMP实际WSL3.10等价6项通过。微基准不是整场收益；失败场保持failed。私有joint.py/runner已恢复为诊断前f5433c2e…/f5411627…，rate/probe保持0b53a16a…/a8bac9ac…。拒绝的追赶投影没有接入。下一步基于61ms区间证据选择改动，不盲重跑同配置；全部原门及已通过PV保持。

父探针诊断uy9ov56b已真实完成并失败：epochbf067fd133454585a0c2c62e9e2bcfb4，tick90132，wall232.496016401s，RateUnmet100116315ns。22523完整组及22524父探针记录（末次未成功begin单独报告）；无spin/census。源码未变、cleanup_errors=[]，同boot9150ec13-5eb1-44e4-ab9e-152e451dfb9b下PGID2086–2095独立全空。Keeper598/start337身份核验后SIGTERM，session20574终态；flight session67260终态，禁止重poll/restart。私有runner现08e20642…（父探针内存deque仅留最新1，完整JSONL保留），worker38f34a8f…、parenta8bac9ac…和rate0b53a16a…保持。Windows tools/run_joint_flight.py未改。

本场started转移分区已由主会话独立核算：priorwork35935249ns、outside_begin3094328ns、initial_health3153715ns、remaining_begin57609467ns；这是释放超额区间，不是总等待时间或OS归因。最大单次释放超额12877513ns@17852，其中12593632ns来自前组工作。本场未重现61ms间隔。末次未开始尝试跨沿197487ns后触发，不能伪造成完成start。分析器在补流序拒绝，当前数字不等于其所有解析路径已验收。

回调候选v2(7855409d…)已修复同组“先成功后失败”混配时间戳问题，独立旧/新实证与WSL Python3.10检查通过；OMP消费者v2(e6e7399b…)和真实生产者10新行+3旧行回放全部通过，cd876e7/db85c24已推送。它尚未施加到运行时：主/私有parent仍a8bac9ac…，私有runner仍08e20642…。已完成的流序分析器及G6有限范围时间算术以6b84e55推送；11.8 major时间绑定正在独立复核，不把11.0 runtime post-step前提直接套用。

PX4冻结源码存在98/99优先级线程创建路径，高于manager FIFO50；尚未证明本场实际线程/回退路径，不能据此归因。B新写的snapshot_reader存在stat索引及身份校验问题，禁止使用，正在退役；复用现有tools/capture_owned_scheduling.py，准备仅在计时前及拆除资源前读取自有PID/TID。所有调度/亲和性/内核参数未改。RT预算950000/1000000的收据仅属于另一空闲boot，不能说明历史飞行有无节流。下一实跑待回调与调度快照接线验收、重负载停止、双WSL前检完成；不盲重跑、不重跑已过PV。

新计划仅准备复用已有sleep/loop-health前后读数的最后回调字段，无新增时钟读取/节拍算法/阈值变化；独立验证后再决定是否必要实跑。已过PV不重跑，所有诊断保持diagnostic_only。G6 token边界修复已以d21eae1推送，13项新/旧真实实现回归、18项原测试及17项候选身份核验通过，模型候选字节不变。

上一有界诊断rfw9nmbb仍保留：24661完整组、18超额/16详细报告/2显式丢弃，diagnostic_only且failed。其48个详细间隙全部在各自4tick组内，旧“16宏边界间隙”分析已被主审拒绝。源快照、失败原件和旧报告保留，不能把CPU与wall移位窗口差值称为精确离CPU时间。

## 已完成：#83

#83已CLOSED，#82已CLOSED。结果/修复/独立复核已推送至f6239b7：
- run joint-public-flight-1w6dru32，epoch a160e99bb6ac46b4a09f0b36b3daeed7，runner与完整raw PV审计PASS，无计时探针。
- tick116004，最坏迟到89299145ns；27493个10s、21245个60s完整滑窗与两栈两段各12001个1ms参考样本全部通过原门；PGID2060–2069独立全空。
- 原件在Linux validation/joint-public-flight-1w6dru32；选取包validation/33-final-combo-luna/pv-settle-1w6dru32。audit-v2 SHA8140d80e5695bb377dedaef7198cb67811456a2429bab005085b2a5926f0e8c4；全部302输入SHA另复核。
- 详见docs/2026-09-13-final-combo-pv-pass.md。v1因重复status失败保留；v2复用原mixed严格规则核验两条完整解码字段相同的状态，保留事件及真实负例。没有重跑PV，也没有改旧原件。
- Task的fresh/估计速度≤.4入场余量已实跑；原2s/.5m/s保持及全部物理门保留。

## 当前#84阻断与下一步

本轮直接CPython扩展已真实编译/31接口检查通过；四模式每轮4000记录的两轮微基准均完成。默认20vCPU：Python返回中位145ns/累计2.435002ms，direct531.5ns/3.398046ms；仅基准线程vCPU0：Python158ns/3.776265ms，direct530ns/3.949961ms。后轮不同boot，不归因CPU固定；不改系统/用户进程。8000原始行已独立重算，仍未显示采用收益，因此停止扩展等待层，不接生产。详见docs/2026-09-13-direct-release-wait-evaluation.md。扩展SHA4d2314c37c7504bb1c98bce8fdafb2e9eeb9b79460abf40dc80f8374fdb4bfe1；私有/root/wksim-release-extension-bench-20260913-01/-02，PGID848/971/1096/752全空。keepalive session78702已结束，旧PID688/start426属8927adab boot；后轮408e35b0，不对新boot同号PID发信号。启动器现实际强制两前检found=[]/同boot/≤60秒，再Popen；不靠文字承诺。

原失败oxv29042由OMP纯标准库全量读取495410行wire分析；7个work>8ms组，总超额15139984ns，主会话从已封存rate.gz独立重算32930组完全一致。最大start_tick127940/work13140957ns。native输入等待与tick间区域各有主导组，边界offset宽436151ns；错误tick对齐两种均空集。原启动脚本显式unset WKSIM_JOINT_CPU_TIMING，三类CPU诊断记录均0，不能从原件再拆CPU阶段。v1/v2报告与脚本在mixed-work-overrun-20260913，详见相应文档。不把残余归因OS，不用固定历史tick触发未来诊断。

主会话已加正式_mixed_proofs必需joint_rate.py与joint_rate_probe.py源键，并拒绝rate_timing_probe/group_work_timing任一标记（不论值）。完整真实函数fixture Linux18tests/8subtests通过；Windows既有symlink权限限制保留。实际PV result.json.gz的两pacer源与raw-pv-audit-v2封存匹配，原pass有效历史不改；mixed仍failed，正式evidence仍空。joint_profile最新改动尚未同步私有Linux检出。源码/测试/核验见pacer-proof-binding-review及本轮main-verification.json。


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
