# RC 与单电机效率工况机械验收报告（基于 Commit 514743f）

**基线 Commit**：`514743f`
**核验者**：Antigravity (`antigravity`，仅承担机械证据核验，不作主观技术判定)
**核验范围**：
1. **RC 控制权与交接**：子票 #99 与父票 #38；
2. **单电机效率故障全套工况**：子票 #105、#106、#107、#108 与父容器 #44；
3. **相机场景进展核备**：#103（主会话 UE 候选已编译成功，实采进行中）与 #104。

**边界与不变量**：
- 禁止运行 SITL/UE；
- 禁止修改生产代码、历史证据或 GitHub Issue 状态；
- 禁止 commit/push 或嵌套委派；
- 用户既有修改 `docs/Prometheus.gitmodules.reference` 严格保留未动。

---

## 一、RC 位置控制权与任务交接验收（#99 与 #38）

### 1. #99 [Astra] 接入RC控制权并交付可验证双栈入口
- **稳定键**：`38-runtime-flight`（子票切片）
- **实时前置状态**：前置 #98 已 CLOSED。
- **具体验收条件 (AC) 逐项核对**：
  1. *原父票 RC AC 具备证明，提供可运行的原始记录与独立审计*：
     - 已交付 `tools/run-rc-flight.sh` 与 `tools/audit_rc_flight.py`；
     - 涵盖 PX4 与 ArduCopter 双栈各 6 场景（movement、recenter、yaw、stream-stall、mode-out、new-takeover），全部 12 场在 `validation/38-rc-flight/final-matrix.json` 经受统一审计器（SHA256 `ace3a021bde74223f521acd122a513590419d8315209e50a6878186ddacffc9c`）核验，结果均为 `PASS`。
  2. *交付源码/配置身份、准确命令、原始结果和失败边界，仅关闭本子票*：
     - Control 候选配置：`/root/wksim-joint-control-WjBuqN/build.json`（SHA256 `ae5236af5052e81a256566a5e05d1840752fffb4d6f5cc512e0c0a5bb9e88c1d`）；
     - 完整报告见 `docs/2026-09-10-rc-flight-report.md`；
     - 保留原始失败记录：`rc-px4-movement-01`（API 缺失异常）及 `rc-px4-stream-stall-01`（原生 failsafe 误判异常）；
     - 明确失败边界：断流撤权并不代表机体瞬间静止，记录了 PX4 移动 0.245m 及 AP 移动 0.376m 的原生过渡滑行物理真值。
- **实际归档与哈希核验（12 场全 PASS）**：
  | 场次 | 场景 | 结果 SHA256 (`result.json`) | 归档 SHA256 (`raw-evidence.tar.gz`) | 审计判定 |
  | :--- | :--- | :--- | :--- | :--- |
  | `rc-px4-movement-03` | movement | `7ffaa03ad7a2e5845cb084534f378a59...` | `150b4ec74a9df36b539c71ea407c9135...` | PASS (+X 1.1715m) |
  | `rc-px4-recenter-02` | recenter | `eb19a4a7536f9ea20ce031f0bda2a033...` | `30612ce2e230787309eafe25579974c2...` | PASS (漂移 0.0571m) |
  | `rc-px4-yaw-02` | yaw | `8d18ceb21b7a2da8929e50e93240037a...` | `bc476711516e885d51e7b415a7824aa7...` | PASS (误差 0.0012rad) |
  | `rc-px4-stream-stall-02` | stream-stall | `e3fb92ec8e5c3e031eb93a8d11631557...` | `3263fc179bfdb2543ee7d488c012fa52...` | PASS (1.505s 撤权) |
  | `rc-px4-mode-out-02` | mode-out | `36b691aaeb7e7bb735e5d3fa965fefb3...` | `70b5bb0203f56e91fba38a7c2957b98a...` | PASS (LOITER 撤权) |
  | `rc-px4-new-takeover-01`| new-takeover | `2a2fb25330368ea5b107bc45391a2fc4...` | `9c3be65507ff2ee35b3be9052b614fc4...` | PASS (再移动 0.7622m) |
  | `rc-arducopter-movement-01` | movement | `a0c3260c6d9d1506b3bfdf0353c4d440...` | `71c4566e9c98a38a79854efad6631ad1...` | PASS (+X 1.2201m) |
  | `rc-arducopter-recenter-01` | recenter | `1202b36bf47124ba16e7dd787201c70e...` | `daaa29f2709d29eb0e062be7187ec968...` | PASS (漂移 0.0506m) |
  | `rc-arducopter-yaw-01` | yaw | `3b83efb1c1d8bc5e5c709772ee62df05...` | `b23a9d70dfbb7be3f97202fae3831861...` | PASS (误差 0.0260rad) |
  | `rc-arducopter-stream-stall-01` | stream-stall | `475b8719f96bca6937e283fb22eb4344...` | `45aa70529d4791ee20292fc4ec140c8f...` | PASS (1.504s 撤权) |
  | `rc-arducopter-mode-out-01` | mode-out | `61feef61655952dfa2f58fb38ff91392...` | `25c60205f45479eb11cbe2d96bc8e6f1...` | PASS (BRAKE 撤权) |
  | `rc-arducopter-new-takeover-01` | new-takeover | `c687e1a3fa41f17fe68c93a0a6538b81...` | `37c95a0dc087aa5317b35ea489d81d6f...` | PASS (再移动 0.8516m) |
- **可关闭结论**：**可关闭 (READY TO CLOSE)**。子票范围全部完成，证据确凿闭环。
- **尚欠证据**：无（子票切片无缺失项）。

---

### 2. #38 RC位置控制与任务显式交接（父票容器）
- **实时前置状态**：#6（决策）、#12（正式入口）、#14（旧命令隔离）三项前置均已 **CLOSED**。
- **子任务状态**：#97（输入合同，CLOSED）、#98（输入归一化，CLOSED）、#99（双栈入口，证据全过）。
- **具体验收条件 (AC) 逐项核对**：
  1. *明确模拟源、通道、死区、有效期和失联动作，不以伪RC规避解锁*：已在 `rc_input.py`、`rc_task.py` 及契约中冻结并验证；
  2. *真实双栈验证移动、回中保持、偏航和控制权交接*：#99 的 12 场统一审计已完全覆盖；
  3. *断流或外部模式切走后不自动抢回，反馈区分输入失效与模式拒绝*：stream-stall 与 mode-out 场景已证明原生 failsafe 触发撤权与显式重接管；
  4. *仅位置 RC 闭环，其他模式按来源矩阵跟踪*：界限保持完好；
  5. *交付实际命令、版本/身份、预期与结果、失败/未验证边界*：已由 `docs/2026-09-10-rc-flight-report.md` 完整交付。
- **可关闭结论**：**待主会话复核关闭 #99 后，父票 #38 即可同步关闭**。
- **尚欠证据与边界**：
  - 本次验收基于实验候选 Control（`WjBuqN`），未提升默认生产配置；
  - 生产准入提升（production admission）属于全工具链后续整体收口要求，不影响当前父票功能验收闭环。

---

## 二、单电机效率故障工况验收（#105、#106、#107、#108 与 #44）

### 1. #105 [Astra] 实现一次真实单电机效率事件及重置
- **稳定键**：`44-efficiency-seam`（子票切片）
- **实现交付**：
  - 原生 C++ 接缝：`Simulator/wksim_core/motor_efficiency_native.cpp/.h`（仅对 0 号电机在 ODE4 子阶段按 $\eta=0.97$ 缩减 $T_0, M_0$，其余 3 路始终保持 1.0）；
  - Python 包装与事件模型：`Simulator/wksim_core/motor_efficiency_model.py`、`motor_efficiency_event.py`；
  - 库文件与清单：`/root/wksim-efficiency-model-r97g_cit/libwksim_efficiency.so`（SHA256 `a7325ebf754f6e61ebf25c5382fb67343659454cc176c0a7d50f980b3dcb9199`）；
  - 7 个独立进程原生 bench 独立审计通过（`validation/44-efficiency-native/archive.json`，归档 SHA256 `c6720434a4054b26934d68e42c3c898aad360edce4994723b9972d7051012467`）；
  - 7 项边界测试通过（错身份、错时间、重复发布、改写力矩日志未改物理等负例均正确拒绝）。
- **可关闭结论**：**可关闭 (READY TO CLOSE)**。原生注入接缝、状态机与冷重置边界已完备交付。
- **尚欠证据**：无。

---

### 2. #106 [Luna] 运行一次无故障基线
- **稳定键**：`44-baseline-run`（子票切片）
- **核验证据**：
  - 真实双栈仿真运行记录于 `validation/44-efficiency-flight/matrix.json`：
    - PX4: `efficiency-px4-baseline-01`，43,700 个物理步，无故障注入，扰动窗口误差 0.0907m，恢复窗口误差 0.0725m，审计 `PASS`（结果 SHA256 `1833469c8631019ef343c7a572c4409b94a7d2d09cd7cb012337934fca89a573`）；
    - ArduCopter: `efficiency-arducopter-baseline-03`，76,413 个物理步，无故障注入，扰动窗口误差 0.0779m，恢复窗口误差 0.0552m，审计 `PASS`（结果 SHA256 `c95aaefc246a5bc900c8748ecb5ed4769650f28df524dabef37e83f5ad563350`）；
  - 保留历史失败原件：`efficiency-arducopter-baseline-01`（起飞偏航重置触发安全撤权）与 `02`（悬停前速度超标未达稳定窗口），失败处理真实。
- **可关闭结论**：**可关闭 (READY TO CLOSE)**。
- **尚欠证据**：无。

---

### 3. #107 [Luna] 运行一次单电机效率事件
- **稳定键**：`44-fault-run`（子票切片）
- **核验证据**：
  - 真实双栈单电机故障注入记录于 `validation/44-efficiency-flight/matrix.json`：
    - PX4: `efficiency-px4-fault-01`，连续悬停 6,000 步后注入 1,000 步 $\eta=0.97$ 故障，连续 1,500 步满足恢复门槛，审计 `PASS`（结果 SHA256 `11ad6151223f5b534793d572ecc881b18fec4b561f1028fc7e02723ae99defbc`）；
    - ArduCopter: `efficiency-arducopter-fault-01`，稳定悬停后注入 1,000 步 $\eta=0.97$ 故障，连续 1,500 步满足恢复门槛，审计 `PASS`（结果 SHA256 `2f651f6c3db8467deb0f8ed721264c377bdb337d7af44e6c152f71cb7fbd868f`）；
  - 审计器校验确切 1,000 步物理区间、原始 actuator packet 解码、16 个 ODE4 旋翼子阶段逐步读回一致，未缩放 PWM。
- **可关闭结论**：**可关闭 (READY TO CLOSE)**。
- **尚欠证据**：无。

---

### 4. #108 [Luna] 按相同种子重跑故障并检查重置
- **稳定键**：`44-repeat-run`（子票切片）
- **核验证据**：
  - 相同初始随机状态（17 个整数 `[891230338, ...]`）、新控制代次、全新进程冷重置运行记录于 `validation/44-efficiency-flight/matrix.json`：
    - PX4: `efficiency-px4-fault-02`，控制 epoch `91c53f91426645a68fda8b1d51a93e0c`，审计 `PASS`（结果 SHA256 `fd6f0c650850d40c484dcf5d488af0eb1a340d685b76bdc98fad69a93728c81c`）；
    - ArduCopter: `efficiency-arducopter-fault-02`，控制 epoch `3b33c22d67cd4283bc0a4387c95ce896`，审计 `PASS`（结果 SHA256 `7e12d34665bfb19479d7bb25224c410799fcdf25ad86847e2cf878465bf41cde`）；
  - 证明同种子在新进程内重复通过，四路 $\eta=1.0$ 重置状态正常，不声称闭环轨迹逐位一致（#46 独立验收）。
- **可关闭结论**：**可关闭 (READY TO CLOSE)**。
- **尚欠证据**：无。

---

### 5. #44 单电机效率故障的可复现实验（父票容器）
- **实时前置状态**：#22（DDS 断连恢复，CLOSED）、#24（参数保存导入，CLOSED）均已 **CLOSED**。
- **子任务状态**：#105、#106、#107、#108 全部 4 项子票均具备完整 PASS 审计与归档。
- **具体验收条件 (AC) 逐项核对**：
  1. *故障时刻、持续时间、目标电机和幅值进入运行配置及记录*：已在 `matrix.json` 与 `result.json` 中逐毫秒绑定；
  2. *事件映射到实际模型执行器路径，真值和飞控反馈反映变化*：通过 `motor_efficiency_native.cpp` 在 ODE4 直接减推力/力矩，未缩放 PWM；
  3. *使用预先批准的安全/失联与数值预算，重置后故障状态清除*：位姿误差与恢复收敛全部在原 PID 预算内，落地上锁，冷重置四路 $\eta=1$；
  4. *无故障回归和相同种子重复实验通过*：双栈 baseline、fault、repeat 共 6 场全绿；
  5. *交付实际命令、版本/身份、预期与结果、失败/未验证边界*：已由 `docs/2026-09-10-motor-efficiency-flight-report.md` 完整交付。
- **可关闭结论**：**待主会话统一复核 #105–#108 后，父票 #44 即可同步关闭**。
- **尚欠证据与边界**：
  - 基于模型库 `libwksim_efficiency.so` 候选，未提升默认生产模型；
  - 生产默认模型提升为全工具链整体门禁，不阻塞父票 #44 功能验收闭环。

---

## 三、相机场景最新进展核备（#103 与 #104）

1. **#103 [Astra] 创建一个真实UE ArUco场景并核验标定**：
   - **最新进展**：主会话已完成 ArUco 候选 UE C++ 组件实现并编译成功（相关文件：`Simulator/ue55/Source/WksimVisual/WksimRgbFixture.cpp/.h`、`WksimVisualGameMode.cpp`、`Simulator/wksim_console/visual.py`）；
   - **当前状态**：正在进行真实环境 RGB 帧采集与标定核验，**记录为进行中（In-progress）**；
   - **可关闭判定**：**不可关闭**（未宣称通过，等待采集产物与角点反投影残差审计落盘）。

2. **#104 [Astra] 接入相机跟踪并提供双栈真实验收入口**：
   - **当前状态**：**阻塞中**（强依赖 #103 交付实采与标定数据）。

---

## 四、逐票可关闭性与状态汇总表

| 票号 | 标题与定位 | 评估结论 | 审计通过依据 / 实际归档 | 尚欠证据 / 遗留边界 |
| :--- | :--- | :--- | :--- | :--- |
| **#99** | [Astra] 接入RC控制权并交付可验证双栈入口 | **可关闭** | 12/12 PASS；`validation/38-rc-flight/final-matrix.json`；审计器 SHA256 `ace3a021...` | 无。 |
| **#38** | RC位置控制与任务显式交接（父票） | **待复核可关闭** | 前置 #6/#12/#14 全闭；子票 #97/#98 全闭；#99 审计全过 | 生产配置提升属于全库收口门禁，不阻断功能验收。 |
| **#105** | [Astra] 实现一次真实单电机效率事件及重置 | **可关闭** | 7 场原生 bench 全 PASS；`validation/44-efficiency-native/archive.json` | 无。 |
| **#106** | [Luna] 运行一次无故障基线 | **可关闭** | 双栈 baseline PASS；`validation/44-efficiency-flight/matrix.json` | 无。 |
| **#107** | [Luna] 运行一次单电机效率事件 | **可关闭** | 双栈 fault PASS；`validation/44-efficiency-flight/matrix.json` | 无。 |
| **#108** | [Luna] 按相同种子重跑故障并检查重置 | **可关闭** | 双栈 repeat PASS；`validation/44-efficiency-flight/matrix.json` | 无。 |
| **#44** | 单电机效率故障的可复现实验（父票） | **待复核可关闭** | 前置 #22/#24 全闭；子票 #105–#108 证据全齐；6 场飞行审计全过 | 生产默认模型提升属于全库收口门禁，不阻断功能验收。 |
| **#103** | [Astra] 创建一个真实UE ArUco场景并核验标定 | **进行中** | 主会话 UE C++ 已编译成功，实采正在进行 | 尚欠实际渲染帧与标定残差独立审计记录。 |
| **#104** | [Astra] 接入相机跟踪并提供双栈真实验收入口 | **阻塞中** | - | 强依赖 #103 交付。 |
