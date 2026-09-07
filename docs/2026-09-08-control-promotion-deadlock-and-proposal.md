# 2026-09-08 控制提升级联：证据层死锁与提升机制提案（#32 相关，提交用户）

承接 C1 轮。本轮全部由主代理完成。首次在 profile 机制下提升控制包（8xt3WC→FVMjak），暴露了此前从未触发过的结构缺口；不代为决定。

## 已完成（无碍部分）

1. FVMjak 控制候选构建 + 81 项候选矩阵通过（含 2 项新速度测试）。
2. 联合 profile 提升：健康提升飞行 `_cs_wxw_`（FVMjak 实飞+独立审计通过）→ joint-profiles 换钉（control/workspace/模型库目录），离线 `check_profile ok:True`。
3. MUlZd0 控制快照按 FVMjak 重同步（.so 字节一致；快照哈希 88f92c9d…，索引已更新）；示例配置换钉。
4. 会话矩阵由 404 增至 406（新增 2 项速度测试通过）。

## 死锁（四处验证，同一根因）

profile 机制下每层证据都绑定「历史飞行↔当前资源」；控制一变，历史飞行的记录即与当前钉不匹配，而**新飞行又必须先通过引用旧证据的预检**：

1. `independent-profile-evidence.json`：历史独立飞行 config 的 `prometheus_workspace=8xt3WC` 与其 `manifests` 均不匹配 FVMjak 钉 → `check_flight_evidence` 拒绝 → 新独立飞行无法启动（实测 `independent-flight-px4-20260908-run1` 预检如实拒绝）。
2. capability-index `session_v1` 证据（px4-dds-hxgna8aa / arducopter-dds-xuvva567）：记录逐文件哈希为旧控制；MUlZd0 同步后 `test_wksim_control_profile` 两栈如实拒绝（「Installed control Python file set differs from both flown results」）。其 legacy 预检同样先查该证据，同样死锁。

**此前从未有过 profile 机制下的控制提升**（8xt3WC 是机制创建时的首个控制），因此没有任何提升通道代码：无 promotion 配置键、无跳过证据绑定的标志、无目录重建工具。

## 提案（提交用户选择）

**A. 显式提升飞行机制（推荐，~30 行+测试）**：实验 config 增加显式 `promotion_flight: true`——预检跳过历史证据绑定（资源/固件/模型/消息/构建校验全部保留），`candidate_status.flown=False`、`flight_provenance='promotion_flight'`；飞完后用新飞行重建两层证据目录（independent catalog 与 capability-index session_v1），并在同一次收口提交中删除该键的全部使用痕迹（审计可见）。不做默认放行，不放宽任何数值。

**B. 暂时回退**：joint-profiles/索引/示例全部回退到 8xt3WC，#32 的速度实施保留为未准入候选（FVMjak 与 81 项矩阵保留），C1 验收无限期等待用户另定提升方式。代价：速度能力长期无法实飞，违背效率目标。

**C. 用户手工执行**：用户自行以既有机制完成换绑（若有供应商侧的既定流程），我方按结果核对。

当前矩阵状态：406 项中 403 通过/29 跳过；3 项红（本节 1 的 1 项 + 2 的 2 项）精确对应两个死锁层，不是产品回归。#32 速度任务全场景干净验收另待宿主窗口（见 C1 报告）。
