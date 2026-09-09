# #82 最终 mixed/PV 倍率候选与失败边界

2026-09-09。结论：三场最终组合真实倍率失败成立；未证明修复，#82 保持 OPEN / needs-triage，#83 不据此解除前置。本文是诊断交付，不是预检或最终飞行通过。

## 身份与复核

最终 AP manifest `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json` SHA256 `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`；Control `/root/wksim-joint-control-OEvS3W/build.json` SHA256 `d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e`。本次 WSL sha256sum 重新读回一致；三场归档的 ap-build.json/control-build.json 也全部一致。这只证明清单字节，未重跑完整源码/二进制准入。运行时仍必须由原入口核验 mixed→PV→fixed、PX4、模型、控制安装和消息层。

新证据 `validation/33-rate-profile/analysis.json` 保存当前四份源码 hash、各场 result/rate/wire 的 SHA256、初始化、实际调度、失败和前十个延迟间隔。只读重算：

```powershell
python validation/33-rate-profile/analyze.py > validation/33-rate-profile/analysis.json
```

全部来自最终 mixed + OEvS3W + full_xyz_pv_yaw_v1，保留双开关合同。不拿 qi66lh_y 或 zk5_nukn 的成功代验。

| 原场后缀 | 失败 tick | 迟到 ms | 相邻起始累计超额 ms | 组内工作超出8ms部分 ms | 其余区间超额 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| z5ediqxp | 49804 | 100.107132 | 99.791421 | 6.108357 | 93.683064 |
| h6jijdzn | 59240 | 100.021679 | 99.754497 | 10.851004 | 88.903493 |
| jo7l_p0b | 74792 | 103.155822 | 99.066328 | 8.607917 | 90.458411 |

起始超额按相邻 actual_start 差减8ms；组内工作按 actual_end−actual_start；其余为两者精确分解。表中的相邻统计不含最后一次没有下一组起始的尾部，因此不应等于最终失败迟到。单锚/tick40/0.5×及失败大于100ms均由脚本断言。

第三场 manager 实际 nice=-10、SCHED_FIFO=1/priority50，仍失败。首场 tick4996 的组内工作仅3.573ms，下一次释放却额外迟23.011ms；不能归因于该组物理计算超8ms。第二/三场 tick1924 组内工作12.770/11.555ms，确有另一类组内超预算。两类都必须保留。

组内含 physics、health、发布和写日志；其余区间含等待、health 回调、外层任务监督和调度抢占。原数据没有这些区间的线程CPU/分段时间，不能把约89%–94%的其余超额直接称作 Windows 或 DDS 根因。

## 冻结的下一候选：仅开启既有阶段采样

候选 ID `33-rate-profile-cpu-v1`。源码修改数为0，唯一配置变化为 `WKSIM_JOINT_CPU_TIMING=1`。现有 `Simulator/wksim_core/joint.py` 已提供 health_and_models、encode_send、native_inputs 的 wall/thread CPU 和 GC 样本，并由 ExitStack 移除回调。这是诊断候选，有记录开销，不能宣称性能修复。

#20 的编码、批量收发和 JointRate 保护等待已有当前源码实现；其历史 nice/FIFO 和宿主 High 实验没有给本组合提供通过证据。`run_joint_flight.py::physics_health` 仍每次 poll 所有孩子，而 #20 正式实现曾采用1ms轮询限制；但当前三场没有足够时间分解证明该处占主因，故不交付未经证实的节流改动。此前减少等待环 check 调用的基准也没有收益，保留原实现。

准确后续诊断命令（在项目根、预约独占运行资源后执行；本次没有启动）：

```bash
WKSIM_JOINT_CPU_TIMING=1 bash tools/run-joint-flight.sh \
  --task-profile full_xyz_pv_yaw_v1 \
  --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
  --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
  --control-manifest /root/wksim-joint-control-OEvS3W/build.json \
  --control-sha256 d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e
```

该入口自行生成唯一 run/live 目录，不指定复用旧目录。保留900墙钟秒/180000tick上限、0.5×、1ms物理、4tick屏障、8ms最小组起始间隔、100ms上限、完整10s/60s滑窗2%/1%、两段12s轨迹及全部原物理误差限。不得活动段重锚或扣除采样/GC/调度时间。

若诊断仍主要在组外，下一源码切片应仅在原始 `JointRate.begin_group` 健康调用、等待及外层监督区间加单调时钟/线程CPU分段采样，预分配缓冲并计入原倍率，不允许跳过检查。这需要扩展 #82 当前仅文档/证据的源码写入范围；本次未改源码。必须先测出具体区间，再选择节流、文件访问缓存或宿主措施，不能盲目重试最终验收。

最终 #83 使用实际新 run 交给 `tools/audit_pv_trajectory.py`，在既有ROS/message环境写新审计文件；只有完整身份、物理、原生输出、最终停止和所有滑窗通过才可称最终组合正常场景通过。开启采样的候选、清单哈希或计时单测均不替代它。

## 本次边界

只运行离线归档分析、清单哈希和既有计时单测；未启动FC/model/ROS、修改默认profile或旧证据、设置宿主优先级。Windows vmmemWSL PID68460可见但 PriorityClass 读取为空，不将其记作 High。分析不具备内核抢占/宿主延迟归因能力。

执行由当前主代理完成，没有子代理。会话指令标识GPT-6；没有可读的实际服务模型ID和推理档元数据，不能验证用户要求的 gpt-6-astra/low，未伪报已切换。
