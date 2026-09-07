# RGB 几何与联合倍率检查点

**本检查点已被 [2026-09-07 倍率优化、RGB 收口与恢复风暴报告](2026-09-07-rate-recovery-rgb-closure-report.md) 覆盖**：生产者停启/冷重置/空中 RGB 已真实通过，0.5× 生命周期回归通过，1× 与恢复风暴为已提交用户的未决项。以下按历史状态保留。

当前分支 `codex/independent-rgb-integration`，承接本地提交 `d14bcd0`。本轮新增内容尚未提交；Goal/Full active，没有新关闭票据。子代理接口返回 agent thread limit reached，因此本轮全部由主代理完成，没有降级或恢复到未经核验的代理配置。

## 已完成的实际验证

`validation/rgb-geometry-20260907/summary.json` 汇总四个真实双飞控地面场景：case0基础（run2）、case1相机平移（run2）、case2遮挡（run2）、case3旋转（run1）。同一原生 v2 DLL，每例15帧，共60帧通过实际 PNG 解码、预先固定的每轴2像素边界带、99.5%内部覆盖/外部精度，以及两模型真值/权威时钟/实际相机位姿审计。实际覆盖与精度最小值均1.0。四例生成33/31/35/30张PNG；消费者断开3秒时物理推进1608/1508/1508/1560步。

标定条件在首个场景运行前写入 `docs/rgb-geometry-fixture.md`。原生瞬态Cube/未受光照材质在专用标定模式生成，未改厂商安装或持久资产；它不是地形/碰撞物理。当前候选清单 `validation/ue55-build-050bd84a926948d8956637610c2be625/candidate-manifest.json`，stage `E:/ue5.5/build/wksim-native-rgb-fixture-20260907-c`。默认全局UE清单仍是上一提交的版本，尚未提升；当前修改了C++源码，默认View预检会要求匹配的新清单。

RGB v2增加每个View独立的stream_id，元数据/通知分别为wksim.rgb.v2/wksim.rgb-ready.v2。物理instance/epoch/step保持独立，实时Reader拒绝旧生产实例和v1；历史v1仍可离线审计。文件名改为rgb_<stream_id>_<frame>，避免长用户标识超出组件长度。

真实失败case2-run1暴露重连时接收一个已经开始采集、晚到的旧帧：重连边界2692，首帧2688。Reader新绑定现在用权威minimum_step过滤此前采集，普通同epoch连续读取不追赶当前步号而误丢正常异步帧。case2-run2/case3-run1验证修复；case0/1在修复前已通过，原证据及来源各自保留。case1-run1为物理启动前的Windows模块枚举空结果失败；原生fixture随后用GetModuleHandleExW(FROM_ADDRESS)+GetModuleFileNameW证明实际DLL和PID，当前驱动比对该PID及文件哈希。两项失败都没有改判。

相机生产者实际停止/重启、真实冷重置旧epoch隔离以及空中RGB仍未验收；#30不关闭。仅消费者断开不是生产者停机。

## 倍率实测及当前候选

新增 `tools/profile_joint_cpu.py` 和 `tools/run_joint_rate_case.py`，均走正式入口，只管理本任务进程。CPU采样由WKSIM_JOINT_CPU_TIMING=1显式启用；joint.py含可选wall/thread CPU与GC诊断，普通运行关闭。旧joint_rate.py timing_probe仍保留，尚未清理/定稿。

1×冷启动原样baseline在tick1948累计100.191109ms冻结；采样版tick2204/101.029246ms。固定步1926/2000出现原生输入等待峰值，另有主线程计算峰值。GC记录均约0.05–0.063ms，未与慢步重合，未关闭或调GC。Linux schedstats当前关闭，不能将runqueue计数0当无调度等待；仅查阅Linux内核官方sched-stats文档，未改内核设置。

joint_lifecycle.periodic当前对重复ROS executor dispatch最多500Hz，保留每个原调用的许可和进程/期限检查，显式阶段变更立即dispatch。两状态各100Hz，暂停/恢复ACK也可各100Hz。先前500us试验在20秒观察结束尚运行（19872tick/84.959441ms），1ms试验在19824tick/100.094292ms失败；这些不是持续倍率验收。

原调度代码下默认0.5起飞后显式切1×（after-ready-run1）在49440→54340期间约5秒失败。当前2ms dispatch候选（after-ready-run2）在49452→72996期间约23.6秒触及100.296162ms而冻结，实际倍率约0.995815；仍失败。两例正常stop并保留，不改100ms、2秒监督、10秒±2%或60秒±1%门槛。

当前2ms dispatch候选仍需要实际0.5生命周期/DDS恢复回归及正确环境的全部矩阵；已有6项针对检查只证明许可不被dispatch合并抑制、显式phase强制读取和几何验证器边界，不是飞行验收。下一步应继续定位状态发布/日志和实际输入等待的耗时，而非重复无依据整轮试飞或放宽数值预算。

## 交接资源状态

本节写入时所有FC、UE、编译与验证exec句柄已wait到终态，没有活动实验。最后16743为after-ready-run2，final_manager_code=0且失败病例已完整复制。下一步不要重复启动旧目录；读取当前Git状态和证据再执行。

本轮源文件：新WksimRgbFixture.h/.cpp、GameMode/Build输入、RGB组件/Reader v2与重连边界、View可选fixture配置；新几何审计/测试、profile/run_rate_case工具及joint_lifecycle/joint.py候选。默认UE清单提升、相机生产者/epoch真实生命周期、倍率回归、总体残留复核、文档/票据更新及提交仍待收口。
