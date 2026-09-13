# RC 双栈仿真与原始审计报告

2026-09-10，续 a875a13 / 762eda3。飞行运行器、软件 RC 输入、Humble 逐包 GID 接收、显式控制权交接和独立审计已交付。**六场景 × PX4 / ArduCopter，共 12 场通过最终统一审计**。这是显式实验候选入口的结果；不修改正式默认准入，也不代表整个仿真工具链 Full 已完成。

## 实现与运行身份

- `tools/run-rc-flight.sh` / `tools/run_rc_flight.py`：每场独占私有 net/ipc/mount 与临时目录，核验固定固件/模型/消息，再启动安装版 Control。保存源码、进程 argv/PID/maps、原始 DDS、逐毫秒物理与退出状态；只有真实落地上锁后记正常结束。
- `ros2/.../src/rc_take.cpp` / `prometheus_control/rc_transport.py`：使用安装 Humble 的 rcl/rmw 编译，读取真实 CDR 和 `rmw_message_info_t.publisher_gid`。不改系统 ROS；两真实 DDS writer 的 GID 与发现端点相符。Humble 原执行器丢弃元数据，原提交的两参数回调不能工作，因此必须补此适配。
- `node.py` / `rc_input.py`：独立墙钟新鲜度与操作时间积分，完整信封/死区/身份检查，显式空中接管，RC→COMMAND 中立意图，撤权后退役流拒绝。RC 不启动解锁/起飞；起飞先走已有 COMMAND 路径。
- `rc_task.py`：六场景的具体输入、生命周期、独立原生模式切换探针和原始观察。`rc_publisher.py` 按 profile 原样发布并记录进程与源/配置身份。
- `audit_rc_flight.py`：独立重算死区与四轴积分，逐 CDR 解码/实际 GID 与唯一 setup 对应、原生目标/模式核对、物理阶段游标与原始轨迹绑定、落地及清理复核。审计不调用产品 RC 积分器。

最终飞行 Control 候选：`/root/wksim-joint-control-WjBuqN/build.json`，SHA256 `ae5236af5052e81a256566a5e05d1840752fffb4d6f5cc512e0c0a5bb9e88c1d`。每个 run 的完整源码/安装身份及模型/固件/消息身份在其 `result.json`、`admission.json` 和原始归档中。

固定旧 Control 继续核验其封存 Python 与当时的 CMake/package 输入；新候选独立核验当前源/构建副本/安装。这修正了旧准入误将当前新 CMake 目标当作历史构建输入的归属错误，篡改历史输入仍被拒绝。原 baseline 摘要不变。

## 最终结果

| 场景 | PX4 | ArduCopter |
| --- | --- | --- |
| movement | PASS；+X 1.1715 m | PASS；+X 1.2201 m |
| recenter | PASS；保持窗口最大速度 0.0566 m/s、漂移 0.0571 m | PASS；0.0309 m/s、0.0506 m |
| yaw | PASS；目标误差 0.00120 rad | PASS；0.02600 rad |
| stream-stall | PASS；末帧后 1.50521 s 撤权，旧流拒绝 | PASS；1.50377 s 撤权，旧流拒绝 |
| mode-out | PASS；独立原生 AUTO.LOITER 请求引发撤权 | PASS；独立原生 BRAKE 服务请求引发撤权 |
| new-takeover | PASS；双向交接、退役旧流、新 stream/新请求、再移动 0.7622 m | PASS；同流程，再移动 0.8516 m |

最终统一审计：[final-matrix.json](../validation/38-rc-flight/final-matrix.json)，12/12 PASS。相同审计器 SHA256 `ace3a021bde74223f521acd122a513590419d8315209e50a6878186ddacffc9c` 覆盖全部 12 场。具体 run_id 与原件路径以此清单为准。

撤权表示停止 RC 输出，不表示载具立即停住：独立断流场的撤权后约 2.02 物理秒内，PX4 移动约 0.245 m，窗口末速度约 0.760 m/s；AP 移动约 0.376 m，窗口末速度约 0.029 m/s。PX4 原生 Offboard 失联 failsafe 与 AP 保留已受理位置目标的行为分开记录。测试随后使用新的显式保持/接管或 LAND 请求收尾，不宣称断流自动安全悬停。

## 验证与失败原件

- 47 项 RC/操作时钟/原生适配/场景生命周期测试在私有 WSL ROS 环境通过，0 skip。
- 9 项准入测试在 WSL 通过，包含历史构建输入篡改。Windows 原有 symlink 负例因缺少创建符号链接权限失败，随后在 WSL 正常验证，未放宽测试。
- 4 项真实证据审计测试通过：原件通过、CDR 内容篡改拒绝、删除原生通道拒绝、篡改物理游标拒绝。游标负例先真实失败，补齐绑定后转绿。
- 首次 PX4 movement 在解锁前因任务 API 错误退出；首次 stream-stall 已正确撤权，但通用 Task 将预期 native failsafe 当作异常而退出。两次失败的原件完整保留，并确认所有本 run 子进程回收。
- 审计迭代的失败也保留：CDR 两接收端尾部对齐字节差异需按独立解码内容/GID 对照；短交接窗口不能强制套用长窗口固定样本数；外部模式反馈必然先于下一次 Control 撤权服务，审计明确校验最后一个最大 50 ms 服务区间。

命令、归档与 SHA 清单见 [RC 验证目录](../validation/38-rc-flight/README.md)。`raw-evidence.tar.gz` 保存原始文件；归档后逐文件解包读回 SHA 核验，原 WSL 运行目录未改写。每场早期单独 audit 和最终统一 audit 分别保留。

## 其余边界

RC 位置候选已具备可运行、可审计的双栈入口。其他手动模式、默认产品入口提升、完整软件算法/模型/ABI、G6 数值和联合倍率门仍按原规格继续。R1 `numerical_failed`、#20/#33 `RateUnmet`、#56 的硬件资源/授权边界均未改判。本次只运行软件 SITL，没有操作真实飞控或发送硬件命令。
