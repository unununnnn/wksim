# Ackermann 速度响应边界最小修复（2026-09-13，DS 席位）

本目录是本任务唯一写入的收据目录；只交付本任务代码、相关测试、稳定 SHA 与未验证边界，交付后停止写入。

```text
工作类别：new-development
实际 cwd：C:/Users/PC/Documents/odid编译/wksim
分支 / HEAD：main / 9e8ba03e43627918d5fab28aa59765a02fb068d1
架构祖先检查：git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD → 退出码 0
已读：AGENTS.md、docs/architecture-implementation-20260912.md、docs/coordination/architecture-continuation-20260913.md、
      docs/coordination/module-delivery-policy-20260912.md、Simulator/wksim_core/{ackermann,vehicle_state,vehicle_models,rover_json}.py、
      validation/test_vehicle_models.py、.gitignore
module / interface：Simulator/wksim_core/ackermann.py 的 AckermannModel.step 与 AckermannParameters 速度响应边界；
      沿用 VehicleState（SI / NED / FRD）与具名执行器 ACKERMANN
直接依赖：math、dataclasses（原有）；wksim_core.vehicle_state.VehicleState（原有）
独占文件：Simulator/wksim_core/ackermann.py、validation/test_ackermann_response_bounds.py、本收据目录
不在范围：VehicleModel 1ms 接口与 Quad adapter、车辆家族映射、rover_json 传输、固件/控制/视觉职责、
      转向响应、max_speed 之外的外部直接写 speed 语义、native/构建/SITL/ROS/UE/MATLAB
受影响既有验证：validation.test_vehicle_models（默认参数路径，本轮未重跑，由 main 执行）
交付：implemented / test-prepared（非 passed）+ 稳定 SHA + main 测试命令 + 未验证边界
```

## 1. 复现的缺口（main 已实测，本席位未重跑）

参数全部合法：`AckermannParameters(speed_response_s=.0001)` 其余默认（`max_speed_m_s=5`、`max_acceleration_m_s2=3`、`speed_response_s=.0001>0` 有限）。

原 `step` 是显式 Euler 响应：

```text
a        = clamp((throttle*max_speed - speed)/tau, ±a_max)
following = speed + a*dt
```

当 **dt > tau** 时，未被加速度钳制的分支给出 `(target-speed)*dt/tau > (target-speed)`，即单步越过目标；被钳制时 `a*dt` 同样可能大于剩余差。因此 2000 次 `step(throttle=1, steering=0, dt_s=.001)` 后 `speed=5.0010000000000785 > max_speed=5`。这是响应实现越界，不是参数非法，也不是物理精度问题。

## 2. 最小修复

```python
target_speed=throttle*p.max_speed_m_s
acceleration=max(-p.max_acceleration_m_s2,min(p.max_acceleration_m_s2,
    (target_speed-self.speed)/p.speed_response_s))
following_speed=self.speed+acceleration*dt_s
if self.speed<target_speed<following_speed or following_speed<target_speed<self.speed:
    following_speed=target_speed
    acceleration=(following_speed-self.speed)/dt_s
```

- **每步有界地接近当前目标**：只在显式 strict 穿越成立时把 `following_speed` 钉在当前目标上，因此该步之后 `speed` 落在 `[min(speed,target), max(speed,target)]` 内，永不越过。
- **保持 max_acceleration 约束**：穿越意味着 `|target-speed| < |a|*dt`，故改写的实现增量 `|target-speed|/dt < |a| ≤ a_max`；非穿越步的增量仍等于被钳制的 `a`。
- **specific_force 对应实际增量**：穿越步把 `acceleration` 改写为 `(following_speed-self.speed)/dt_s`，与 `speed` 的实际变化一致；返回元组第 6 项第 1 元素仍是该 `acceleration`。
- **默认参数下原数值路径与输出不变（静态论证，未执行）**：默认 `tau=.25`、契约 `dt ≤ .02`，故 `dt/tau ≤ .08 < 1`；`a` 与 `(target-speed)` 同号，`following` 恒不穿越目标，两个 strict 比较均为假，分支不执行。原语句的运算顺序与类型（`max/min`、乘法、除法）逐字保留，`target_speed` 只是同一乘法的绑定；因此默认路径与旧实现的浮点结果逐位相同。已准备的等价用例对位置/速度/姿态/角速度/比力/时间做逐位比较（由 main 执行）。
- **未新增拒绝合法参数**：`__post_init__` 未加任何 `speed_response_s` 下界或 `dt/tau` 约束；dt 契约仍为 `0<dt_s<=.02`。
- **未改**：1ms 接口（`VehicleModel.dt_s=.001`）、Quad adapter、车辆家族映射、转向指数响应、yaw/位置积分、重力项、四元数。

## 3. 已准备的测试（本轮未运行，状态 test-prepared）

`validation/test_ackermann_response_bounds.py`（9 用例，纯模型接缝，无固件/ROS/GPU/MATLAB）：

| 用例 | 覆盖 |
| --- | --- |
| `test_small_response_constant_cannot_exceed_the_declared_max_speed` | 正向：`speed_response_s=.0001`，2000×(.001) 后每步速度 ∈ [0,5] 且终值恰为 5.0 |
| `test_small_response_constant_holds_the_reverse_speed_bound` | 反向：throttle=-1 时每步 ∈ [-5,0] 且终值恰为 -5.0 |
| `test_zero_throttle_brakes_to_rest_without_crossing_it` | 刹停：从 4 m/s、throttle=0 单调降到恰为 0.0，不穿越 |
| `test_crossing_step_reports_the_bounded_increment` | 穿越步：单步从 4.999 到 5.0，specific_force 等于实现增量且 ≤ a_max |
| `test_reported_specific_force_is_the_realised_speed_increment` | 5 组参数：逐步 `specific_force[0] == (speed_{k+1}-speed_k)/dt`，|增量| ≤ a_max |
| `test_bound_holds_across_every_allowed_step_length` | 小/中/默认响应常数 × dt ∈ {.0001,.001,.005,.01,.02}：单调不降、不超目标、单步增量 ≤ a_max·dt |
| `test_default_parameters_keep_the_verified_response_path` | 默认旧新等价：3 组工况 × dt ∈ {.001,.02}，1000 步内按原闭式重算并逐位比较全部输出字段 |
| `test_small_response_constants_stay_legal_parameters` | `.0001/.001/.25/5.` 仍合法；0/负/NaN/inf/字符串/bool 仍被拒 |
| `test_signed_command_and_step_contract_is_unchanged` | dt=0、dt=.0201、|throttle|>1、|steering|>1、NaN 仍被拒，dt=.02 合法 |

**main 执行命令（本席位未执行，不得据此报告 passed）**：

```text
python -m unittest validation.test_vehicle_models validation.test_ackermann_response_bounds -v
python -m unittest discover -s validation -p 'test_ackermann_response_bounds.py' -v
```

## 4. 本轮静态检查（已执行，只读）

`check_ackermann_response_bounds_source.py` 只用 `ast` 解析两份交付源码，**不 import 模型、不调用 `step`、不运行任何模型测试/构建/native**：

```text
python validation/coordination/ds-ackermann-bounds-20260913-01/check_ackermann_response_bounds_source.py
→ {"failed": [], "checks": 25, "model_sha256": "cb0dea4c…", "test_sha256": "feea4b95…"}  退出码 0
```

25 项检查含：穿越条件逐字、穿越分支两条改写语句、返回元组第 6 项首元素仍是 `acceleration`、重力项未变、`__post_init__` 仍只有 2 处 `Raise` 且未引用 `speed_response_s`、dt/throttle/steering 契约文本未变、导入集合仍为 `dataclasses/math/vehicle_state`、`step` 内除输入校验外只有穿越一个分支、转向响应语句未变、测试文件 9 个用例名齐全且不在导入期调用 `step`。证据：`evidence/static-check.json`。

## 5. 未验证边界与遗留限制

- **测试未执行**：9 个用例仅静态审阅，未运行；状态是 test-prepared，不是 passed。
- **默认路径等价未实测**：结论来自静态论证 + 未运行的逐位等价用例；`validation.test_vehicle_models` 未重跑。
- **未运行任何真实栈**：无 native、构建、SITL、ROS 节点、UE、MATLAB、厂商模型；未重跑 `validation/rover-reference-*` 历史收据，也未把旧 PASS 复制为当前验收。
- **只覆盖 `AckermannModel.step` 的油门→速度响应**：调用方直接写 `model.speed` 超过 `max_speed_m_s` 时仍不受界（保持原语义，不在本次目标内）。
- **不改物理主张**：本修复只是把数值响应限制在已声明目标内，不声称新的轮胎/滑移/地形物理准确性。
- 未提交、未推送、未发 GitHub 评论、未关票；未改 `/root/wksim-release-acceptance-fe3` 或任何历史工作区；未触碰他人修改与 perf 目录。

## 6. 交付文件（稳定 SHA）

| 文件 | 字节 | sha256 | git blob |
| --- | --- | --- | --- |
| `Simulator/wksim_core/ackermann.py` | 3137 | `cb0dea4c6d0ba3f541cf306cd23a730f728d8fa5642f7d7a70ba97783cb8c2ed` | `2d02acef606498d227a989440c4092b02b8c4022` |
| `validation/test_ackermann_response_bounds.py` | 8232 | `feea4b9589abc649ea026f4c4be51eb0449e5f7658f8a7f8823f8d5f3a37e13e` | `df08ffe991e707144f726a609635d443d2b993ab` |
| `validation/coordination/ds-ackermann-bounds-20260913-01/check_ackermann_response_bounds_source.py` | 8088 | `4d84d3fb546f6d8869a5a3bf93422826c9ed247364b684b22b648b463ed2c503` | `aeec048d178728181d7417aa80b2d8c0bed5e6d7` |
| `validation/coordination/ds-ackermann-bounds-20260913-01/evidence/static-check.json` | 2263 | `986e7c25ff0de0fe11794d3617f315d085c1b9898b0c01af540d488ecd8c4d47` | `2b5456faaf6b87b8c603b2a082977cc06e5d9bb5` |

`validation/coordination/**` 与既有 `validation/test_*.py` 在 `.gitignore`（`/validation/*/`）下多为未跟踪；`validation/test_ackermann_response_bounds.py` 位于 `validation/` 顶层，`git status` 显示为未跟踪新文件。精确提交由主推进会话决定。

## 7. 停止写入

交付以上 SHA 后本席位停止写入本模块；如 main 运行任一新用例失败，请附失败用例名与原始输出，由本席位在该切片内修正后再交付新 SHA。
