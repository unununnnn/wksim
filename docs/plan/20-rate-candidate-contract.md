# #61 — 1× 调度候选合同（2026-09-09）

本票交付 `rate61-linux-cpuset8-v1`：保持产品源码与倍率语义，使用 Linux `taskset -c 0-7` 固定本次自有联合服务及继承子进程的可运行 CPU 集。资源只读准入通过；候选尚未实飞、没有性能 PASS。#20、#33、G2、Full 和历史 RateUnmet 结论不变。

## 已测瓶颈与证据强度

实读指定的 `docs/2026-09-09-joint-step-acceptance-review.md`、`docs/2026-09-09-rate-release-check.md`、批准倍率合同及原始失败数据。离线重放使用真实 `JointRate` 注入原始单调时间，无墙钟等待或飞控，四场均重现原始失败值。表中时长从该 1× 段首组开始到末组完成，包含稳定期，**不是有效空中验收时长**。

| 原始 case | 1× 组数 / 段墙钟秒 | 已观察后继组的累计新增相位迟到 ms | 前组超期贡献 ms / 其余释放延迟 ms | 原始失败迟到 ns |
| --- | --- | --- | --- | --- |
| `joint-rate-flow-p9koy63e` | 7801 / 31.302175882 | 99.231475 | 25.554960 / 73.676515 | 100011792 |
| `joint-rate-flow-bwd4iwsc` | 11741 / 47.061388279 | 98.798914 | 18.594263 / 80.204651 | 100102022 |
| `joint-rate-flow-wy1_f8pu` | 10252 / 41.106674889 | 96.062778 | 31.818183 / 64.244595 | 100080057 |
| `joint-rate-flow-h7b729ld` | 5863 / 23.704128793 | 57.618669 | 22.148339 / 35.470330 | 252965151 |

分解公式为 `increment = next_start - start - 4ms`、`inside = max(0, end-start-4ms)`、`residual = increment-inside`。逐组验证 `increment >= inside`，不删除失败窗。它只对有后继已完成组的相邻记录求和；h7b729ld 的末组 **198.510124ms** 超时直接终止，没有后继，因此不包含在表的累计新增值，绝不能从 57.619ms 推出未越过100ms。

本次选定的可证实瓶颈是 **health/model 阶段失去监督线程 CPU 时间的长尾，阻塞同步四步组完成**。p9koy63e 的 tick 76833：

- 阶段 `health_and_models` 墙钟 **5,128,973ns**，监督线程 CPU **293,791ns**，差 **4,835,182ns**，单这一阶段已超过完整 4ms 组周期。
- 所属组 76832→76836 实际 **8,570,450ns**，比4ms超出 **4,570,450ns**；下一组新增相位迟到 **4,652,309ns**，其中额外释放开销 **81,859ns**。这是该1×段最大的相邻组迟到增量。
- 同 tick 的 encode/send 仅73,979ns（CPU67,048ns），native inputs 539,216ns（CPU497,894ns）。该段127个步骤采样及原始行号保存在证据包；采样条件是步骤>2ms或tick%250=0，不能当全量总体均值/分位数。其他三场未启用阶段采样，明确记为不可得，而非零耗时。

源码接缝为 `Simulator/wksim_core/joint.py:JointPhysics.advance` 从入口健康检查到 `receive_workers`、`clock.commit` 后首个计时标记；`Simulator/wksim_core/worker.py:receive_workers` 已先向全部 worker 发请求再收响应，不能再把“串行改并发”包装成新优化。上述两个文件和 `joint_rate.py` 与p9原运行封存副本逐字节相同，见 `checks-01/historical-source-identity.json`。

**归因边界：** 线程CPU差包含模型进程执行、IPC/文件等待、Linux/宿主调度及抢占。现有证据不能区分这些原因，不能证实“Windows中断”或“磁盘写入”是根因。释放残差也混合调用者工作、健康检查、等待及抢占。这里证明的是时间损失所在阶段与它对相位的影响，不是某个OS机制。CPU放置是针对该长尾的可证伪工程候选，改善仍待实测。

## 排除已知无收益方案

2026-09-09 timer-only 原/候选均1000组、最小起始间距8,000,000ns，原/候选最坏迟到1,161,983/1,928,489ns，CPU1.038121179/1.038547094秒。当前timer与该实验 `before.py` SHA256均为 `59e329db948802e545fa5167b2430ae18bf3bdb6e1c534a374a82dafcc70da6c`。本次没有重跑会覆盖旧结果的 `benchmark.py`，没有恢复已撤销改动。

也不将历史 nice/SCHED_FIFO 或 vmmemWSL=High 重做当成新收益证据。Linux既有优先级保持现状；本次没有设置Windows优先级或停止其他应用。历史恢复风暴的撤回归因遵循指定复核报告，不引入新重锚或恢复预算。

`timer-raw-check.json`另从两份原事件数组重新计算1000组的最小间距和最坏迟到，与原汇总相同。原after实现没有独立源码副本，旧脚本指向的产品路径已恢复；不声称能从当前文件重建当时after字节。

## 冻结候选身份与负载

权威机器可读清单为 `validation/20-rate-candidate-profile/candidate.json`，58个源码/配置SHA256（含实际运行器、独立审计入口和三份配置）；资源完整路径/二进制/源码树/消息/Agent哈希在 `checks-01/preflight.json`。仓库并发提交时以这些文件内容为准，不把最新HEAD当历史运行身份。冻结时HEAD为 `117cd58f048d592851b4aa471ce3c15f83fd0b82`。

| 项目 | 冻结值 |
| --- | --- |
| 主机 | Intel Core Ultra 7 265KF，20逻辑CPU；WSL Ubuntu-22.04，内核 `6.6.87.2-microsoft-standard-WSL2` |
| 新变量 | 自有运行树允许CPU从启动环境0–19收窄至0–7；启动前、地面就绪监督进程与各子进程读回亲和性 |
| 选择理由/限度 | 8个在线vCPU给两模型、双FC和DDS/控制服务保留并行空间，同时缩小迁移范围；这是事先固定的第一候选，不是搜索得到的最优CPU集合。不认为0–7是物理P核，也不声称独占这些CPU。 |
| 系统负载 | 一次一场双栈quad-X公共位置任务，ROS2/DDS；无UE/RGB、显示socket、CPU采样；hold=35、waypoint=35仿真秒；完整起飞/保持/航点/落地 |
| profile | `joint_quad_dds_v1`；Control `FVMjak`，AP clock-stop `OXQqdR`，PX4 state `ONa1Kw`；不选未具备P+V兼容性证据的mixed profile |
| AP / PX4固件SHA256 | `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de` / `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a` |
| 模型库SHA256 | `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`；现有生成quad-X，并非Hex或新的自主物理/G6证明 |
| 控制/调度代码 | 产品源码零修改；既有manager FIFO50、model/FC FIFO40和nice策略不变，实际值仍须从运行结果核对；RT runtime/period观测为950000/1000000µs |
| 额外宿主条件 | Windows背景负载不可由此脚本冻结；每场留存进程/负载/优先级快照。准入期间vmmemWSL PID46056 priority8仅是当时观察，不能跨VM重启沿用PID；不把它写成已实施High。 |

本次不修改生产调度、协议、固件或核心接口，因此不创建源码实现子票。若后续测量指向具体源码瓶颈，另建只含该源码范围的实现子票；不得在#62–#64运行票里临时改timer或进程放置。

## 不变预算

物理dt=1ms、双栈输入屏障=4tick；请求1×周期4ms（0.5×仍8ms）。`earliest=max(ideal,previous_actual_start+period)`不变；不追赶、不跳tick、不稀释传感器、不自动降档。累计迟到 **>100ms** 才触发原 `rate_unmet/resource_insufficient`，在最后完整屏障冻结并撤销控制；精确100ms按既有边界执行。

每档至少3独立epoch，每场至少60连续墙钟秒有效空中段；头2s稳定期不计有效段但仍执行100ms监督。全部完整不重叠10s窗口±2%，完整60s段±1%，并报告最坏相位与所有失败窗；不拼接暂停两侧、不混入地面。0.5×既有成功不自动覆盖本候选，若最终采用此宿主放置，须在原票的回归范围下核对受影响的0.5×与生命周期，不能用三场1×替代。

原生状态新鲜度2s、健康许可100ms/500ms、模型RPC3s、输入/恢复5s、接管/动力学/健康/RC合同不变。批准提案原件SHA256 `54dcd1df7d70caeb483ab101e7071f8d48168f29e22a93da594e455a459a02a5`，显式start-recovery-task附录不改变数值。

## 可执行命令与输出

以下PowerShell命令均从 `C:/Users/PC/Documents/odid编译/wksim` 运行。`--check`与`--preflight`已实际执行；去掉`--check`的完整实飞命令是后继票的一次运行，本票未执行。

```powershell
# 当前文件身份、Linux内核与实际CPU集，零飞行进程
wsl -d Ubuntu-22.04 -u root -- taskset -c 0-7 /usr/bin/python3 -B validation/20-rate-candidate-profile/run-one.py 1 --check

# #62唯一一次候选运行；内部先重新准入，然后正式服务 + steady驱动
wsl -d Ubuntu-22.04 -u root -- taskset -c 0-7 /usr/bin/python3 -B validation/20-rate-candidate-profile/run-one.py 1
```

第2、3场命令仅将最后编号分别改为2、3；固定配置分别为`experiment-2.json`、`experiment-3.json`。前场`audit.json`不是pass时拒绝下一场。每场具有独立固定新run_id、新`/root/wksim-rate61-cpu8-eN-e2561e27`持久目录，正式服务自行生成独立epoch。已存在证据目录或output-root即拒绝，失败不得覆盖或自动重试。

原始审计在同一WSL系统解释器下source以下实际消息覆盖层，保持原入口，不编辑旧flow来伪装成steady：

```bash
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-FVMjak/install/local_setup.bash
/usr/bin/python3 -B tools/audit_joint_rate.py validation/lunar-20-epoch-1/case --require-epochs 1 --output validation/lunar-20-epoch-1/audit.json
# 每场独立通过后才执行完整同候选cohort审计
/usr/bin/python3 -B tools/audit_joint_rate.py validation/lunar-20-epoch-1/case validation/lunar-20-epoch-2/case validation/lunar-20-epoch-3/case --require-epochs 3 --output validation/lunar-20-epoch-3/cohort-audit.json
```

审计文件放在`case/`外且必须新建；第2、3场单场命令同步替换两处编号，不能跳过单场审计直接只看cohort。旧`steady-one-after-ready`驱动可证明失败但当前审计明确只接受`flow.mode=steady`，故新候选从配置请求1×并完整steady执行。35s+35s提供连续空中窗口的机会，不保证飞行或窗口成立。

输出schema沿用已读原入口：`case/experiment.json`、`wrapper.py`、`wrapper.json`、`preflight.log`、`service.log`、`driver.log`、`flow.json`、`run/result.json`、`run/epochs/<epoch>/`完整原始truth/wire/rate/clock/CDR/来源快照/原生maps/清理结果。wrapper额外保存`candidate_id`、清单SHA、亲和性与进程身份读回；manager退出0不代表driver或审计通过。原始审计顶层`status=pass`且实际returncode0、单场及三场身份/物理/窗口/无残留全部成立才可作相应证明。

## 本票验证、原件与边界

`validation/20-rate-candidate-profile/analysis-02/`保存四场重放、逐组gzip结果、p9原始诊断行号、完整输入SHA；`checks-01/`保存逐命令argv/stdout/stderr/returncode和当前资源证明。`profile.py`的新输出目录必须不存在；复跑如改为`analysis-03`，不能覆盖历史结果。实际命令：

```powershell
python -B validation/20-rate-candidate-profile/profile.py --output validation/20-rate-candidate-profile/analysis-02 joint-rate-flow-p9koy63e joint-rate-flow-bwd4iwsc joint-rate-flow-wy1_f8pu joint-rate-flow-h7b729ld
wsl -d Ubuntu-22.04 -u root -- /usr/bin/python3 -B validation/20-rate-candidate-profile/check-delivery.py checks-01
```

实际结果：资源准入`ok=true`、`children_created=0`；12项timer边界测试通过、0跳过；错误CPU集/启用诊断/源码变更3个拒绝检查成立；真实旧日志重放返回1且失败100011792ns原值匹配。这些检查没有启动FC、模型或ROS节点。完整运行/清理异常路径尚未在实飞验证，后继票不得将本票检查称为飞行通过。

另以 `wsl -d Ubuntu-22.04 -u root -- /usr/bin/python3 -B validation/20-rate-candidate-profile/test_runner.py` 完成2项纯模拟失败边界：准入失败保留实际码/零子进程，前场审计失败拒绝后继。`runner-tests.json`保存命令、原输出与退出0；临时模拟文件由测试在自有临时目录清理。

原数百MB实飞日志继续本机只读保留，未整包推送；本次提交紧凑的逐组派生原数值、诊断行号、被引用的历史源码、哈希和命令。首次`analysis-01`未采样字段使用零值，`analysis-02`修正为null并压缩逐组输出；前者本地保留、不作为本结论。资料定位曾误用根目录`capability-index.json`（实际在`Simulator/wksim_runtime/`）以及Windows rg通配路径，均已纠正，无源码或实验改动；WSL localhost代理提示和ps终端尺寸提示原样保留，不作为性能故障。

候选若无收益/变差/RateUnmet/身份拒绝，保存原件，后继运行票保持OPEN、转needs-triage；不运行下一epoch、不暗换CPU或预算。R1仍numerical_failed，#33最终P+V失败未重判。#61完成仅意味着测量归因、候选冻结和入口交付满足本子票AC，不关闭父票。

实际执行主会话：本地匹配本任务ID的session `turn_context`记录 `model=gpt-6-astra`、`effort=high`，时间`2026-09-09T08:14:27.753Z`。仅导出该必要配置元数据；没有子代理。
