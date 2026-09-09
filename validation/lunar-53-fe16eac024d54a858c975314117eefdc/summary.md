# #53 `40-target-command` ArUco 目标到公共速度意图摘要

## 票据与边界

- GitHub：#53 `[Luna] 实现新鲜ArUco目标到公共速度意图（两文件）`
- 稳定键：`40-target-command`
- 绑定时状态：`OPEN`，标签含 `ready-for-agent`。
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`20a627e feat: audit Hex physics evidence streams`
- 仅新增 `Simulator/wksim_perception/target_intent.py` 与 `validation/test_target_intent.py`；未发布 ROS/DDS、飞控或私有控制命令。

## 实现

`TargetIntentConfig` 强制显式提供 `desired_body_flu_m`、`gain_per_s` 和 `max_speed_mps`，不提供飞行默认参数。`TargetIntent.update(target, authority_step=...)`：

- 校验 `wksim.aruco-target.v1`、run/epoch/stream 绑定、目标 step 的未来/重复/回退状态和 `valid_until_step`（边界包含）；
- 使用 Consumer 的 `position_body_flu_m` 计算误差并乘显式增益，按三维速度向量范数限速；不读取 `velocity_world_ue_mps` 诊断值；
- 有效输出只包含 `XYZ_VEL_BODY`、`velocity_ref`、`yaw_rate_mode=true` 和 `yaw_rate_ref=0` 等公共意图字段；
- 缺失、未来、过期、外来、无效或重绑定目标返回零速度 `HOLD`，并清除历史 step；没有 ROS 依赖。

## 测试

精确命令：

```text
python -m unittest validation.test_target_intent -v
```

结果：`7` 项通过、`0` 失败、`0` 错误，耗时 `0.001s`。覆盖轴向限速、斜向向量范数限速、忽略世界诊断速度、未来/过期/外来/缺失、丢失后重获、重复/回退、显式配置、绑定和重绑定清理。

负例均返回 HOLD，速度为 `[0.0, 0.0, 0.0]`；正例只返回 `XYZ_VEL_BODY` 意图。测试输出保存在 `validation/lunar-53-fe16eac024d54a858c975314117eefdc/test.stdout.log`，SHA256 `b1020afde8050ca73721b2970f2f90389f2b9992d9d3aed2c55fe751be4e0632`。

## 身份与证据

- ArUco 输入契约报告 SHA256：`85399f3e2ce92b5884e75520d717aebd397ad080dbe4a7494cacc4652cf298a5`。
- 既有 Consumer `Simulator/wksim_perception/aruco.py` SHA256：`8e51688ad16fe929ae01a27294805cdf2aa54372d88bcb31a7d260fb38e2ae0b`。
- 新模块 `Simulator/wksim_perception/target_intent.py` SHA256：`b271de310adf45e94445f74b50fea2337fea2e76e7e5ce28fc0a0be4fba88cc9`。
- 新测试 `validation/test_target_intent.py` SHA256：`1d4a7cfe577c593e8e6c3dfb9bf7548c28d45da00a92abaa66cee283cade712a`。
- 活动证据目录：`validation/lunar-53-fe16eac024d54a858c975314117eefdc`，包含票据选择、命令、测试结果和原始 stdout。

## 完成判定与未覆盖范围

本票完成条件满足：两个纯模块/测试文件通过，body FLU 输入和新鲜度/绑定校验可复查，诊断世界速度没有被直接当作命令。可以评论并关闭 #53。

本票不证明真实 UE 标记、真实相机跟踪、延迟/遮挡飞行预算、双栈任务接入、动作完成或 #40 父票关闭；这些仍需相应真实集成前置。
