# Full 硬件/资源逐模式前置清单（#56 交付）

2026-09-10。本文是 GitHub #56（稳定键 `1-hardware-boundary`）的交付：把适用串口/网络硬件的模式与纯软件 SITL 证据分开，逐模式记录硬件/固件/接口/安全测试条件与 owner。**本清单不发送任何硬件命令，不推断一揽子授权；所有硬件模式一律记录为 `deferred-pending-explicit-authorization`，缺设备阻塞原样保留。**

## 一、纯软件证据（无需硬件，已另有切片）

以下已有软件 SITL/DDS/模型证据，不属于硬件模式，不因此清单获得任何硬件语义：固定 PX4 SITL（`d6f12ad1` + 固件 SHA256，见 `docs/project-isolation.md`）、固定 ArduCopter SITL、原生 DDS 双栈、自主模型构建与纯模型探针、UE5.5 异步显示。SIM-11（PX4_SIH_SITL）按 #55 复核**不**因 SIH 名称被列为必须硬件；其前置是固定 PX4 源内 SIH 模式核对（见 `docs/plan/full-contracts/sim-11.md`）。

## 二、硬件模式逐条前置

| 模式 | 稳定行 | 所需硬件/固件/接口 | 安全测试条件 | 状态与 owner |
| --- | --- | --- | --- | --- |
| PX4_HITL（串口） | SIM-01，`full-scope-expansion.md:13` | 实体 PX4 飞控一块；与既有 SITL 固件对应或另行固定的 HIL 固件（来源/版本/SHA 待固定）；USB-UART 串口线及端口识别 | 移除全部螺旋桨与动力风险（断电上桨禁止）；台架固定；急停/断电可达；串口独占 | `deferred-pending-explicit-authorization`；owner：硬件 owner（用户）+ 运行 owner（主代理预约隔离资源） |
| PX4_HITL_NET | SIM-05，`:17` | 实体 PX4 飞控；HIL 固件；飞控与主机同网段的网络接口（Ethernet/串口转网络） | 同 SIM-01；网络拓扑固定、无其他地面站抢占 | `deferred-pending-explicit-authorization`；owner 同上 |
| EXT_HITL_COM | SIM-06，`:18` | **一个**明确的外部飞控（厂商/型号/固件版本可核验，不泛指任意设备）；MAVLink 串口接口 | 同 SIM-01；外部飞控身份在运行记录中逐项出现 | `deferred-pending-explicit-authorization`；owner：硬件 owner（用户提供设备身份）+ 运行 owner |
| PX4_SIH_COM | SIM-09，`:21` | 实体 PX4 飞控；支持 SIH 的对应固件（固定源内核对，见 sim-11 合同）；串口 | 同 SIM-01；物理位于飞控内部，显示/任务时间须重映射，不启动第二物理核心 | `deferred-pending-explicit-authorization`；owner 同上 |
| PX4_SIH_NET | SIM-10，`:22` | 同 SIM-09 的设备/固件；网络接口 | 同 SIM-01；与串口分开验证连接、状态、停止和重连 | `deferred-pending-explicit-authorization`；owner 同上 |
| PX4_SIH_FLY | SIM-12，`:24` | 实体 PX4；RFly 定制固件（来源/许可/接口先核对，不以标准固件代替）；相应链路 | 同 SIM-01 | `deferred-pending-explicit-authorization`；owner 同上 |

## 三、授权语义

- 每模式进入执行前沿前需要**逐模式显式授权**：设备可用性确认、固件身份固定、动力风险排除确认、端口/网络资源预约。任何一模式授权不外推到其他模式。
- 缺设备、缺固件身份、缺安全条件任一项，对应模式保持 `blocked`，不以软件 SITL 证据冒充 HIL 通过。
- 本清单未核验任何设备在本机的实际存在；后续执行票的第一步仍是设备/端口/固件只读核对并记录原始结果。

## 四、来源身份

- `docs/plan/full-scope-expansion.md`（12 仿真模式冻结行，行 13–24）
- `docs/plan/requirement-coverage.md`（#55 复核：SIM-01/05/06/09/10/12 均 blocked，由 #56 承接）
- `docs/project-isolation.md`（固定 PX4/AP 身份，软件证据边界）
- `docs/plan/full-contracts/sim-11.md`（SIH 软件/硬件边界）
- 本 slice 证据：`validation/lunar-56-63c8029177eece1f/`（只读命令与事实 JSON）
