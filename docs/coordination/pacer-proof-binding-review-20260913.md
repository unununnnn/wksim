# pacer-proof-binding-review-20260913：#84 正式证据标记拒绝的纯测试复核

范围：仅 `validation/test_joint_profile.py` 与本文档；未改任何实现、旧证据或 Git。

## 被测实现（只读核对）

`Simulator/wksim_runtime/joint_profile.py::_mixed_proofs`（274–276 行）：对每份 pinned flight 结果检查键存在性，`('rate_timing_probe','group_work_timing')` 任一键出现即 `ValueError('Formal mixed/PV evidence cannot include '+marker)`——与值无关。故 True/False/None/空对象四种值必须全部拒绝。

## 测试变更（真实函数 + 完整真实夹具，非源码字符串比对）

- `_mixed_proof_fixture` 新增通用 `marker=(name,value)` 注入参数（旧 `add_probe_record` 参数与行为不变）。
- 新增 `test_rejects_group_work_timing_marker_with_any_value`：在同一完整两任务 mixed/PV 证据树（pin digest 全部由实际写入字节算出）上跑真实 `_mixed_proofs`，`group_work_timing` 取 True/False/None/{} 四个 subTest 均断言拒绝。
- 保留未动：两 pacer source 钉扎正例（`test_positive_with_pacer_sources_present_and_sealed`）与移除反例（`test_rejects_when_either_pacer_source_removed_from_flight_and_audit`）、旧 `rate_timing_probe` 负例（`test_rejects_timing_probe_marker_in_formal_evidence`）及全部既有钉扎/篡改负例。

## 结果

- WSL Ubuntu-22.04（Python 3.10.12）：`python3 -m unittest validation.test_joint_profile` → **18/18 OK**（含真实 symlink 逃逸负例）。
- Windows 主机：17/18，唯一 error 为既有 `test_source_file_tamper_and_escape` 的 `symlink_to` 段——原限制说明：Windows 创建 symlink 需特权（WinError 1314），该真实 symlink 负例在 Windows 不可创建，非本次引入，未删改；WSL 下通过。

## SHA-256

- `validation/test_joint_profile.py`：`4a7ce076f24f92ac6b69f72d3308575db40ac1670b04973cacbcdb77111485a0`
- 实现参考（未改）`Simulator/wksim_runtime/joint_profile.py`：`575adb530944f48fa164a127a88b5abb76991e522ee1dbb8e54ef10ccc6bf5a2`

## 限度

纯夹具测试证明键存在即拒的契约；不证明任何真实飞行证据合格/不合格；不改全场验收状态。
