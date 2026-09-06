# 单机位置任务、暂停与取消

这是 Prometheus `tutorial_demo/basic` 中 ENU、BODY 位置和 waypoint 任务流程的 ROS2 迁移。原 ROS1 源码不动；全球经纬航点另属 #47。当前安装控制层为 `/root/wksim-ros2-MUlZd0`，含已实测的空中当前位姿接管和 AP 显式 BRAKE 支持；本次任务生命周期改动不修改该安装、消息类型、原生适配器或动力学方程。

## 正式入口

从 wksim 目录，在 Ubuntu-22.04 执行：

```bash
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/px4-mission.json --output-root validation/my-mission
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/arducopter-mission.json --output-root validation/my-mission
```

每次新实验使用新 run_id；输出目录不得已存在。同一配置结构只选择不同 stack。当前示例为 ENU `[2,3,3]`、原地转向 π/2、BODY FLU `[1,0,0]` 相对移动，逐点连续驻留 2 个飞控 boot 秒，再请求 LAND、观察解锁状态解除和物理落地。它们仍是独立实验，不是联合场景。

配置可选 `mission`；未设置时，旧的单航点回归流程不变。任务必须显式使用 `session_v1`，本票不准入 mission 与地面控制重启的交叉组合。

```json
{
  "version": 1,
  "cancel_policy": "land",
  "waypoints": [
    {"frame": "enu", "position_m": [2,3,3], "yaw_rad": 0, "dwell_s": 2},
    {"frame": "enu", "position_m": [2,3,3], "yaw_rad": 1.5707963267948966, "dwell_s": 2},
    {"frame": "body_flu", "position_m": [1,0,0], "yaw_rad": 0, "dwell_s": 2}
  ]
}
```

1–8 点，位置三分量均为有限数值，不接受布尔值、未知字段、重复 JSON 键或非法常量。当前 quad-X 输入范围：ENU x/y ±20m、z 1–10m；BODY 每轴偏移 ±10m，派发时解算后的 ENU 仍必须在同一范围。yaw_rad 为 ±π；驻留 2–10s。它们是此任务的准入范围，不是完整模型能力边界或正式动力学等价预算。

BODY 使用真实 `XYZ_POS_BODY` 命令，控制层在首次计算时锁存当前位置/偏航。任务在发送前另存一份新鲜状态快照，独立估算 ENU 目标作验收；不拿已输出的设定值反推期望。两份快照可能相差一个控制周期，不宣称同步采样。水平遵循 FLU→ENU 的偏航旋转，z 和 yaw 都是相对量；不将 BODY 位移每帧重复累加。

## 进度与身份

终端打印阶段；运行目录有原子替换的 `mission-status.json`、追加写入的 `mission.jsonl`、完整公共消息 `prometheus.jsonl` 和最终 `result.json`。

- `accepted`：配置受理，不是飞控确认。
- `takeover`：真实模式和公共控制状态确认任务接管。
- `running`：当前航点执行；command_accepted 不表示已到达。
- `pausing` / `paused` / `resuming`：撤销任务输出并观察交接、等待新的显式请求、重新请求并观察接管；都不是停止物理仿真。
- `landing`：已有 LAND 请求在执行；不是落地确认，不提供暂停/恢复操作。
- `completed`：全部点反馈连续达标并观察公共落地；最终还须 result 的独立物理检查通过。
- `cancelling` / `cancelled`：分别表示正在处理取消、任务不再派点且所选处置已得到公共反馈；是否物理落地看 `safe_landing`。
- `failed`：失败终态，不自动重获控制。实验进程收回不等于安全降落。

run_id、每次新建的 mission_id、控制节点 control_epoch 分别标识实验、任务和控制代次。native_generation 标识当前原生状态代次。公共请求 request_id 采用新鲜 SessionState 的 last_request_id 高水位；等待 ACK 始终匹配该次请求的固定 ID。MOVE/LAND 的 command_id 大于本任务及已观察的已受理命令；取消/恢复不回绕，不重放旧请求。

## 暂停航点任务，不暂停物理

从 `mission-status.json` 读取 run_id、mission_id、当前 action_token 和 allowed_actions，再提交：

```bash
python3 tools/control-wksim-mission.py RUN_DIRECTORY --run-id RUN_ID --mission-id MISSION_ID --token CURRENT_TOKEN --action pause
# 等待 state=paused，然后重新读取新的 action_token
python3 tools/control-wksim-mission.py RUN_DIRECTORY --run-id RUN_ID --mission-id MISSION_ID --token NEW_TOKEN --action resume
```

Windows Python 也可对共享运行目录提交。成功只表示提交，完成须看 `mission_paused` / `mission_resumed` 反馈。令牌与 run/mission/epoch/native_generation 绑定，一次运行中的每个令牌最多受理一次；转换状态后旧令牌失效。文件只发布不覆盖，校验非普通文件、符号链接/junction、重复 JSON 键、非有限数值、大小和身份；这不是本地管理员攻击防护。

显式暂停经现有 Prometheus SET_PX4_MODE 请求：PX4 使用 AUTO.LOITER，AP 使用 BRAKE（保持原 AUTO.LOITER→LOITER 映射，BRAKE 不等于 RC 接管）。等待 ACK 和实际模式/控制状态后才进入 paused。外部操作者已切走模式时，只观察其转换，不另发保持命令。WSL 物理与飞控继续运行，任务不派发 MOVE、模式或保活目标；状态失效和原生故障不作为可恢复的操作暂停。

恢复必须使用 paused 状态的新令牌，发新的 COMMAND_CONTROL 请求，先保持当前位姿，再用新 command_id/request_id 派发被中断的目标。BODY 首次仍使用原生 XYZ_POS_BODY；恢复使用首次记录的 ENU 目标和航向（XYZ_POS），不按暂停后的当前位置重新锚定。原始独立估算与控制层首次采样仍可能差一个控制周期，不宣称数值逐位相同。中断记录、每次派发身份和原停留窗口保留；恢复后必须重新连续驻留整个 dwell_s。

同一 epoch 内 native_generation 改变、控制 epoch 改变、失联或状态时钟回退，不会重放已记录目标。暂停中收到取消而其他操作者仍在空中时，取消保持待处理：操作者可自行落地，或明确提交 resume 授权新接管后由任务 LAND；取消本身不会自动抢回控制。

任务物理进程使用 `--run-until-stopped`，不存在旧的 3600 仿真秒隐含截止。运行器只从 `180+45×航点数` 的活动墙钟预算中扣除真正等待操作者的 paused 时间；模式 ACK、状态新鲜度、进程存活和物理执行器超时不暂停。结果分别记录总墙钟、操作者等待、活动墙钟。这不是联合场景的冻结/单步功能，也不保证无限燃料/电池或故障下继续飞行。

## 取消不是即时停止

从状态文件核对目标身份后，通过本机文件通道提交；不需要加入实验的隔离 DDS 网络：

```bash
python3 tools/cancel-wksim.py RUN_DIRECTORY --run-id RUN_ID --mission-id MISSION_ID
```

Windows 也可用本机 Python 和 Windows 运行目录路径调用。两个身份参数必须显式提供。CLI 成功仅表示请求已提交，应继续查看 status/result。

请求文件只允许一个当前身份的取消操作，限 4096 字节，原子独占发布、不覆盖既有请求；同一有效请求幂等，旧运行/旧任务、坏文件和符号链接拒绝并记录。它是可信本地协作机制，不是防御本地管理员的安全机制；要求文件系统支持同目录硬链接。已结束的任务不能重新激活。

取消一经任务观察，就不派发后续 MOVE。已送出的请求先等真实受理/完成反馈或超时，不伪造撤回。取消发生在起飞接管过程中，已接受的接管流程可能完成后才进入降落处置。初始未解锁地面取消不发飞行命令；已解锁但尚未起飞只允许普通地面 disarm，适配器仍核对原生 landed 状态。空中只有新鲜状态、当前任务所有权仍在时才发 LAND，并等待实际落地；普通外部控制释放按上述暂停规则等待，数据失效仍失败。不强制 disarm、不伪造 RC、不自动切回 OFFBOARD/GUIDED。取消发生在正常降落中不会重复发 LAND。

外部控制交接即使没有 control_revoked 文本事件，也通过公共模式和控制状态识别；公开设置可能先撤销 COMMAND_CONTROL 再完成模式 ACK，期间不派发新航点。旧 `validate_mission_product.py external_mode` 预期立即失败拆除运行的诊断已拒绝执行，新的 `run-mission-lifecycle.sh STACK external_resume` 验证保活与显式恢复。未用实际 QGC 交互冒充本测试。

## 验收时间与误差

逐点位置误差 ≤0.5m、速度 ≤0.5m/s；转向测试增加偏航误差 ≤0.15rad。连续驻留窗口内每次公共反馈都须达标。超调使整个窗口重启并写 `waypoint_dwell_reset`，15 个墙钟秒内不能稳定完成就失败；不能把零散达标片段相加。链路失效、时钟回退仍立即失败；普通外部接管进入暂停，不自动重试，显式恢复后开始新的完整驻留窗口。

驻留使用原始飞控 boot 时间。开始/结束时另存原始物理日志记录游标，独立复核对应窗口的位置、由物理位置差分得到的速度以及四元数偏航。两种时钟不重标、不强行等同；游标采集延迟会使物理窗口时长略不同，报告保留原值。报告中的这些控制集成门槛不替代尚待确认的正式动力学/传感器数值预算。

所有正常结束还需要新鲜、有效、已解除解锁的公共状态，以及新鲜物理地面真值。取消且落地的 result.status 是 `cancelled`，不是把未完成航线记为 `pass`；CLI 对这种已处置取消返回 0。失败返回非零，`stop_kind=unsuccessful_isolated_teardown`。

## 本票限制

尚不包含空中 DDS 失联处置、联合共享时钟、动态重规划/增删点、重启后续飞、原生全球位置任务、RC 实机和 MATLAB；这些继续由原计划工单承担。暂停/恢复交付为 CLI 和状态文件，工作台按钮及实际 QGC 交接仍须另行实现/验收。
