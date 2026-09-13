# 参考端 pqr 求解输入观测模式

主会话已将审查后的端口采集接入实际连接追踪，并完成run-04/05。完整证据与限制见[矩阵求解边界](../2026-09-13-first-step-solve-boundary.md)。

第四参数opts.probe_pqr_input默认false，开启时必须为标量logical。默认不注册额外采集listener，但报告增加enabled=false节，并预留/清理三个workspace名；没有声称字节或schema零变化。

开启后从实际pqr积分器输入线取源块与源端口号；resolve_probe_solver_input沿SubSystem匹配的直接Outport以及单输入/输出Reshape穿越，最多16跳，歧义、循环或其它未支持路由返回unavailable。Product类型本身不证明具体算法，实际路径、Inputs/Multiplication及全部端口观测共同供后续核验。

端口数用运行对象NumInputPorts/NumOutputPorts，逐端口记录native dtype/shape/hex；每条事件保留真实序位。独立事件上限10000及丢弃计数，禁止把同时间minor合并。实际run-05观测到2输入、1输出，尺寸1x3/3x3/1x3，共5条、丢弃0。前四个输出与实际pqr导数一致。

输入/模型/init哈希钉、R2022b约束、独占新目录与CREATE_NEW、UDD.Data、缓存隔离、回调/path恢复、listener与workspace清理、close(0)不保存仍保留。run-04/05的主输出和全部积分器事件与旧run-03一致；旧报告未覆盖。静态字符串检查仅保留作原审查记录，不替代这次真实运行核验。

本模式只提供诊断证据；G6/R1未通过，不能据有限首步观测声称全模型一致。
