# Luna 执行子票完整索引

2026-09-09：72个子票已发布，34个Luna、36个Astra、2个具体决策。原17张实施父票及#9/#1/#10保留为验收/决策容器。状态实时查询请使用 `python tools/lunar_queue.py next`；下面是结构索引，不是运行许可缓存。

[完整推进指南](../../lunar模型完整推进指南.md) · [任务定义](lunar-backlog.json) · [GitHub映射](lunar-issued.json)

## 可先执行的五票

| 子票 | 稳定键 | 工作 |
| --- | --- | --- |
| [#50](https://github.com/unununnnn/wksim/issues/50) | `35-preflight` | 执行一次 PX4 PID 只读准入 |
| [#51](https://github.com/unununnnn/wksim/issues/51) | `35-ap-preflight` | 执行一次 AP PID 只读准入 |
| [#52](https://github.com/unununnnn/wksim/issues/52) | `25-physics-core` | 实现 Hex 逐毫秒输入/时钟检查器（两文件） |
| [#53](https://github.com/unununnnn/wksim/issues/53) | `40-target-command` | 实现新鲜ArUco目标到公共速度意图（两文件） |
| [#54](https://github.com/unununnnn/wksim/issues/54) | `1-full-ledger` | 逐项整理 Full 原规格覆盖台账（不判完成） |

## #1 Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）

原父票依赖：无原生前置边。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#54](https://github.com/unununnnn/wksim/issues/54) | Luna | `1-full-ledger` · 逐项整理 Full 原规格覆盖台账（不判完成） | 按资源/身份预检进入 |
| [#55](https://github.com/unununnnn/wksim/issues/55) | Astra | `1-full-coverage` · 复核Full台账并把真实缺口转换为实施票 | #54 |
| [#56](https://github.com/unununnnn/wksim/issues/56) | 决策 | `1-hardware-boundary` · 明确Full硬件/资源的具体可验收边界 | #55 |

## #9 可选模型插件与场景反馈接口决策

原父票依赖：无原生前置边。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#58](https://github.com/unununnnn/wksim/issues/58) | 决策 | `9-contract` · 确认可实施的剩余ABI与场景反馈合同 | #57 |
| [#57](https://github.com/unununnnn/wksim/issues/57) | Astra | `9-evidence` · 核对模型DLL ABI与反馈合同的具体证据缺口 | 按资源/身份预检进入 |

## #10 规格：Prometheus 到 wksim 完整仿真工具链移植

原父票依赖：无原生前置边。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#60](https://github.com/unununnnn/wksim/issues/60) | Astra | `10-full-acceptance` · 按完整原规格及G0–G6进行最终Full复核 | #55, #56, #59, #20, #25, #26, #27, #28, #29, #33, #35, #36, #37, #38, #39, #40, #44, #45, #46, #47, #9 |
| [#59](https://github.com/unununnnn/wksim/issues/59) | Astra | `10-g6-remediation` · 确定来源一致的 G6 数值验收路线并保留R1失败 | 按资源/身份预检进入 |

## #20 联合场景暂停单步与冷重置

原父票依赖：#19, #8。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#61](https://github.com/unununnnn/wksim/issues/61) | Astra | `20-rate-engineering` · 定位并修复一个有证据的1×调度瓶颈 | 按资源/身份预检进入 |
| [#62](https://github.com/unununnnn/wksim/issues/62) | Luna | `20-rate-epoch-1` · 1× 第1个独立60秒epoch：运行一次并原始审计 | #61 |
| [#63](https://github.com/unununnnn/wksim/issues/63) | Luna | `20-rate-epoch-2` · 1× 第2个独立60秒epoch：运行一次并原始审计 | #62 |
| [#64](https://github.com/unununnnn/wksim/issues/64) | Luna | `20-rate-epoch-3` · 1× 第3个独立60秒epoch：运行一次并原始审计 | #63 |

## #25 六旋翼从参数配置到双栈运行

原父票依赖：#17, #24。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#52](https://github.com/unununnnn/wksim/issues/52) | Luna | `25-physics-core` · 实现 Hex 逐毫秒输入/时钟检查器（两文件） | 按资源/身份预检进入 |
| [#66](https://github.com/unununnnn/wksim/issues/66) | Luna | `25-ap-live` · 执行一次 AP Hex 飞行及六旋翼实时显示 | #65 |
| [#67](https://github.com/unununnnn/wksim/issues/67) | Luna | `25-ap-reset` · 执行一次 AP Hex 冷重置验证 | #66 |
| [#68](https://github.com/unununnnn/wksim/issues/68) | Luna | `25-px4-existing-audit` · 审计本轮 Hex PX4-03 既有记录（不重飞） | #65 |
| [#69](https://github.com/unununnnn/wksim/issues/69) | Luna | `25-px4-reset-live` · 执行一次 PX4 Hex 冷重置及实时显示 | #68 |
| [#65](https://github.com/unununnnn/wksim/issues/65) | Astra | `25-raw-auditor` · 完成 Hex 原生链、物理窗口与冷重置独立审计 | #52 |

## #26 生成模型构建导入与无MATLAB运行

原父票依赖：#24, #9。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#71](https://github.com/unununnnn/wksim/issues/71) | Luna | `26-generate-build` · 生成并构建一个已批准模型 | #70 |
| [#70](https://github.com/unununnnn/wksim/issues/70) | Astra | `26-generation-source` · 确定一个实际可用的模型生成来源及合同 | 按资源/身份预检进入 |
| [#72](https://github.com/unununnnn/wksim/issues/72) | Luna | `26-import-reset-run` · 验证无MATLAB依赖导入与一次冷重建 | #71 |

## #27 可选旧ABI模型DLL生命周期闭环

原父票依赖：#12, #23, #9。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#75](https://github.com/unununnnn/wksim/issues/75) | Luna | `27-core-without-dll` · 验证禁用DLL后自主核心仍可运行 | #72 |
| [#73](https://github.com/unununnnn/wksim/issues/73) | Astra | `27-host` · 实现一个已确认旧ABI的隔离宿主 | #58 |
| [#74](https://github.com/unununnnn/wksim/issues/74) | Luna | `27-legacy-lifecycle` · 执行一个旧ABI样本的生命周期 | #73 |

## #28 可选新ABI模型DLL与扩展输出

原父票依赖：#27, #9。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#78](https://github.com/unununnnn/wksim/issues/78) | Luna | `28-legacy-regression` · 执行旧ABI兼容回归 | #77 |
| [#76](https://github.com/unununnnn/wksim/issues/76) | Astra | `28-modern-adapter` · 实现一个已确认新ABI与扩展输出适配 | #75, #58 |
| [#77](https://github.com/unununnnn/wksim/issues/77) | Luna | `28-modern-lifecycle` · 执行一个新ABI样本及扩展输出检查 | #76 |

## #29 坡面与障碍场景的物理反馈

原父票依赖：#17, #23, #9。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#79](https://github.com/unununnnn/wksim/issues/79) | Astra | `29-contact` · 实现已批准的一种坡面/盒体接触模型 | #58 |
| [#81](https://github.com/unununnnn/wksim/issues/81) | Luna | `29-live-contact` · 执行一次可视场景与物理反馈验证 | #80 |
| [#80](https://github.com/unununnnn/wksim/issues/80) | Luna | `29-static-contact` · 执行已冻结坡面/盒体接触夹具 | #79 |

## #33 双栈混合轴与轨迹跟随

原父票依赖：#32, #6。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#83](https://github.com/unununnnn/wksim/issues/83) | Luna | `33-final-combo-run` · 执行一次最终组合PV任务和原始审计 | #82 |
| [#84](https://github.com/unununnnn/wksim/issues/84) | Astra | `33-formal-promotion` · 提升同一已证实组合并验证正式入口 | #83 |
| [#82](https://github.com/unununnnn/wksim/issues/82) | Astra | `33-rate-candidate` · 修复最终mixed/PV组合的真实倍率阻塞 | 按资源/身份预检进入 |

## #35 Prometheus PID控制器选择与闭环

原父票依赖：#34。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#50](https://github.com/unununnnn/wksim/issues/50) | Luna | `35-preflight` · 执行一次 PX4 PID 只读准入 | 按资源/身份预检进入 |
| [#51](https://github.com/unununnnn/wksim/issues/51) | Luna | `35-ap-preflight` · 执行一次 AP PID 只读准入 | 按资源/身份预检进入 |
| [#87](https://github.com/unununnnn/wksim/issues/87) | Luna | `35-arducopter-flight` · 执行一次 AP 外部PID定点/轨迹/扰动 | #86, #51 |
| [#88](https://github.com/unununnnn/wksim/issues/88) | Astra | `35-product-selector` · 复核 PID 配置选择与结果可见性，补齐原AC缺口 | #86, #87 |
| [#86](https://github.com/unununnnn/wksim/issues/86) | Luna | `35-px4-flight` · 执行一次 PX4 外部PID定点/轨迹/扰动 | #50, #85 |
| [#85](https://github.com/unununnnn/wksim/issues/85) | Astra | `35-raw-auditor` · 实现 PID 原始控制/扰动/物理独立审计 | 按资源/身份预检进入 |

## #36 Prometheus UDE控制器闭环

原父票依赖：#35。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#89](https://github.com/unununnnn/wksim/issues/89) | Astra | `36-algorithm` · 移植固定上游 UDE 算法与复位状态 | 按资源/身份预检进入 |
| [#92](https://github.com/unununnnn/wksim/issues/92) | Luna | `36-ap-run` · 运行一次 AP UDE 冻结工况 | #91, #35 |
| [#91](https://github.com/unununnnn/wksim/issues/91) | Luna | `36-px4-run` · 运行一次 PX4 UDE 冻结工况 | #90, #35 |
| [#90](https://github.com/unununnnn/wksim/issues/90) | Astra | `36-runtime` · 接入 UDE 选择并冻结单次运行合同 | #89, #35 |

## #37 Prometheus NE控制器闭环

原父票依赖：#35。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#93](https://github.com/unununnnn/wksim/issues/93) | Astra | `37-algorithm` · 移植固定上游 NE 算法与复位状态 | 按资源/身份预检进入 |
| [#96](https://github.com/unununnnn/wksim/issues/96) | Luna | `37-ap-run` · 运行一次 AP NE 冻结工况 | #95, #35 |
| [#95](https://github.com/unununnnn/wksim/issues/95) | Luna | `37-px4-run` · 运行一次 PX4 NE 冻结工况 | #94, #35 |
| [#94](https://github.com/unununnnn/wksim/issues/94) | Astra | `37-runtime` · 接入 NE 选择并冻结单次运行合同 | #93, #35 |

## #38 RC位置控制与任务显式交接

原父票依赖：#12, #14, #6。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#97](https://github.com/unununnnn/wksim/issues/97) | Astra | `38-input-contract` · 确定RC模拟输入、死区、过期与交接合同 | 按资源/身份预检进入 |
| [#98](https://github.com/unununnnn/wksim/issues/98) | Astra | `38-input-port` · 实现已冻结RC输入归一化与状态复位 | #97 |
| [#99](https://github.com/unununnnn/wksim/issues/99) | Astra | `38-runtime-flight` · 接入RC控制权并交付可验证双栈入口 | #98 |

## #39 单机规划绕障到真实飞行

原父票依赖：#15, #29, #33, #6。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#100](https://github.com/unununnnn/wksim/issues/100) | Astra | `39-planner-contract` · 选择真实上游规划器并限定停机/ID修复 | 按资源/身份预检进入 |
| [#102](https://github.com/unununnnn/wksim/issues/102) | Astra | `39-planner-flight` · 接入规划器并验证一个真实绕障场景 | #101, #29, #33 |
| [#101](https://github.com/unununnnn/wksim/issues/101) | Astra | `39-planner-stop-id` · 修复规划器停止优先级与递增命令ID | #100 |

## #40 真实相机驱动ArUco目标跟踪

原父票依赖：#30, #32, #6。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#53](https://github.com/unununnnn/wksim/issues/53) | Luna | `40-target-command` · 实现新鲜ArUco目标到公共速度意图（两文件） | 按资源/身份预检进入 |
| [#104](https://github.com/unununnnn/wksim/issues/104) | Astra | `40-closed-loop` · 接入相机跟踪并提供双栈真实验收入口 | #103, #53 |
| [#103](https://github.com/unununnnn/wksim/issues/103) | Astra | `40-real-scene` · 创建一个真实UE ArUco场景并核验标定 | 按资源/身份预检进入 |

## #44 单电机效率故障的可复现实验

原父票依赖：#22, #24。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#106](https://github.com/unununnnn/wksim/issues/106) | Luna | `44-baseline-run` · 运行一次无故障基线 | #105 |
| [#105](https://github.com/unununnnn/wksim/issues/105) | Astra | `44-efficiency-seam` · 实现一次真实单电机效率事件及重置 | 按资源/身份预检进入 |
| [#107](https://github.com/unununnnn/wksim/issues/107) | Luna | `44-fault-run` · 运行一次单电机效率事件 | #106 |
| [#108](https://github.com/unununnnn/wksim/issues/108) | Luna | `44-repeat-run` · 按相同种子重跑故障并检查重置 | #107 |

## #45 GNSS中断与状态有效性恢复

原父票依赖：#22, #23。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#109](https://github.com/unununnnn/wksim/issues/109) | Astra | `45-ap-native` · 实现AP权威tick的原生GNSS中断候选 | 按资源/身份预检进入 |
| [#112](https://github.com/unununnnn/wksim/issues/112) | Luna | `45-ap-run` · 运行一次 AP GNSS 中断/恢复 | #111 |
| [#110](https://github.com/unununnnn/wksim/issues/110) | Astra | `45-px4-injection` · 接入PX4真实GNSS发包门与原包记录 | 按资源/身份预检进入 |
| [#121](https://github.com/unununnnn/wksim/issues/121) | Astra | `45-runtime-auditor` · 交付双栈 GNSS 单次运行入口与独立原始审计 | #110, #109 |
| [#111](https://github.com/unununnnn/wksim/issues/111) | Luna | `45-px4-run` · 运行一次 PX4 GNSS 中断/恢复 | #110, #109, #121 |

## #46 固定输入实验的确定性重新运行

原父票依赖：#16, #20, #24。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#113](https://github.com/unununnnn/wksim/issues/113) | Astra | `46-input-contract` · 确定一份完整可重算的物理输入合同 | 按资源/身份预检进入 |
| [#114](https://github.com/unununnnn/wksim/issues/114) | Astra | `46-reexecution` · 实现独立物理重算与缺输入拒绝 | #113 |
| [#115](https://github.com/unununnnn/wksim/issues/115) | Astra | `46-reexecution-run` · 执行一次无飞控物理重算与对照 | #114 |

## #47 双栈全球航点与home基准

原父票依赖：#12, #14, #23。原验收文字保留，子票关闭不自动关闭父票。

| 子票 | 执行层 | 稳定键 / 单一交付 | 本票前置 |
| --- | --- | --- | --- |
| [#120](https://github.com/unununnnn/wksim/issues/120) | Luna | `47-ap-run` · 运行一次 AP 全球航点/home工况 | #119 |
| [#117](https://github.com/unununnnn/wksim/issues/117) | Astra | `47-coordinate-module` · 实现已冻结global/home转换与失效检查 | #116 |
| [#116](https://github.com/unununnnn/wksim/issues/116) | Astra | `47-home-contract` · 确定全球坐标与两栈权威home合同 | 按资源/身份预检进入 |
| [#118](https://github.com/unununnnn/wksim/issues/118) | Astra | `47-native-adapters` · 接入已批准全球航点原生适配 | #117 |
| [#119](https://github.com/unununnnn/wksim/issues/119) | Luna | `47-px4-run` · 运行一次 PX4 全球航点/home工况 | #118 |
