# #83 最终组合控制身份刷新

2026-09-11。首个新尝试 `joint-public-flight-l8xlqwdq` 使用已冻结的 AP mixed 与 OEvS3W 控制 manifest。入口在实验准入阶段以 `Sealed control build input differs` 拒绝：`children_created=0`、无 epoch、0 个物理 tick，墙钟 46.495731359s。原始 `result.json`、`experimental-admission.json` 和当次执行源码保留在同名 validation 目录；没有把预检失败改写成倍率或物理结果。

两个私有旧控制目录自身未变。差异来自后续已接纳的 RC 提交 `0ae940d`：当前 `CMakeLists.txt`/`package.xml` 新增 `rcl`、`rmw` 和 `wksim_rc_take`，当前控制 Python 也包含 RC 接线。OEvS3W 因此不再满足新候选必须与今日 repository/staged/installed 三方一致的检查。另一方面，`ap_pv_candidate._sealed_control()` 仍复制了一份旧验证器，错误要求历史 FVMjak 的 build inputs 等于今日仓库；正式 `joint_profile._control(..., sealed=True)` 已正确只把历史 manifest 绑定到其 staged/installed 字节。此次删除重复实现并复用正式验证器：旧 staged/installed、build log 和 build script 的任何变化仍拒绝；今日源码及构建输入由独立 `check_control` 候选分支完整负责。

当前源码经原 `tools/build-joint-control.sh` 构建并封存为 `/root/wksim-joint-control-0DQQz9/build.json`，manifest SHA256 `25edbf816e1b417028be73f409b211b48a1579cce4d63b0d9c6c9b5277e6d610`。构建输入为 CMake `8e879120…591`、package `6c7b9f84…8b4`、启动脚本 `b73f77d5…cfc`、`rc_take.cpp` `d6969f1d…ee6`；生成的 RC transport SHA256 为 `f00ccb7d…07c`。没有覆盖 OEvS3W 或 FVMjak。

验证结果：

- 30 项 candidate/PV/mixed/profile 定向单元测试全部通过。
- 第一次 81 项控制候选矩阵暴露 `0ae940d` 未同步 `test_joint_control_candidate.py` 的 `rc_take.cpp`/共享库夹具，原失败日志保留；补齐夹具与篡改拒绝检查后，第二次 81/81 通过。
- 使用真实 AP mixed、固定 PX4/模型/消息、历史 FVMjak 及新 `0DQQz9` 运行完整 0-child admission，结果 `ok=true`、`children_created=0`、无拒绝原因；新控制 root 与历史 baseline root 分别为 `0DQQz9` 和 `FVMjak`。

`tools/ap_mixed_candidate.py`、最终组合运行合同和待接证据的 mixed profile 已换钉新控制 manifest。随后真实场 `joint-public-flight-zzmg3k47` 已通过本准入，但在 tick 98,700 以累计迟到 `100.092095ms` 失败；详见 [失败报告](2026-09-11-final-combo-rate-failure-zzmg3k47.md)。本次准入修复不证明物理、倍率或正式 profile 已通过，也不改变旧三场 RateUnmet 和本次 0-tick 失败。
