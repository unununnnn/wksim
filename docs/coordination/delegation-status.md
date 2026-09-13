# 外部代理分工与主会话进度

用户指定通过Codex把低难度任务交给Oh My Pi和agy，主会话继续技术推进。本批使用`codexhost`创建独立会话，保留目标当前默认配置，没有修改全局模型/权限设置，也没有宣称Fast已核验。该次指定外部Harness的指令与旧通用Luna路由不兼容之处已向用户说明，未改AGENTS规则。

| 代理 | 已交付任务 | 结果 | 跟踪 |
| --- | --- | --- | --- |
| Oh My Pi | 全球飞行归档机械核对 | 26项SHA匹配；12个归档大小匹配；主会话要求修正了result.json误用归档长度的12个字段 | [OMP任务](codex://threads/9c4c33c6-3f34-4df0-9a2b-f868a6292e87) |
| agy / Antigravity | 进度导航与链接检查 | [导航页](../progress-index.md)已落盘，11个本地链接存在；主会话独立复核 | [agy任务](codex://threads/9ef3a71a-c4fb-4b72-8950-1df2dae018de) |

完整`delegationId/threadId/turnId/deepLink/status`和产物SHA在[派发表](../../validation/coordination/dispatches.json)。agy首次工具调用被其request-review模式拒绝；先完成纯文字草稿，用户随后确认权限恢复，才继续落盘并检查链接。未绕过权限或把受阻尝试改记成功。

## 本会话继续负责的技术工作

已扩展`tools/analyze_joint_scheduler.py`，把原始调度事件限定到`native_inputs`时间窗，排除前面的模型计算和编码耗时。新增检查覆盖时间区间、AP单独等待/四tick边界组合等待，以及阶段时间一致性；分析模块5项检查通过。

既有真实记录tick1926的8.098026ms AP输入阶段中，监督线程离CPU 7.476ms，其中唤醒前阻塞7.441ms、可运行排队仅35μs。原始阶段线程CPU为0.653392ms；跟踪打印为微秒精度。这支持“该样本主要在等待输入”，不支持把它归因为监督线程长期排队，也不能单凭此确定飞控或Windows根因。派生记录在[主会话分析](../../validation/coordination/parent-native-wait-analysis.json)，原始证据未变。

固定AP源的`SITL_State::wait_clock`由主线程推进FDM；`Scheduler::stop_clock`还会周期调用IO处理。它是下一步应验证的候选路径，但本批只有一个符合对应周期相位的慢样本，不能用相位巧合证明因果。实际启动参数`--speedup 3`也已读取，不把内部wall pacing未经测量就当作根因。

本批没有修改物理步长、输入屏障、100ms门槛或生产调度，没有新增飞行通过结论。后续机械整理仍可复用上述代理会话；技术方案与验收结论由主会话核验。用户既有`docs/Prometheus.gitmodules.reference`修改保持不动。
