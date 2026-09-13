# G6 / R1 首个数值分歧定位（离线只读,谨慎结论)

2026-09-13。负责人：Claude（短周期席位）。任务：定位 G6 数值 R1 已有 **5684** 个失败值的**首个分歧**及其输入/模型/单位/坐标契约。

本工作为**纯离线只读分析**：不重跑模型、不启动 MATLAB/native/ROS 节点、不构建、不改冻结契约/阈值/接受门、不改任何既有证据。仅新增离线对比脚本与其测试,读取已封存证据。

- 工具：`tools/diagnose_g6_first_divergence.py`
- 测试：`validation/test_g6_first_divergence.py`(29 项)
- 机器结论：`validation/coordination/g6-first-divergence-20260913/v3/diagnosis.json`
- 说明：首版 `.../diagnosis.json` 与次版 `.../v2/diagnosis.json` 均**原状保留**(首版结论过强且未做完整性核验；次版已审慎但未真正做到 read-once)。本版报告写入 `v3/` 子目录，独占创建、拒绝覆盖。

## 结论摘要（谨慎)

最早分歧在 **case `C3G`、样本 `k=1`、`Vehicle60[3]`**(NED 北向速度，单位 m/s)。参考 `6.254852369965466e-30`，目标 `6.2548523699654644e-30`，差 **2 ULP**(binary64 `0x1.fb743384c5850p-98` vs `0x1.fb743384c584ep-98`)，绝对误差 `1.401298464324817e-45`。

**这只是一条假设（未证）**：本冻结数据**与**两个被冻结执行引擎（MATLAB R2022b normal 参考 vs g++ `-O2 -fno-fast-math` 编译 C 目标）在共享模型方程上的**浮点求值差异一致**；**确切原因需首步步内证据**（现存证据只含逐 1ms 主输出，无步内中间量）。仅"小相对误差 + 无符号翻转"**不足以排除所有坐标/单位/时序合同问题**；本文不作此排除性定论。

## 最早分歧索引（事实)

| 项 | 值 |
| --- | --- |
| case / epoch | `C3G` / `bfc32bfdf4c74490a02a91c84b8ecf4d` |
| array[index] | `Vehicle60[3]` |
| 样本 k | **1**（全部失败中最小；k=0 初态完全一致，无 k=0 分歧） |
| observable | `velocity_ned` |
| 单位 / 语义 | `m/s` / `mapped_physical_observable` |
| 坐标/帧 | NED 速度北向分量（源 `cpp:7823-7827`;SLX `VelE`) |
| 期待（reference) | `6.254852369965466e-30` = `0x1.fb743384c5850p-98` |
| 实得（target) | `6.2548523699654644e-30` = `0x1.fb743384c584ep-98` |
| ULP 距离 | 2（绝对误差 `1.401298464324817e-45`，量级约 1e-30 m/s) |

**共最早轴（同 k=1)**:`Vehicle60[3]`(2 ULP，速度）、`Vehicle60[11]`(1 ULP,Euler 分量 rad)、`Vehicle60[15]`(64 ULP，四元数分量，无量纲）。三者同属被积分的刚体运动/姿态状态。此处只报告其观测值与量级，不就其物理显著性下定论（合同未提供物理阈值）。

## 输入 / 模型 / 执行源契约（SHA)

- **输入源**:case `C3G`(ground_motor_1_step)。`input.csv` SHA256 `721c88bf3f621923b98bb43251c50bae7817106a984be64345c0528d34d3adcf`;`applied-input.f64` SHA256 `496336f7535f9b134e9d0cd4911cfcc996646d89a40ca7c7dba518e21329a7a9`。k=1 处零阶保持电机输入 `inPWMs0_to_3 = [0.6, 0.6, 0.6, 0.6]`(event first_k=0)，即首个激活步。
- **参考（模型）**:e0 SLX 11.8,SHA256 `c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392`；引擎 `MATLAB 9.13.0.2049777 (R2022b), Simulink normal`,ODE4、固定 1ms。
- **目标（执行源）**：生成 `Exp1_MinModelTemp.cpp` SHA256 `a3eba68e1a4a5cefc772fb502a63eac1e7475548688adebb83cbc9390086a073`；可执行 `major_model_recorder` SHA256 `c685817a974471113793fde3c78eeed26f7c7b56eef1194f9df1fd2ecf7e8d49`;`build.json` SHA256 `6e16102ae1197a899eef554b9c938f5ca32220516fdd8630c7b8b1b19267cce3`；记录器 `major_model_recorder.cpp` SHA256 `d0a194b0cb4f60854f8a9f4f16de0199770dc05ec79d1c09c28184127c744051`;profile `Ubuntu-22.04 g++ 11.4.0 -O2 -fno-fast-math`。
- **合同**:R1 `numerical-conformance-v1.json` SHA256 `23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0`,120 槽 abs/rel 预算均 0，判据 `x == r`（含 ±0 相等）。

## 证据完整性核验（fail-closed)

工具对每个输入**只读一次字节**，解析与最终 SHA256 均来自**同一份捕获字节**（不在结尾重开文件），并交叉核对；任一不一致即**明确拒绝**，不输出定位成功：

- 实际 contract 字节 SHA == run-index `contract_sha256` == 每条 failure 的 `contract_sha256`;
- 失败行数 == run-index `failed_values`（此处 5684);
- 实际读取的代表 case(C3G)manifest 字节 SHA == run-index 记录 SHA（可执行/生成 cpp 的 SHA 取自该已核验 manifest);
- 每条 failure 的十进制 `reference`/`target` 与各自 `*_hex` 解码一致。

篡改 contract/计数/行内契约/hex-十进制/manifest 中任一项，定位即拒绝（测试覆盖）。读取一次性由两个测试锁定：在 manifest 核验期间篡改 failures/run-index 文件后，报告哈希仍对应**实际解析的原字节**；以及底层 `open` 计数测试（`read_bytes` 与 `sha256` 同走 `Path.open`）证明每个证据文件恰好打开一次。

## 确定性观测（事实，支持但不证明假设)

代表轴 `Vehicle60[3]` 的首分歧**逐位一致**复现于 `C2G`:`C2G` 在 `k=101`（其电机输入 onset 为 k=100）出现与 `C3G` 在 `k=1`（onset k=0)**完全相同的 binary64 对**。两例 `first_failure_k == input_onset_k + 1` 均成立。该观测与"分歧随首个激活积分步确定性出现"一致。

## 全量观测（事实)

对全部 5684 个失败逐行计算：最大相对误差 `1.576e-12`、符号翻转数 `0`、比率越界（∉ [0.5, 2]）数 `0`、最大 ULP 距离 `8192`。**这些观测本身不排除所有坐标/单位/时序合同问题**（例如在这些近零量级上，某些合同错误可能不表现为比率或符号变化）；它们只是与浮点求值差异假设相容的数据点。

## 假设与缺口

- **假设（unproven)**：本冻结数据与两个冻结引擎在共享冻结模型方程/参数/随机种子上的末位 ULP 浮点求值差异一致。
- **为何不定论**：留存证据只有逐 1ms 主根输出，不含步内（ODE4 各级）或导数级中间量，无法从现有制品隔离首个分歧运算（FMA 收缩、求值顺序/非结合性、超越函数库等）。按 10-g6-remediation 合同，未经隔离不归因于编译器/库。
- **最小缺失证据**:case `C3G`、轴 `Vehicle60[3]`/`VelE`、k=0→1 的**全 binary64 步内差分轨迹**（双引擎 ODE4 各级导数 + 状态更新），据此判定 2-ULP 差进入于导数求值还是状态更新。

## 最小可执行入口（规格，不代建)

按 10-g6-remediation 合同，新同源比较入口须由主任务在分配的 tools/ 范围内实现；本任务边界为离线分析且证据不足时**不造实现框架**，故只给精确入口规格：

- **接缝**：在既有目标记录器 `tools/major_model_recorder.cpp`(SHA `d0a194b0…`)+ 驱动 `tools/run_numerical_conformance.py`(SHA `7f3bc0c8…`）与参考导出器 `tools/export_model_reference.m`(SHA `bc435319…`）上新增有界 "first-step trace" 模式：仅对 case `C3G` 跑 k=0→1，双引擎各导出 `VelE` 通路的步内全 binary64 中间量，离线逐运算比较，命名首个分歧运算。
- 这是**新诊断入口**，不是把旧 R1 重跑入口充当新 G6 命令，也不改动预算/接受门。

## 复现命令（本任务纯离线)

```powershell
python tools/diagnose_g6_first_divergence.py                 # 写 v3/diagnosis.json(独占创建,已有则拒绝)
python -m pytest validation/test_g6_first_divergence.py -v   # 29 项(Windows 28 passed + 1 symlink skip)
python validation/test_numerical_conformance.py              # 既有比较器负向检查,不受影响
```

WSL（真实 symlink 可用）下 `python3 -m pytest validation/test_g6_first_divergence.py` **29/29 通过**（含真实 dangling-symlink 覆盖）。

## 边界

未重跑任何模型/MATLAB/native/ROS；未修改 R1 结果、合同、阈值或既有接受门；未触碰旧执行证据 pin/source 快照；C0/C2G/C3G 原执行仍 `numerical_failed`,G6 仍未通过。本定位只给出首个分歧的精确身份与一条**未证假设**，不把 ULP 噪声改判为通过，也不把"小相对误差/无符号翻转"当作排除合同错误的证明。
# 主会话最终收口

read-once v3实现与真实数据重算已复核。额外拒绝相同数值（包括正负零）、非finite与bool被标作严格binary64差异，确保“真正分歧”的声明由数值验证支持。原5684项数据和v1/v2/v3原报告不变，零预算不变；当前Windows30passed、1项既有symlink权限skip、5个新标量subtests，旧作者Linux29项包含真实symlink。最终源码/测试SHA与验证范围见同目录证据的main-verification-final.json。下文记录此前交付阶段；精确浮点根因仍未证。
