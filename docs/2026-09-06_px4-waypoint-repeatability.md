# PX4 waypoint 重复性离线审计（2026-09-06）

结论：首次实际失败项为 **MAVLink 估计位置误差 > 0.5 m**，超出 0.005596367 m；不是速度门槛，也不是驻留超时。第二次完整运行 pass，但不能据单次复跑宣布稳定性解决。两次均存在观测源时间错位；现有证据不能将失败归因于并行负载，亦不能把估计位置越界直接等同于真实动力学位置越界。

## 范围与证据身份

仅离线读取现有源码、result、telemetry、DDS 和 truth；仅新增本文。未修改代码、测试、阈值、飞控或配置，未启动 FC/ROS 节点或硬件，未写 GitHub。AP 时钟候选归档及后续联合调度属于主线，不在本审计内。已读根目录与 wksim 的 AGENTS、CONTEXT-MAP、相关 CONTEXT、domain 指引及本地决策记录；兄弟项目 ADR 不自动约束此迁移。

使用 diagnosing-bugs 技能的证据核算与可证伪假设方法；按本侧线的离线范围跳过新运行复现、修复和回归执行。主代理显式委派 gpt-6-astra/low 并从实际 turn_context 核验，本侧线未嵌套委派。

主线已执行的前置命令（本审计未重跑）：

```sh
WKSIM_CONTROL_PROTOCOL=session_v1 bash tools/run-prometheus-validation.sh px4 /root/wksim-dds-VxM6Ni /root/wksim-ros2-MUlZd0
```

下文 F = [px4-dds-gieop6c6](../validation/px4-dds-gieop6c6/result.json)，P = [px4-dds-jxvhi_jx](../validation/px4-dds-jxvhi_jx/result.json)。JSONL 行号从 1 起，result 以字段和事件名定位。

| 项目 | F | P |
|---|---|---|
| result.utc（UTC） | 2026-09-06T00:41:16Z | 2026-09-06T00:43:36Z |
| status / error | failed / Waypoint dwell thresholds failed | pass / 无 error |
| wall_seconds（含清理） | 25.157999246002873 | 47.44140279700514 |
| waypoint reached MAVLink 源时间 ms | 43624 | 49712 |
| dwell 终点 MAVLink 源时间 ms | 43920（失败） | 51712（通过） |

两份 result 的 `implementation_sha256` 映射与 `environment_overrides` 分别完全相同；FC commit 均为 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，记录的 FC binary SHA256 均为 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`。这是运行记录的一致性核对，未重新读取或启动 FC。固定 PX4 未在本审计中更改。

## 实际门槛与失败帧

[validate_sitl_physics.py](../tools/validate_sitl_physics.py) L373–385：`waypoint_reached()` 要求 MAVLink 到 NED `[3,2,-3]` 的三维距离 ≤0.5 m、三维速度模 ≤0.5 m/s，以及 DDS 位置距离 ≤0.5 m。首次满足即开始驻留；以 MAVLink `time_boot_ms` 累计 2000 ms，每次 `pump()` 后重新检查，一次失败即抛错，不等待重新收敛，也没有在此处独立检查 DDS 速度。

F 的 [telemetry.jsonl](../validation/px4-dds-gieop6c6/telemetry.jsonl) 最后五个 `LOCAL_POSITION_NED`：

| 行 | time_boot_ms | telemetry.wall（s） | 位置误差 m | 速度 m/s | 意义 |
|---|---:|---:|---:|---:|---|
| 3139 | 43520 | 24.764553212007740 | 0.384670885517 | 0.681543327614 | 速度未达入窗条件 |
| 3147 | 43624 | 24.817183187013143 | 0.441552609892 | 0.497170751274 | 开始驻留 |
| 3153 | 43720 | 24.868682701009675 | 0.477096099694 | 0.338690419386 | 合格 |
| 3163 | 43824 | 24.935235305005335 | 0.499190186076 | 0.181676737269 | 合格，距边界约 0.810 mm |
| 3169 | 43920 | 24.979617367003810 | 0.505596366759 | 0.063022418377 | 位置越界约 5.596 mm |

失败帧原始位置为 `[3.407252550125122, 2.2993366718292236, -2.9869384765625]`，速度为 `[0.05954962223768234, -0.011577960103750229, 0.017076842486858368]`。计算使用欧氏范数，未四舍五入后判定。驻留仅推进 `43920-43624=296 ms`；不是满足 2 s 后失败。最后 `pump()` 先处理 DDS 再接收该 MAVLink 帧，抛错后没有继续 pump。F 的 DDS 最后一条位置（L3711，源时间 69120000 µs）误差为 0.007007086476 m；从 reached 对应位置 L3686 到末尾共 25 个 DDS 位置样本最大误差 0.007566580359 m。因此实际导致返回 false 的是 MAVLink 位置项，且短路表达式在该项已停止。

P 的 [telemetry.jsonl](../validation/px4-dds-jxvhi_jx/telemetry.jsonl) L3328–3472 内共有 21 个位置样本，覆盖 49712–51712 ms；最大误差 0.463793688535 m（L3350，50016 ms），最大速度 0.439563918823 m/s（L3406，50816 ms）。result 的 `waypoint dwell passed` 终点为 51712 ms。该次通过仍只是一次运行的证据。

离线核算已实际在 PowerShell 以 `@'…'@ | python -` 执行：用 `ast.parse` 从实际源码提取唯一的 `waypoint_reached` 函数，`compile/exec` 该函数，向 `latest` 注入原始 MAVLink 样本，DDS 固定为对应 reached 事件的合格位置。输出 F 的 false 时间为 `[43920]`，P 为 `[]`；断言 F 仅此帧 false、P 全部合格且覆盖 2000 ms 均通过。另独立核算上述 DDS 窗口。此为**实际谓词的离线数据检查**，未复现每次回调交错，不是 controller replay，也不是重新运行飞控闭环。

## 时间轴与动力学证据的边界

[pump](../tools/validate_sitl_physics.py) L239–284 在开头读取 `now`，先 DDS pump / freshness，再至多取一条 MAVLink 消息；telemetry.wall 使用这个开头的 `now`，不是报文产生时间或严格的接收完成时间。`wait_for` 事件 wall 则在谓词满足后读取。[sitl_dds.py](../tools/sitl_dds.py) L63、110–115、201–204、241–250：DDS 有独立 `started`，wall 是回调记录相对时间；每次 pump 最多 spin 20 次；freshness 仅检查 position/status 回调距当前墙钟是否超过 2 s，不检查 MAVLink 新鲜度，也不保证两种源时间一致。snapshot 保存 status 时间，但未保存 position 时间，后者须回查 raw DDS。

| reached 事件 | F | P |
|---|---:|---:|
| result 事件 wall s | 24.818612546005170 | 29.220448938998743 |
| MAVLink time_boot_ms | 43624 | 49712 |
| DDS status.timestamp / 1000，ms | 68596 | 80976 |
| 同事件 position 在 raw DDS 的行 | 3686 | 4346 |
| 该 position.timestamp / 1000，ms | 68640 | 81048 |
| 该 position 的 DDS wall s | 23.852785675990162 | 28.088624336000066 |
| status 源时间减 MAVLink 源时间，ms | 24972 | 31264 |
| position 源时间减 MAVLink 源时间，ms | 25016 | 31336 |

不能直接相减两个文件的 wall 来算传输时延：起点不同，且采样时机也不同，日志未保存起点差的精确值。上表源时间差也不等于墙钟延迟。P 的源时间错位更大，仍 pass，所以“有错位”不足以单独解释这一次失败。

F 的 [dds.jsonl](../validation/px4-dds-gieop6c6/dds.jsonl) L2355 在 DDS wall `15.612749981999514` 已记录 `timestamp=timestamp_sample=43920000 µs`，位置与之后 MAVLink L3169 **逐值相同**，误差同为 0.505596366759 m。F 到末尾 DDS 已到 69.120 s，MAVLink 只处理到 43.920 s；这支持旧 MAVLink 状态被较晚消费/记录，而非两个估计值在同一源时刻互相矛盾。尚无发送端、socket/parser 队列或调度跟踪，不能定位积压于发布、传输或消费中的哪一段。

独立 [truth F](../validation/px4-dds-gieop6c6/truth.jsonl) 及 [truth P](../validation/px4-dds-jxvhi_jx/truth.jsonl) 的对照：

| 运行/行 | model time s | actuator_time_usec | truth 位置误差 m | 对照意义 |
|---|---:|---:|---:|---|
| F / 2182 | 43.62 | 43616000 | 0.386488091062 | 距 reached MAVLink 源时刻 −4 ms |
| F / 2197 | 43.92 | 43916000 | 0.462551937333 | 与失败 MAVLink 数值源时间相同，truth 未越 0.5 m |
| F / 3431 | 68.60000000000001 | 68596000 | 0.084842807680 | 与 reached DDS status 对应的 actuator 时间 |
| P / 2502 | 50.02 | 50016000 | 0.436909035679 | 对照 MAVLink 50016 ms 的峰值附近，model +4 ms |

F L2197 的 truth NED 位置为 `[3.386649863547075, 2.252739877185101, -3.0240568541194843]`。[px4_mavlink.py](../Simulator/wksim_core/px4_mavlink.py) L69–81、111：先以已有 actuator 推进一步并发送 sensor，然后写 truth，再接收下一 actuator。两份 trace 中所有非空 actuator 的 `model_time - actuator_time_usec/1e6` 均约为 0.004 s（浮点误差约 2e-14 s）；这为模型/FC 源时间对照提供依据，不能用 3 倍墙钟或任意平移去配准。truth 常规采样间隔 20 ms；上述近邻不插值，不能据几个点证明整个连续驻留窗口的真实轨迹均合格。F 末尾 model 69.14 s、truth 误差约厘米级，只证明后来接近目标，不能抹去较早估计轨迹的越界。

## 尚需区分的可证伪假设

以下按与现有证据接近程度排序，均为后续验证建议，本审计未运行新实验：

1. **观察端消费不足造成历史状态积压。** 预测：按同一源时间匹配的 MAVLink/DDS 状态相符，但发送/接收/消费跟踪显示延迟增长，消费速率低于到达速率。现有同值匹配支持此方向；若端到端跟踪无排队而时间映射不同，应否定或修正该解释。需要定位具体队列，不能仅凭 pump 结构定根因。
2. **首次进入容差带后仍有估计轨迹超调，且两次边界裕量不同。** 预测：同源时间的完整估计曲线在 F 入窗后越界、P 保持窗内。现有数据支持观测到的局部差异；是否由命令生效时刻、初态或控制过程变化造成，需配准原生目标、估计状态与 actuator。若源时间配准后该超调不成立，此解释应被否定；不能用后来稳定位置替代原驻留窗口。
3. **估计值与真实模型位置的差异使 F 跨越门槛。** 预测：对齐坐标原点和采样时刻后，F 的估计误差仍 >0.5 m，而同期 truth ≤0.5 m。43.920 s 的记录支持此局部预测，但尚未分解估计偏差、原点偏差与采样影响；更完整的时间/原点配准若显示 truth 也越界，则不能坚持“仅估计越界”。
4. **并行负载影响命令时序或消费延迟，进而改变边界结果。** 主线提供背景：F 与已隔离的 239 项 unit/RMW 矩阵同时执行，P 串行。该背景未在本侧线中独立重建；一次失败/一次成功不是因果证据。预测需在固定构建、初态与任务下，以有/无负载的重复对照及调度、队列、命令生效时间证据验证。若结果与负载无可重复关联，或仅延迟变化而源时间轨迹和门槛不变，应否定相应因果主张。

尚未完成重复性统计、积压根因定位或连续 truth 驻留判定；也未提出或实施阈值放宽。通过样本仅说明该固定构建存在一次成功路径。

## SHA256 复核清单

本审计直接对文件原始字节执行 `hashlib.sha256(path.read_bytes()).hexdigest()`。以下完整摘要可用 `Get-FileHash -Algorithm SHA256 <path>` 复核；路径相对 wksim。

| 文件 | SHA256 |
|---|---|
| validation/px4-dds-gieop6c6/result.json | `3009e30fb76d9555c4a66bce3e10ccaece5aa66a080980ffba0a12b7d57ca708` |
| validation/px4-dds-gieop6c6/telemetry.jsonl | `9653caa16f53a86da5be2115159afde8a463c52bc322ad62d60ad67dac2a5c06` |
| validation/px4-dds-gieop6c6/dds.jsonl | `67e7372d9ad99b0c7cb77d262b981a9cb5eba79d91800a0b6711fc5ab3c19e93` |
| validation/px4-dds-gieop6c6/truth.jsonl | `0b5d4ab6ba1df97440f8c416fc61ebdb1b0c129d16681f610f1f85a00ce9da97` |
| validation/px4-dds-jxvhi_jx/result.json | `67dfcc0470b19975bb0ed3104fdf911dc01f9698e42e8992b8143f3c61f4bb07` |
| validation/px4-dds-jxvhi_jx/telemetry.jsonl | `ecbfab8dac941efec574b09260ebc74f2e4b3dd1d812c5f5510bef8e7b964743` |
| validation/px4-dds-jxvhi_jx/dds.jsonl | `11f1a5887cf22cff1fece1bbfa131471567e04ed1c13dbc2df5675b9aa76bea8` |
| validation/px4-dds-jxvhi_jx/truth.jsonl | `a748380c11eecf0119c468e7643edb78ea6ba3cafd8a9679888b1d643582a5ef` |
| tools/validate_sitl_physics.py | `2eab332d8825ad38a506afe0e29da97347caeeaef36fc486dae41a8bc6df7680` |
| tools/sitl_dds.py | `3a40c00c8c4c2219a57ece2808340ecc1f71afa7022ce5c3910bce4bf88e61f1` |

上述两项实际源码摘要分别与两次 result 中记录的摘要及各自 `source__tools__validate_sitl_physics.py.txt` / `source__tools__sitl_dds.py.txt` 原始字节摘要一致，可据快照复核行号和谓词，避免未来源码变更影响本结论。
