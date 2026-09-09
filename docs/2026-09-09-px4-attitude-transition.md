# #34 PX4 姿态接管切换只读诊断

2026-09-09。首轮 `attitude-px4-01` 的 5° 阶跃失败与原生控制使能切换延迟有直接证据对应：新的 attitude-only 输入已到达，但 Commander 到 27.632s 才关闭位置控制器；位置控制器在此之前继续覆盖同一个 `vehicle_attitude_setpoint`。不是主机错误地同时设置 position/attitude，也不是位置控制器永久不退出。这个结论不证明消除切换延迟后便一定通过原有物理预算。

主代理核验会话 `01a08422-417b-7261-a426-e4945617f4c2`、agent_path、`gpt-6-astra/high` 后 RELEASE。先向独立审计代理取得其已读时间序列，再只读抽取尚未分析的原生控制状态。使用 diagnosing-bugs 和 ponytail 技能；已有失败现场替代新建飞行复现，本任务授权仅含只读诊断和本报告。没有启动 FC/model、测试、构建、改参数、改源、提交或 Issue 操作，没有嵌套委派。

## 固定现场和可重复读取

- 运行根：`/root/wksim-attitude-flight-px4-20260909-01/attitude-px4-01`。
- ULog：`log/2026-09-09/02_58_28.ulg`，本轮重算 SHA256 `302b34e5bf4d4f12b2890a7245454a4ce687e6849a0fe0017f3980750ddf12c9`。
- PX4 源根：`/root/wksim-px4-state-ONa1Kw/src`；本轮实际 `git rev-parse HEAD` 为 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`。已有 SITL board/EKF2 修改及 submodule 状态保持；本报告不把该工作树宣称为干净上游 checkout。
- 实际已安装主机文件：`/root/wksim-attitude-control-x3_2v4wb/install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control/native_px4.py`。本轮实际读取发送函数，SHA256 `d72234ddb0c95f2660f469315dbdd7b3a4871381238767734a178e834141d085`，与 `work/ap-attitude-stage-20260909/after/control/ros2/src/prometheus_control/prometheus_control/native_px4.py` 相同。
- 冻结预算 `work/ap-attitude-stage-20260909/flight-budget.json` 本轮 SHA256 仍 `9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f`。

使用审计代理已有私有 pyulog 1.2.2 `/root/wksim-attitude-audit-deps-g_2y8olg` 和系统 numpy，没有安装依赖。执行过下列同等只读窄抽取；其输出的关键行见下一表。这是已捕获失败的状态抽取，不是重放真实控制执行或新的回归通过。

```python
import sys
sys.path.insert(0, '/root/wksim-attitude-audit-deps-g_2y8olg')
from pyulog import ULog

root = '/root/wksim-attitude-flight-px4-20260909-01/attitude-px4-01'
ulog = ULog(root + '/log/2026-09-09/02_58_28.ulg',
    message_name_filter_list=['vehicle_control_mode', 'offboard_control_mode',
        'vehicle_attitude_setpoint', 'vehicle_local_position_setpoint', 'vehicle_status'])
for dataset in ulog.data_list:
    data = dataset.data
    fields = ([key for key in data if key.startswith('flag_')]
        if dataset.name == 'vehicle_control_mode' else
        [key for key in data if key != 'timestamp']
        if dataset.name == 'offboard_control_mode' else
        ['nav_state'] if dataset.name == 'vehicle_status' else [])
    for i, stamp in enumerate(data['timestamp']):
        if 27100000 <= stamp <= 27890000:
            print(dataset.name, int(stamp),
                  {key: data[key][i].item() for key in fields})
```

## 原始状态对应关系

以下时间是 PX4 原生 boot timestamp 的秒值；27.360s 的原始 DDS 解码和物理接收游标来自独立审计提供的已核对结果。其余 ULog 行由本轮独立抽取复核。

| 原生秒 | 实际记录 | 含义 |
| --- | --- | --- |
| 27.128 | `vehicle_control_mode`: MC position、position、velocity、altitude、climb_rate、acceleration 全为 true；offboard、attitude、rates、allocation 为 true；manual/auto 为 false | OFFBOARD 位置闭环在运行 |
| 27.280 | ULog `offboard_control_mode`: position=true，attitude=false | 此次被记录的旧输入 |
| 27.360 | 原始 DDS 姿态目标 roll=5°；同流 OCM attitude=true、其他控制标志 false | 主机开始新阶跃；不能称 native 接管 ACK |
| 27.376 / 27.424 | ULog attitude roll=-0.1133° / -0.1091° | 仍出现旧位置控制器输出 |
| 27.384 | ULog OCM attitude=true，其余 false | 原生 uORB 已收到正确新使能意图 |
| 27.464 | ULog attitude roll=5.00000004°，thrust_body.z=-0.53096056 | 新外部目标也确实进入同一个原生 topic |
| 27.520 / 27.576 / 27.624 | ULog attitude roll=-0.1232° / -0.1247° / -0.1583° | 新目标之后再次被旧控制器输出覆盖 |
| 27.424 / 27.520 / 27.624 | `vehicle_local_position_setpoint` 有相同 timestamp 的输出 | 与 mc_pos_control 紧邻发布两个 topic 的源码吻合 |
| 27.632 | `vehicle_control_mode`: MC position 及上述五种位置/速度相关控制全部 false；offboard、attitude、rates、allocation 仍 true | 原生位置控制真正被指示退出；nav_state 仍为 14/OFFBOARD |
| 27.640 / 27.680 / 27.744 / 27.784 / 27.840 | ULog attitude 均为 5.00000004° 和冻结 thrust | 此后所记录目标一致；不是永久第二发布者 |
| 27.860 | 原物理审计 actual roll≈2.7089° | 未达到 5°±2°，保留失败 |

`vehicle_control_mode` 从 27.128 到 27.632 相隔 504ms，与源码 500ms 条件和调度粒度相符。新阶跃至控制位退出约 272ms，占去原 500ms settling 的一大部分。不能因此把旧阶跃起点改成 27.632 或 27.640；原结果仍不通过。

本版本 logger 默认 `offboard_control_mode` 100ms、`vehicle_attitude_setpoint` 50ms、`vehicle_local_position_setpoint` 100ms；`vehicle_control_mode` 无额外采样间隔。上述稀疏姿态记录不能证明每一包目标或精确首次控制器消费时刻。原始输入 DDS 与 ULog 配对也不把 DDS 接收时刻升级为飞控 ACK。

## 实际原生发布链

本轮所有 PX4 路径均相对上述固定外部源根，已读实际文件，不用本项目图外推外部飞控结构。

1. 实际主机 `PX4Link.send` 的 attitude 分支先发布 `OffboardControlMode(timestamp=timestamp, attitude=True)`，然后发布四元数和 FRD `thrust_body=[0,0,-thrust]`。位置分支单独激活位置等轴并发 `TrajectorySetpoint`，没有在 attitude 分支再次发旧轨迹。原始 OCM 和实际函数吻合。
2. `src/modules/uxrce_dds_client/dds_topics.yaml:140`、`:161` 分别声明 OCM 和姿态目标输入。它们是独立 topic；主机连续两次 publish 没有跨 topic 原子切换保证。
3. `src/modules/commander/Commander.cpp:2983` 的 `offboardControlCheck()` 更新 `_offboard_control_mode_sub`，但只在 `_failsafe_flags.offboard_control_signal_lost` 时设置 `_status_changed`。已有健康 OFFBOARD 流中的 position→attitude 变更没有由此触发立即状态发布。
4. 同文件 `:1931–1940` 只在距 vehicle_status 上次发布≥500ms、`_status_changed`、导航/失效变化或 armed 标志变化时调用 `updateControlMode()`。`:2600–2618` 重新清零并生成控制标志，再由位置/速度/高度等位合成 `flag_multicopter_position_control_enabled` 并发布。这不是每个 10ms Commander 周期都更新控制使能。
5. `src/modules/commander/ModeUtil/control_mode.cpp:123–154` 按 position→velocity→acceleration→attitude 优先级选 OFFBOARD 控制层。attitude-only 正确结果仅启用 attitude/rates/allocation 和外层 offboard；本次 27.632 的真实状态恰好如此。没有证据支持“消息布尔默认值不对”。
6. `src/modules/mc_pos_control/MulticopterPositionControl.cpp:402–415` 读取实际 `vehicle_control_mode`，由 enabled→disabled 才清掉 `_setpoint`。`:452` 的使能分支和 `:602–612` 在位置控制仍开启时继续计算并发布本地位置目标和 `vehicle_attitude_setpoint`，timestamp 为当前 hrt。旧轨迹不需再次从主机收到即可继续产生近水平姿态。
7. `src/modules/mc_att_control/mc_att_control_main.cpp:290–318` 在 attitude enabled 下消费同一 topic，只接受比 `_last_attitude_setpoint` 更新的 timestamp。没有“外部目标优先于位置控制器”的来源仲裁。旧位置控制器产生较新 timestamp 时可以覆盖/压住外部输入。该文件另有手动姿态发布分支，但需要 manual=true；本次实际 manual=false，故不符合该分支条件。
8. `src/modules/mavlink/streams/ATTITUDE_TARGET.hpp:58–94` 从真实 uORB 姿态 topic 读 q/thrust 并用 `att_sp.timestamp/1000` 填 `time_boot_ms`。可以用于后续在线接管证据，仍不是电机/物理成功证明。

由此，最贴合证据的结论是**该固定 PX4 版本的控制层变更缺少及时状态通知，使已有位置控制器延迟退出**。它可由源码预期解释，具有明确上限附近的周期性传播行为；不能将此解释为 DDS 一直没送到、随机传感器误差、持续错误发布者或姿态增益已证明不够。

## 最小后续选择

保留已封存 PX4 时，建议在实验任务内加入明确的“水平姿态接管”前置阶段，复用现有公开 XYZ_ATT 路径和冻结 hover，不改主机适配器或飞控。这是对原先“位置恢复完成即直接发阶跃”流程的显式修订；需在新运行前记录，不能冒称与首轮完全相同的程序或回填旧结果。

1. 在位置恢复后，先发送公开 `XYZ_ATT(roll=0,pitch=0,entry_yaw,frozen_hover)`；期间不能发送 5° 或 hover+0.03，不能重算 hover。
2. 在 recorder 里只读订阅已有 `/fmu/out/vehicle_control_mode`（实际使用现有 namespace/version helper）。`dds_topics.yaml:66` 已导出该 topic，50Hz 是最大速率，不会让 Commander 的 2Hz 周期变快。验证本运行原生发布身份、单调 source timestamp 和新鲜度；要求其 timestamp 不早于本次中性请求的原生输入 timestamp，不能复用上次姿态阶段的旧 true 标志。
3. 要求 armed/offboard/attitude/rates/allocation=true；MC position、position、velocity、altitude、climb_rate、acceleration、manual、auto、termination=false。再要求真实 `ATTITUDE_TARGET` 中性 q/thrust 匹配，源 `time_boot_ms` **严格晚于**控制使能切换 timestamp（换算同单位），从而不把中性 DDS 发布本身当作执行层证据。一个凑巧近水平旧位置目标不足以代替 mode 证据。
4. 接管阶段设独立、预先记录的物理时间上限和墙钟 watchdog，保持原 abort envelope、状态新鲜度和既有失败 LAND。建议物理上限 1s，仅为新前置阶段的有界失败期限，并非经实飞验证的达标参数。native 模式证据缺失/过期或超时就失败，不能以“睡够 0.5s”替代。
5. 接管通过后才发送首个 5°。阶跃计时仍从首个匹配的原生输入发布对应物理起点开始，并由离线原始时间线复核；不能从较晚原生目标或看到响应才重置。继续保留 0.5s settling、随后连续 0.4s 门槛、总 1s、原误差和原 8s 位置恢复。保留接管前的恢复/安全锚，阶跃锚及状态显式记录，不能滚动改锚掩盖漂移。
6. 推力试验也需要同样的 position→neutral 接管。当前 `thrust_baseline` 只有 0.2s，少于原生状态发布最坏相位等待；应在接管证据之后再收集完整的既定 0.2s baseline，然后发 +0.03 并保留原 0.5s/速度门槛。不能增加推力持续时间以补偿。

两秒中性校准也有同类切换：如果接管发生在这两秒内，部分时间仍可能由位置闭环维持。后续使用相同前置接管证据后再运行**完整原定两秒**直通校准，比仅修复 5° 前置更一致；这是加强直通校准的语义，应明确写入新运行程序，不把原校准记录改写成已证明两秒全部为纯姿态控制。

如果目标是让任意主机实时控制层切换都及时生效，真正共享根因修复点在 Commander：比较 OCM 的控制语义标志（排除 timestamp），有变化时触发 `_status_changed` 或等效的及时控制模式重算，保留原 signal-lost 处理。比较需覆盖 position/velocity/acceleration/attitude/body_rate/thrust_and_torque/direct_actuator，避免每包时间变化都触发全量状态。此路线必须新建 PX4 候选、补丁/构建/身份/回归，不能修改既有封存安装，也不能声称它完全消除独立 topic 的瞬时传播顺序。当前未实现此路线。

无论选哪条路线，都没有新证据支持调姿态增益、推力值或放宽物理门槛。下一轮真实完整日志才可判断在原 settling 窗口内是否通过。

## 只读来源校验

本轮实读 SHA256：

| PX4 相对路径 | SHA256 |
| --- | --- |
| `src/modules/commander/Commander.cpp` | `ab21f8b26e7c44d8569b5c34bdd5f629d72bf8c969723f4927bc46ac5a5fffff` |
| `src/modules/commander/ModeUtil/control_mode.cpp` | `1159c0383fc66226a28b555d04a09d1583ef22c7a7590d06c3c94d7d67dd8c4e` |
| `src/modules/mc_pos_control/MulticopterPositionControl.cpp` | `0e025b28e1dcd40f8e861b64668b1bafc502b3223277a29b76564f8997dcbeac` |
| `src/modules/mc_att_control/mc_att_control_main.cpp` | `dbe4f3b6afbbee95b3c79ab77fa0e288dc113206937dfa372c2394e53631ffb1` |
| `src/modules/logger/logged_topics.cpp` | `33c1cd7c55dc81d4fa53153b7f269401b67c7f6edc929707ec536203096bcfe5` |
| `src/modules/uxrce_dds_client/dds_topics.yaml` | `7e9c730d45b22af92acfebbb81cb5de4e4a69ac0ca46b012b71ed8fa5c89cbc0` |

仓库内仅直接读取已知 `attitude_task.py`、staged/installed adapter、相关计划和报告；未知 PX4 结构属于未索引外部源码，按专门授权进行直接定位。没有依赖仓库结构图的新查询，未运行重索引。本报告只新增当前文件，不更改任何旧失败证据、预算、源码或准入声明。#34 仍未通过。
