# 后续推进的统一架构合同

2026-09-13。用户明确要求后续推进沿用已经完成的模块解耦架构。本合同用于新任务、续派、代码集成和新验收候选；不修改历史运行的源码、身份或验收结论。

## 当前依据与工作区

- 实施基线：`f333316e6efa6b299b4288a9d91fb2bccedfb9d6`，见 [实施报告](../architecture-implementation-20260912.md)。[早期检查](../architecture-decoupling.md) 的未实施描述属于历史，不能据此重复开发已完成模块。
- 开发主线：`C:/Users/PC/Documents/odid编译/wksim` 的 `main`。后续功能分支从包含上述提交的主线建立，仍遵循一个文件一个写入者。
- 新架构验收候选：Ubuntu-22.04 `/root/wksim-architecture-acceptance-20260913`，分支 `codex/architecture-acceptance-20260913`。它是源码候选，不是已获正式准入的运行组合；部署资源、私有接线、构建和运行均须分别验证。
- 历史对照：`/root/wksim-release-acceptance-fe3`，核查时 HEAD `db1200d`。保留冻结 Control、私有 runner 与已有证据，不将它们的通过状态复制给新候选。其他固定历史 probe 工作区同理。

## 必须复用的 module 与 interface

| 变化 | 归属与约束 |
| --- | --- |
| 动力学、新载具 | `wksim_core/vehicle_models.py`、`vehicle_state.py`、`actuator_layout.py`；统一 SI/NED/FRD 与具名执行器。旧 16/120 ABI 保留在原模型 adapter，不成为所有新载具的公共 interface。 |
| 外部位置控制 | `wksim_control/position_contract.py`、`controllers.py`；PID/UDE/NE 使用公共输入和显式算法选择。`native_thrust.py` 仅是多旋翼悬停标定，不适用于车轮或固定翼舵面。 |
| 固件底层 LQR/MPC | `Simulator/firmware/rate_control/` 的纯算法与 PX4/AP adapter；原生估计反馈、周期、输出尺度、控制分配和失败回退由相应 adapter 明确处理。外部位置环通过不等于替换固件 PID。 |
| 固件升级 | 新建可追溯候选，区分固件家族/目标、模型、算法、消息和能力；升级受影响 adapter 并重验，不能只改默认哈希放行。 |
| 实验与部署 | `wksim_runtime/experiment_bundle.py` 与 `tools/run_experiment.py`；实验意图与本机路径/候选 SHA 分开，保持组合校验。现有冻结 runner 可保留兼容接线，新增场景不得另造重复的身份/部署解析体系。 |
| UE 资产与外观 | `WksimVehicleVisual.*` 和 `Config/WksimVisualAssets.json`；GameMode 保留显示生命周期和状态路由，视觉不决定物理参数或飞控目标。保留 LIVE/REPLAY/FIXTURE 与陈旧检查。 |

车辆参考闭环和内环实验已经有证据；固定翼、任意硬件控制器、正式 MIXED/G6/Full 并未因此自动通过。独立 perf/审计模块只依赖其实际需要的 interface，不为“统一架构”强行引入无关模型或控制依赖。

## 派发与开工核验

每次新派发和续派均填写以下内容；旧任务上下文不能替代当前核验：

```text
工作类别：new-development / new-architecture-acceptance / historical-comparison
实际 cwd、分支、HEAD：
架构祖先检查退出码（新开发与新架构验收必须为 0）：
已读：AGENTS.md、architecture-implementation-20260912.md、本合同
本次 module / interface；直接依赖；沿用的 adapter：
独占文件；不在本次范围的接线：
受影响测试与实际验收；验收资源/候选身份：
交付：稳定源码 SHA、测试结果、遗留限制；交付后停止写入：
```

在实际执行检出运行：

```text
git branch --show-current
git rev-parse HEAD
git status --short
git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD
```

必须检查最后一条命令的退出码；非 0 不可继续新开发或宣称新架构验收。历史对照允许旧 HEAD，但须说明比较对象和冻结来源，不能作为新功能落点。工作树中的修改也必须复核，祖先检查本身不能发现后来删除或绕过 interface 的改动。

## 集成与验收交接

主推进会话在接收稳定交付时复核实际 diff：是否复用上表已有 module，是否让算法导入 UE/部署/固件细节，是否把具名执行器退回通用四旋翼数组，是否将模型、外观和固件身份重新绑定。发现问题先在该切片内修正；必要的 interface 演进记录原因和兼容迁移，不创建平行实现规避约束。

旧工作区未提交的私有接线不能通过更新整个目录迁入新候选。由主推进会话先保存源码身份和 diff，逐文件确认是否仍需要，再适配现有 module。新候选从自身实际路径归档源码/构建/部署身份，运行前沿用原有负载、boot、新鲜度、原生屏障与安全门。没有完成这些步骤时保持候选未准入。

按变化运行相关测试：模型/控制/实验 interface 变化至少覆盖 `validation.test_vehicle_models`、`validation.test_control_module_seams`、`validation.test_experiment_bundle` 及被改变模块的原测试；UE 变化需要实际构建与视觉检查；固件/内环变化需要适用栈的构建和真实对照。纯文档或独立 perf 变化不无条件重跑已通过飞行。旧证据保留，受新变化影响的组合另建运行证据，不能沿用旧 PASS 冒充当前候选。

本合同是执行约束，不是后台调度器，也不替代工单的既有验收门。
