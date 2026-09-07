# 2026-09-08 C1 双栈速度/偏航实施与证据轮报告（#32 进展，不关闭）

承接 `d9fcf71`，分支 `codex/independent-rgb-integration`。本轮全部由主代理完成（本会话无 gpt-6-astra 可核验配置）。Goal active；未关闭任何 G2/Full 门槛。

## 结果总览

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 语义冻结（票据验收 2） | 已冻结并入票 | [票 22](plan/tickets/22-velocity-yaw.md) |
| AP 原生速度入口 | `native_arducopter` cmd_vel/TwistStamped（固件 `rt/ap/cmd_vel` 处理器既有，`AP_DDS_ExternalControl.cpp:47` 实证）；受理前能力门 `supports()` | `ros2/src/prometheus_control/prometheus_control/native_arducopter.py` |
| 候选控制构建与矩阵 | **81 通过**（79 基线 + 2 新速度测试） | `/root/wksim-joint-control-FVMjak`、`validation/joint-control-checks-sdJuXZhJ` |
| 控制准入提升 | 健康提升飞行 FVMjak 实飞通过+独立审计；joint-profiles 换钉 FVMjak + 新模型库目录（.so 字节一致） | `validation/joint-public-flight-_cs_wxw_/{result,audit}.json`、profile 离线 `ok:True` |
| 速度任务联合场景（4 次正式尝试） | **双栈全部速度/偏航相位 4/4 通过**（含 AP 无效组合受理前拒绝+2s 无副作用 3/3）；**全场景干净收尾 0/4**（宿主噪声） | `validation/joint-velocity-yaw-{e4f9ty29,v1rpdh3g,k92rajnx,dn5n_5al}/` |
| 位置任务回归（票据验收 4 后半） | 通过（即提升飞行，健康公共位置任务+审计） | 同上 `_cs_wxw_` |

## 实际命令（可复现）

```
bash tools/build-joint-control.sh    # 产出 /root/wksim-joint-control-FVMjak
bash tools/check-joint-control.sh /root/wksim-joint-control-FVMjak/build.json f02edf158bf9b4d75cfd2221412bdbe83a10b21bc1642c97259294e12ef487a7
bash tools/run-joint-flight.sh --ap-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json --ap-sha256 f347ba25… --control-manifest /root/wksim-joint-control-FVMjak/build.json --control-sha256 f02edf15… --px4-manifest /root/wksim-px4-state-ONa1Kw/wksim-build.json --px4-sha256 d7e905b3…
python3 tools/audit_joint_flight.py validation/joint-public-flight-_cs_wxw_ --verify-current-sources
python3 validation/velocity-yaw-20260908/run_velocity_yaw.py
```

## 冻结语义与门槛（验收 2，全文在票 22）

XYZ_VEL/XYZ_VEL_BODY 惯性速度 + yaw-rate 为双栈公共支持；yaw 角度+速度组合 PX4 支持、AP 受理前拒绝（`arducopter_velocity_requires_yaw_rate_mode`）；XY_VEL_Z_POS*/TRAJECTORY/姿态/全球坐标归 #33/#34/#47。门槛：阶跃逐轴 |Δ|≤0.3 m/s×3s；零保持 |v|≤0.25 m/s、漂移≤1.0 m×4s；偏航速率 0.5 rad/s 积分角 |Δ|≤0.35 rad×4s；拒绝后 2s 无副作用。

## 四次正式尝试明细（样本全部保留）

1. `e4f9ty29`：双栈全相位通过并正常降落；驱动包络断言缺陷（setup/command 信封混读，已修），场景因驱动退场被终止——不计干净收尾。
2. `v1rpdh3g`：双栈全相位通过；降落段宿主持续漂移 100.02ms 如实 rate_unmet（72732 tick）。
3. `k92rajnx`：双栈全相位通过；降落段 100.03ms 如实 rate_unmet（72772 tick）。
4. `dn5n_5al`：起飞后 AP 原生 freshness 撤销（宿主噪声窗口，段内 72.26ms<100 非倍率违例），任务级失败。

AP 无效组合拒绝（`invalid_combo_rejected` + `invalid_combo_no_side_effects`）在 1–3 场均真实验证；拒绝原因字符串、请求身份与零副作用由任务事件与真值核验。

## 宿主环境观察（与 1× 同族）

本日 WSL VM 至少 4 次重启（一次发生在提升飞行完成写出结果之后）；四次速度任务运行的段末累计漂移持续贴近 95–100ms。`vmmemWSL`/`vmwp` 提权失败（非交互无管理员），该已授权宿主机措施需用户经 UAC 施加。

## 未决（不替用户回答）

1. #32 全场景干净验收：待宿主安静窗口或用户施加 vmmemWSL=High 后重跑 `run_velocity_yaw.py`（实现/证据已就绪，预计单次 6–8 分钟）。
2. 五项批准记录的其余项（#42 构建、#31 深度）继续按记录执行。

#32/#21/#20/#42/#6/1×/G2/Full 保持 open；未放宽任何阈值，未推送远端。
