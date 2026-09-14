# 接口决策包离线入库说明（2026-09-14）

## 绑定范围

- 观测提交：`e8defc1d8317892e022ee24de086b026c1317e5a`；架构祖先：`f333316e6efa6b299b4288a9d91fb2bccedfb9d6`。
- 原件：`docs/coordination/ds-interface-decision-packet-20260912.md`。
- 原件 SHA-256：`a7cfe224f2528a5651c6037eae7cf1547ae57e1dfe210c7792308ad247d5e382`。
- 原件保持字节不变。本说明只把它接入为历史上下文和证据来源，不把它提升为决策依据。

本说明不作预算批准、接口选择、厂商 ABI 取舍或所有者决定，也不授予 #9、#26、#29、#33、#84、Full、G6 或 Goal 的验收与关闭资格。

## 两份历史跟踪记录

`docs/plan/9-vendor-abi-defer-boundary.json` 及同名 Markdown 把原件登记为 `tracked=false`。这是真实的历史/来源状态观测：在本批次入库前，原件仍是工作树未跟踪文件。该记录中“原件不能作为决策权威”的结论继续有效；即使跟踪状态随后改变，原件仍明确不替用户作决定。

`validation/coordination/ds-dll-abi-evidence-20260913-01/audit.json` 及 `audit.md` 把同一原件登记为 `tracked=true`。在本批次入库前，该布尔值与实时 Git 状态不符。若原件按本说明保持原哈希提交，`tracked=true` 只会变成当前跟踪事实；它不会追溯修改前一份记录的观测时点，也不会把原件提升为批准、验收或所有者决定。

两份记录对原件路径和 SHA-256 的绑定一致。差异仅在跟踪状态的观测时点与语义，不能用来推导新的接口决定。

## 已过期的读取方陈述

原件第 5.3 节称 `wksim.display-manifest.v1` 的唯一读取方是离线审计器 `tools/audit_29_terrain_evidence.py`。该陈述已被后续已跟踪实现 `Simulator/wksim_runtime/display_scene_binding.py` 取代；后者包含 `load_manifest()` 和 `validate_manifest()`，会读取并校验显示清单。

这只使“唯一读取方”陈述过期，不证明 UE 侧消费者、真实 UE/WSL/FC/ROS2/DDS 闭环或 #29 验收已经完成。原件保持不改，由本说明显式记录时间差。

## 与 #83 诊断证据的边界

提交 `e8defc1d8317892e022ee24de086b026c1317e5a` 已接入 #83 联合速率诊断原件和离线一致性测试。该证据处理 GC 锁存、分组迟到与 `RateUnmet` 记录；本接口包处理 #9/#29 的接口、显示清单和厂商 ABI 决策边界。两组证据主题、schema 和验收作用均不同，不能互相替代。

## 依赖与离线测试接缝

后续纯离线测试应固定并验证：

1. 原件路径和 SHA-256 保持不变，且本说明明确限制为上下文证据。
2. 两份 JSON 中对应原件的路径和哈希唯一且一致；`tracked` 分别为历史 `false` 和预期入库后 `true`。
3. `Simulator/wksim_runtime/display_scene_binding.py` 是已跟踪文件，并包含显示清单加载与校验入口；本说明必须标记原件的“唯一读取方”陈述已过期。
4. #83 证据路径属于提交 `e8defc1d`，且本说明不把联合速率结论解释成接口或场景验收。
5. 任一重复记录、缺失字段、路径/哈希漂移、权限提升措辞或验收措辞都应失败封闭。

该测试只证明入库语义、身份和过期陈述得到明确绑定。它不运行原生程序、WSL、MATLAB、ROS、DDS、SITL、飞控、UE、模型、构建或飞行，也不替代任何真实运行门。
