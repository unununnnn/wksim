# Claude：末尾 HOLD 原生等待 独立复核（仅当前 ~40 行运行时）

对象：仅 `aruco_joint_task.py:443-485` 当前版 `_final_hold`/`_wait_final_hold_native`
（bc092f4 后已加 armed+COMMAND_CONTROL 门；publisher guard 的 state/native GID 绑定
另行验收，不在本片）。native_holds 审计器与大型留存数据未重审。结论：**未发现阻断性
身份/截止缺陷**。

已核对的链路（行号）：

- 请求身份：`expected_request = self.request_id`（457）在最终 HOLD 的
  `Task.send` ACK 之后取值，`task.py:334` 先自增再发布、adapter 借宿主 send
  （aruco_task.py:152），故该值即本 HOLD 的 request_id。
- 谓词身份（472-475）：last_request_id == expected、run_id、control_epoch、
  COMMAND_CONTROL、非 failsafe、`state.armed`、`self.fresh()` 全部逐 poll 复查；
  任一失守即持续 False 直至超时。
- 边界语义（477-483）：首个合格 SessionState 的 RMW source_timestamp 记 boundary，
  再要求 `boundary < native_stamp < state_stamp`（当前最新 state）——严格不等；
  相等/缺样本/缺后随 state 均停滞。
- 截止：`Task.wait` 原有语义（task.py:310-318 超时 raise TimeoutError，
  pump 对 stale/error 同步 raise），谓词返回值未被忽略成放行；超时即任务失败、
  **不会 LAND**（`_land_tail` 在 521 行之后）。复用冻结 profile 的 0.5s ROS 预算，
  未新造 sleep 或放宽倍率。
- AP13/PX410 两缺口的根因均被该次序覆盖（先 state 承载本 HOLD → 再更新原生 →
  再后随 state，然后才 LAND）。

两个非阻断注意项：

1. **447-448/457**：`_last_sent == 'hover'`（如遮挡中收场）时不发新 HOLD，等待
   仍执行且 expected_request 是**旧的**最后请求——退化为"hover 仍在原生流出"
   证明。有界、仍先于 LAND，安全；但与 docstring"its accepted SessionState"
   字面合同不符，建议主会话知悉即可。
2. **479**：硬依赖非零 RMW source_timestamp；不支持源时间戳的 RMW 下该等待
   恒超时（fail-closed，但为永久失败模式）。当前栈真实留存均带非零戳，无影响。
   （另：472 行 `current is None` 为死防御，deserialize 只会 raise。）

独立负例（`validation/test_aruco_final_hold_review.py`，自带 harness，不改主文件；
WSL ROS 2 过 / Windows 2 skip）：

- `test_native_without_a_following_state_cannot_pass`：boundary 之后已有更新原生
  样本（101>100）但无后随 SessionState → 必须 TimeoutError，LAND 不得放行。
- `test_unarmed_failsafe_or_non_command_state_cannot_confirm`：后随 state 分别
  失 armed / 起 failsafe / 出 COMMAND_CONTROL → 均不得确认（中间有合格原生样本
  亦然）。

本片未改 runtime/审计器/配置，未嵌套，未 commit；无 SITL 并发。初始接管、公共
ACK、graph 排他身份仍由各自独立验收负责。
