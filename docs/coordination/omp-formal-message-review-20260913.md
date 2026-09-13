# OMP 正式 message 接线独立审查（2026-09-13，只读）

对象：提交 `4584093`（Bind formal capability proofs to sealed current message
packages）。只读源码与已落盘小 JSON；未跑大扫描/整套测试；无 native/构建/ROS/
嵌套/Git。主会话 Linux 24 passed/52 subtests 未重复。

## 审查结论：四项要点全部成立

### 1. 封存选择同时约束五个面 ✓
`_mixed_message_proof`（joint_profile.py:243-260）一次性钉死：
flight.message_candidate == candidate、admission.message_candidate == candidate、
admission.identities.message_candidate == candidate、admission 的
manifest path/sha == Control 封存值、**审计 hash**
（`evidence_sha256['message-build.json'] == checksum`）、**留存 manifest 字节**
（`_pinned_json(message-build.json) == candidate`）。`_mixed_proofs:287-292` 再把
message 纳入 flight 三方 manifest 比较。测试 `..._mismatches_cannot_fall_back_to_baseline`
覆盖六种逐项失配，`test_retained_message_bytes_are_verified_not_just_recorded_hashes`
覆盖留存字节篡改——无遗漏面。

### 2. 仅两个消息包可覆写，其余仍匹配 baseline/index ✓
`_candidate_message_packages`（:221-240）强制包集合恰为
`{'prometheus_msgs','wksim_msgs'}`、prefix 恰为 `root/install/<name>`（绝对路径）、
`installed_sha256` 为 64-hex、`complete_snapshot=True`；集合或身份不符即
fail-closed。`check_resources:471-476` 从 INDEX baseline（排除 prometheus_msgs）
+ session_v1 installed（排除 prometheus_control）组装后**仅** `.update` 候选两包；
digest 用 complete snapshot 复核内容；`_overlay` 三重（spec origin/ament/linker/
已导入模块）绑定实际原点。mixed 下 prometheus_msgs 仅由当前封存提供——这是设计
内的事实，不是漏洞：它的源文件属 Control 工作区，overlay 原点仍受 _overlay 约束。

### 3. 不从缺 mixed 证明或旧 overlay 授予 capabilities ✓
`message-binding-final.json` 实证：message binding pass 的同时
`profile_still_rejected=Missing final mixed/PV capability flight proofs`、
`capabilities=[]`、`children_created=0`——消息层通过与能力授予严格分离。
旧 overlay：`message-old-overlay-rejected.json` 实证 MUlZd0 原点被 _overlay 拒绝
（fresh process、当前 Rzj3Pf 起源必须拒绝）。`result['capabilities']` 只在全部
检查通过后赋值（:502）。

### 4. 诊断不得提升 ✓
`test_mixed_result_with_rate_timing_probe_is_rejected` 证明 `rate_timing_probe`
键存在即拒（含 None/{}/False 标记——`in` 检查键存在性），且 `_raw_proof` 未被
调用；无 probe 时走既有路径。

## 定向反例核对（已执行，无新问题）

- **覆写范围**：若候选包集合含第三名 → 集合相等性拒绝 ✓（:228）。
- **legacy 路径**：candidate 为 None 但 flight/admission 带 message_candidate →
  拒绝 ✓（:246-248）。
- **prefix 尾斜杠/非绝对路径**：字符串严格相等 → 拒绝 ✓（:233-237）。
- **符号链接包目录**：内容 digest 可过，但 `_overlay` 的 `resolve()` 原点比对
  捕获 ✓（已验证代码路径）。

## 未发现缺陷的边界声明

- 未执行 native/大扫描；以上均为源码+已落盘 JSON 的静态复核。
- INDEX baseline 内容若与 Rzj3Pf 重叠的第三方包 digest 由 INDEX 自身完整性
  承担（本次未重算 INDEX 全部 digest——属主会话资源窗口内检查）。
- `_mixed_message_proof` 的 legacy 负分支仅由类型检查覆盖，无真实 legacy
  mixed 运行原件可复核（本就没有）。

**有界结论：4584093 的 message 接线审查通过，无阻断项。**
