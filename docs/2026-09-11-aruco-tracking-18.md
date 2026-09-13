# 第18场：PX4输入等待的220ms峰值

`aruco-track-e8b6165cde` / `401aa911f17a49759f753beff0a622a4` 在tick9388失败，累计迟到230.194579ms，未起飞/启用RGB；驱动退出1、管理器退出0。原件183成员、2分片，SHA256 `6e0e88d7b42291c7fced6508930ef95b2c04ec9edcef51c83117f5cc675040d7`。

在失败前，最后一个已释放组的相位差约15.077ms，组执行中位3.293684ms。失败组耗时223.117222ms，其中PX4输入等待219.973566ms，监督器线程CPU25.078397ms；AP等待仅0.147981ms。循环边界探针确认此窗口管理、时钟发布和时钟证据写入均短，主要长耗时属于physics中的PX4等待，不能由监督器JSON写入解释这次220ms峰值。

这仍不区分PX4等待actuator_outputs、组件屏障、发送路径或调度。已实读TCP_NODELAY两侧启用，不作为“新修复”；native send依次执行poll、准备、wait_for_components、send_controls。不能按100ms倍数反推具体路径，现有原生日志没有这些分段墙钟。

下一候选增加显式原生计时，保留原poll超时、注册/进度/信号量语句、空组件立即返回、所有屏障参与者与日志功能。原始失败保留，不放宽100ms门。

证据目录 `validation/40-aruco-tracking-18-px4-loop`；派生记录 `validation/coordination/aruco-18-{rate-replay,failure-timing}.json`。更新后的分析器分别输出嵌套核心/运行时区间，不能把它们相加为总耗时。
