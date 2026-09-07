# 正式联合入口、操作与冷重置实测

本轮把已经验证的联合核心和独立 AP/PX4 候选接入正式 `tools/run-wksim.sh`，新增 `joint_scene` 配置及显式操作接口。最终健康流程、两侧 Agent 各自失联后的显式恢复/新任务/冷重置均通过，三份原始审计各重复两次、输出字节一致。13 次流程尝试记录的 29 个 Linux 进程组均无残留。完整 Goal、#8/#19/#20/#22 和 Full 继续开放。

工作以本地 `6d2e371d918f202acd64e822dee4300e86942bcd` 为提交基线，承接[原生状态频率与独立 PX4 报告](2026-09-06_native-state-cadence-report.md)。本轮代码仍在 wksim 独立工作区，未新增提交或推送；原 Wayfinder 父图、已批准规格及原生阻塞关系保持原状。

进展已更新至 [#8](https://github.com/unununnnn/wksim/issues/8#issuecomment-5560281235)、[#19](https://github.com/unununnnn/wksim/issues/19#issuecomment-5560281549)、[#20](https://github.com/unununnnn/wksim/issues/20#issuecomment-5560281867)、[#22](https://github.com/unununnnn/wksim/issues/22#issuecomment-5560282153)，正文逐条读回一致且四票均 OPEN。[发布记录](../validation/product-joint-entry-20260906/publication.json)保留评论ID和正文哈希。

## 使用者现在能执行的流程

[操作说明](joint-product-entry.md)给出完整命令。与单机实验使用同一正式启动脚本：

```bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/joint-scene.json --preflight
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/joint-scene.json --output-root /root/wksim-joint-operator-001
```

服务先运行地面仿真，操作客户端读取 `status.json` 后提交 `start-task`。后续根据当前许可执行暂停、四步单步、继续、故障恢复、新恢复任务、冷重置或停止。任务仍由真实 Prometheus Task → 已安装 Control → 原生飞控路径执行；观察器仅订阅消息，验证驱动只调用正式动作接口和终止经过 PID/启动时间/可执行文件核对的本实验 Agent。

`submitted`、`accepted` 和 `completed` 分别表示文件已提交、监督器已受理及操作效果已完成。任务启动操作完成不等于飞行完成；原生 ACK、公共任务阶段、接管和最终模型真值分别保留。不可用、旧代次、重复令牌及过期许可会明确拒绝。冷重置保留旧操作结果，新 epoch 不执行旧指令或自动起飞。

## 固定资源与运行身份

| 对象 | 实际候选及 SHA256 |
|---|---|
| AP 构建清单 | `/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json`；`f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a` |
| PX4 构建清单 | `/root/wksim-px4-state-ONa1Kw/wksim-build.json`；`d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6` |
| PX4 可执行文件 | `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a` |
| 已安装 Control | `/root/wksim-joint-control-8xt3WC/build.json`；`28c58fb755f9ef9c0a207db67517f90da2fde65379f4b4207c7aa90197302492` |
| 自主模型库 | `/root/wksim-private-tmp-8ecszk82/artifacts/wksim-model-ljny7flc/libwksim_model.so`；`cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3` |

`joint_quad_dds_v1` 单独核对源树、构建产物、历史原始证据、当前/构建副本/安装 Control、五层 ROS 环境及实际消息解析来源。旧单机准入规则和旧参考固件保留，不能通过只换一个路径来接受其他构建。

最终每个实际运行 epoch 保存 runtime/core 源码副本、初始哈希及结束时变更核对。AP 最终运行对应添加 PX4 CLI 原始标记之前的封存源码；PX4 与健康最终运行对应之后的源码。审计按每场实际副本验证，不把所有历史运行说成同一版源码。

在真实模型/飞控进程就绪与退场前分别读取 `/proc/<pid>/exe`、`maps`，关联原始进程身份、候选可执行文件哈希和模型库路径。最终五个 epoch 均无 CopterSim、Gazebo/ignition 或 MATLAB 运行库；原生模型和飞控正常退出。历史构建证据仍由上一报告及准入清单关联，本轮没有重新构建或修改原厂安装。

## 最终实测

| 场景 | 原始证据目录，均在 `validation/` | 结果 |
|---|---|---|
| 健康正式流程 | `product-joint-flow-vd3464wq` | 69,528 个共同 1ms 步；同飞 14.006s；51,856 → 51,860 四步单步；继续确认在 52,236；两次各 4s 冻结、正常公共任务和落地退出 |
| AP Agent 空中失联 | `product-joint-flow-61t52y3j` | 冻结 tick 53,484；显式物理恢复 1.771595 墙钟秒；新任务落地至 67,396；冷重置后新地面 epoch 到 41,180，旧指令拒绝 |
| PX4 Agent 空中失联 | `product-joint-flow-32s6alit` | 冻结 tick 52,028；显式物理恢复 0.800529 墙钟秒；新任务落地至 64,672；冷重置后新地面 epoch 到 41,108，旧指令拒绝 |
| 启动期间停止 | `product-joint-flow-3of_mg1l` | 0.170651s 完成；只读预检已退场，未启动模型/飞控 |
| 启动期间外部中断 | `product-joint-flow-l_x55in9` | 0.113890s 完成受管退场；服务如实返回失败退出码 1，验证判定通过，无飞控启动 |

这些墙钟数字是观测结果，不是新批准的保证或数值预算。两场失联均在真实飞行中终止 Agent，旧公共任务自然失败，冻结前后两侧完整模型记录相同。恢复先核对双侧新原生来源、home/airborne 状态和已撤销任务控制，再等待新的 `start-recovery-task`。AP 新请求 ID 为 4–6，PX4 为 4–7；PX4 新任务显式选择原生保持，未重放原起飞/航点。

PX4 重启 DDS 客户端时核对本实验 Unix socket 的 `SO_PEERCRED`，原始生命周期文件保留实际对端 PID、两个 CLI 命令和退出码。两场恢复审计都核对退役的原生发布者、恢复确认中的新来源及真实 DDS ACK。冻结零新增步的线路核验区间从第一条原始 faulted 许可到显式 recovering 许可，完整 4s 模型冻结另有前后原始记录。

冷重置先退场整个旧场景进程组，再创建新的 net/ipc/mnt 空间和模型/飞控/Control。监督器持有旧 namespace 的文件描述符直到新空间完成比较，避免把内核编号复用当成空间复用。新旧 Control epoch 不同；新场景只有地面物理推进，没有 task、解锁或旧原生任务确认。

## 原始审计和门槛

[`final-audits.json`](../validation/product-joint-entry-20260906/final-audits.json)记录三场各两次实际命令、审计 SHA256、逐场源码和加载库核验。健康原始时间线有 17,382 个 4ms 边界，其中启动后的 17,373 个严格同步；启动的 9 个未同步边界如实保留。AP 的 next-frame 是模型输入协议进展，未将它改称主控制器新计算完成 ACK。

健康高度驻留最大误差 AP/PX4 为 0.112362/0.197624m，航点驻留为 0.196075/0.457733m，满足既有 0.6m/0.5m 门槛。PX4 初始高度窗最大模型真值速度为 0.636328m/s；该初始物理高度窗的既有审计没有 0.5m/s 限制，因此这里没有声称它满足该速度预算。恢复驻留则分别核验两秒共同时间、0.5m 位置和 0.5m/s 速度：AP 失联场景双侧最大速度 0.053704/0.026381m/s；PX4 失联场景 0.040477/0.478076m/s。没有事后放宽阈值，也不把这些控制任务门槛解释为 G6 动力学等价预算。

新的审计工具直接解析实际模型请求、AP 原始 PWM/传感器、PX4 原始 MAVLink 执行器/IMU/GPS、权威时钟、公共 DDS CDR、场景许可/确认和任务发送日志。地面重置显式采用地面审计分支，原生输入、时间和最终地面真值检查仍保留，零飞行不被算成飞行通过。

- [公开预检和矩阵命令记录](../validation/product-joint-entry-20260906/final-checks.json)：19 项新接缝、74 项安装候选、329 项默认矩阵（27 跳过）、11 项旧预检；矩阵存在交叠，不相加为覆盖率。
- [Windows 既有入口回归](../validation/product-joint-entry-20260906/windows-entry-tests.log)：29 项 workspace/HTTP 检查通过；不等于实际浏览器验收或联合 UI 已实现。
- [真实证据损坏负例](../validation/product-joint-entry-20260906/audit-lifecycle-negatives.json)：篡改源码副本、伪造可执行文件哈希、在 maps 中加入禁止库并同步伪造摘要哈希，三例均被拒绝。另有 4 项原始许可/时钟审计检查，其中 3 项为破坏负例。
- [全部流程进程组检查](../validation/product-joint-entry-20260906/cleanup-audit.json)：13 次尝试、29 个记录的 manager/epoch 进程组均为空；用户原 AP `pid=828, pgid=828, start_ticks=19268` 前后及当前一致。

## 保留的失败

| 样本 | 原因与处理 |
|---|---|
| `failed-first-service`，位于 `product-joint-entry-20260906/` | 初次正式入口集成使用了不存在的 `Task.convert` 类属性，已改为消息转换函数；先前覆盖层数和 PowerShell→bash 参数展开错误的日志同时保留，后续全部使用 argv 数组。 |
| `product-joint-flow-sqgk1d05` | PX4 仍在起飞模式时提前提供暂停，真实 Control 拒绝；现在须两侧处于当前已接管的位置控制状态。 |
| `product-joint-flow-e_mn88sd` | 四步实际正确，客户端却读取到上一版状态；操作响应前同步发布过渡状态，客户端以完成 tick 和新的动作许可等待。 |
| `product-joint-flow-zzpak1c5` | 预检占住动作循环，启动停止等待 20s 超时；改为受管只读预检子进程，并实测停止/中断。 |
| `product-joint-flow-bsw35e7p` | 验证脚本把正常 exec 后的 argv 改变误判成进程替换；改为核对 PID/进程组/启动时间并另存当前 argv。 |
| `product-joint-flow-hxbqzl0h` | 两个旧组均已退出，但内核复用了销毁后的 namespace 编号；现在用保留句柄比较真正不同的新旧空间。 |

初始健康 `j5j_r_6o` 和初始 PX4 恢复 `clzu8b85` 的通过记录保留，但最终验收以上表三场为准。首次缺 ROS 环境、错误 ACK 审计规则和一次审计期间源文件更新的中间结果分别保留；最终六次审计源文件稳定并字节一致。

## 写入与后续边界

配置预检代理及独立原始审计代理各负责互斥文件，均从实际 rollout `turn_context` 核验 `gpt-6-astra` / `reasoning_effort=low`，证据在 `profile-agent-config.json`、`audit-agent-config.json`。主代理检查实际改动、实现正式服务/操作/重置/恢复、串行使用真实 SITL 资源，并运行集成回归；没有嵌套委派。

Codebase Memory 曾在本轮结构探索前成功刷新至 46,110 节点/155,626 边；新入口文件随后添加，之后只直接读取已知源，下一依赖这些变化的结构查询须再次检查/刷新，详见[索引记录](codebase-memory.md)。

剩余工作包括正式倍率和完整迟到/掉队行为、联合 UI/UE 双载具显示、环境/出生点/碰撞与其他 G3–G6/Full 义务。HIL/SIH、MATLAB 首期实际联测、未决硬件及数值预算继续保留原门槛。38 张初始票据不是全部范围；本轮未关闭阶段、删减 Full、操作真实硬件、修改原厂安装或发布厂商资源。
