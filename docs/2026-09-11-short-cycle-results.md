# 短周期执行结果：生成模型与分栈等待

前一轮 Goal/三代理接力设置属于有效推进。本轮取得真实代码生成、冷重建和新调度采集证据，Goal 继续 active，未改变 Full 终态。

## 生成模型

已提交 `50897b8`：SLX 11.8 真实 MATLAB/Embedded Coder 生成，5 项 license test/checkout 与 9 个阶段成功；独立 Linux 首构建和修正后的 CLI 再构建均通过。主会话从源码重新冷构建，由两个独立进程各执行两轮 Model 创建/1000步/销毁，共 480,000 值、四份原始记录字节一致；时间门槛仍为现有 1e-8s，未加载 MATLAB/MCR/Gazebo 运行库。项目包装器驱动 inPWMs[16]，TerrainIn15d[15] 保持零。

详见 `docs/2026-09-10-generated-e0-lifecycle.md`、`validation/codegen-e0-lifecycle-01/audit.json`。#70/#71/#72 按原依赖逐票复核关闭；#26 仍保留 #9 原依赖，G6 和 R1 未改判。关闭读回见 `validation/coordination/codegen-closures-50897b8.json`。

## 相机控制接入

主会话读取固定 Prometheus `aruco_tracking.cpp:175–180` 后修正 TargetIntent 方向为“观测相对位置减期望位置”，并用静止目标的三轴相对运动检查验证误差减小。丢失/坏帧不清掉去重高水位；接缝支持同 epoch 的显式相机重连和保留 stream 的冷重置，拒绝退役流/旧帧、绑定前目标和不一致配置。36 项相关检查通过。

这仍是 #104 的接入前置。`071c7fc` 已完成公共命令发送器的首次 HOLD、当前权威时间、内层 command_id 高水位和公共受理未定记录；主会话另外修正缓存 MOVE 到期不能被去重跳过、ACK 未定后重新悬停、畸形消息与 uint32 回绕拒绝。19 项 Windows 编排及 WSL 真实消息构造检查通过，记录在 `validation/coordination/parent-aruco-public-command-tests.log` 和 `parent-aruco-public-command-types.log`。尚未启动跟踪飞行，联合 profile/任务工厂与实时图像输入接线继续推进，不把这些测试替代 #104/父 #40 验收。

## 新的真实输入等待证据

Claude Code 交付了显式诊断开启时的 AP/PX4 分段计时，主会话读取差异并复跑原生计时/既有分析 14 项检查。默认关闭无新增时钟读取或计时日志；原输入顺序、物理步长、屏障与迟到门槛保持不变。

主会话执行 `/root/wksim-scheduler-probe-shortcycle-01`，run `scheduler-692db7ad88f8`，epoch `914c9a2172774d44b290b18b12c99d2a`。10 秒私有 tracefs 完整无丢失、全局控制未变、实例和 epoch 组均已退出。原件与 source SHA 副本已归档到 `validation/native-input-shortcycle-01/`，逐成员解流核验一致。

| 等待 | 实测 wall | 监督线程唤醒前阻塞 | 可运行排队 |
| --- | --- | --- | --- |
| AP tick1926 | 7.297658ms | 6.188ms | 30µs |
| PX4 tick2000 | 7.673218ms | 6.802ms | 31µs |
| PX4 tick5504 | 6.610963ms | 5.796ms | 27µs |

41 条记录共 63 段，其中 35 段完全处于采集窗内（AP24/PX4 11），28 段被边界排除。采样条件是原生等待合计 >2ms 或 tick%250==0；这些不是总体统计。与旧数据相似的两条共同边界慢等待，在新场次已经能明确归于 PX4 等待，而非全部归于 AP；仍不能由监督线程阻塞推定 FC 内部函数或 Windows 根因。

新分析器首轮实测拒绝了短等待的 CPU>wall。原计时的 wall/CPU 端点顺序读取，两窗口略有偏移：例如 tick3750 wall409703ns、CPU410956ns，并不违反测量方法。主会话保留首个拒绝日志，修为保留 CPU 原值且不强制 CPU≤wall，拒绝负数；空记录/全部在窗外也明确失败。16 项分析检查通过，最终结果在 `analysis-final.json`。没有修改物理误差或倍率门槛。

接下来继续由 Claude Code 对固定原生源码和日志调查 PX4 两个时刻的候选工作，只有源证据支持才设计下一次测量；不按相位巧合直接修改参数保存、日志缓冲或调度。
