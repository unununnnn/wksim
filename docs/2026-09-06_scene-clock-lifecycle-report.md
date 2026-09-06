# 联合场景核心时钟、ROS 时间与冷重建验证

状态：核心模块已实现，并通过真实 PX4/AP 的地面生命周期验证；**不是联合飞行任务、完整冷重置产品入口或 G2 完成**。沿用[用户批准的原则](2026-09-06_recommended-decisions-accepted.md)与[已构建 AP 修正候选](2026-09-06_ap-clock-stop-candidate-report.md)，不改变默认生产准入或原安装。

## 新增的核心实现

- [worker.py](../Simulator/wksim_core/worker.py)：每个 OS 进程仅一个生成模型生命周期；复用已有 `Model`。协议携带 version/epoch/tick，严格验证下一步、16 个有限归一化输入、字段、重复键、帧大小和响应。snapshot 不隐式推进；异常通道不能重试复用。Linux 非阻塞管道约束完整 RPC 的截止时间，不为每个 1ms 调用创建新线程。
- [scene_clock.py](../Simulator/wksim_runtime/scene_clock.py)：一个 `SceneClock` 作为两模型的整数 tick 权威；只有两份同 epoch、同 tick、时间字段匹配的模型回应才能提交。4ms 输入屏障未完成时不能进入下一段；暂停/四步单步/继续/停止受状态和递增请求身份约束。旧 epoch 请求不改变新实例。
- 同文件 `ClockPublisher` 使用真实 ROS `rosgraph_msgs/Clock`，以实际 ROS context 的 domain 和 Linux 私有网络内抽象 socket 保证协作式唯一所有者，并拒绝已发现的其他 `/clock` 发布者。发布从 0 开始且不跳过/倒退 tick，不允许未提交状态或未退场 epoch 跨越。
- [现有有界双飞控入口](../tools/probe_joint_clock.py)增加显式 `--scene-clock`、`--cold-reset-once`，实际使用上述核心模块。[观察器](../tools/scene_clock_observer.py)创建真实 `use_sim_time=true` ROS 节点，读其 `get_clock()`；正常物理推进不等待该消费端。显示、任务控制和飞行命令没有由观察器代发。

这不是把两个独立 `serve` 循环事后对齐，也不修改已经收到的原生时间戳。生命周期请求目前在受控运行器内调用核心方法，尚未接入完整产品 CLI/UI 协议。实际 `Task`/`MissionTask`、ControlNode 的超时、状态新鲜度和稳态控制定时器保持原样，未借发布 `/clock` 就宣称任务时钟已迁移。

## 已预定的验证边界

本轮沿用每模型 1ms 子步、4ms 输入屏障、8000 tick 暂停、四步单步、再次暂停及再走 2000 步的固定实验。暂停各超过两墙钟秒；模型 RPC 3s、飞控输入等待 5s、总实验 90s 是本轮验证上界，不是已获用户批准的生产失联参数或 G6 数值预算。FC speedup 参数仍为原值3，未据此声称实际墙钟倍率达到3。

模型响应不完整/错误会使权威时钟 faulted，不假装两个进程已经回滚。此基础对象不允许直接 resume fault；**正式掉队/重连后的恢复路径仍待实现和确认**，不能把“所有异常一律只准 cold reset”冒充已定 Full 策略。

## 真实运行结果

所有运行均为新建私有 net/ipc/mount 和 `/dev/shm` 内的真实 AP、PX4、两个 Agent、两个真实模型进程。ROS 观察/时钟三个节点位于主进程，无任务控制节点，始终检查未解锁与零电机输入。

| 证据目录 | 结果 | 说明 |
|---|---|---|
| `joint-scene-clock-u37_xl0y` | failed | 完成物理循环后，报告调用了不存在的 Humble `get_subscription_names_and_types_by_node`；改为实际 `get_subscriber_names_and_types_by_node`，并补真实 ROS 回归。失败不改写为通过。 |
| `joint-scene-clock-p_gab4ai` | pass | 首个完整单轮；随后同一进程尝试冷重建。 |
| `joint-scene-clock-gqcbrsgy` | failed | 冷重建在私有 TCP4581 重新 bind 时 Address already in use；未启动新 FC。补充监听端 `SO_REUSEADDR`，没有置换别人的监听器；新增实际连接退场/重新绑定测试。 |
| `joint-scene-clock-hwdlxd05` | pass | 修正后的冷重建第一轮。 |
| `joint-scene-clock-st9tq0yx` | pass | 第一轮完整退场后构造新 epoch 的第二轮；旧场景 stop 请求被拒绝。 |

最后一对运行的[第一轮审计](../validation/joint-scene-clock-hwdlxd05/audit.json)、[第二轮审计](../validation/joint-scene-clock-st9tq0yx/audit.json)均核对当前源码、快照、原始模型输入/真值、AP/PX4 数据包、原生 CDR 及 ROS 时间记录。

| 项目 | 第一轮 | 冷重建后 |
|---|---:|---:|
| 模型 tick（两模型各自） | 10004 | 10004 |
| 4ms 输入屏障 | 2501 | 2501 |
| 严格 PX4 屏障 / 起始 tick | 2488 / 56 | 2489 / 52 |
| `/clock` 发布次数（含初始0） | 10005 | 10005 |
| 真实 ROS 消费到的不同时间值 | 9239 | 9134 |
| 最后 ROS 时间 ns | 10004000000 | 10004000000 |
| AP 原生微秒样本 | 402，全在1ms网格 | 403，全在1ms网格 |
| PX4 原生微秒样本 | 476，全在1ms网格 | 477，全在1ms网格 |
| 两次暂停墙钟秒 | 2.01727 / 2.01775 | 2.01792 / 2.01822 |
| 实验墙钟秒（含准入/清理） | 33.15985 | 26.83099 |

两次都只有一个 `/clock` 发布者，第二个协作式所有者被原子拒绝；真实 ROS 消费时间在暂停期间不变，单步只走四个模型 tick，继续没有补发历史场景动作，停止保持 tick10004。ROS 消费是允许丢中间样本的实时读取，不要求每次发布都交付；记录没有用插值补齐。AP next-frame 仍只证明输入握手，不是新控制计算完成 ACK。

第一轮 epoch `1e661b84c4ab48618723c4e926feb707`，第二轮 `29563736ad7a44a29600ffede53dd9d3`。两个模型、两个 FC、两个 Agent 及 ROS context 全部退场后重新创建，不在存活模型上将计数器改零。冷重建关联见 [cold-reset.json](../validation/joint-scene-clock-st9tq0yx/cold-reset.json)。新实例从0开始、第一条模型步为1，拒绝旧 epoch 的生命周期请求；这尚不等于跨联合任务、UI客户端或全部原生队列的旧命令隔离验收。

## 回归与清理

- [15项针对性检查](../validation/scene-clock-integration-20260906/targeted-tests.log)全部通过：纯状态约束、实际 Humble 观察器/唯一所有者、真实 TCP 重绑、严格管道/部分行超时、两个独立真实模型、旧 epoch 和12种无额外步拒绝场景。真实模型测试不是模拟飞控证据，真实双FC运行另列在上表。
- [18项既有工具检查](../validation/scene-clock-integration-20260906/tool-tests.log)通过。[完整产品矩阵](../validation/session-product-checks-cFz8NUgm/session-tests.log)254项、跳过5项，其余通过；其中4项新 ROS/真实模型条件测试已由上述显式环境补跑，原有1项跳过仍保留。[旧版准入10项](../validation/session-product-checks-cFz8NUgm/legacy-preflight-tests.log)通过。
- 五次真实场景尝试共24个自建进程组，按实际内核PGID检查均无成员。成功运行的模型与FC均退出0；首次报告异常的两模型经受控TERM退出-15，未冒称正常EOF。原 AP PID828/PGID828/start_ticks19268 未改变。
- Franklin侧线仅写worker与其测试，显式gpt-6-astra/low并核验实际会话配置，无嵌套；主线调整了Linux管道实现并重新实测全部15项。侧线及复核模型测试的临时目录保留 `children.json`、trace、stderr；没有清理原厂资源、原UE或其他任务进程。

## Codebase Memory 状态

在后续依赖新增结构的查询前，MCP fast+persistence 刷新返回 Pipeline failed；按约定设置现有 CBM_CACHE_DIR/CBM_RUNTIME_DIR 的本地 CLI 重试，同样退出1/报错。数据库随后可读为600527节点/712312边，覆盖代次更新至2026-09-06T03:45:49Z；但仓库持久化 artifact 仍为2026-09-05T20:55:31Z、92892节点/202270边。这是**部分状态更新与总体失败并存**，不是一次已证成功的完整索引/持久化。

两核心文件和两测试文件的精确覆盖没有记录解析缺口，但 freshness=metadata_changed；观察工具仍按tools子树排除。完整记录见[index-state.json](../validation/scene-clock-integration-20260906/index-state.json)。没有因错误而删除旧库、修改全局权限或声称新结构查询已验证；当前实现依据实际源码和运行 SHA。持久化失败原因尚未定位，不能把 ready 等同于刷新成功。

## 复现与剩余项

在 Ubuntu-22.04/root、wksim 根目录执行：

```bash
bash tools/run-joint-clock-probe.sh --native-clocks --require-aligned-clocks \
  --scene-clock --cold-reset-once \
  --ap-build-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-build-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a
```

下一步仍需把这些核心接缝用于正式联合配置/启动、两载具 Prometheus 公共任务及任务虚拟时间，同时设计并实测暂停状态新鲜度、墙钟监督、倍速、迟到/掉队与显式恢复。现有任务暂停是释放控制且物理继续，不能替代本物理暂停；原ControlNode仍用稳态计时与原新鲜度规则，没有关闭健康检查来绕过差异。正式策略细节/#8及#19/#20验收继续开放。UE、空中DDS失联、MATLAB、插件/环境反馈、G6数值预算与全部Full扩展义务没有缩减。
