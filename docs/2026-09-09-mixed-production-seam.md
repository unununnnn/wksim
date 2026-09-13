# #33 mixed / P+V 的正式 profile 接缝

2026-09-09。这是有界源码审阅和后续实施顺序，不是生产提升结果。主代理核实本子任务实际为 `gpt-6-astra/high` 后 RELEASE；无嵌套代理。只阅读指定源码、报告、配置和 #33，唯一写入为本文；没有构建、运行测试/准入、启动 SITL、刷新索引、改 profile/pin/旧证据或写工单。审阅期间主代理正在执行 AP native timeout；本文不判定该场结果。

**建议保留旧 `joint_quad_dds_v1` 的固件、控制和证据行，新增一个明确命名的 mixed/PV joint profile，先补最终组合的 P+V 实飞，再接正式任务入口。** `joint_quad_dds_mixed_pv_v1` 是建议的新 ID，当前不存在。用户“全程你自己确认即可”已授权此前范围内的常规工程和提升；本路径没有新增审批前置。不是把所有 native 边界都做完才允许接线，也不能仅将实验 PASS 改名为正式 PASS。

## 已有证据与实际缺口

| 能力/资源 | 已有证据 | 不能由此推出的结论 |
| --- | --- | --- |
| mixed nominal | `joint-public-flight-zk5_nukn`，135,328 tick，双栈逐 1ms/原始包/连续倍率审计 PASS；见 [mixed 报告](2026-09-09-mixed-flight-report.md) | 尚未通过正式 joint profile 启动；不是 P+V 轨迹或异常边界证明 |
| 完整 XYZ P+V/yaw | `joint-public-flight-qi66lh_y`，116,024 tick，原始审计 PASS；见 [PV 报告](2026-09-09-pv-flight-report.md) | 实际 AP PV 二进制 SHA 为 `7dfeb027e06712380f499611e2ba1bc809ed71f74ae477807ac5b2d51d62bb44`，控制为 ami5Gd；不能代验最终 mixed/OEvS3W 组合 |
| 最终拟选 AP mixed | manifest `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json`，SHA `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`；二进制 SHA `509c60163b3fceb261d17ceb2d0814c10ec65846e5d8d6689375e3ee05ab731f` | 本文从指定报告读取身份，未重跑当前全源/二进制核验 |
| 最终拟选 Control | `/root/wksim-joint-control-OEvS3W/build.json`，SHA `d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e` | mixed flight 只启用 mixed 参数；同一安装具备 PV 分支不等于该分支已在此组合上飞过 |
| 当前正式行 | `Simulator/wksim_runtime/joint-profiles.json` 仍为 FVMjak + AP clock-stop，PX4 state 固定 | 不能静默把此 ID 的 AP/control 换成新候选后沿用旧证明 |

上表二进制身份以完整 SHA 为准；历史 manifest 的 `built-not-admitted`、`production_admitted=false`、`flown=false` 是构建封存时状态。后续正式准入应另写 profile/evidence 绑定，**不修改这些历史字段来表示今日已飞或已提升**。

已实读 `AGENTS.md`、`CONTEXT.md`、父目录 Context Map；wksim 没有 `docs/adr/`，父/兄弟 ADR 不自动成为本迁移要求。结构结论来自以下已知文件及其直接引用，未用过期图覆盖新增实现。

## 必须补的生产接缝

1. **固件清单类型与完整证明。** `joint_profile.select_profile()` 只接受旧 ID；`check_resources()` 又要求描述符等于该旧行，AP manifest 必为 `wksim-build.json`，并交给 `_firmware()` 读取 `commit/source/repository_inputs/artifacts`。mixed 是 `mixed-build.json`，经 `mixed-source.json` 和 mixed→PV→clock 链验证，schema 不同。直接换路径必被拒绝。应在已选 profile 内显式标明受支持的 AP manifest 类型，严格分派到现有 mixed verifier；返回正式运行器所需的 AP `path/sha256/commit/source_files` 身份，保留全部链核验。不要把 mixed 伪造成旧 build schema，也不要按“文件存在”降级。

2. **证据按实际 schema 和能力绑定。** 旧 `check_resources()` 要求每个 flight 的 `manifest_sha256` 恰等于 AP/PX4/control 三钉，且从最后一份 flight 同目录的 `arducopter-preflight.json` / `px4-preflight.json` 取 Agent 身份。候选 `run_joint_flight.py` 的 PV/mixed 分支只在顶层记录 AP/control 两钉；固定 PX4/Agent/model 真实身份位于实验 admission 的 baseline，亦没有生成旧位置分支的逐栈 preflight 文件。审计严格验证了这些真实来源，但不能原样套旧 schema。最小改法是给新 profile 使用一个新的、固定 schema 的证明描述，引用未改动的 run、audit、admission 和完整三资源身份，从候选真实位置取证。mixed 与 PV 两个必需 task profile 都应有与本行**同一 AP binary、control manifest、PX4、model**匹配的成功原始审计；不能因“找到任意 healthy flight”就开放全部能力。

3. **任务类型不能决定固件类型。** `run_joint_flight.py:782` 的 PV CLI 排斥 `--ap-mixed-manifest`，`ap_pv_candidate._pv_record()` 又强制 PV 目录/schema；mixed CLI 反过来只允许 mixed task。补一个窄、显式的组合：“PV task + 已验证 mixed manifest”，保持旧 PV task + PV manifest 原分支不变。继续使用 mixed verifier 验证固件，能力/任务描述必须写 PV；`audit_pv_trajectory.py:126` 当前强制 `pv_admission` 与 PV schema，也要新增严格的 mixed-firmware 身份分支。新分支保留原轨迹、逐包、每 1ms、停止/重锚和倍率门槛，不通过重写旧 PV admission 来迁移成功记录。

4. **正式启动和任务。** `runtime.launch_spec()` 只传 `arducopter_position_yaw:=true`；PV/mixed 两个只读参数仅由实验 runner 追加。`node.py:35,59` / `native_arducopter.py:46` 已允许分别或同时启用，默认仍关闭。由新 profile 的已准入能力派生启动参数，而不是给用户一个任意绕过固件的布尔开关。`joint_config.py`、`joint_task.py`、`joint_evidence.py` 当前只实现 `public_position/public_velocity_yaw`；需要增加明确的 PV/mixed task selector、任务执行和相应真值/原始证据验证。只改 `launch_spec` 会让新能力仍无完整的正式使用流程。

5. **正式 task 的生命周期和观察者。** `PVTask`/`MixedTask` 已有任务语义，可复用；但 `PVTask.request_graph_ready()` 要求恰好两端点且 recorder 名为 `wksim_joint_flight_clock`，正式 `JointTask` 要求一端点；PV 两段还有 ready/go 轨迹协调。正式 joint supervisor 的 `JointMonitor` 不能被假定为该 recorder。迁移这些具体接线并保留精确 endpoint/GID 和 go 身份，不改为 `>=1`。正式 worker 的 scene epoch、Task 接管、暂停/重启语义也要由已支持的流程明确承接；若新任务初版不支持某个操作，在操作受理前拒绝并说明，不能在既有恢复分支里落回 position 后声称原轨迹已恢复。

## 最小实施与验证顺序

1. **冻结最终组合，先做 P+V 兼容性实飞。** AP mixed 七文件补丁保留原 P/P+V/velocity 分支，控制安装亦含两个独立开关，这支持“无需重新编译就值得试”的源码判断；不支持“已经验证兼容”的结论。使用 mixed manifest + OEvS3W，开启 PV，重跑既有两段 12s PV 合同、两次停止/重新锚定/降落及原始审计。若拟交付同时启用 PV/mixed 的 profile，则该验证和最终正式验证也应使用这两个实际启动参数；当前 mixed nominal 的单开关结果不能自动代验双开关状态。
2. **补 profile 验证、证据描述和正式任务接线。** 只支持当前确有两种 manifest schema 和两种新 task，不建立通用插件/任意固件适配框架。新例子显式选择新 profile；旧例子保持原身份。profile 未满足必需证据时准确拒绝且不创建孩子进程。
3. **验证旧用户路径兼容性。** 新组合至少执行旧 `public_position` 与 `public_velocity_yaw` 的命令/输出差分和正式任务回归，确认 P、V、yaw、停止与模式切换没有被新分支截获，且原有任务可按其原合同运行。mixed nominal 内的位置准备不足以覆盖全部旧 velocity/yaw 或 scene recovery。旧 ID 的原资源预检/启动与当前新 ID 预检也各读回；不可只验证新 ID。
4. **新 profile 的真实使用流程走通并封存。** 从正式 JSON/CLI 入口选择任务，完成显式 start-task、实际公共请求、双栈反馈、原始连续真值、停止/新锚、正常落地及 owned cleanup。证明内容应足够再次独立审计，并记录正式执行源码；实验 PASS 保持实验身份。最后才把新描述/证据加入正式 catalog，输出用户可执行配置、命令和预期结果。
5. **按实际改变的共享入口处理旧提升链。** 若保留旧行与旧安装、并让新 profile 有独立控制来源，旧 independent/session catalog 不需要仅因为增加新 profile 就全部换绑。如果要把现有 `independent_quad_dds_v1` 或 MUlZd0/session 的控制安装也提升到 OEvS3W，则必须复用下节流程，不能只同步 Python 或修改旧 result 的哈希。

正式路径的接线检查和有界负例先于重型实飞；实现稳定后由主代理预约串行运行。本文不安排与当前 native timeout 并跑。原误差、1ms、0.5×、100ms/滑窗门槛保持；持续 1×/#20/G2 是其自身义务，不新增为本接缝的隐含前置。

## 旧 profile 和现有提升流程的复用范围

现有 `joint_profile._control()` 同时比较当前仓库、候选 staged、installed Python。当前仓库为 OEvS3W 的新控制源，而旧行仍钉 FVMjak；旧行的“当前源码相等”会如实拒绝。这是**已经存在的生产准入缺口**，不能以“目录/行没改”宣称旧入口完整兼容，也不应覆盖 FVMjak 安装内容来消除错误。

最小、显式的保留办法，是将旧行标识为已封存历史控制来源，复用 `ap_pv_candidate._sealed_control()` 的 staged/installed/manifest/build-input 全验证；旧行只能从该安装执行，历史 flight/control 摘要必须一致。新行仍把当前仓库/staged/installed 绑定到 OEvS3W。两种来源在已钉 profile 中选择，拒绝任意用户配置跳过当前源码，不把 `_control()` 全局改为忽略源差异；对新行改源码、旧行改已安装文件、错误 overlay 都必须继续拒绝。当前 `_sealed_control` 位于 tools，若正式代码需要复用，移动/提取到现有身份模块并保留历史实验分支含义即可，不新增大框架。

另一条有效路径是**显式提升旧正式行及其所有受影响入口**，但其验证/证据重建范围更大，且必须清楚声明旧 ID 换了版本，故不是此次保留旧固件/控制的首选。现有 [控制提升报告](2026-09-08-gcs-promotion-report.md) 已解决循环证据问题；此前 [提案](2026-09-08-control-promotion-deadlock-and-proposal.md) 的额外用户决策阶段已结束，不应重复要求批准 A。

具体复用：`independent_profile.check_profile()` 的 `promotion_flight:true` **仅在 `joint_profile.check_resources()` 已通过之后**省去旧 independent flight 绑定，仍写 `flown=false`/`flight_provenance='promotion_flight'`。`preflight.control_sources()` 的 promotion 分支仍要求旧 joint 行的已钉控制和完整 installed snapshot。它们不是 mixed schema、新 joint proof 或正式 task 支持的绕过开关；joint config 目前也没有 promotion 字段。

若确要提升独立/session：先完成 joint 资源/证明准入，再用显式 promotion 运行双栈独立三航点；新旧 GCS 联测不是每次控制提升的必要依赖，已有纯 `tools/validate_independent_profile.py` 可承接飞行。旧 session 六请求回归按原固定固件运行；`tools/rebuild_promotion_evidence.py --independent ...` / `--session ...` 产出新的只供替换审阅的 catalog，保留实际 promotion config 和执行源码。最后才替换默认 catalog/必要安装快照、移除未来启动配置中的 promotion 标志，双栈默认预检读回。保留 baselines/resource_locations 的既有来源，不改旧 evidence；此流程不能代替新 mixed/PV profile 的组合实飞。

## 哪些是真阻塞，哪些应另列

| 项目 | 对本交付的作用 |
| --- | --- |
| 最终 mixed/control 的真实 P+V 兼容性 | 若新 profile 宣称 PV，属于必需证据；PV baseline PASS 不能替代 |
| AP manifest/profile 证明接线、正式 task/参数/审计、旧路径兼容 | 实际工程阻塞；没有这些使用者仍只能用实验脚本或预检拒绝 |
| 已在执行的 native timeout + 新公共接管 | 该 native 停流保证的必要证据；结果由主代理当前场审计，不能用 nominal 代验，也不阻止先写生产接线 |
| Fence 拒绝、home/origin 改变/reset、native pause/resume、水平避障主动触发 | 补丁切片替身测试没有真实执行这些。对这些保证必须另有实跑；若首个正式 profile 明确限定已验证正常 home/origin/环境、未支持 native pause，不能把所有此类测试自动扩张为无限提升前置。任何已有冻结合同明确要求的边界仍须履约，#33 是否关闭由主代理据完整义务复核 |
| 任意空中控制热重启、完整轨迹恢复、垂向速度避障、terrain、加速度执行/yaw-rate 组合 | 当前未交付范围；明确拒绝/声明不支持。A 仅保留参考，不作原生前馈；不能由消息字段推断生效 |
| 持续 1×、#20/G2、Full、#42 用户 GCS 操作 | 独立义务，不由 mixed/PV 0.5×候选完成，也不凭本接缝关闭 |

## 后续实际编辑位置

| 文件（均以 wksim 根为基准） | 必要改动/检查 |
| --- | --- |
| `tools/ap_mixed_candidate.py`、`tools/ap_pv_candidate.py` | 固件 verifier/基线链复用；显式支持 mixed 固件跑 PV，分离构建身份与 task 能力；旧实验准入保留 |
| `tools/run_joint_flight.py`、`tools/run-joint-flight.sh` | 最终组合 PV 兼容性入口、完整资源证明、真实双开关参数/源留档；不可改写旧 run |
| `tools/audit_pv_trajectory.py`、`tools/audit_mixed_control.py` | 新组合严格身份分支、正式证据接入；数值/包络/连续时钟校验复用，保留旧审计可重放 |
| `Simulator/wksim_runtime/joint_profile.py`、`joint-profiles.json` | 显式新 ID/manifest 类型/控制来源、能力→证明匹配、准确身份与 Agent 来源；保留旧 row |
| `Simulator/wksim_runtime/joint_config.py`、`joint_task.py`、`joint_evidence.py`、`joint_runtime.py` | 新任务选择/worker/observer/ready-go/审计/生命周期受理边界；`joint_runtime` 不能仅复制实验参数而缺任务协议 |
| `Simulator/wksim_runtime/runtime.py` | `launch_spec` 从已准入 profile 能力派生 PV/mixed 参数；实际 import/overlay 仍由正式准入核验 |
| `tools/pv_trajectory_task.py`、`tools/mixed_control_task.py` | 复用任务语义并将具体 recorder/scene/go 接缝纳入正式运行；不降低端点数量和身份约束 |
| `Simulator/wksim_runtime/examples/` 和用户运行说明 | 新 profile 的可执行配置/命令、PV/mixed 实际版本、A/yaw-rate/恢复限制；旧例子保留原资源 |
| 仅在提升共享独立/session 时：`independent_profile.py`、`preflight.py`、`independent-profile-evidence.json`、`capability-index.json`、`tools/rebuild_promotion_evidence.py` | 复用既有显式 promotion 和 catalog 重建；新 profile ID 选择不能继续误用硬编码旧行；实际独立/session 回归先于默认换绑 |

本文不修改控制节点或原生补丁：现有节点已经具备两个独立只读能力开关。若后续 formal scene 适配确实要求改控制源，必须重新封存新控制候选，并以实际最终组合重跑受影响证据，不能继续把 OEvS3W 的旧飞行说成新控制已飞。#33 仍 OPEN。
