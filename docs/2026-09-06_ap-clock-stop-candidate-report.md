# AP 整数时钟与暂停停机：独立候选验证

状态：已实现、独立构建并通过本报告列出的限定验证；**没有替换生产固定候选，也没有完成 G2 或 Full 项目**。用户“全按照推荐”已批准此前提出的联合调度原则和 MATLAB 首期范围，见[批准记录](2026-09-06_recommended-decisions-accepted.md)。

## 实现与构建

[第三个 AP 补丁](../patches/arducopter/0003-json-integer-clock-interruptible-stop.patch)在既有 DDS 补丁之后应用，只修改五个 AP 源文件：

- `SIM_JSON.cpp/h`：将绝对 JSON 秒时间量化为整数微秒，再作整数差分，避免每步截断浮点差导致累计亏差。重复量化时间不调用补帧；拒绝非有限、负数和溢出时间。原 JSON 反向时间的 boot 偏置语义保留，但生产 cold reset 仍须新进程/新 epoch，不能以此热重置替代。
- `Scheduler.cpp/h` 与 `HAL_SITL_Class.cpp`：退出标志改为 `volatile sig_atomic_t`；主循环和 JSON 等待共用原有正常 `exit(0)` 路径。JSON 收包前后及重试循环检查退出，不需要恢复传感器或额外推进物理。信号处理器本身不执行退出清理；未改 SIGINT 的既有非 coverage 行为。

复用[原构建脚本](../tools/build-ap-dds-yaw.sh)，增加显式 `--with-clock-stop`。从固定干净源复制、依次应用三个补丁，先运行源码边界测试，再 `waf configure --board sitl --enable-DDS` / `waf copter -j4`。新候选不重建消息接口，继续使用原来已固定的 state ROS overlay。

| 身份 | 值 |
|---|---|
| AP upstream commit | `1511f27194f1dcc3728270883047bdf022b3fd53` |
| 新候选 | `/root/wksim-ap-clock-stop-OXQqdR` |
| 新固件 SHA256 | `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de` |
| 新补丁 SHA256 | `4b188847ae93a00897d79275ca1c239180ae5b3c202b4d4365181083c8494b71` |
| 构建清单 SHA256 | `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a` |
| 原 AP 固件 SHA256（未替换） | `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5` |
| 原 PX4 固件 SHA256（未修改） | `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd` |

构建日志记录编译完成耗时 2m10.959s。`Aj0xBr` 是保留在 WSL 的源码编辑暂存副本，未作为已构建候选运行。

## 准入边界

[实验准入工具](../tools/ap_clock_candidate.py)先要求原固定 baseline 完整预检通过，再校验调用者明确给定的清单 SHA、候选路径、三个补丁、构建脚本/日志、二进制和完整源快照。该候选覆盖 24,593 个源条目、22 个 Git 仓库；目录符号链接同时记录链接和其内部目标内容，不静默跳过 MAVLink 的本地模块。源/文件集合变化和清单篡改有负向测试。

成功结果明确标记 `experimental=true, production_admitted=false, flown=false`，并独立保留 baseline 预检。这里的 `flown=false` 表示准入本身不是飞行证明；飞行证据在下面独立列出。未修改产品 `AP_SHA256`、capability index、原配置或健康检查。[当前复核](../validation/ap-clock-stop-integration-20260906/admission-recheck.json)确认实验准入通过，原生产预检仍以路径和固件哈希不匹配拒绝新候选。

## 回归与真实运行

| 验证 | 原固定 AP / 对照 | 新 AP 候选 |
|---|---|---|
| 实际源码 10,004 × 1ms | 少计 1,820µs | 每个 tick 精确；末值 10,004,000µs |
| 实际源码 200,000 × 1ms | 少计 41,974µs | 每个 tick 精确；末值 200,000,000µs |
| 11 项源码边界用例 | RED | 全部通过，30,050 条断言 |
| 停流后 TERM，tick 2000 | 5.0018s 后仍未退出，清理 -9 | 3.727ms，exit 0，仍为 tick 2000 |
| 停流后 TERM，tick 10004 | 历史负对照保留 | 3.541ms，exit 0，仍为 tick 10004 |
| 双栈原生时间测试 | 本次 386 个 AP 样本均偏离 1ms 网格，严格门失败 | 两次共 768 个 AP、954 个 PX4 样本均在 1ms 网格，严格门通过 |

源码边界测试提取实际 JSON 时间代码及实际 `Aircraft::time_advance` 编译执行，只有同步/速率回调是记录器；不是重写一套时钟算法来验证自身。包含 4ms 序列、重复、亚微秒、复位偏置、同步开关和溢出。初版测试把十进制半微秒当成精确 binary64 值，产生一项不正确的期望；保留 `tmjbmi7g` 失败包，改用可由独立整数算术判定的非半点输入后，两套源码重新运行，未为此修改候选算法。

两次共同场景地面验证都由同一父调度器发出 10,004 个权威 1ms tick，两份真实模型各在独立进程运行；每次 2,501 个 4ms 输入边界，其中从 tick 60 起 2,487 个严格 PX4 时间边界。tick 8000/8004 各暂停超过两秒，中间只推进四步。原始模型状态、逐包握手、CDR、源码快照与当前源哈希的[首轮审计](../validation/joint-native-clock-nhint6xd/audit.json)及[复跑审计](../validation/joint-native-clock-bioahg6e/audit.json)均通过；两次 AP 最终正常退出 0，无需再发传感器。AP 下一请求序号仍不是一次新控制计算的 ACK。

这是已测原生时间样本的整数对齐，不是每个 DDS 样本与当前接收 tick 同步到达；观测到 AP 最大接收年龄 2,000µs、PX4 9,000µs，不把它们定义为正式数值误差预算。审计里的 `ap_arithmetic_fingerprint` 保留旧固定源码的反例公式，不驱动任何时钟，也不是新候选的算法预测。

### Prometheus 公共接口飞行

新 AP 在[真实飞行](../validation/arducopter-dds-7jo4nu9m/result.json)中经安装的 Prometheus `session_v1` 完成正常预检/解锁、起飞、悬停、航点、LAND/解除解锁及地面 DDS 重连。独立物理最大高度 2.9963m、最小航点误差 0.02250m、落地高度近零；悬停最大高度误差 0.06130m。6 个公共请求取得 6 个原生接受 ACK，诊断 DDS 观察器未代发控制命令。

固定 PX4 第一次[回归](../validation/px4-dds-gieop6c6/result.json)在航点保持阶段失败，MAVLink 位置误差 0.505596m 超过原定 0.5m；没有放宽阈值。随后相同配置的[串行复跑](../validation/px4-dds-jxvhi_jx/result.json)通过，不能据此宣布重复性问题消失。独立问题见[重复性审计](2026-09-06_px4-waypoint-repeatability.md)。[双栈飞行审计](../validation/ap-clock-stop-integration-20260906/flight-audit.json)确认这两份通过样本的六个公共输入相同、安装源身份匹配、原生确认和物理真值满足原门槛；失败样本不从总体结果中删除。

这两份飞行是**独立实验回归**，其地面 Agent 断开时物理继续运行的旧实验行为，不能作为联合场景整场景冻结或空中失联验收。

## 测试、失败保留与资源

- [工具边界测试](../validation/ap-clock-stop-integration-20260906/tools-tests.log)：18 项通过；[单独原生接口测试](../validation/ap-clock-stop-integration-20260906/native-tests.log)：10 项通过。
- [产品矩阵](../validation/session-product-checks-KdwyBzOI/session-tests.log)：239 项，跳过 1 项，其余通过；[旧版准入矩阵](../validation/session-product-checks-KdwyBzOI/legacy-preflight-tests.log)：10 项通过。它们不是 Full 完成证明。
- 中断后一次直接在主网络命名空间运行原生测试，被两项隔离前置断言拒绝；未据此当作产品失败或忽略检查。随后在独立 net/ipc/mount、私有 `/dev/shm` 中运行同样 10 项并通过。首次源码复制的空暂存、补丁上下文不匹配和目录链接封存拒绝也没有被当作成功构建。
- [停机离线审计](../validation/ap-shutdown-audit-jy_sfufw/audit.json)包含历史 13 次及本轮 3 次共 16 份，检查逐包地面/时间/信号身份和证据哈希；原有不完整 GDB 身份记录限制继续保留。
- 中断后按实际内核 PGID 检查本轮三次停机、三次双栈地面、三次飞行涉及的 35 个自建进程组，均无成员残留。原 AP PID828/PGID828/start_ticks19268 未变；原 UE PID35256 已不在运行，本轮未发出终止该 UE 的操作，也未修改 P450 资源。
- 三个实现侧线及后续离线审计侧线均显式 gpt-6-astra/low，并从实际 turn_context 核验；无嵌套、代码写入范围互斥。
- Codebase Memory 当前仍 ready（92,892 节点/202,270 边）。[精确覆盖复核](../validation/ap-clock-stop-integration-20260906/codebase-coverage.json)显示这些 tools/docs 按子树排除，新补丁无跟踪记录；本轮直接读实际源码，不宣称新增代码已索引。外部 WSL AP 源不属于该 wksim 索引，也没有为仅修改排除项反复全量索引。

## 复现

以下在 Ubuntu-22.04/root、wksim 仓库目录执行；真实运行入口自行创建私有 net/ipc/mount 与 `/dev/shm`。构建不覆盖原安装。构建出的新路径和清单 SHA 必须使用该次实际输出，不照抄旧清单冒充新构建身份。

```bash
# 下列命令复核已封存的 OXQqdR，不重新 seal 或覆盖它。
bash tools/run-ap-shutdown-probe.sh --ticks 2000 --signal TERM --flow stopped --dds 1 \
  --ap-build-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-build-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a
bash tools/run-joint-clock-probe.sh --native-clocks --require-aligned-clocks \
  --ap-build-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-build-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a
bash tools/run-prometheus-validation.sh arducopter /root/wksim-dds-VxM6Ni \
  /root/wksim-ros2-MUlZd0 /root/wksim-ap-dds-yaw-state-4Wr27s \
  /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a
```

重新构建执行 `bash tools/build-ap-dds-yaw.sh /root/wksim-dds-VxM6Ni --with-clock-stop`，再将该次输出的全新目录作为 `python3 tools/ap_clock_candidate.py seal` 的最后一个参数。封存后用该次新清单路径和 SHA 重跑上述验证；已封存目录会拒绝覆盖。

## 下一集成门

AP 根因修正的源码/构建/地面/停机/独立飞行证据已具备。仍须在 #8 中落实 ROS 任务虚拟时间、墙钟监督、迟到和重连条件、具体超时及 cold reset 契约，再由 #19/#20 接入版本明确的候选、唯一公开时间、共同任务、生命周期和旧代次隔离。当前探针不是生产联合运行入口。PX4 航点重复性、正式数值预算、空中 DDS 失联、实际 UE/浏览器/QGC、插件/环境反馈、MATLAB 实际联测和 Full 扩展继续保留，不将这批验证等同于阶段或项目完成。
