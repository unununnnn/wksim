# 本轮收尾与 Luna 交接状态

2026-09-09。用户要求本轮运行结束后改为拆票与完整指南交接，因此停止开启新功能/试飞。#24、#34已在本轮主复核后关闭；原剩余17张实施票、#9及Full父票仍保留。这里的Hex结果不构成#25关闭依据。

## 六旋翼真实运行

固定Hex X源模板库在 `/root/wksim-hex-candidate-private/build-ihnane6f/libwksim_hex_candidate.so`。六路编号、方向、初始化前22项参数、单通道响应及冷进程重复已完成18项静态检查。质量/惯量是原模板值，不是实机标定。

| 场次 | 结果及真实边界 |
| --- | --- |
| `/root/wksim-hex-flight-px4-01/hex-px4-01` | failed。地面第一项参数解析发现本地MAVLink便捷get_payload多含4字节报头；未解锁。原始帧提取改为MAVLink1的6字节、MAVLink2的10字节头，真实编码回归通过。 |
| `/root/wksim-hex-flight-px4-02/hex-px4-02` | failed。地面确认期望0的CA_ROTOR0_PX实际为0.1515；未解锁。PX4早期环境值等于通用默认0时，后续airframe set-default仍可覆盖它。 |
| `/root/wksim-hex-flight-px4-03/hex-px4-03` | observed。启动完成后只在地面显式应用CA_ROTOR0/1_PX=0，随后77项参数逐项真实读回；完成起飞、5秒悬停、航点、2秒驻留和降落。safe_landing、children_reaped、source_unchanged、candidate_unchanged、processes_absent_after_stop全部true，cleanup_errors为空。独立原始飞行审计尚未实现。 |

当前飞行合同 `Simulator/wksim_runtime/hex-flight-v1.json` SHA256 为 `33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc`。两项启动期参数应用修正未改变任何物理阈值；旧失败原件不变。AP计划另明确关闭旧copter.parm的9.6–12.8V电压补偿，保留原模型所需的1ms请求/解锁检查/观测流；这是首次飞行前的配置复核。Hex AP真实飞行、两栈cold-reset-from以及实际飞行到UE的链路尚未运行。

当前代码用新进程隔离适配器复用原协议循环，原生产四旋翼模型、飞控源和默认pin没有修改。参数/包处理修正均有针对性检查。独立ROS回环证明实际消息CDR与两个合格请求订阅者；其夹具真值是人工构造，不能作为飞行证明。

## UE 构建与真实静态夹具

候选项目：`E:/ue5.5/build/wksim-native-hex-20260909-01/WksimVisual.uproject`。构建37.315秒、退出0；模块SHA256 `15af1f6e400e77d6a8a207fd047b48b1d04c54260a5668312178051c119e6245`。封存manifest在 `validation/ue55-build-1029ab27e6534f6d816b1837dd380edf/candidate-manifest.json`。原默认构建manifest未提升。

`validation/hex-view-fixture-dfa0bc1d/` 是实际UE的六机臂/六旋翼几何、姿态、源步相位、错误输入无状态变化及停流标陈检查：153次合法ACK、11个拒绝、stale检查通过，真实截图已目视核验。首次夹具 `hex-view-fixture-0f75770d` 因测试信封漏填ended字段在发包前失败，原记录保留。

两轮夹具的自有UE进程均已退出，记录的exit_code为−1：脚本请求关闭窗口并等待10秒后，终止了仍存活的本轮自有进程。这证明本轮进程已回收，不构成UE正常窗口退出或优雅关闭的证明。三轮Hex的12条原生孩子身份检查均已退出，当前完整argv/cwd检查无残留；复核记录在 `validation/lunar-publishing-20260909/native-cleanup.json`。

这些是**人工输入驱动的UE边界夹具**。即使截图HUD出现LIVE，也不代表模型正在真实飞行；本目录不能用于关闭真实飞行显示验收。后续必须使用 `Simulator.ue55.hex_bridge` 绑定实际run/model，消费新追加且新鲜的原始物理记录，保存同一飞行的桥接ACK和截图。原始物理流已每20ms flush并在start绑定run_id/model_identity。

## PID 已交付及未运行部分

纯外部PID实现、明确复位与推力映射在 `Simulator/wksim_control/`。1,884次、18,840值原C++/Eigen对照通过，12项纯检查通过。精确输入协议SHA为 `076bd5bbd3502fe11eacc4189c21e24bbf1a300fe4daf5b4493710be35914f61`。第一轮跨平台重新生成sin/cos导致26个末位差异，没有当作精确协议证明；第二轮从原冻结文件读取，原始证据在 `validation/pid-source-20260909-run2/`。

PID运行候选已交付，14项纯检查通过；`pid-flight-v1.json` SHA为 `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`。本轮没有执行其真实preflight、FC/model/ROS、定点/轨迹/扰动闭环，不能关闭#35。下一步可先让Luna执行一次已有只读preflight，再按独立审计器/单次试验拆票推进。

## 回归与未变门槛

最终通用WSL矩阵在 `validation/session-product-checks-7ys5nTEW/`：667项，626通过、41跳过；旧预检11通过。41跳过包含29项既有条件及默认WSL环境缺可选OpenCV的12项。ArUco专用项目私有Python已单独运行12项，全部通过、无跳过。首次通用矩阵的可选视觉导入错误，以及随后模块级SkipTest在显式模块加载中的错误均保留；最终改为类级条件跳过，不安装全局视觉包或伪称跳过等于通过。

新纯PID/运行候选合计26项检查通过；Hex物理/启动接缝和参数真实编码回归分别保留。完整回归没有启动FC、模型、UE或MATLAB。R1仍numerical_failed，G6/Full、#20持续1×及#33最终组合RateUnmet保持原有结论；拆票不会删除失败、改预算或重新定义父票通过条件。
