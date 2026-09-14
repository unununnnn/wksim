# OMP G6 参考端首步证据独立审查（2026-09-13，只读）

对象：`tools/probe_reference_first_step.m` 与
`validation/coordination/g6-reference-probe-20260913/`（run-03 结果 +
execution-03 分析/输入检查/退出）。未跑 MATLAB/整套测试；未改实现/原件；
无 native/构建/Git/嵌套。

## 逐项核对结果

### 1. 相邻同时间观测的严格区分（关键核对）
PostDerivatives 时点分布：0×4、0.0005×8、0.001×4（4 积分器 × 时点组
0/.0005/.0005/.001，与 UDD Data 访问声称一致）。逐块核对同一块的两个
0.0005 事件（以 q0 为例）：**状态 hex 完全相同，导数 hex 不同**
（第二次出现非零导数）。结论：两次相邻同时间观测**只能靠内容区分**——
`(event, time, block)` 三元组身份本身有歧义，任何以时间为键的合并都会
把两次观测折叠成一次。审方强调：主会话 JSON 已如实标
`ode4_stage_mapping: unverified; event order alone is not a solver-stage proof`，
该克制成立，不得仅以事件数（72）宣称 G6 通过。

### 2. 事件与访问完整性
72 = PreOutputs 20 + PostOutputs 20 + PreDerivatives 16 + PostDerivatives 16；
dropped=0；4 积分器 double 状态与导数均以 IEEE 全精度 hex 留存 ✓。
状态 `partial`（数值可访问性与阶段映射需进一步检查）为如实状态，非失败。

### 3. major 输出与输入
major_times [0, 0.001]；Sensor30/GPS30/Vehicle60 各 2 行样本，共
(30+30+60)×2=**240** 个 f64；`major_bit_differences` 三项全 0——与冻结
C3G 前 2 行逐位一致 ✓。`inputs_unchanged=True`，changed=[] ✓。

### 4. 发现的真实问题
1. **输入检查一项 False**：`wksim\tools\run_numerical_conformance.py`
   expected≠actual（staged 副本 True）——本次执行用的是 staged 副本；
   仓库当前副本与 staged 已分叉，**不能把 staged 的通过读成"仓库当前版本
   已验证"**。需 owner 裁定是更新 staged 还是回填仓库。
2. **Java 输出非崩溃原子**：`CREATE_NEW` 把"拒绝覆盖"与打开绑定（好），
   但无 tmp+fsync+rename——写入中途崩溃会留下半成品文件，且同一路径下次
   CREATE_NEW 必失败（自锁）。当前报告完整未受影响（exit 0），属边界风险
   而非本次缺陷。

### 5. 清理/回调边界（核对通过）
`onCleanup` 注册顺序正确（环境清理先于模型清理注册 → 触发时模型清理先行）；
listener 句柄逐个 delete、StartFcn/InitFcn 恢复原值、模型 close(0) 不保存、
base 变量清除、path 与 fileGenControl 恢复——边界完整。

## 边界声明（强制）
本审查只把**已观测的** 4 积分器状态/导数与 240 个 major 输出当参考；
不据此排除上游未观测状态，不推断目标端（接收侧）得到相同值；阶段映射未证；
前 2 次访问不完整的原件已保留，本审查仅覆盖 run-03 与 execution-03。
