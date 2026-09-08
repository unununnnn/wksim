# #32 双栈速度与偏航收口

2026-09-09。原始正式联合速度场景已完整通过，独立入口补齐机体系速度及 PX4 速度+yaw 角组合；主代理重新审计原始数据。此前各次 rate_unmet/freshness/驱动失败保留。本次收口只覆盖 #32，不宣称持续 1×、#20/G2 或 Full 已完成。

## 正式联合场景

未改原流程，执行 `python3 -B tools/run_joint_velocity_yaw.py`。证据目录为 `validation/joint-velocity-yaw-vl8z83cz`，原始输出根 `/root/wksim-formal-joint-iaqqu14j`，run_id=`joint-velocity-yaw-iaqqu14j`，epoch=`7a52dde6be924beca8837680ea3d29b8`。driver、flow、manager 均 pass，epoch 正常 stopped，任务 completed、无 fault、所有模型/控制/飞控正常退出。

两机共享 79,832 个真实 1ms 物理步，连续同高于 1m 共 27,652 tick。79,833 次权威时钟发布、19,949 个严格原生输入屏障；AP/PX4 原始公共状态分别 15,957/15,949 条。原生逐包、模型逐步、公开事件/请求及最终有效落地状态分别重算，不以任务报告代替物理数据。

| 原始物理门 | AP | PX4 | 冻结门槛 |
| --- | --- | --- | --- |
| 惯性速度最大逐轴误差 | 0.02443m/s | 0.09036m/s | ≤0.3m/s，连续3s |
| 零速保持最大速度 | 0.02836m/s | 0.03558m/s | ≤0.25m/s，连续4s |
| 零速保持最大漂移 | 0.57775m | 0.61463m | ≤1m，连续4s |
| 0.5rad/s偏航积分最大误差 | 0.14310rad | 0.11375rad | ≤0.35rad，连续4s |
| AP不支持组合拒绝后最大速度 | 0.02506m/s | 不适用 | ≤0.25m/s，连续2s |

每个3s/4s/2s门分别有3,001/4,001/2,001条逐步记录。AP拒绝原因严格为 `arducopter_velocity_requires_yaw_rate_mode`；原始事件中无额外 setup/command rejection 或 control_revoked。最终物理高度 AP -0.00001944m，PX4 -0.00000492m。

倍率仍为原定 0.5×。19,948 个调度组最坏迟到 **17,815,421ns**，低于不变的100ms限制。逐个检查所有完整滑动10s/60s窗口：18,448个10s窗口最坏相对误差 **0.0810213%**（门槛2%），12,198个60s窗口最坏 **0.0184428%**（门槛1%）。没有删去失败样本、钳制时间或调整倍率门槛。此轮无其他自有实飞/UE/GCS负载；未取得 vmmemWSL 优先级证据，不归因于优先级提升，也不声称宿主停顿已普遍解决。

## 来源与审计

沿用已准入 profile 的 AP clock-stop、PX4 state 及控制 FVMjak，非 AP P+V 候选。AP 固件 SHA256 `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de`；PX4 固件 `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a`。运行 ready/stopping 的真实加载映射和可执行文件身份均绑定当次 preflight；39份实际执行源码在 epoch/source 按记录SHA留存，未用后续工作区版本代替。

epoch/result.json SHA256：`c403cee36ad206b0249160a45dfa7e475595127e495b8506653775237415d7a9`。

离线复核先执行 `tools/audit_joint_velocity_yaw.py` 的身份/物理检查，再由 `validation/independent-velocity-20260909/audit_joint_complete.py` 组合现有 retained_identity、audit_product_timeline、raw_public、schedule/measurement。原通用位置任务审计预期六次请求并拒绝所有 command_rejected，因此本速度案例使用原始CDR解码后核对精确预期拒绝，不放过其他拒绝。审计01的可选 faults 字段读取错误、02的错误位置审计复用均保留，没有把这两次审计程序错误写成实飞失败。

04/05两次完整审计输出由Linux原生重定向生成，字节一致，SHA256均为 `38de60f7839c191f0a12fde7c8c9e49f40a0c86b414d55d357202bc57de991f1`。03通过输出经PowerShell捕获为CRLF，与04语义相同但字节不同，未覆盖或冒称三者字节相等。

审计使用以下环境，再运行上述脚本：

```sh
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-joint-control-FVMjak/install/local_setup.bash
python3 -B validation/independent-velocity-20260909/audit_joint_complete.py
```

历史管理器已记录所属进程组无残留。随后WSL boot_id发生变化，原current_host检查正确拒绝跨boot核对，不能将当前裸PID映射回旧进程。`joint-cleanup-02.json`重新验证历史记录，再以每个原始子进程的完整argv和cwd扫描当前/proc，无匹配。没有按名称终止任何用户进程。

独立复核代理 `/root/velocity_closure_review` 经主代理实读session_meta/turn_context确认 `gpt-6-astra/high` 后执行。只读重跑双栈独立和联合原始物理审计、核对76个归档项/每栈27份独立源码及39份联合源码、原始请求/拒绝及倍率覆盖，未发现影响本范围收口的问题。该复核未独立重跑ROS反序列化；完整ROS原始包审计和当前进程检查由主代理完成。

## 独立组合与改动

另见[双栈独立速度报告](2026-09-09-independent-velocity-report.md)和[首次运行前计划](2026-09-09-independent-velocity-plan.md)：两栈真实位置基线→世界速度/回中→yaw-rate→支持或拒绝角度组合→机体系速度/回中→落地，每场13个公共请求，原始物理审计均通过。额外PX4速度+yaw角及角度回中通过；AP受理前拒绝角度组合且无副作用。独立约50Hz证据未伪装为联合1ms证据。

唯一生产源码修正为速度任务的偏航积分时基：独立任务与既有dwell统一使用FC boot时间，共享场景仍用权威ROS时间。真实Task方法测试先复现独立3×的墙钟误用，再验证两个时基路径。准备段只允许在12墙钟秒内连续满足原保持界1.5个boot秒，正式驻留期间仍一旦越界即失败；没有调整控制律/固件参数。

全量矩阵469项：440通过、29条件跳过；旧预检11通过，日志 `validation/session-product-checks-06FITPm9/`。新增时基、连续稳定准备、真实双栈原始审计及8类单字段篡改负例通过。独立两次失败角度准备及早期联合失败保留。P+V轨迹、真正混合轴、持续1×、G6预算及Full其余范围继续开放。
