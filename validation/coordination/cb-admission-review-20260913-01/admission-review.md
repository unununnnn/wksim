# cb-admission-review-20260913-01：正式准入保障独立复核

范围：只读本库 validator/上游测试 + 两场原始证据；新增仅本目录 `test_admission_safeguards.py`。未改正式目录/validator/验收状态，无 Git/issue 写。

## 1. validator 保障核对（joint_profile.py `575adb53…`）

`_mixed_proofs` 实测路径：标记键存在即拒（274–276）；status/flight_completed/source_unchanged/control_shutdown_clean/cleanup/audit 双 pass（278–284）；raw 证据逐文件 SHA（`_raw_proof` 214–217）；admission 身份/能力/manifest/候选钉扎（286–312）；explicit message 绑定（`_mixed_message_proof` 243–260）；sealed source 链（317–328）；pacer 源必含且 flight↔audit↔admission 三向一致（329–342）；argv 双能力参数（343–351）；PX4/model/baseline 同一资源集（352–360）。

## 2. 独立新增测试（复用真实 `_mixed_proof_fixture`，不 monkeypatch validator）

`test_admission_safeguards.py` 5 项全过（`python -m unittest discover -s validation/coordination/cb-admission-review-20260913-01`）：

- 正向控制：真实 fixture 通过真实 `_mixed_proofs`；
- 两标记 × True/False/None/{} 八组合均按"cannot include <marker>"拒绝（上游只各覆盖一种值）；
- 两 pacer 各自三种破坏：缺失→"Missing executed mixed proof source identity"、flight 哈希篡改→"Retained executed source is not sealed"、留存快照篡改→"Raw flight evidence differs"（上游仅 pacer[0] 两种）；
- admission 源钉扎绑错 pacer digest（经诚实的 mutate→重写→重算 pin/audit 链到达目标检查）→"Admission/execution source differs: <pacer>"（上游仅 run_joint_flight.py）；
- legacy 证明带未绑 message_candidate→"Unbound message candidate in legacy mixed proof"（上游未覆盖）。

## 3. 为何两场都填不上"未探测 MIXED 证明"缺口

| 场 | task_profile | status | 标记 | 结论 |
|---|---|---|---|---|
| rfw9nmbb | `xy_velocity_z_position_yaw_v1`（MIXED 半） | failed：RateUnmet tick 98684，lateness 100,019,970 ns，flight_completed=false | 含 `group_work_timing`（census，valid，24,661 组/18 超预算） | 双重失格：非 pass 且标记键存在——诊断正是"probed"，正式门即拒 |
| 1w6dru32 | `full_xyz_pv_yaw_v1`（PV 半） | pass，flight_completed/source_unchanged=true，pacer 源已封 | 无 rate_timing_probe/group_work_timing | 只证 PV 半；`_mixed_proofs` 要求证据集 == 两个 MIXED_TASKS，MIXED 能力半仍无未探测证明 |

结论：MIXED 缺口只能由一场**无诊断标记且 pass** 的 mixed-profile 飞行补上；rfw9nmbb 的 census 诊断合法但天然 diagnostic_only，1w6dru32 再干净也只是另一半。

## SHA-256

- `test_admission_safeguards.py`：`fa147073523f6c72e231b9723fb8a0b794617fb731fa89af874cabf40cbdbc1c`
