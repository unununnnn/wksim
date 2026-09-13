# PX4 第16场：起飞前倍率失败

`aruco-track-8e056c491a` / `d47cb442efcb48bcae670c0c7a246f6b` 在tick27956触发倍率保护，累计迟到121.048875ms，未启用RGB、未起飞。驱动退出1，管理器退出0，保留失败原件；没有用AP第15场的成功改判本场。

真实JointRate时间重放精确复现该组结束时的拒绝。6979组的执行中位数3.312444ms、最大29.642500ms，15组超过8ms。tick13008还有14.907570ms组外相位增量，前组自身仅3.137898ms，不能只看模型平均耗时解释失败。

27920..27956窗口9组工作100.949ms，已采样阶段累计：health_and_models墙钟17.820ms/线程CPU15.131ms，encode_send13.668/13.661ms，native_inputs16.054/10.194ms。原生等待中有PX4约5.97ms与AP约3.23ms峰值；GC最大0.443671ms。采样不是完整普查，阶段以外部分仍未归因。结果与第15场主要AP等待的峰值不同，不能只修改某个飞控或据此排除宿主调度/计时影响。

原件 `validation/40-aruco-tracking-16-px4-cpu` 共205个归档成员、3个分片，SHA256 `ced666013a65a8a866581ccdcc3be3e72a956f681174421d8d5862ae5a7d460f`。派生证据为 `validation/coordination/aruco-16-px4-rate-replay.json` 与 `aruco-16-px4-failure-timing.json`。

下一可执行诊断是经过身份/退出边界复核的外部只读线程采样，不改变原倍率/屏障/步长，也不凭单场成功提升正式倍率能力。PX4采用末尾HOLD与writer守卫的对应完整场仍未完成，#104保持OPEN。
