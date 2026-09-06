# 独立实验并行隔离（GitHub #13）

每次 `tools/run-wksim.sh` 启动一套独立环境、独立物理时间线和输出目录。两个并行运行不是联合场景。此实现只覆盖现有固定 quad-X / native DDS 基线，不扩大配置准入。

## 入口和预约

正式入口创建 private network、IPC、mount namespaces，关闭 mount propagation，再为 `/dev/shm` 挂载独立 tmpfs。Fast DDS 默认可能使用共享内存；仅 netns 不足以证明隔离。这里同时分离 DDS 网络发现、System V/POSIX IPC 与 Fast DDS 共享内存文件，不改安装树或全局 DDS 配置。Unix 文件系统显示 socket 仍可供外部显示桥访问，必须单独预约。

`isolation.py` 在 `/run/wksim-reservations` 使用标准库 `fcntl.flock(LOCK_EX|LOCK_NB)`：

- 全局预约活动 run_id、解析符号链接后的输出目录、显示 socket 路径；已存在显示 socket 也预约设备/inode，避免别名静默共用。
- 网络命名空间内预约 vehicle_id、DDS domain、公开/native namespace、MAVLink sysid、XRCE client key 和固定 TCP/UDP 端口。整个 domain 预约覆盖当前固定公开 topic 与 DDS 动态端口；不支持同一网络内多实验共享 domain。
- 不同网络命名空间允许复用固定载具 ID、domain 和端口。全局 run_id 仍不得跨输出根重复。
- 获得全部锁后才创建输出；冲突返回退出码 2，且不创建第二个运行目录。部分预约失败自动释放已有锁。锁文件不删除，避免 unlink/recreate 产生双 inode 锁。
- 锁描述符传给自建子进程；正常回收后关闭。子进程仍持有描述符时，父进程退出不会立即释放该锁。预约是协作机制，不抵御有权改写 `/run` 或在检查后改动符号链接的恶意本地进程。

每次输出 `isolation.json`、`config.json`、独立 truth/public logs、`result.json`。结果包含实际 net/ipc namespace、shm device、墙钟开始/结束、独立物理时间、固定身份与源码/飞控哈希。

| 资源 | PX4 | ArduCopter |
| --- | --- | --- |
| vehicle / domain / public namespace | 1 / 77 / `/uav1/prometheus` | 1 / 77 / `/uav1/prometheus` |
| native namespace | `/wksim_px4_21` | `/ap` |
| MAVLink sysid / XRCE key | 22 / 22 | 241 / `0xAAAABBBB` |
| 固定 UDP | 18888, 18591, 14661 | 12019, 19002, 19003, 19004, 14660 |
| 固定 TCP | 4581 | 无 |

PX4 key 来自固定源码 `ROMFS/px4fmu_common/init.d-posix/rcS` 的 instance+1；AP key 来自固定候选 `libraries/AP_DDS/AP_DDS_Client.h` 的常量。UDP 清单列显式接口端口，非所有临时 DDS socket 的枚举；后者由私有网络和整个 domain 预约隔离。

停止语义保留：成功须经公开 disarmed 状态与物理落地真值共同确认，记录 `landed_stop`；启动/任务失败或信号中断记录 `unsuccessful_isolated_teardown`，仅回收本次自建进程组，不假称安全落地。未实现空中恢复策略、资源配额或 SIGKILL 后自动恢复服务。

## 复现与真实证据

在 PowerShell 执行（只启动自建隔离实验，保留原用户 PID828）：

```powershell
wsl -d Ubuntu-22.04 -u root -- bash -lc 'cd /mnt/c/Users/PC/Documents/odid编译/wksim && python3 -m unittest validation.test_wksim_runtime validation.test_wksim_isolation -v'
wsl -d Ubuntu-22.04 -u root -- bash -lc 'cd /mnt/c/Users/PC/Documents/odid编译/wksim && python3 tools/validate_product_isolation.py'
```

Harness 从版本化示例读取固定安装资源，为两个实验生成不同 run_id，同时通过 `bash tools/run-wksim.sh CONFIG --output-root DIR` 启动。记录实际 argv、PID、时间序列与 PID828 的启动 ticks/命令行；双栈 truth 已产生且双方存活时，用同一 PX4 run_id、不同输出根再次启动，要求退出2；随后要求先结束者正常落地，存活者物理时间继续前进超过1秒，最终两者成功且全部自建进程组无残留。220秒总墙钟上限；失败时只向自己启动的正式 runtime 发送 SIGTERM。

2026-09-05 原legacy阶段实测：16项测试通过、无跳过。[acceptance.json](../validation/product-isolation-lu271npn/acceptance.json) 为 pass；下列数值属于当时未增加session包络的运行，不改写历史哈希。

- PX4 `isolation-px4-c6f1425ed1`：commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，1665条真值，最大高度3.178m，最小航点误差0.059m，最终仿真时间33.28s，正常落地。
- AP `isolation-arducopter-c6f1425ed1`：commit `1511f27194f1dcc3728270883047bdf022b3fd53`，3318条真值，最大高度2.997m，最小航点误差0.022m，最终仿真时间66.34s，正常落地。
- 实验启动墙钟分别1788612792.7965与1788612792.8252。重复启动拒绝时 AP/PX4 仿真时间分别7.24/0.32s。PX4清理结束后首次采样 AP时间41.48s，后续持续至66.34s。
- net namespace 分别 `4026532319`/`4026532252`，IPC分别 `4026532318`/`4026532251`，shm device分别128/126。最终自建进程组成员为空；PID828 start_ticks持续为19268，命令行未变。

首轮 [acceptance.json](../validation/product-isolation-ojv4n4g8/acceptance.json) 同样成功，但其资源元数据误将 AP XRCE key写为1；源码核对后修正并完成上述复跑，历史证据未改写。中间一次只读 `pgrep`/`ss` 诊断受跨Shell引号影响失败，未取得socket枚举，不用于通过结论。WSL没有rg时，固定源码核对使用grep。最初读取工作区内 `docs/agents/domain.md` 不存在，随后读取父工作区实际文件。

该代理阶段无UE、硬件、原ROS1修改、vendor安装变更、提交推送或Issue状态修改。SIGTERM/部分启动失败清理有单测，真实并行负例是启动预约拒绝，不声称所有空中故障通过。共享CPU/磁盘竞争没有配额控制。

主代理随后集成#14，并在新session候选上复跑：默认harness现读取`*-session.json`，指定`--control-protocol legacy_v1`才读旧例子。[新版acceptance.json](../validation/product-isolation-64k66y71/acceptance.json)通过，PX4正常退出后AP从42.46推进至66.40s，全部自建进程组无残留、原PID828未变；完整当前源码审计和双栈UE回归见[第二批报告](2026-09-05_product-second-wave-report.md)。历史两份运行不覆盖新接口；当前证据另存，不补改历史。
