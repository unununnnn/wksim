# OMP ArUco 启动/倍率时序重叠分析（tracking-02，r2 校正版）

日期：2026-09-11。只读分析，未改 runtime/门槛，未重跑，未编译/起节点。
工具：`tools/analyze_aruco_startup_timing.py`（通用，接受 epoch 目录与窗口参数）。
证据（x 模式新文件）：`validation/coordination/aruco-startup-timing-02.json`
（完整 group 表、逐 tick 原生等待/阶段/GC 窗口，不含 raw_hex）。

实际命令：

```powershell
python tools/analyze_aruco_startup_timing.py validation/40-aruco-tracking-02/run/epochs/48ab11fb5c4c4c679d55a2ed9d2b71f9 --output validation/coordination/aruco-startup-timing-02.json
```

## 数值结果（原始 tick/ns，未截断）

失败形态：`rate_unmet/resource_insufficient`，tick 12136，lateness 100,152,917ns。
理想组 = 4 tick / 8ms（数据逐组核实无异形）。

**晚期窗口 11900..12136（59 组，理想 472ms）**：组内工作合计 273.898ms，
组前间隔合计 231.305ms。起始滞后从 11896 的 57.958ms 单调爬到 12132 的 96.464ms。

**早期窗口 2800..3000（51 组，理想 408ms）**：组内工作 261.536ms，组前间隔
183.431ms（含计划内节拍空闲）。

**归因校正（依据主会话精确分解
`validation/coordination/aruco-release-decomposition-02.json`）**：
本报告初版“滞后增长的载体是组前空隙”**不成立**——gap_before 混含计划内节拍空闲
与累积超时，不能由总 gap 推因。精确 start-to-start 分解：累计漂移
96,404,182ns = 组内超 8ms 工作 55,913,979ns + 残余 release 40,490,203ns
（残余含组外工作与等待，分解本身不作因果归因）。早期大跳变几乎全为组内超期工作
（2816：11,936,371/12,205,400ns；2924：9,462,633/9,626,701ns；2956：
11,753,631/11,787,716ns）；晚期 12024（5,253,248ns）与 12124（3,355,780ns）
跳变几乎全为残余 release。**12136 的 100ms 滞后是全场累计，非单点事件**；
11896 处已有 57.96ms 继承滞后。

**已记录仪器覆盖的重叠**：
- 分栈原生等待 >2ms：早期 px4 7.445ms@2924、arducopter 2.465ms@2966；
  晚期 arducopter 3.044ms@12001、px4 4.984ms@12020、arducopter 4.519ms@12130。
  这些落在组内 `native_inputs` 阶段内（阶段值吻合，如 12020 的 5.094ms）。
- health_and_models 4–5.6ms 尖峰散布于 11991/12032/12064/12093/12119
  （位置各不同，模型健康侧）；encode_send 单尖峰 4.433ms@12069。
- GC：全窗仅 0.106ms@12024；**全场最大 418,951ns（≈0.42ms）**，与既有结论一致，
  不能解释毫秒级漂移。

## 可证实的归因边界

- 能归因：约 58% 的累计漂移来自组内超期工作，其中部分对应分栈原生等待
  （两栈不同 tick，非单边）与 health_and_models/encode_send 阶段尖峰。
- **残余 release（40.49ms）不在任何仪器窗口内**：候选（节拍等待过冲/ROS spin/
  日志/OS 调度）无法用现有统计区分；不排除其中任何一个。
- thread_cpu_ns 个别略超 wall_ns 属原 clock 读取窗口差异，证据原值保留，未判损坏。

## 最小下一探针建议（供主会话选择实施）

在 rate 组边界之间加一对单调 ns 时间戳：上一组结束发出后到下一组
earliest/actual_start 之间（即 `joint_rate`/supervisor 的节拍等待段），把
“计划内节拍睡眠”与“超时滞留”分开记录。一次运行即可判定残余 release 是
调度器过睡还是未覆盖工作；不需要全库插桩。tracking-01（tick848/107.146683ms）
可用同一工具直接复核。

## r2 变更说明

仅校正归因措辞（区分 planned idle 与累积超时，引用 release 分解数据）；数值表、
证据文件与探针建议不变。跟踪-02 运行原件未触碰。
