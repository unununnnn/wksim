# 原生状态频率与独立 PX4 候选工作检查点

本轮已归档，完整结果见[正式报告](../2026-09-06_native-state-cadence-report.md)。当前三场8k0pfleo/c8brdmu4/8_xg9ibk全部当前源码审计及重复字节检查通过，6个审计负例正确拒绝；10场127个自建组无残留。最终安装74项通过、默认310项（27跳过）、旧预检11通过。43156、46318和86102均已结束退出0，没有这些句柄要继续等待。下一轮直接推进正式产品配置/联合入口，不重复下述已完成工作；Full/Goal保持active。

完整 Goal active。上一轮 DDS 审计收口已完成；本轮取得新的真实根因与候选，不是 G2/Full 完成。

## 当前结果

- 新观测工具 `tools/debug_px4_native_state.py` 只包装实际封存 Control 的回调/状态/新鲜度方法，原方法各调用一次；不发命令、不改判断。Humble只给DDS source/received时间、不提供逐消息GID，发现的发布者身份另列。2项差分/真实RMW检查通过。首两次适配失败和旧矩阵分组夹具失败均保留。
- `joint-public-flight-ueydtnu6`：固定PX4/JlC29M，真实AP Agent断连恢复和观测通过；已按封存源码审计。
- `joint-public-flight-acl9ohp6`：仅在降落阶段每4ms场景屏障至少等待12ms墙钟，真实复现Task定位失效。实际Control检查时仅estimator超龄2.004632929s，其他源新鲜、全部原生健康标志正常、generation不变。旧任务失败另属预期DDS撤销，不混为此降落失败。
- PX4独立复制/构建：首版`/root/wksim-px4-state-cNIif6`仍链接Gazebo，未飞行；合法空rc.serial触发过封存失败后已按字节保留。最终`/root/wksim-px4-state-ONa1Kw/wksim-build.json`，SHA256 `d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6`，固件SHA `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a`。42,012源文件/40个Git仓库，只有EKF2周期改200ms、去掉SITL gz模块两处源修改；不改2s门槛。仅链接libc/libm/libgcc_s/libstdc++，运行前后maps另核查。
- `joint-public-flight-68f_gxw1`：ONa1Kw + JlC29M，在同一慢速降落条件真实通过，原始恢复/候选/运行库审计已通过；此后Task/Node有新更改，后续按其封存源码理解。
- `joint-public-flight-03quqqlx`：ONa1Kw + JlC29M，健康暂停/单步/完整公共任务通过，待最终审计。
- `joint-public-flight-a04c93yc`：PX4 Agent断连后，物理就绪时无failsafe，新的Task读取时已有failsafe；原条件offer拒绝发送必要原生保持，等待55sim秒失败。已将新PX4恢复Task明确选定公开AUTO.LOITER→原生确认→新接管，不再以瞬间快照决定是否执行已授权入口；增加高水位/uint32 LAND保留空间检查。
- `joint-public-flight-0l_skmzi`：新Task已完成原生保持，但接管被真实节点以missing_home_or_landed_state拒绝。恢复确认原先未覆盖这些接管前提；现要求保留home及新鲜native flying=true，并在ACK报告，5s恢复上界不改。
- 新Control候选`/root/wksim-joint-control-8xt3WC/build.json`，SHA256 `28c58fb755f9ef9c0a207db67517f90da2fde65379f4b4207c7aa90197302492`。源接缝64项（6跳过，其余通过），安装候选73项通过，13项Task恢复测试通过。准入正负5项通过，默认生产配置仍拒绝实验PX4。

## 此前执行记录

92525已结束退出1：最终产品矩阵AeLVTGLq为309项（27跳过，其余通过）、旧预检11通过；随后n4njgjkm被真实AP Task在起飞前读到半写入go.json而失败。已将run_joint_flight.save改为同目录临时文件+原子替换；确定性读者窗口负例先复现空JSON、修复后两种首次/替换情形均通过。

随后43156已结束退出0：`joint-public-flight-8k0pfleo`，ONa1Kw + 8xt3WC +当前Task/原子交接已完成真实PX4 Agent中断/恢复/新任务/正常降落，约130.006墙钟秒，尚待最终独立审计。当前正在串行跑同组合AP慢速降落和健康回归，实时进度分别写入`validation/native-state-observation-20260906/final-ap-slow-landing.log`、`final-healthy-flight.log`。先查当前工具句柄/真实进程，不能因旧描述或观察超时重启。

此前46088、1249、87061、55386、3549、26722、51050、80449、1216、39371、17064均已结束；失败样本如上，不等待旧句柄。

## 后续工作

1. 把已实测独立候选接入正式产品配置/联合启动与操作流程，保留原参考，不靠扩大默认准入名单跳过身份/构建检查。
2. 继续正式倍率、迟到掉队、完整复位/旧队列、UI/UE与Full余项；本轮诊断慢速条件不是倍率验收或G6预算。
3. 下次新结构查询前按Codebase Memory检查/刷新，旧持久化失败尚未被宣布修复。已知证据可直接按新报告读取，避免重复实飞或探索。

没有修改原PX4/AP安装、SDK/UE/P450、用户AP PID828；未操作硬件或推送代码。本轮主代理独立执行，无新子代理。
