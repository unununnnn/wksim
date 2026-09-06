# 工作台显式暂停/恢复：真实双栈 HTTP 验证

2026-09-06 JST。工作台已接入既有 MissionTask 的暂停、显式恢复及暂停后取消流程，使用正式 Windows 服务 → WSL 入口 → Prometheus 任务 → 原生 DDS 适配器。新增请求端只发布已有文件接口，未另建飞控命令通道，未替换正式 Task 或物理实现。四个真实服务场景首次运行均通过；**不是实际浏览器或 QGC 验收，#18/#42 仍 OPEN，Full Goal 未完成**。

## 实现与边界

- `records.py` 的 action_offer 要求真实跨轮询源时间推进、有效已解锁状态和一致的 run/mission/epoch/native_generation。暂停还要求当前 OFFBOARD/GUIDED、COMMAND_CONTROL 且无 failsafe；过期、终态和过渡中不提供动作。
- 五字段 POST 固定 `mission_id/action_token/action/control_epoch/native_generation`。Workspace 再读实际状态、检查当前进程归属，然后调用原有 `request_action`；新增可选 expected_offer 校验消除确认与文件读取之间的代次升级。CLI 不提供此参数时行为不变，运行时仍须在消费时重新校验自身健康与身份。
- 原生 HTML 确认框冻结 job/run/mission/epoch/代次/令牌/动作；确认前重新 GET，任何身份、选择或新鲜度变化均作废。不会将旧确认换成新令牌。浏览器本地新鲜度使用 performance.now，超出 JS 精确整数范围的代次不可提交。
- 文件提交、任务受理、暂停/恢复确认分别呈现。确认需匹配原任务事件及其嵌套 request_id 和全部身份。已拒绝请求与响应丢失/服务端异常分开显示；未知状态不自动重试。刷新页面不保存未取得的提交回执，这个限制没有隐藏。
- 采用 codebase-design 的同一调用接口与模块边界：复用原文件请求实现，不添加第二套控制逻辑。ui-ux-pro-max 的适用建议用于 disabled、aria-busy、焦点及异步结果反馈；主代理追加单调时钟、JS 整数精度和事件外层代次检查。DOM 替身测试不等于真实键盘或读屏器检查。

暂停停止任务派点而不是冻结物理，PX4 AUTO.LOITER / ArduCopter BRAKE 仍由正式任务发出。恢复是新的显式接管；BODY 航点继续使用第一次记录的 ENU 目标，新命令身份并重新完整停留。暂停中取消不自动抢回控制，显式恢复后直接 LAND，不再 MOVE；其他所有者自行落地路径仍由原契约处理。原生故障和过期状态没有改为自动恢复。

## 固定配置与四个真实场景

证据根目录：`validation/operator-mission-actions-20260906/`。正式服务 PID55656，地址 `http://127.0.0.1:55829`，新 workspace、server_instance `7fef5f3ef6dd4790842ba7f3578494c0`。9项 console 源码/前端输入在服务启动时留哈希，并在审计时与当前文件重核。

全部场景先保存/重载、拒绝非法任务、执行错误候选预检和正确候选预检，再以正式配置启动。每航点 `dwell_s=10` 在运行前固定；在第三个 BODY 航点驻留开始后至少0.7秒提交暂停。恢复例等待至少6秒 FC boot 时间，取消例再等待至少6秒后显式恢复。仍保留原位置/速度/偏航阈值，不通过放宽物理或时钟门槛获得通过。

| 场景目录 | job_id | 正式终态 | 暂停期间物理推进 / s | 最低物理高度 / m | BODY 尝试数 |
| --- | --- | --- | ---: | ---: | ---: |
| http-px4-resume | e99de52b7b8a4ed3b910eebe2f2fc6f6 | pass | 6.70 | 2.960894 | 2 |
| http-ap-resume | 81d28fda9a654b7fa545640dd0980a55 | pass | 7.66 | 3.012974 | 2 |
| http-px4-cancel | 66aa8bdc2f114ffe9b6a957019ed8b12 | cancelled + safe_landing | 13.36 | 2.953537 | 1 |
| http-ap-cancel | 2f85514bde0a49eca163c02aa01e3cba | cancelled + safe_landing | 13.40 | 2.989448 | 1 |

各例的 HTTP 服务审计均严格为 pause200 → 旧令牌400 → resume200，实际原子请求文件与返回身份一致，接收事件可在原始 mission.progress 中逐项找到。任务报告的暂停期间发布增量为0；独立物理真值继续推进且高度保持在2.5m之上。两例恢复均完成新的10秒源时钟驻留；两例取消没有补发第三航点 MOVE，降落结果不冒充完整航线成功。AP 取消例在第二航点出现一次 `waypoint_dwell_reset`，随后按原门槛重新完整驻留；未擦除该记录。

本 HTTP 客户端没有额外原生 DDS 订阅，**不把 Task 发布计数称为独立原生输出静默证明**。此前带只读原生观察器的固定证据见 [任务生命周期报告](2026-09-06_mission-lifecycle-report.md)，本轮不重写其旧哈希为当前值。FC boot、物理与墙钟分别保留，不能从接近的持续时间推导同场景联合时钟已实现。

候选与环境未替换：

- Ubuntu-22.04、ROS2 Humble，`/root/wksim-ros2-MUlZd0`；DDS `/root/wksim-dds-VxM6Ni`。
- PX4 commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`；实际二进制 SHA256 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`。
- ArduCopter commit `1511f27194f1dcc3728270883047bdf022b3fd53`；可选候选 `/root/wksim-ap-dds-yaw-state-4Wr27s`；实际二进制 SHA256 `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5`。
- 全部 formal result 的 runtime_sha256 和 product_sha256 与当前源文件一致。主线 helper `mission_actions.py` 为 `cf393e07445c055b52b9addbe0c9026d0b94c2dae35727c8c1be23e986135119`。

## 测试、审计与清理

- Windows console/actions 矩阵：81项，78通过、3项因 Windows 符号链接权限不足跳过；真实 junction 用例通过。`windows-console-actions.log`。
- HTTP 观察器逻辑4项通过；Node前端逻辑10项通过，`node --check` 无语法错误。`http-observer-tests.log`、`console-web-tests.log`。首次48项检查是上述子集，不重复计为新覆盖。
- WSL：239项，238通过、1项 Windows-only junction 跳过；10项 legacy preflight 全通过。Windows 跳过的3项符号链接在此平台真实执行通过。证据 `validation/session-product-checks-bvkHq0aj/`，不声称单平台无跳过。
- 独立磁盘审计 `audit-final.json` 重新读取结果/请求/事件、复核物理窗口及源码哈希，4例通过。SHA256 `455dd47a26d300019a497f018af5498e488bc1aa8640bd27753550061aa93b19`。
- 全部4次正式飞行及8次预检的12个 Windows 启动器 PID 已退出；16个 Linux 子进程组无残留，专属 socket 和 run_id 命令行无残留。4次错误候选是预期失败，不是飞行失败，原始报告保留。
- 已通过本服务 shutdown API 正常关闭 PID55656，`shutdown.json` 读回 server_remaining=0。用户已有 ArduCopter PID828/start_ticks19268/命令行和 UE PID35256/创建时间/命令行不变。没有全局按名称清理进程，服务 stderr 为空。

子代理 Pascal 仅写 web 三文件及新增离线前端测试，实际 turn_context 核验一次：gpt-6-astra、effort=low、collaboration reasoning_effort=low；来源为 `C:/Users/PC/.codex/sessions/2026/09/06/rollout-2026-09-06T05-36-11-01a07349-30b5-7422-965f-7f7255e74a99.jsonl`。主代理负责后端、额外审查、实飞、整合与票据；子代理已关闭，没有嵌套委派。

## Codebase Memory 与保留资源

依赖新源码的结构审查前先读 index_status，再使用明确 CBM_CACHE_DIR/CBM_RUNTIME_DIR 的原生 fast+persistence 刷新，36.708秒成功。快照 **2026-09-05 20:55:19UTC，92,892节点 / 202,270边**；metadata20:55:22，artifact20:55:31。日志 `C:/CBMData/logs/wksim-prometheus-1788641731.log` 与本轮 `memory-index.log`；MCP实读 ready，精确5项入口完整返回、has_more=false，导航后复读实际源码。

五个实际实现文件无记录解析缺口，但 freshness 仍为 metadata_changed，不称完整解析。tools 验证器/审计器按祖先排除，直接读取；998partial、371excluded、0skipped是索引信号，不是Full完成率。`memory-query.json`保留精确覆盖回读。后续只改报告不重复索引，下一依赖源码变化的结构查询仍须检查/刷新。

Prometheus P450 机体、CCW/CW旋翼、两种材质与上游许可仍在 `Simulator/ue55/Content/Wksim/P450/`，本轮没有修改或重导资产。当前部署清单 SHA256仍为 `b1cad9c9b432c7987279a51832e2e2a45994310797f410b1bde76e181d363bfa`；Python远程执行配置保留。其下载、原生导入、许可和先前真实UE显示证据见 [P450报告](2026-09-06_p450-view-report.md)。本轮未启动新UE，没有用旧截图充作新显示验收。

## 复现与未完成项

先按 [工作台说明](wksim-console.md) 启动新的本地服务，再用实际地址替换 URL。每次使用新的证据目录，四种栈/场景组合均执行：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 -B tools/validate_operator_http.py --url http://127.0.0.1:8765 --stack px4 --case pause-resume --dwell-s 10 --evidence validation/my-console-px4-resume
& 'D:/date/miniconda/python.exe' -X utf8 -B tools/validate_operator_http.py --url http://127.0.0.1:8765 --stack arducopter --case pause-cancel --dwell-s 10 --evidence validation/my-console-ap-cancel
```

原始四例审计可重复读入，但新输出不能覆盖旧审计：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 -B tools/audit_operator_console.py validation/operator-mission-actions-20260906 --case http-px4-resume --case http-ap-resume --case http-px4-cancel --case http-ap-cancel --verify-current-sources --output validation/operator-mission-actions-20260906/my-reaudit.json
```

`--verify-current-sources`会拒绝后续源码漂移；旧证据仅代表其固定快照，不能绕过哈希检查宣称是新实现的验证。

实际浏览器策略仍未核验，未绕过；真实页面、键盘、响应式、读屏器和QGC尚未验收。UE冷启动时延稳定性、长时等待、空中DDS失联、联合场景时钟、Full构型/模式、MATLAB和数值预算等门槛不变。工作区仍为上游基线上的未提交迁移内容，git diff --check不能替代对未跟踪源码的上述检查；未推送混合工作区或发布厂商资产。原Wayfinder #1、规格#10和用户未回答的HITL决策不改写或关闭。
