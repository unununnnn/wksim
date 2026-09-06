# DDS 恢复进行中检查点

完整Goal继续active；此文件是工作检查点，不是阶段验收报告。上一Goal轮属于实际进展，当前轮也已有代码、实测和失败诊断。

## 当前授权与工作区

- 两项语义/监督值均已批准，见 `../2026-09-06_joint-wall-supervision-accepted.md`。不再询问已批准内容。
- 工作中其他项目管理任务完成了独立资源搬迁；现以当前 `../../AGENTS.md` 和 `../project-isolation.md` 为准。PX4使用 `/root/wksim-dependencies/px4-d6f12ad1`，不回退配置到兄弟工程。固定二进制SHA未变。
- 新目录缺少PX4生成的alias/模块入口，曾造成真实启动失败。已一次性复制固定参考构建的启动文件到独立目录，模块链接只指向同目录px4；没有覆盖已有文件或改原安装。清单 `/root/wksim-dependencies/px4-d6f12ad1/wksim-runtime-files.json` SHA256 `a2d006075834791947120992d14c26cfef782a2b3112a07ae2b508e51e722e21`，已纳入预检。`runtime.launch_spec`显式指定独立test_data和bin PATH。

## 当前代码

- `SceneClock`记录每个AP实际输入确认，通信故障可冻结在已完成的1ms微步；部分模型/输入或时钟错误仍不可恢复。显式recover不改变epoch、不重标时间。
- `JointLifecycle`已迁入 `Simulator/wksim_runtime/joint_lifecycle.py`，旧tools文件仅兼容导入。
- 许可协议v2携带 `faulted_uav_ids`。明确退出的Agent旧DDS发布者GID可以在显式恢复时退休，其他未知多发布者仍拒绝；解决发现缓存保留旧发布者导致误判。
- 恢复把原生链路/导航就绪与任务控制资格分别报告，保持真实failsafe标志。必要时明确授权的新PX4任务先通过公共AUTO.LOITER请求和原生ACK恢复健康，再请求COMMAND_CONTROL；不伪造状态，不关闭飞控健康检查。
- 新 `Task.recover_then_land()` 只接新任务，按公共高水位用新请求接管、2s共享时间保持、LAND和正常停止；原Task终态失败，不重播旧航点。无具体请求归属的撤销事件仍致命。
- PX4被动重连受仿真时钟ping周期限制。显式恢复时通过本实验PX4原生CLI仅stop/start DDS客户端模块；先用SO_PEERCRED验证目标PID。`isolation.isolate_temporary_files()`用私有overlay隔离/tmp写入，保留旧构建读取，新模型产物写入项目私有持久目录。共享正式runtime也已接入，预检失败前不创建此挂载。
- 审计公共模型/原始执行器/传感器/clock验证已抽到 `audit_joint_flight.audit_timeline`。新DDS恢复审计在 `tools/audit_joint_dds_recovery.py`。模型速度ABI是state[3:6]、位置state[6:9]；曾误用姿态9:12，已依据实际sensor_message修正，并加测试，阈值未变。

## 构建与已有实测

当前Control候选 `/root/wksim-joint-control-JlC29M/build.json`，SHA256 `9bcdf892f57ee56486fc5732f96aa4666e1f7ab3bd6c8a84ab1825d253791201`。AP仍用 `/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json`，SHA256 `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a`。

- AP Agent断连/恢复成功：`validation/joint-public-flight-svzk81sz`，较早VtsiPZ候选；原始审计已通过。冻结tick51461，显式恢复约2.910墙钟秒；两新Task请求4/5/6，正常降落。后续源码变更后应按封存快照审计，不能再次声称它验证当前全部源码。
- 最终JLC候选PX4 Agent断连成功：`validation/joint-public-flight-39f4dlru`，审计 `dds-recovery-audit.json` 已通过；冻结tick51429，恢复0.510墙钟秒，15个场景进程组无残留。AP新请求4/5/6，PX4因真实failsafe经明确原生保持新请求4/5/6/7。独立物理保持误差0.0378/0.2649m，速度0.0306/0.2952m/s。原生CLI、私有/tmp及目标PID有证据。
- 安装候选73项通过：`validation/joint-control-checks-M8r02V99/tests.log`；源接缝61项、跳过6且另在安装检查覆盖：`validation/scene-lifecycle-checks-Y7LncvgR/tests.log`。之后另加了缺alias预检测试、更新了部分启动失败的文件系统夹具，需最终完整矩阵。

## 最新运行终态

最终JLC AP Agent复跑已启动：

- exec会话ID：**26894 已结束，退出0**。最后实际poll确认 `status=pass`、墙钟120.526s，正常完成降落退出。不要重启或把该句柄当活跃进程。
- 仓库证据目录：`validation/joint-public-flight-gjoiiu49`
- WSL实时目录：`/root/wksim-joint-flight-bh8o1m5u`
- 命令：`bash tools/run-joint-flight.sh --ap-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json --ap-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a --control-manifest /root/wksim-joint-control-JlC29M/build.json --control-sha256 9bcdf892f57ee56486fc5732f96aa4666e1f7ab3bd6c8a84ab1825d253791201 --scene-lifecycle --dds-loss arducopter`

该运行已结束；当前源码独立审计也已通过，结果 `validation/joint-public-flight-gjoiiu49/dds-recovery-audit.json`，日志 `validation/joint-dds-recovery-integration-20260906/final-ap-audit.log`。审计会话41155也已退出0，当前没有遗留的运行/审计句柄需等待。其他候选通过记录和失败样本继续保留。

## 保留失败

- `5y5s1fat`：AP重连有新鲜有效数据，但旧DDS发布者仍被发现，5s就绪失败；后续精确诊断证明count=2。
- `yuk0rgxx`：独立依赖搬迁遗漏px4-alias.sh，PX4启动退出255，未飞行。
- `6j56sh3u`：诊断明确 `/ap/status: count=2`，促成v2退休范围修正。
- `9eeyzgyj`：PX4 Agent回来但原生客户端被动重连未在5s窗口完成。
- `eglc5bjf`：原生客户端显式重启成功，但原生failsafe仍在；促成链路/任务资格分离与新任务原生保持。
- `kj284sh1`：JLC AP复跑在PX4临近触地时约22ms odom_valid=false后又恢复，任务按规则失败。尚未定位到具体导航字段；不得用过滤或放宽阈值改成通过。
- `sn40rz3y`：故障注入身份保护门拒绝；旧实现未保留第二次观测详情，不能倒填原因。当前保护改为PID/PGID/start_ticks + /proc/exe校验并保存比较，未对身份不符进程发送信号。

## 下一步

1. gjoiiu49已实际pass/退出0，当前源码独立审计pass，13组无残留；最终PX4案例39f4dlru原始审计也pass（15组）。继续汇总而不重复这两次飞行。
2. 当前代码再跑健康 `--scene-lifecycle` 回归，并核对v2协议审计（已允许v1/v2健康许可）。
3. 跑 `check-scene-lifecycle-source.sh`、最终 `check-session-product.sh`（含11项旧预检）、必要审计负例/可重复性；不要把跳过算通过。
4. 用实际内核身份汇总本轮全部场景进程组及原AP PID828前后身份。已有场景列表见上文，另有当前gjoiiu49及随后健康回归。
5. 完成报告、README/对应票据与Codebase Memory覆盖记录，更新#8/#19/#20/#22。当前轮尚未发布这些新结果；不关闭父图，不标记Goal完成。重复性、任意网络丢包、倍率、完整冷重置、正式UI/UE和全部Full/G6仍留账。

子代理Peirce仅改Task/新测试，actual turn_context已核验gpt-6-astra/low，配置证据在 `validation/joint-dds-recovery-integration-20260906/agent-config.json`；已完成，不能用不支持显式模型设置的续派接口恢复它。
