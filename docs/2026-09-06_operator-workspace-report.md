# 第四批：wksim 工作台实现与服务联测，#18 保持 open

日期：2026-09-06 JST。主体仍为 Prometheus `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`，目标仓库 `unununnnn/wksim`。未提交或推送混合工作区，未修改/关闭原 Wayfinder #1 或规格 #10。

## 结论与未通过门槛

已实现本机工作台、正式预检/启动/取消、独立 UE 查看和只读证据接口；**51 项 Windows 检查、185 项 WSL 回归和 6 个真实 HTTP/飞控服务用例通过**。这不等于浏览器交互通过，不关闭 #18，也不宣布 G1 或 Full Goal 完成。

内置浏览器在访问 `http://127.0.0.1:8765/` 时报告管理员安全策略无法核验并拒绝访问。按浏览器工具限制未绕过，也未用另一套驱动伪装 UI 验收。实际表单、错误焦点、保存重载、页面重连、375/1440 布局、交互截图仍待验证。

另一个人工验收问题来自 UE 原始帧：部分冷启动帧显示 Preparing Shaders 且近黑，后续帧可见基础 quad-X 和场景但照明偏暗。Actor 坐标吻合及 LIVE PNG 存在只证明数据/渲染链路，不证明展示可读性或完整机型资产已交付。该项与浏览器门槛一起保留。

## 实现与职责

- `Simulator/wksim_console/workspace.py`、`server.py`、`preflight_entry.py`：本机独占数据目录、严格配置/版本比较、候选预检、正式 WSL 入口、精确任务取消、进程归属和同源 HTTP 边界。无新的原生飞控发布器。
- `records.py`：有界增量读、实际运行/控制代次核对、保留时钟来源、必需导航字段有效性；原始未知遥测不伪造数值；结果原文/哈希包装和既有离线 loader 分页。
- `visual.py`：固定 UE5.5 DLL、源与 staging 哈希校验，独占端口，已有产品桥，实际 Actor 回读；启动/关闭只用所持有的进程句柄。物理创建前准备可选 UE，创建后不等待显示。
- `web/`：本地中文配置/观察/结果工作台，保留 JSON 与表单互通、错误摘要/字段焦点、取消确认、历史实验和时钟提示。ui-ux-pro-max 影响了表单、对比度和布局；其营销页面模式未采用。codebase-design 促使界面复用正式入口，不复制飞控逻辑。上述前端设计尚未取得实际浏览器验收证据。

## 实际命令与运行

服务启动方式见 [wksim-console.md](wksim-console.md)。本轮数据根为 `validation/operator-fourth-wave-20260906/workspace`；启动日志保留 `server*.stdout.log` / `server*.stderr.log`，各 job 保存请求配置、执行配置、配置版本、argv、Windows PID、正式结果目录及服务实例。后续实例的 `server-*.json` 保存启动时 Python 版本和源哈希；第一次集成失败前尚未实现该快照机制，不补造其历史源码哈希。

真实用例通过 `D:/date/miniconda/python.exe -X utf8 -B tools/validate_operator_http.py`，选择 `--stack px4|arducopter`、`--case mission|cancel`、可选 `--view`、表中对应 `--evidence validation/operator-fourth-wave-20260906/<用例>` 执行。每例都真实验证无效任务拒绝、错误候选预检失败、修正后通过、保存重载哈希、活动任务互斥、拒绝活动中关闭服务、终态结果原文哈希和物理记录分页。

| 用例 | 正式结果 | job ID | 补充证据 |
|---|---|---|---|
| http-px4-fixed | pass | 25f6e38d9f4f44d1a672e73e1bd1e398 | 三航点及实际落地 |
| http-ap-view-fixed | pass | 09087cfd8db045dbb56fb790a2cac843 | 三航点；两次实际 UE 连接 |
| http-px4-cancel | cancelled | 3223f56234a7466aacb9462b27c2ea39 | 第一点取消，仅一项 MOVE，后续航点未派发 |
| http-ap-cancel | cancelled | 26da40d2ec414426a5b686f0ec9d69ae | 同上，真实 ArduCopter 降落 |
| http-px4-prepared | pass | 1a58c057629d407a936f3b55c6ce69b8 | 创建物理前准备 UE；关闭/重开后 Actor 序号推进 |
| http-ap-prepared | pass | e962e01d67f148afa08c43543141a27c | 同上；配置重用保持相同版本、执行身份全新 |

所有例的 `http.jsonl` 与 `observations.jsonl` 是服务观察证据，不是浏览器操作日志。取消的终态与完整任务完成分别报告。任务位置/速度/偏航门槛仍为 0.5 m / 0.5 m/s / 0.15 rad，连续 FC boot 驻留和独立物理窗口不混为一条时钟。

飞控未变更：PX4 commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，binary SHA-256 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`；ArduCopter commit `1511f27194f1dcc3728270883047bdf022b3fd53`，binary `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5`。UE DLL 仍为 `8ff466fbd1eb6489b7e8ac29209bbb7885cf7c876ee97dbcc314ebf41dc00b4a`。完整身份在每份正式结果中。

## 保留的失败样本及修正

1. `http-px4-first`：正式飞行 pass，但控制台误把可选遥测 NaN 当作整份结果/导航无效。修正后保留原文、SHA-256 和显式 nonfinite 标记；位置/速度/姿态等必需字段仍严格拒绝非有限值。未改写旧结果。
2. `http-ap-view-first`：飞行 pass，UE 观察器没有就绪。其 stdout 预先占用 `ue.log`，UE 实际改写到 `ue_2.log`。分离 stdout 与 Unreal 自有日志，并加回归约束；旧文件保留。
3. `http-px4-view`：短任务结束前缺少完整显示重开窗口。改为物理尚未创建时异步准备可选 UE；不放慢/暂停已运行物理，也不延长任务或放宽门槛来制造通过。重开仍异步接最新状态。

三次集成失败均保留，它们的底层正式任务实际 pass；不得把应用层失败擦成通过。合计本轮 9 次正式飞行：7 pass、2 cancelled。

## 独立审计与回归

`tools/audit_operator_console.py` 只读核对上述 6 例的原始结果哈希、任务/取消身份、实际源推进、每次 UE 的 Actor 数值和 LIVE PNG，并检查全部 9 次尝试的进程及 socket。固定 Actor 门槛：位置 `2e-4 cm`、四元数 `2e-6`、仿真时间 `1e-8 s`。不把 ACK 当成像素截图；PNG 另有原生捕获日志及哈希。

- `validation/operator-fourth-wave-20260906/audit-final.json`：pass；SHA-256 `5c0dc332195233a71135cdf44b558fd1add5da7d63cd1a444acba5e6621a27fb`。
- 关闭测试控制台后再次执行得到 `audit-recheck.json`，同样 pass 且 SHA-256 完全相同。测试服务 PID 868 已退出，8765/TCP 与 19060/UDP 均无监听/绑定；需要查看工作台时按使用说明重新启动。
- 实查 **36 个 Linux 进程组、57 个 Windows 启动器 PID** 均无残留，所有相应 socket 消失。原用户 ArduCopter PID 828、start_ticks 19268、原命令保持一致。此结果不等于服务被强杀后自动全树回收保证。
- Windows：`windows-console-tests-reviewed.log`，**51 tests，17.598 s，无 skip**；SHA-256 `999f081dd8f48c743cfa3a538ce69fdca15a0c8f96cdeabe3810ad65698fe723`。
- WSL：`wsl.exe -d Ubuntu-22.04 --cd /mnt/c/Users/PC/Documents/odid编译/wksim --exec bash tools/check-session-product.sh`；`validation/session-product-checks-NBXbzwLt/` 的 177 + 8 tests 均通过、无 skip。Windows 控制台测试按平台在 Windows 单独执行，不塞进 Linux RMW 矩阵。
- WSL 两日志 SHA-256 分别为 `c18683d6eebe6a79be2bc4b2ad161658c192f9b5525072e4f74049c25d336cf2`、`e99cce1b8e460f2da0185cf7c281eb8963e7db8fc56d7a6e9d01f15d39c33d8e`。

51 项测试包含最终主线增加的准备阶段互斥、可选显示失败、历史 UE 不冒充在线和未释放显示资源阻止服务退出。最后两项是正常飞行后的归属审查修正，验证使用真实 Workspace/HTTP 与受控进程接缝，未把接缝测试写成实机试飞。

## 多代理与下一步

本批四个独占写入子代理：Archimedes（web）、Ohm（records）、Nash（visual）、Planck（workspace tests），均显式 gpt-6-astra / low，实际 rollout turn_context 已核验，包含 Nash 的继续执行。主代理负责共享契约、服务/正式入口、集成修正和全部真实资源测试。没有嵌套委派；全部子代理已关闭。验收计数以主线真实日志为准，不引用代理自报的测试数字。

Codebase Memory 已刷新并持久化，最终 2026-09-05 16:36:00 UTC，72,451 nodes / 179,977 edges；索引只是导航，不是 Full 完成度。精确查询 7 个新入口完整返回，has_more=false；源文件直接复核。详见 [codebase-memory.md](codebase-memory.md)。

下一步：恢复内置浏览器策略校验后完成真正交互/响应式/键盘验收；改善 UE 冷启动及场景可读性并复核实际图像；通过后才能考虑关闭 #18。联合场景、空中 DDS 失联、MATLAB、数值对照、插件和 Full 扩展门槛保持原义，不推定用户已回答未决问题。
