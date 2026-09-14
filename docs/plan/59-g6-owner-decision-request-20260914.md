# #59 G6 owner-decision 请求：求解形式、OD-01/OD-02 调度/时间语义、OD-20 active/extra 电机输出范围

状态：`request_only` / `effective=false` / `owner_decisions_made=false`。本文件只是**向 owner 提出三组决策请求**，不是决策、不是预算、不是验收、不是合同冻结。机器可读载荷为
[`validation/e0-g6-owner-decision-request-20260914.json`](../../validation/e0-g6-owner-decision-request-20260914.json)，
校验器为
[`validation/test_e0_g6_owner_decision_request.py`](../../validation/test_e0_g6_owner_decision_request.py)。
被请求的 owner 决策只有 `OD-01`、`OD-02`、`OD-20` 三项，其余 `OD-03..OD-19`、`OD-21..OD-24` 继续开放。

本请求依据的已提交材料（**至多六份**，全部按 tracked HEAD 的 SHA256/size 钉定）：

| pin id | 路径 | SHA256 | size |
| --- | --- | --- | --- |
| `g6_remediation_contract` | `docs/plan/10-g6-remediation-contract.md` | `48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0` | 9935 |
| `dynamic_budget_source_map` | `docs/plan/59-e0-dynamic-budget-source-map.md` | `35a56084105409329131add7d4b9e35be6d1a145c6e18268c96324805313cd42` | 11215 |
| `frame_datum_binding` | `validation/e0-frame-datum-binding-20260914.json` | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | 105018 |
| `solve_form_decision` | `validation/e0-g6-solve-form-decision-20260914.json` | `5086c3fbddd52b4e754a785706cce938ca7f8d68beb5056d564e7f116b34c293` | 11339 |
| `budget_approval_provenance` | `validation/e0-budget-approval-provenance-20260914.json` | `2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d` | 285820 |
| `r1_contract` | `Simulator/wksim_core/numerical-conformance-v1.json` | `23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0` | 29846 |

## 三组请求（全部 `not_made`，无一项被选中）

### DG-1 求解形式（G6/B5）

C3G 首步求解形式选择：采用诊断用统一对角 reciprocal-multiply 分支、保留当前生成的 division/mrdivide 形式、或暂缓。三个候选 option 的 `chosen` 全为 `false`，`state=not_made`，`chosen_option=null`。该组只钉定 C3G 首步观测；C0/C2G、其余 major 样本、23 个未映射状态与非对角惯量仍未被观测，观测到的 1 ULP **不得**反推为任何预算值。`blocked_by=[B1, B4]`。

### DG-2 OD-01 / OD-02 调度与时间语义

槽位：`Vehicle60[2]`、`Sensor30[0]`、`GPS30[0]`（`schedule_metadata`）。

- `OD-01`：这三个时间字段是排除在物理精度比较之外（B3），还是各自获得有依据的界？
- `OD-02`：`vehicle_time`、`sensor_time`、`gps_time` 的绝对零点/epoch 是什么，微秒到秒的关系如何锚定？

采样只固定 k 网格（k=0..500、固定步长 0.001 s）与 major-root 输出相位，不绑定 epoch。`state=not_made`，`blocked_by=[B1, B3]`。

### DG-3 OD-20 active/extra 电机输出范围

槽位：`Vehicle60[20]`..`Vehicle60[23]`，`contract_semantic_status=inactive_channels_not_aircraft_coverage`。

- `OD-20`：`extra_motor_speed` 的非活动通道是否属于对外比较契约？

四个 active 槽位 `Vehicle60[16]`..`Vehicle60[19]` 不在该组范围内，`OD-19`（标量转速 frame 与 rpm 参考）对全部八个电机槽继续保持开放。`state=not_made`，`blocked_by=[B1, B4]`。

## 证据与拒绝边界

- 祖先关系：必须满足 `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` 与 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 都是当前 HEAD 的祖先（`git merge-base --is-ancestor` 退出码必须为 0）；**不**断言精确 HEAD 相等，`observed_head` 只是记录值，后续无关提交不使本请求失效。
- pin 身份：每份来源按 tracked HEAD blob 的 SHA256/size 钉定，且工作区字节必须与同一 SHA256/size 一致；缺失、替换、多余、未跟踪或漂移一律失败关闭。
- 证据路径：任何 `validation/coordination/...` 形式的证据路径在**大小写不敏感**归一化后一律拒绝。
- 派生：`RD-01..RD-12` 为禁止派生类别；`derivation_class` 与 `derivation_ref` 必须为 `null`，非空即拒绝。
- 预算：本请求**不含任何数值预算**，禁止出现 `abs_budget`、`rel_budget`、`rms_budget`、`tolerance` 等数值字段；预算批准声明一律拒绝。
- owner 选择：任何被选中的 option、`state=made`、`made_by`/`decided_utc`/`decision_text` 非空一律拒绝。
- 关闭声明：`issues_closed` 为空 `[]`；`#84`、`G6`、`Full`、`B1`、`B3`、`B4`、`OD-03..OD-24`（除 `OD-20`）保持开放，任何关闭或验收声明一律拒绝。

## 保持不变的状态

- `r1_status=numerical_failed`
- `budget_approved=false`、`g6_acceptance=false`、`physical_accuracy=false`
- `owner_decisions_made=false`、`effective=false`
- `issues_closed=[]`；`#84`/`G6`/`Full` 开放；`B1`/`B3`/`B4` 开放
- 请求中的三组决策状态全部 `not_made`

本切片未启动 native/模型/MATLAB/ROS/FC/UE/构建，未运行 #83，未修改、暂存或提交真实索引（临时索引仅在仓库外用于测试），未提交、未推送、未改动 GitHub issue，也未触碰兄弟工程。本请求不是数值验收或 G6 通过，R1 结果不被改写。
