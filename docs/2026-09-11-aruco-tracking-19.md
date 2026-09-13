# 第19场：原生屏障等待与动态工作队列

`aruco-track-78cb277e06` / `e60d74f1719f4e5684e144ff09513b76` 使用v1诊断固件，进入PX4相机跟踪后在tick60168、累计迟到100.119728ms失败，15帧。驱动退出1、管理器退出0，进程组无残留、无清理错误。316个归档成员、5分片，SHA256 `0c42c2c169622507d74baa46236af083b63ddabd1c79656a245c4fb137f210bb`。

原生分段记录首次直接证明：本场hrt5504000us附近的发送循环，poll约7.983ms、组件段26.160ms、发送约0.031ms；内部sem等待26.152ms。约21.774ms的倍率相位增量与该区间对应。启动早期还记录了329.782ms poll，但它不属于已建立的同一个倍率窗口，不能直接算作该窗口的迟到。最终故障时没有再次出现长native wait，是此前累计相位耗尽门槛。

原生记录同时暴露了v1探针的缺陷：共有81563次注册日志。除logger与SimulatorMavlink直接注册，`platforms/common/px4_work_queue/WorkQueue.cpp`也通过包装函数为队列动态注册/注销；注册发生在Add调用线程，因此任务名可能是hrt或simulator，并不是队列名。v1未观察注销释放，故5504ms那条记录的最近progress释放时间早于此次wait，不能据此归因logger。高频注册输出还可能扰动时序，本场不是无探针性能保证。

v2因此移除注册输出，增加慢工作项和慢队列批次观察，区分progress与unregister释放。原控制与屏障算法不变，不能移除工作队列参与者来规避100ms门。原生二进制与v1失败原件保持不动。

数据在 `validation/40-aruco-tracking-19-px4-component`；派生记录为 `validation/coordination/aruco-19-{native-trace,rate-replay,failure-timing}.json`。PX4修复后完整场仍未通过，#104继续OPEN。
