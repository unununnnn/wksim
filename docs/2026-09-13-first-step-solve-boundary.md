# G6 首步差异已定位到矩阵求解边界

参考与目标的五次实际求解中，分子向量和惯性矩阵全部逐位相同。第三次求解（第二个 t=0.0005 事件）的 q 输出不同：参考 `bc56d4db33a987b8`，目标 `bc56d4db33a987b9`，相差 1 ULP。其它四次求解的三分量结果均相同。

这将首个已映射差异定位到了相同操作数下的求解计算过程。它不证明参考实现的内部算法，也不证明其它时刻或全部 36 个状态一致；G6/R1 仍未通过。

## 实际观察

- 目标：`validation/coordination/g6-target-mrdivide-20260913/first-step-trace.jsonl`，SHA `9cee60eb5b3e5ccc96730f13423f5e0fa07de19654a481d32e9e885953f4bed3`。
- 参考：`validation/coordination/g6-reference-probe-20260913/run-05/reference-first-step.json`，SHA `72ff7d8eaeee7854bf026d19a7ee37f38c061764ce5369d0dd5845b1aa084c62`。
- 实际连接为 p,q,r 积分器 ← Calculate omega_dot 子系统的端口 1 ← Reshape ← Product2。查找按真实连接和端口号完成，不按 Product2 名字选块。
- Product 实际配置为 `Inputs='*/'`、`Multiplication='Matrix(*)'`；两个输入分别为 double 1×3 与 double 3×3，一个输出为 double 1×3。矩阵在五次观测中均为 diag(0.0211, 0.0219, 0.0366)。
- 五个事件按真实序位对应 0、0.0005、0.0005、0.001、0.001。前四次 Product 输出逐位等于参考端实际 PostDerivatives 的 pqr 导数；目标端相同关系也已验证。相同时间没有被合并。

详细对照保存在 `execution-05/solve-comparison.json`。第三次 q 分子为 `bc000013449033b2`，矩阵相应元素为 `3f966cf41f212d77`。对这组实际目标操作数离线计算，直接除法得到目标值，乘以倒数得到参考值；这是一项候选运算顺序的证据，不是参考内部算法的证明。

## 仪器验证与失败保留

参考 run-04 在真实 Reshape 节点处明确返回 unavailable，没有伪造操作数。主会话只增加对单输入、单输出 Reshape 的穿越后执行 run-05，捕获五次事件、丢弃数为零。

两次 MATLAB 均 exit 0，PID 25320、71816 已退出，随后独立检查无 MATLAB 残留。运行前分别检查两套 WSL，无竞争 native 进程。run-04/05 均保留原 run-03 的全部 240 个主输出和 72 条积分器事件，逐位/逐字段一致；37 个实际使用的冻结输入及本次 probe、resolver 前后哈希均不变。缓存、代码生成材料和厂商库未发布。

执行 probe SHA 为 `eb485804023c5310ea436af5d14f862e3aa5e75f3342fd057d6f313f00649603`；成功 run-05 的 resolver SHA 为 `d87e61d7e3606cd2bccbef83a790e595fc4ee8ed37200afc62df89ca5a6d12fb`。完整调用、进程、源快照及核验结果在各自 execution 目录。

下一步只在独立诊断候选中验证对有限非零对角矩阵统一采用乘以倒数能否消除首步差异；原通用求解路径、历史源和正式模型保持。候选通过首步也不足以代替完整 R1 验收。
