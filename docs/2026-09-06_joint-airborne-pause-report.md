# 联合空中暂停诊断、暂停时钟重发与连续飞行回归

状态：取得真实空中冻结和零额外步停止证据，修正暂停末次时钟无法补达的接缝；**完整暂停/恢复、#8/#19/#20/G2/Full 尚未验收**。原生墙钟新鲜度仍会在物理冻结后撤销控制，待用户确认[暂停与异常恢复提案](2026-09-06_joint-pause-contract-proposal.md)，没有把提案中的监督数值当作已批准值。

报告完成后的用户答复：首期墙钟监督值已经单独[获批准](2026-09-06_joint-wall-supervision-accepted.md)；任务暂停/恢复语义问题仍待答复。以下实测保持原实验结果，不追溯改为生产参数验收。

## 主要结果

- AP/PX4 均经自己的安装 Prometheus 控制节点正常预检、普通解锁并进入共同位置控制。观察器只订阅原始 DDS，不代发模式、解锁、起飞或航点命令。
- 最终暂停候选在共同 tick **51732**、两机真实高度 **2.960/2.798m** 时冻结 **4.001s 墙钟**。两个真实模型的完整状态快照相同，暂停及停止新增 **0 个模型步**，模型、FC、Control 均退出 0。
- 暂停期间向同一 `/clock` 重发 **40 次相同的 51.732s**。所有重发均关联原 epoch/tick、独立记录墙钟和发布计数；没有改原始时间戳或新增模型步。68,293 条原始 DDS 消息、模型输入/输出、发布记录及当前实际源码的审计通过。
- 两个 Control 仍分别在暂停后约 **1.872/1.995s** 以 `native_state_stale` 撤销控制，两个 Task 退出 1。暂停诊断结果为 `observed`、`flight_completed=false`；任务未降落，不能算完整飞行或 G2 通过。
- 随后的正常连续公共任务回归完成 **69,224 个共同 tick**、同飞 **13.914 仿真秒**、69,225 次时钟发布；两机各六条公共输入，起飞/驻留/航点/降落和正常退出、当前源码/原始数据审计通过。

## 发现与改动

[诊断入口](../tools/joint_pause_probe.py)由现有 [run_joint_flight](../tools/run_joint_flight.py) 的显式 `--pause-probe` 启用。暂停门要求同一实验和正确嵌套载具身份、当前真实状态、双机已接管且真实高度超过 2.5m，以及完整的 4ms 输入屏障。四秒只是预先固定的观察窗口，不是生产超时、许可有效期或动力学误差预算。

首次运行直接显示了新鲜度冲突：即便模型冻结、通信线程还在，源状态不再推进仍会触发原有 2s 规则。AP/PX4 分别约 1.538/1.994s 撤销控制；AP 的部分必需状态在冻结开始前已经有一定年龄，不能把“暂停后多久”直接等同于状态超时配置。原生位置/保活输出在撤销前仍出现一段时间，具体次数和最后接收时间保留在审计中。

第二次运行触发时钟一致性失败：两模型及发布记录已到 tick 51440，原始观察端最后只有 51439。旧 `/clock` 使用 volatile/best-effort，最后一条消息没有补发机会。该次没有保存暂停前后完整快照的缺口也保留，不事后补造为成功证据。观察工具现会在一致性校验失败时保存具体比较项和快照。

[ClockPublisher](../Simulator/wksim_runtime/scene_clock.py)增加严格的暂停边界重发：必须是同一 epoch、同一已提交 tick、无待完成模型步、完整且同步的输入屏障、当前 phase 为 paused。运行中同 tick 重发、旧 epoch、故障状态及不完整屏障仍拒绝。总发布次数与暂停重发次数分别计数；没有新增物理时钟来源。

新路径先在真实 Humble 晚加入消费者上复现旧实现失败，再通过修正后的同一测试：消费者从未收到暂停前的 volatile 样本，补发后读到准确 4ms，SceneClock 的整个快照不变。它验证真实 ROS 接缝；测试里的状态数据不是飞控或动力学验收证据，双飞控证据由真实场景另列。

最终 `--pause-probe --repeat-paused-clock` 使用每 100ms 重发已提交冻结时间的限定候选。这个实验频率不等于批准了提案中的生命周期许可、任务暂停或任何生产监督参数。Control、Task 和两个飞控的健康/新鲜度检查没有改变。

## 运行及失败样本

| 目录 | 结果 | 边界 |
|---|---|---|
| `joint-public-flight-_e9clfj2` | 暂停观察及当时当前源码审计通过 | tick51504；两任务因新鲜度失败；零额外步停止；没有恢复/降落 |
| `joint-public-flight-q39twwxw` | failed，保留 | tick51440；观察端最后只到51439；没有宣称暂停时间一致，模型清理为受控TERM |
| `joint-public-flight-l_lgyxx0` | 最终暂停观察/当前源码审计通过 | tick51732；40次同时间重发；两任务仍失败，未做恢复/降落 |
| `joint-public-flight-6kgq2i49` | 正常连续任务/当前源码审计通过 | tick69224；同飞13.914s；实际完成降落和正常退出 |

暂停审计：[最终结果](../validation/joint-public-flight-l_lgyxx0/pause-audit.json)。连续回归：[原始数据审计](../validation/joint-public-flight-6kgq2i49/audit.json)。连续回归的 AP/PX4 航点驻留最大真实位置误差为 0.18923/0.48244m，仍使用原先 0.5m 任务门槛；这个数值不是 G6 动力学等价预算。

[集成记录](../validation/joint-pause-integration-20260906/integration.json)重新读取内核进程组，四次场景共 **40 个自建进程组无残留**；原 AP PID828、PGID828、start_ticks19268 不变。异常样本的退出码逐一保留。没有操作真实硬件、UE/P450 资产或厂商原安装，没有推送混合工作区。

## 版本、验证与复现

沿用已封存的 AP `/root/wksim-ap-clock-stop-OXQqdR`：清单 SHA256 `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a`，固件 `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de`。Control `/root/wksim-joint-control-I4sbJN` 清单 `3b0bca977f9d2775a5f9ddbacd8c29e76e8ebf63b2c9682f339ea8f458bfe4d3`；PX4 固件仍为 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`。这些候选和默认生产准入没有被本次修改。每次记录自身实际执行源码、模型构建、候选清单、启动命令和哈希。

- [13 项针对性检查](../validation/joint-pause-integration-20260906/targeted-tests.log)全部通过：场景请求/屏障/旧代次、真实ROS时钟和唯一所有者、暂停重发、诊断身份/源状态时效等。[修正前负对照](../validation/joint-pause-integration-20260906/paused-clock-negative.log)保留真实失败。
- [证据负向检查](../validation/joint-pause-integration-20260906/audit-and-negative.log)3 项通过：拒绝将 observed 认作完整飞行、拒绝停机额外一步、拒绝被后续正常时钟掩盖的短暂伪造时间。只改独立证据副本，原运行记录未变。
- [既有产品矩阵](../validation/session-product-checks-tHF4HeM0/session-tests.log)274 项，跳过14项，其余通过；[旧版准入](../validation/session-product-checks-tHF4HeM0/legacy-preflight-tests.log)10项通过。真实 ROS 新测试已在前述13项显式环境运行；其他条件跳过仍保留，不计为通过。

在 Ubuntu-22.04/root、仓库 wksim 目录执行本次暂停候选：

```bash
bash tools/run-joint-flight.sh \
  --ap-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a \
  --control-manifest /root/wksim-joint-control-I4sbJN/build.json \
  --control-sha256 3b0bca977f9d2775a5f9ddbacd8c29e76e8ebf63b2c9682f339ea8f458bfe4d3 \
  --pause-probe --repeat-paused-clock
```

去掉最后两个选项即为本次运行的连续公共任务回归命令。审计在相同 Humble/消息 overlay 环境使用：

```bash
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
python3 -B tools/audit_joint_pause.py validation/joint-public-flight-l_lgyxx0 --verify-current-sources
python3 -B tools/audit_joint_flight.py validation/joint-public-flight-6kgq2i49 --verify-current-sources
python3 -B validation/joint-pause-integration-20260906/check_audit_rejections.py validation/joint-public-flight-l_lgyxx0
python3 -B validation/joint-pause-integration-20260906/integrate.py
```

## 下一门槛

已提交用户确认的问题是：有许可的用户暂停是否保留任务/驻留，而真实异常冻结撤销任务且需新请求恢复；以及许可100ms/500ms、原生新鲜度2s、模型RPC3s、输入屏障/恢复等待5s等候选监督值。尚未收到确认，不能替用户定为生产契约。

#19 原生阻塞仍为已关闭 #12/#14 和开放 #8；#20 原生阻塞仍为开放 #19/#8。没有修改或关闭 Wayfinder 父图，也没有重新创建38张票据。任务暂停/显式继续、异常/掉队处理、倍速、正式联合配置/UI和UE查看、环境/碰撞、MATLAB、DLL/Full、硬件条件及G6预算仍按原计划推进；本诊断不缩减任何终态义务。

Codebase Memory 实读可用数据库仍为600527节点/712312边；本次核心和测试路径是 metadata_changed/not_tracked，tools按规则排除。工作采用已知源码直接读取及真实运行SHA，没有进行依赖新改动的结构查询，没有为报告重复全库索引；此前索引/持久化失败未被宣称解决。[索引证据](../validation/joint-pause-integration-20260906/index-state.json)。本次由主代理执行，没有新建或恢复子代理。
