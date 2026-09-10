# OMP 已运行票据验收核对（514743f）

日期：2026-09-10。核对基线：HEAD `514743fcb5b4941d2b83e60dcf8c7f6007ef07fd`。
性质：**只读核对 + 离线复算**。未启动 SITL/UE/FC/ROS 节点；未修改生产代码、原证据、预算或 Issue 状态；未 commit/推送；未嵌套委派。审计复算只读取原始运行目录，新输出写入 WSL `/tmp`（易失，未动归档）。
机器可读结果：`validation/coordination/omp-ticket-acceptance-514743f.json`。

## 票据当前状态（gh 实读）

| 票 | 状态 | 前置/依赖实读 |
| --- | --- | --- |
| #47 双栈全球航点与home基准（父） | OPEN | Blocked by #12/#14/#23：三票均 **CLOSED** |
| #45 GNSS中断与状态有效性恢复（父） | OPEN | Blocked by #22/#23：均 **CLOSED** |
| #118 接入已批准全球航点原生适配 | OPEN | 前置 #117 CLOSED；#116 CLOSED |
| #119 运行一次 PX4 全球航点/home工况 | OPEN | 前置 #118 OPEN |
| #120 运行一次 AP 全球航点/home工况 | OPEN | 前置 #119 OPEN |
| #121 交付双栈 GNSS 单次运行入口与独立原始审计 | OPEN | 前置 #109/#110 CLOSED |
| #111 运行一次 PX4 GNSS 中断/恢复 | OPEN | 前置 #110/#109 CLOSED、#121 OPEN |
| #112 运行一次 AP GNSS 中断/恢复 | OPEN | 前置 #111 OPEN |

## 独立复算结果（本次实际执行）

1. **四场最终运行独立重审计**（用归档入口脚本、原 `/root` 原始目录，输出到 `/tmp`）：
   - `bash validation/45-gnss-flight/audit-command.sh /root/wksim-gnss-flight-px4-05/d1d4028e65da402f918eef2ec768d8bb --output /tmp/omp-audit-gnss-px4.json` → `status=pass`，physical_ticks=69244，max_distance=3.3142418097363637，suppressed_candidates=150，withdrawal=`native_navigation_invalid_control_released` — 与 `validation/45-gnss-flight/final-matrix.json:5-29` 逐值一致。
   - 同脚本 ap-05 目录 → `status=pass`，ticks=104871，max_distance=3.64074036008803，suppressed_bytes=27690，recovered_write_bytes=61344 — 与矩阵 `:32-64` 一致。
   - `bash validation/47-global-flight/audit-command.sh /root/wksim-global-flight-px4-20260910-08/d8bc659871d44a18a1846cc5a4412245 /tmp/omp-audit-global-px4.json` → `ok:true`，ticks=45832，tilt=0.03591029377755194，quiet=1.01015832s；输出与归档 `validation/47-global-flight/px4-08/audit.json` **逐字节相同**（SHA256 均为 `d3d94fe44a2ae10b07789311c39c32ff443d4f41f705a43f592e0bf644fc4d06`，`cmp` IDENTICAL）。
   - 同脚本 ap-20260910-05 目录 → `ok:true`，ticks=78418，tilt=0.045325337608438286，quiet=1.00755818s — 与 `ap-05/audit.json` 字段一致（该次 `/tmp` 输出未保留，未做字节 cmp；打印全文留存于作业记录）。
2. **矩阵内嵌审计 == WSL 外部审计原件**：`final-matrix.json` 两场 `runs[].audit` 与 `/root/wksim-gnss-flight-{px4,ap}-05-audit-final-v3.json` 逐字段相等（True/True）；外部原件 SHA256 `24270224…`（px4）、`dfe7735e…`（ap）。GNSS 原始审计输出文件本身只在 WSL `/root`，未归档进仓库 — 内容经矩阵内嵌 + 可复算双重保留（见"差距"G2）。
3. **归档哈希**（Windows `sha256sum`，与矩阵/归档记录一致）：
   - `47-global-flight/px4-08/raw-evidence.tar.gz` = `e09f0acb…` ✓、`result.json` = `0a340c9a…` ✓；`ap-05/raw-evidence.tar.gz` = `9d5e311f…` ✓、`result.json` = `906699da…` ✓（514743f 的 `omp-global-evidence-check.md` 已 26/26 PASS，本次抽查最终两场复核一致）。
   - `45-gnss-flight/px4-05/raw-evidence.tar.gz` = `9ff54870…` = 其 `archive.json:70` `archive_sha256` ✓；`ap-05/raw-evidence.tar.gz` = `1016a534…` = `archive.json:71` ✓。
   - 审计器源码：`tools/audit_gnss_flight.py` = `8889886aa…`（= 矩阵 `audit_sha256` 字段与 run-source 外当前版）；`tools/audit_global_flight.py` = `e31e165e…`、`tools/audit_global_home_flight.py` = `9ee2901c…`，均与 `47 final-matrix.json:165-168` 一致。
   - GNSS run-source 一致性：`gnss_task.py`/`gnss-flight-v3.json`/`run_gnss_flight.py`/`run-gnss-flight.sh` 当前 SHA 与 `45-gnss-flight/px4-05/archive.json:27,31,49,50` 记录一致。**例外**：run-source 封存的 `tools/audit_gnss_flight.py` 为 `f4c10e35…`（archive.json:47），当前版为 `8889886aa…` — 运行后审计器有后续修改，最终审计用当前版复算通过（见 G3）。
4. **入口存在且 --help 退出 0**：`tools/run-gnss-flight.sh --help`、`tools/run-global-flight.sh --help`、`tools/audit_gnss_flight.py --help`（WSL，只读）均打印真实 usage；只读预检证据 `45-gnss-flight/preflight-{px4,ap}-final.json` `ok:true`、Control SHA `14a00696…`。
5. **离线回归**（Windows 本机 `python -B -m unittest`）：`test_gnss_audit`/`test_gnss_flight`/`test_gnss_observers` 10 项 OK（5 项按设计 skip：需显式保留飞行目录/隔离 ROS 环境）；`test_global_audit`/`test_global_home_audit` 8 项全部按设计 skip（无保留飞行环境变量）。WSL 侧既有日志复核：`45-gnss-flight/audit-tests.log` 4/4 OK；`47-global-flight/home-audit-tests-px408.log` 4/4 OK；`home-audit-tests-ap05.log` 3 通过 1 跳过（跳过为"AP 场景原点不适用"负例，与报告 `docs/2026-09-10-global-flight-report.md:64` 一致）；`oracle-tests-final.log` 16/16 OK、60 个双栈数值用例 max 误差 0/0.01m；`control-tests-final-complete.log` 68 项 OK（1 skip）；`45-gnss-flight/control-tests-final.log` 51 项 OK。
6. **仓库状态**：`git status` 唯一脏文件为用户修改的 `docs/Prometheus.gitmodules.reference`（保留未动）；两套证据已分别随 `e075d0d`、`ff63c72` 提交，514743f 只新增协调/分析产物。

## 逐票核对

### #118 接入已批准全球航点原生适配 — 建议：可关闭（待主代理复核签字）

| AC | 结论 | 证据 |
| --- | --- | --- |
| 两栈原生接入 + 完整物理目标/datum 证据通过；无不支持模式静默转换 | 满足（实验候选范围） | `validation/47-global-flight/final-matrix.json:3-5`（ok/experimental/production_admitted=false）、`:7-50` 两场 final；独立重审计逐字节/逐值复现（上 1）；datum 探针与拒绝记录 `px4-07-datum-reaudit.json`（ok:false，旧通过被撤回）；旧 `LAT_LON_ALT` 未绑定拒绝见 `docs/plan/47-global-run-contract.md:7` |
| 交付源码/配置身份、准确命令、原始结果和失败边界 | 满足 | 报告 `docs/2026-09-10-global-flight-report.md:18-20`（Control/home manifest SHA、准确命令模板）；12 场原始归档及失败场（ap-01/02、px4-01/03 等）保留于矩阵 attempts；`px4-seal-v2-comparison.json` 固件一致性 |

差距：G1 — 子票写入范围原本只含合同 + 证据目录；生产控制源码实现由主任务在 `47-global-run-contract.md:5` 自述的用户授权下完成，票据中无该授权的评论记录，需主代理/用户确认此授权声明。
下一步：主代理确认 G1 后关闭 #118（`gh issue close 118 --repo unununnnn/wksim` 并附本核对链接）。

### #119 运行一次 PX4 全球航点/home工况 — 建议：可关闭（需主代理确认写入范围偏差）

| AC | 结论 | 证据 |
| --- | --- | --- |
| 本次范围原始审计 PASS、证据/退出身份完整 | 满足 | px4-08 审计 `ok:true`（`px4-08/audit.json:2`），独立重审计逐字节复现；run_id/epoch/control SHA 在矩阵 `:8-27` |
| 交付源码/配置身份、准确命令、原始结果和失败边界 | 满足 | 报告第 16-20、46-58 行；失败场 px4-01/03/04/05/06 原始归档保留 |

差距：G4 — 票定写入范围为 `validation/lunar-47-px4-run/`，实际证据落在 `validation/47-global-flight/`（`lunar-47-px4-run/` 不存在）。实质证据完整，路径与票面不一致。
下一步：主代理确认以主任务证据目录为准（或补一个索引说明），随后关闭。

### #120 运行一次 AP 全球航点/home工况 — 建议：可关闭（同 G4）

同 #119，证据为 ap-05：`ap-05/audit.json:2` `ok:true`，独立重审计字段复现；矩阵 `:30-50`；AP 特有审计修复（float/double 高度转换）记录于报告 `:60`，旧拒绝记录保留在 `ap-04/audit-initial-rejected.json`。写入范围偏差同 G4（`lunar-47-ap-run/` 不存在）。

### #47 双栈全球航点与home基准（父） — 建议：可关闭候选（主代理复核条款未走完）

| 原 AC | 结论 | 证据 |
| --- | --- | --- |
| 补齐并验证 PX4 全球位置适配，保持 AP home/局部转换边界 | 满足（候选） | px4-08/ap-05 审计 ok；NED 投影与 AP 原生 FRAME_GLOBAL_REL_ALT 边界见报告 `:42` |
| 经纬度/AMSL/相对高度/ENU/NED 转换有显式基准与数值检查 | 满足 | `oracle-tests-final.log` 16/16 + 60 用例误差 0；datum proof 绑定 `final-matrix.json:27,49` |
| 全球目标真实飞行、越界拒绝、home 变化后旧目标失效两栈分别通过 | 满足（候选） | 矩阵 final 两场 + 审计 `home_change` 块（quiet≈1.01s、旧/新 request_id、native_acks=1）；越界拒绝见报告 `:32`（ap-03）与负例测试日志 |
| 不把 EKF origin 当 home、未校验全球目标不静默改局部 | 满足 | px4-07 通过被 datum 复审撤回（`px4-07-datum-reaudit.json`），px4-08 用配置原点探针修复后通过；合同 `:44` 拒绝未知 datum |
| 交付命令/身份/预期/结果/失败边界；**主代理复核后才能关闭** | 交付满足；复核待主代理 | 本核对即复核输入；报告与矩阵完整 |

依赖：#12/#14/#23 均 CLOSED（gh 实读）。
差距：G5 — 报告 `:3` 与进度索引自述"实验候选、默认生产未提升"。原 AC 未要求生产提升，故不阻塞关闭；但"主代理复核后才能关闭"条款要求主代理显式复核本核对后再操作。

### #121 交付双栈 GNSS 单次运行入口与独立原始审计 — 建议：需小补（runbook 正文陈旧矛盾），实质满足

| AC | 结论 | 证据 |
| --- | --- | --- |
| 双栈运行器、冻结合同、独立原始审计器及正/负例通过 | 满足 | 票定 8 文件全部存在（实读核对）：`Simulator/wksim_runtime/gnss_task.py`、`gnss-flight-v1.json`（冻结运行为 v3）、`tools/run_gnss_flight.py`、`run-gnss-flight.sh`、`audit_gnss_flight.py`、`validation/test_gnss_flight.py`、`test_gnss_audit.py`、`docs/plan/45-gnss-runbook.md`；负例 4/4（`45-gnss-flight/audit-tests.log`）；两场最终飞行审计独立复现 pass |
| runbook 含两栈可复制完整命令、资源/输入 hash、输出 schema、失败处理；依赖脚本 --help/只读预检实际通过 | 基本满足，runbook 正文矛盾 | --help 三入口实跑退出 0；预检 `preflight-*-final.json` ok:true。命令/hash 实际在 `docs/2026-09-10-gnss-flight-report.md:18-36` 与矩阵；runbook 头部（`:3-5`）已指向，但 `:71-74` 仍保留"正式 --help/预检/飞行/审计尚未交付，不能执行"的历史表述 |

差距：G2（GNSS 原始审计输出文件未归档进仓库，仅存 WSL `/root` + 矩阵内嵌；可复算，建议归档 `*-audit-final-v3.json` 副本）；G6（runbook 历史段落与新头部矛盾，需清理或显式标注失效）。
下一步：主代理决定是否先清理 runbook 再关闭；证据实质已足。

### #111 运行一次 PX4 GNSS 中断/恢复 — 建议：受前置阻塞（#121 未关闭），证据已满足

| AC | 结论 | 证据 |
| --- | --- | --- |
| 本次范围原始审计 PASS、证据/退出身份完整 | 满足 | GNSS px4-05 审计 pass 独立复现（上 1）；矩阵 `final-matrix.json:5-29` |
| 交付身份/命令/原始结果/失败边界 | 满足 | 报告 `docs/2026-09-10-gnss-flight-report.md:38-47`（v1/v2 失败与修复保留）；px4-01/02/03 失败场归档在库 |

差距：G4 同类（票定 `validation/lunar-45-px4-run/` 不存在，证据在 `validation/45-gnss-flight/`）；G7 — 票面前置含 #121，#121 仍 OPEN，按"本票前置"规则需先关闭 #121。
下一步：#121 关闭后由主代理确认范围偏差并关闭 #111。

### #112 运行一次 AP GNSS 中断/恢复 — 建议：受前置阻塞（#111、间接 #121），证据已满足

同 #111，证据为 ap-05（矩阵 `:32-64`、审计复现 pass）；AP 原生串口字节抑制/恢复写入 27690/61344 字节、显式 LAND 原生确认见报告 `:9-12`、`:42-43`。前置 #111 OPEN → 阻塞。

### #45 GNSS中断与状态有效性恢复（父） — 建议：受子票未关闭阻塞；原 AC 证据实质满足，策略批准来源需主代理确认

| 原 AC | 结论 | 证据 |
| --- | --- | --- |
| 注入在真实传感器链、保留原始 GPS 质量与源时间 | 满足（候选） | PX4 HIL_GPS 发包门抑制 150 候选、AP 原生 UBX 串口 27690 字节抑制（矩阵 sensors 字段）；审计核对源时间不打戳（报告 `:16`） |
| 定位失效/失联/过期数据分别可观察，旧坐标不因新时间戳变有效 | 满足 | "活跃数据链上定位无效"（报告 `:10`）；stale/replay 拒绝负例 `audit-tests.log`；离线合同 `docs/2026-09-09-gnss-event-report.md:13-24` |
| 按已批准策略验证任务撤销、飞控动作、恢复后显式接管 | 证据满足；**批准来源待确认** | 撤权 `native_navigation_invalid_control_released`、PX4 `COM_OBL_RC_ACT=4` LAND、AP 显式 LAND 原生确认、新请求恢复（矩阵 + 报告 `:11-12`）。但 #121 评论（2026-09-09）指出 #22 批准仅覆盖 Agent 链路、未批准 GNSS 专属 failsafe/预算；后续 v2/v3 选择的原生 LAND 动作与 15s/4m 包线在哪一票获批，票据中无显式记录（G8） |
| 故障计划、真实传感器/状态/真值、固定预算一并记录；其他传感器故障不自动通过 | 满足 | `gnss-plan.json`/v3 冻结配置 SHA 在 archive.json；包线 4m/15°/4.5m 与 0.3m 门槛见报告 `:16`；scope 字段明示不含 G6/倍率 |
| 交付命令/身份/预期/结果/失败边界；主代理复核后关闭 | 交付满足；复核待主代理 | 同上 |

依赖：#22/#23 CLOSED。差距：G8 + 子票 #121/#111/#112 未关闭（容器票惯例需子票先关闭）。

## 差距汇总

- G1：#118 实现超出原子票写入范围的授权仅有合同文档自述，无票据评论记录 → 主代理/用户确认。
- G2：GNSS 两场原始审计输出（`*-audit-final-v3.json`）未归档进仓库；内容 = 矩阵内嵌字段，且可用当前审计器复算复现。建议下次维护窗口归档副本（本次不改证据目录）。
- G3：GNSS run-source 封存的审计器（`f4c10e35…`）与最终复算版（`8889886aa…`）不同；最终矩阵审计由当前版产出并复现一致，非证据篡改，但矩阵 `audit_sha256` 字段名实为"审计器源码 SHA"，易误读为审计输出 SHA。
- G4：#119/#120/#111/#112 票定 `validation/lunar-*-run/` 证据目录均不存在；证据实际在 `47-global-flight/`、`45-gnss-flight/`。实质满足、字面偏差。
- G5/G7：父票"主代理复核后才能关闭"与子票前置链（#121→#111→#112）流程未完成。
- G6：runbook `:71-74` 历史"未交付"表述与 `:3-5` 新头部并存。
- G8：#45 AC3 的 GNSS 专属 failsafe/预算批准来源在票据中无显式记录。

## 本次未做（边界声明）

未启动任何 SITL/UE/FC/ROS 节点；未修改生产代码、原证据、预算、Issue 状态；未 commit/推送；未嵌套子代理；未对用户修改的 `docs/Prometheus.gitmodules.reference` 做任何改动。审计复算的 `/tmp` 临时输出未保留（可复算，归档未触碰）。候选通过不等于生产提升：`final-matrix.json` 的 `experimental:true`、`production_admitted:false` 保持原义。
