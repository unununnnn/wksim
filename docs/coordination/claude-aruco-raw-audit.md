# Claude：ArUco 追踪原始 CDR＋公共命令链审计器（离线，可运行；主审修复版）

仅写 `tools/audit_aruco_tracking_raw.py`、`validation/test_aruco_tracking_raw.py` 与本文件；
其它源未动。未启动 ROS 节点/仿真/编译，未 commit/push，未嵌套。布局与字段全部以真实保留
证据核对：`validation/40-aruco-tracking-01|02`（capture root = `report.json` + `run/`）。

## 主审 7 点的落实

1. **真实嵌套**：aruco 块在 `report['task']['aruco']`（tracking-01 实测）；夹具按真实
   布局重建，不再用顶层 aruco。实测细节：未绑定即失败的 run 里 selected 栈
   `adapter_actions=None` 合法存在（adapter 未建），peer 恒 None。
2. **入口分层**：默认位置参数 = **capture root**，精确校验 `report.json`（session.run_id
   与 run 对账）+ `run/result.json`，缺一即报具体缺失；`--run-root` 显式直读 run 目录
   （跳过 capture 对账并在输出 entry 标注）。错层调用（把 run/ 当 capture root）得到
   明确报错而非隐含猜测。
3. **provenance 拒 'mock'**：start 记录三个 SHA 必须 64hex；并对账——
   `builder_sha256` == `epochs/<epoch>/source/Simulator/wksim_runtime/aruco_raw_capture.py`
   实文件 sha256；`rc_take_source_sha256` == `preflight.identities.control_candidate
   .python_sha256['rc_transport.py']`；`rc_take_lib_sha256` == `control_candidate
   .rc_transport_sha256`；preflight 本体须与 epoch result 内嵌一致且 ok。
   **真实数据上两栈两 run 全部 IDENTITY_OK**。测试夹具用显式 64hex。
4. **MOVE 全字段对照**：agent_cmd/move_mode(=XYZ_VEL_BODY)/control_level(=DEFAULT)/
   yaw_rate_mode/yaw_rate_ref/command_id/velocity_ref 三轴全部比对；双精度（adapter
   public_fields、report envelopes）经 `quantize32()`（struct float32 打包）与 raw CDR
   字段精确等值——协议量化，非物理容差；非有限值拒绝。真实 WSL 消息
   序列化→反序列化测试（0.1、1/3、3.0，不起节点）**在 WSL 实测通过**；并发现
   NEP 50 语义（`np.float32(0.1)==0.1` 为 True），断言改写为 float64 视角差异，
   审计比较语义不受影响。
5. **loss/occlusion→HOLD 不声称已证实**（本片已升级为独立门，见下节）：必要条件
   （每个 hover action 必须有真实 raw CommandRequest＋command_accepted；send_failed
   必须保持 ack_unconfirmed）之外，新增 loss_hold_correlation 独立门；门未关闭时
   该项保留在 uncovered，整体维持 pending 语义。
6. **public_chain 严格限定**：interpret 的样本 topic 必须恰好是本 uav 的
   v2/setup|v2/command|v2/state|text_info 四者；任何含 `/prometheus/` 的异机样本即失败；
   SessionState 全字段身份（version/run_id/control_epoch/state.uav_id）；**所有** TextInfo
   事件（真实 event() 基座恒带 control_epoch，node.py:112-122 已核）须 run_id+
   control_epoch 相符；每个 raw 请求恰一条终态事件；任何
   setup_rejected/command_rejected/control_revoked 或任务 status≠pass → 整体 **fail**，
   不给 clean pending。
7. **sys.path 修正**：`parents[1]`（repo root）+ `parents[0]`（tools/），不再插入文件路径。

## 真实数据验证（WSL ROS 仅反序列化，只读，不起节点）

对两个真实失败 run 逐阶段核验（hash 链真实可读 + audit 正常 fail 而非 pending）：

| run | stack | 全链 hash/计数 | provenance 对账 | public chain | 整审 |
|---|---|---|---|---|---|
| tracking-01 | arducopter | OK (227) | OK | fail：任务无会话（control_epoch 无效） | **fail** |
| tracking-01 | px4 | OK (254) | OK | fail：control_revoked | **fail** |
| tracking-02 | arducopter | OK (3017) | OK | fail：control_revoked | **fail** |
| tracking-02 | px4 | OK (3172) | OK | fail：control_revoked | **fail** |

（整审 fail 的首个抛出点是共享 timeline/物理阶段——`audit_product_timeline` 原样默认、
100ms/rate 未放宽——失败 run 本就该在此被拒；分阶段驱动证明 raw 链与身份对账先行通过。）

## 测试（45 项：本 turn 已执行，Windows 与 WSL ROS 双环境通过）

本 turn 执行结果（第六场 rate_unmet 退场后、无 SITL 运行；仅离线测试与真实消息
反序列化，未起节点/构建/压缩）：**Windows 45 项 44 过 + 1 skip（ROS round-trip）；
WSL ROS 环境 45 项全过**（含真实 rclpy round-trip 与真实 scene-03 帧验证）。
真实失败 run 回归（tracking-01/02 只读）：两栈 CHAIN_OK + IDENTITY_OK、PUBLIC_FAIL
（control_revoked）、整审 **fail**（共享 timeline 先拒）——失败 run 依旧 fail 而非
pending。

夹具按真实 schema 重建：sensor_id=`'front_rgb'` 字符串；target/metadata 的
step/frame_id 十进制字符串、valid_until_step int；happy 路径是一整条
初始 HOLD@50 → MOVE@100 → null 失效 HOLD@200（TTL 150 撤回）→ suppressed@210
（吸收第二条 null link）→ 恢复 MOVE@250 → 最终 HOLD@410（=first_step 10+4×100
场步）闭环周期（adapter 计数 actions=6/sent=5）。profile 夹具为完整
aruco-tracking-v1.json 形状，`PROFILE_SHA` 由内容动态算出并写入
`sources/...` 锚定文件。

负例/边界（knob 同名）：PNG 篡改、路径逃逸（同基名 root 外真实文件）、未映射 MOVE、
过期后 MOVE（now=160>150）、旧帧重喂、无依据 HOLD（120≤150 无 link 无失效）、孤儿
suppressed_hold、MOVE 消费 null 观测、观测身份篡改、**宽松步字符串拒收**（`' 100'`）、
**entry.target 漂移**、**task binding 边界不符**（episode_end 411≠410）、**profile
文件锚篡改**、**sensor_id 类型错**（int 7）、**过期 duplicate_record**（now=200>150）、
新鲜 duplicate 合法、消费时已过期 target 合法 HOLD、无失效不关门（no_loss）、
撤回无恢复不关门（no_recovery）、过期 MOVE 无新 link 关门（expire_hold）、
最终 HOLD 越界前发（final_early@300）、边界处 MOVE（move_past_end@420）。
既有负例（链篡改/缺 end/计数/sequence 空洞/write_failed、hover 无 raw、peer MOVE、
终态缺失、三处 epoch 身份、reject、失败任务、mock provenance、builder/rc_take 对账、
float32 量化边界、错层入口、CLI 退出码/x-mode）全部保持。夹具 bug 修复：CDR 假索引
跨栈碰撞（px4 事件 60+rid、AP 150+ 隔离）——假 deserializer 仅按 hex 键控。

**RealSceneFramesTest**：用留存 `40-aruco-flight-scene-03` 前 5 帧真实生成观测行
过 `_verify_frames`，并显式断言真实契约类型（metadata.step str、target.step/
frame_id str、valid_until int、sensor_id str）；target.step 篡改即 fail。
目录缺失时 skip。

## 未覆盖（uncovered；全过也只给 pending，exit 2）

- `loss_hold_correlation`：仅当其独立门实际关闭（gate='closed'）才移出；
  not_exercised 或无 report 层时保留。native 设定值逐字段关联（TrajectorySetpoint/
  cmd_gps_pose CDR ↔ 公共 MOVE/HOLD）；native FC ACK/动作完成不声明；DDS 发布者排他性
  与超出已对账 recorder/control pin 的执行身份。

## loss_hold_correlation 独立门（主审 6 点修复版；本 turn 已执行全部测试）

实现于 `loss_hold_chain()` + `_verify_frames()` + `_stepish()` + `_target_verdict()`，
仅在 capture-root 入口（有 report.json 层）运行；`--run-root` 入口无该层证据，
`loss_hold=None` 且 uncovered 保留该项。主审 6 点的落实：

1. **真实 schema**：camera.sensor_id 是**字符串**（真实 `front_rgb`，须匹配
   `[A-Za-z0-9_-]{1,96}` 且 == 冻结 profile camera.sensor_id）；Consumer 的
   metadata/target 的 step/frame_id 是**十进制字符串**、valid_until_step 是 int
   （真实 scene-03 帧：step `"53168"`/valid_until `53468` 已核）。新增 `_stepish()`
   严格解析（regex `0|[1-9][0-9]{0,18}` 或 int，拒 bool/空格/ lax int()  coercion），
   与 `aruco_joint_task._stepish` 完全同构。**用留存 `40-aruco-flight-scene-03`
   真实 5 帧**按 run_aruco_tracking.observation() 的构造生成观测行，过
   `_verify_frames`（真实 PNG 重算哈希经 `_frame_file` 边界转换）；篡改 target.step
   字符串即 fail。不再只造 int target 假数据。
2. **无 link 的合法 HOLD 只认三种真实形状**（aruco_joint_task.py:370-415 已核）：
   初始 HOLD（binding 已加载、尚无观测且无任何已消费有效 target——`_tracking_step`
   的 no-file/no-cached 分支）；cached-MOVE 过期 HOLD（`authority_now_step >
   活动 intent 的 valid_until_step`，expired_move 降级路径）；最终 HOLD
   （`_final_hold`：`authority_step >= binding.first_step + profile.scene 四段总步数`
   ——用 task.aruco.binding.episode_end_step 与 report binding/profile 重算对账——
   且之后无任何 MOVE）。其它无 link HOLD 一律 fail，不信 seam_reason。
3. **消费时已过期的非空 target 同样合法触发 HOLD**（`_target_verdict` 返回
   null/future/expired/before_binding/duplicate 之一即合法；新鲜有效 target 被
   HOLD 消费 = fail）。与 TargetIntent.update 的可证拒绝形状一一对应。
4. **suppressed_hold 窗口已加上界**：`last_hover_now < link.authority_step <=
   action.authority_now_step` 内不得消费新鲜有效 target；未来恢复 MOVE 不再误否
   更早的遮挡悬停（happy 夹具本身就是回归：suppressed@210 后接 recovery MOVE@250）。
5. **关门需要完整周期**：时间状态机按实际消费与 action.now 推进（now/record step
   单调、record step 不在未来——adapter 自身不变量）；只有观测到
   **null/过期失效（有活动 MOVE）→ 真实 HOLD 发送按 TTL 撤回 → 新鲜有效 target 的
   恢复 MOVE** 至少一个完整周期才 `closed`；否则 `not_exercised`，uncovered 保留。
   `duplicate_record` 必须紧跟其 MOVE/duplicate 同 step 链且 `now <= 活动
   valid_until`——重复记录不能让过期 MOVE 仍活动；episodes 边界（>= episode_end）
   只允许最后一个无 link 最终 HOLD；结束仍有活动 MOVE = fail。
6. **逐字段对账**：`entry.target == observation.target` 深等值；report binding ↔
   task.aruco.binding（first_step/stream_id/episode_end_step 重算）↔
   **冻结 profile 文件本体**（`sources/Simulator/wksim_runtime/aruco-tracking-v1.json`
   字节 sha256 == profile_sha256 == source_sha256 记录，内容 == report.profile）；
   metadata.image == image_path 基名；`entry.now_step == authority.tick`。

判定仍全部 fail-closed；ACK ≠ 动作完成（note 明示 public send+acceptance only）。

## 未覆盖（uncovered；全过也只给 pending，exit 2）

- `loss_hold_correlation`（见第 5 点）；native 设定值逐字段关联（TrajectorySetpoint/
  cmd_gps_pose CDR ↔ 公共 MOVE/HOLD）；native FC ACK/动作完成不声明；DDS 发布者排他性
  与超出已对账 recorder/control pin 的执行身份。

## 主会话后续

45 项测试双环境已过，工具就绪。下一场真实成功录制产出后，在 WSL ROS 环境运行：
`python3 tools/audit_aruco_tracking_raw.py <capture root 的 WSL 路径> --output <root 外新文件>`
（或 `--run-root <run 目录>`，该入口无 report 层、loss-HOLD 门不运行且 uncovered 保留）。
本工具只读；schema_version≠1 即 fail-closed 待复核。成功录制若保留
binding/frames/observations 且观测到完整 失效→撤回→恢复 周期，门关闭后 uncovered
只剩 native 三项（setpoint 关联/ACK/排他性），整体仍 pending。真实运行至今无 RGB
帧产出的成功录制；不声称任何 flight 通过。
