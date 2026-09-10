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
5. **loss/occlusion→HOLD 不声称已证实**：仅保留必要条件（每个 hover action 必须有真实
   raw CommandRequest＋command_accepted；send_failed 必须保持 ack_unconfirmed）；
   "消费的 null 观测/过期 authority → 该具体 HOLD" 的因果关联证据未保留，列入
   uncovered `loss_hold_correlation`，整体保持 pending 语义。
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

## 测试

Windows：20 过 + 1 skip（真实 ROS 消息 round-trip 在 Windows 跳过）；WSL ROS 环境该
round-trip **实测通过**。负例：链篡改/缺 end/end 计数/sequence 空洞/write_failed、
hover 无 raw 请求、peer MOVE、无终态事件、raw 请求/SessionState/终态事件 control_epoch
不符、reject 终态事件、任务失败不得 pending、mock provenance、builder 与 epoch source
不符、rc_take 库 pin 不符、float32 量化边界（含 1e-8 漂移拒绝与 NaN 拒绝）、错层入口、
CLI 退出码（pending=2/fail=1）与 x-mode 不覆盖。

## 未覆盖（uncovered；全过也只给 pending，exit 2）

- `loss_hold_correlation`（见第 5 点）；native 设定值逐字段关联（TrajectorySetpoint/
  cmd_gps_pose CDR ↔ 公共 MOVE/HOLD）；native FC ACK/动作完成不声明；DDS 发布者排他性
  与超出已对账 recorder/control pin 的执行身份。

## 主会话后续

agy 交回锁 schema 后，在 WSL ROS 环境对新的真实成功录制运行：
`python3 tools/audit_aruco_tracking_raw.py <capture root 的 WSL 路径> --output <root 外新文件>`
（或 `--run-root <run 目录>`）。本工具只读；schema_version≠1 即 fail-closed 待复核。
