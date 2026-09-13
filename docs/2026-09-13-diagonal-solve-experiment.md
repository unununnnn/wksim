# 对角求解顺序的单步验证

主会话在独立 Linux 副本中增加统一对角矩阵分支后，C3G 首步的 240 个主输出、13 个已映射连续状态及四级导数、末态和五次求解操作数/结果，与参考 run-05 全部逐位相同。主审独立比较和自动比对器均报告零差异。

本实验验证了一个有明确边界的修复假设：相同对角矩阵下，将除法改成乘以倒数，能消除这一步已观测到的差异及其传播。它不证明参考引擎内部算法，也不构成完整 R1、同源数值合同或 G6 的通过。

## 实际配方与身份

- 配方：`validation/coordination/g6-diagonal-solve-candidate-20260913/prepare.py`。只在新目录 `/root/wksim-first-step-diagonal-solve-20260913-01` 创建副本，保留原始及原插桩源。
- 三个分子和三个非零对角元须有限，六个非对角元须为零；三个倒数也须有限。三个轴统一计算 `y[i] = u0[i] * reciprocal[i]`。否则执行原通用求解函数。没有时间、特定 q 分量或特定数值判据。
- 移除新增分支后逐字恢复原插桩源；原 archive、builder、recorder、输入及配方运行后五项哈希检查相符。正式模型未替换。
- 候选 CPP SHA：`0107001b1a4aeef4591b2516ffad338866e4645a59c519c3c3e367073acac001`。可执行 SHA：`2b867710633e713db60c275fbbb1f356bd3c3c606d0162bae3252853cc251fb0`。
- trace SHA：`5e89b720dac275a4980df1881aae2dfde76d223ad9a0bc8dbeba15edaa1e1d09`。参考 report SHA：`72ff7d8eaeee7854bf026d19a7ee37f38c061764ce5369d0dd5845b1aa084c62`。

编译/run 均 exit 0，自有 PGID 669、678 均清空；编译及运行前分别核验两套 WSL 无竞争进程。记录器仍强制四级、一轮 ODE4 更新、两份 major 和五次求解。原生成源、头文件和可执行程序只在本地保留；仓库保存配方、JSON、日志和哈希。

## 比对器与独立复核

`tools/compare_first_step_trace.py` 支持旧两版 trace 和新求解 trace，核验实际事件顺序、求解输出到导数的对应、端口配置/形状/类型，并保留同时间事件序位。它的 `aligned` 表示结构可比较，不能当成数值或 G6 通过；本例另检查全部差异列表为空。

主审补充畸形容器、缺字段、端口数量与布尔类型拒绝，30 项测试、8 个子测试通过。`comparator-result-v2.json` 与先前实际比较的语义结果相同，工具最终 SHA 和测试身份见 `main-verification-v2.json`。OMP 独立审查见 `docs/coordination/diagonal-solve-candidate-review-20260913.md`；未实测的非对角/极小数回退路径继续单列。

## 对后续工作的约束

已核验旧 11.0 与新生成 11.8 的实际求解函数体逐字相同（两者函数体 SHA 均 `7e0be87b4e760028fbd191e6be1011a67da749e6791f0b1ea06d0d63460dfcf9`），但这不能代替两个整模型的同源比较。最初误选前置声明的提取已作废并保留错误说明，正确结果在 `g6-solve-same-source-20260913/source-comparison-v2.json`。

对已保留的同源 11.8 C0 major 记录与既有 normal C0 做离线对照，共 60,120 值，仍有 Sensor30[10] 在 k153、k181 两处气压差异；没有启动模型，也没有赋予新的误差预算。证据和可重复离线脚本在 `g6-solve-same-source-20260913/`。

因此本轮不盲目重跑旧 R1 或把首步零差异扩大为全工况结论。原 R1 失败保留；同源入口的逐量预算、物理精度、#84 性能及其它 Full 必需项继续开放。
