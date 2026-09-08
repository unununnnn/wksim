# AP DDS 完整 P+V 候选补丁（已构建，未准入）

主代理后续实际构建通过：`/root/wksim-ap-pv-vn04950x`，waf copter 1m54.346s，固件SHA256 `7dfeb027e06712380f499611e2ba1bc809ed71f74ae477807ac5b2d51d62bb44`。构建后全源快照仍等于准备快照，固定OXQqdR原源/清单未变；签认记录为 `validation/migration-followup-20260908/ap-pv-sealed.json` 与候选 `pv-build.json`。准备器增加独立.git目录/实际Git顶层检查，避免对固定工作树执行patch。仍未安装/准入/实飞，适配器与正式默认飞控未切换。下文“未构建”均描述子代理源准备交付当时的边界。

2026-09-08。此交付仅为 #33 的完整 XYZ 位置 + XYZ 速度前馈 + 可选 yaw 固件候选；不是混合轴实现，不是固件准入或 #33/Full 验收。完整 Full 终态及原门槛保留。

## 来源与隔离

实际子代理 JSONL `C:/Users/PC/.codex/sessions/2026/09/08/rollout-2026-09-08T15-40-42-01a07fbf-5bbf-7560-af0b-9e94359226ea.jsonl` 的 `session_meta.agent_path=/root/ap_pv_candidate_patch`，`turn_context.model=gpt-6-astra, effort=low`；没有嵌套委派。已读项目 AGENTS/CONTEXT、context map、C2 接缝预检、两份相关批准记录及现有 AP 候选脚本。

补丁精确基于 `/root/wksim-ap-clock-stop-OXQqdR/src`：commit `1511f27194f1dcc3728270883047bdf022b3fd53` + 已批准 0001/0002/0003。固定 `wksim-build.json` SHA256 为 `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a`。四个原文件逐个与该 manifest 匹配：

| 文件 | 原 SHA256 |
| --- | --- |
| `libraries/AP_DDS/AP_DDS_ExternalControl.cpp` | `59c9e20ca9db9a8cfbbbe315000af52643a92d80d6117e52863d8b7ba23f7c25` |
| `libraries/AP_ExternalControl/AP_ExternalControl.h` | `9423b61155de818b21ffeceb46891eb1c1c6a70fb8c8265457556bf9646a93c5` |
| `ArduCopter/AP_ExternalControl_Copter.cpp` | `cb3dd63da635063805b983cd4ae06c921bc39f5c79454b625c273cb3fece1e09` |
| `ArduCopter/AP_ExternalControl_Copter.h` | `4e0ec86baf939be96eb2fdf3705a498592f1a7efea3ca1c909a6cf7d1fe635f8` |

新补丁 `Simulator/firmware/ap-pv-candidate/0004-dds-global-position-velocity.patch` SHA256：`06e0610fb1346a309fb1f967c69c27e8c82900bd521c315565e082a14692b3cf`。不向固定源 apply；MUl 安装、runtime、pins、控制适配器与消息 schema 均未改。

## 行为

GlobalPosition 的 `map` 帧接受四种精确 mask：2496（P+V+yaw）、3520（P+V，yaw 忽略），以及原有 2552（P+yaw）和 3576（P）。完整位置必须激活；速度必须三轴全激活或三轴全忽略。部分 P/V、有效 A、force、yaw-rate 和未知位全部拒绝。保持原经纬度/高度有限值与范围、有效 yaw、高度 frame 5/6/11 校验；新增有效速度 double 有限值、float 范围及转换后有限值校验。被 mask 忽略的载荷仍按原约定忽略，避免改变纯 P 行为。

P+V 使用 `velocity.linear` 的 ENU m/s 转 NED `(y,x,-z)`；yaw 延续 `wrap_PI(pi/2-yaw)`。新增 ExternalControl 虚方法默认拒绝不支持的机型；Copter 实现保留 ready 检查，使用 `Location::get_vector_from_origin_NED_m(Vector3p&)`。其实际实现先解析 ABOVE_ORIGIN 高度及相对 EKF origin 的 NE，再转换 cm→m 和 U→D；不把 home 当 origin，所需 origin/home/terrain 信息缺失则返回失败。

仅调用现有 `ModeGuided::set_pos_vel_NED_m`；fence 返回值直接传播，原生目标 timestamp/timeout 与控制律保持。加速度由现有该接口显式置零。未更改健康检查、GUIDED_OPTIONS、fence、timeout、外部 PID 或轨迹加速度契约。原纯 P 调用仍使用 `set_global_position` / `set_global_position_and_yaw`，不会改走 P+V 子模式。

## 已执行检查

WSL Ubuntu-22.04 的 `python3 tools/test_ap_pv_candidate.py` 通过：仅四文件复制到新临时目录后 apply/reverse；读取实际候选 mask 表达式枚举全部 65,536 个 uint16 值，仅上列四个通过；原纯 P yaw 分支起至文件末尾逐字一致；ENU 转换、origin API、原生 Guided 调用/参数及 ready 检查源码 guard；逆补丁恢复与固定源前后 hash 不变。最后一次证据目录 `/tmp/wksim-pv-guard-1uhiu0_f` 保留完整 `baseline-manifest.json`、`before-sha.json` 与四个恢复后的源文件。

`bash -n tools/build-ap-pv-candidate.sh` 和仓库 `git diff --check` 通过。尚未编译 AP，离线 guard 不是 C++ 编译或飞行行为证明。准备工具的全树 snapshot/复制尚未执行，遵守主代理真实双 FC/UE 测试期间的资源串行约束。

## 后续准确命令

在 WSL Ubuntu-22.04 root 下：

```bash
cd '/mnt/c/Users/PC/Documents/odid编译/wksim'
python3 tools/test_ap_pv_candidate.py
# 仅准备：全量核验固定manifest，复制到新的 /root/wksim-ap-pv-*，apply并保存pv-source.json。
python3 tools/prepare_ap_pv_candidate.py
# 独立完整构建入口（会另建一个新候选；仅在主代理释放资源后执行）：
bash tools/build-ap-pv-candidate.sh /root/wksim-dds-VxM6Ni
```

构建入口延续原脚本的 DDS generator PATH、`waf configure --board sitl --enable-DDS` 与 `waf copter -j4`，所有 out/log/bin 在新候选目录。保存 baseline manifest、原 patch、prepare 脚本、准备后全源 snapshot 与 SHA，以及构建输出 SHA；不安装、不修改现有 manifest 或准入、不切换 ROS overlay。已有 schema 没变，无需新消息 overlay。

剩余工作：真实编译和候选身份封存；非有限输入/坏帧拒绝的可执行验证；不同 home/origin、terrain 缺失、fence 拒绝、原生命令 timeout 的运行证据；显式新 profile 的适配器接入；冻结阈值后的双栈轨迹/停止恢复验证。DDS 当前失败无 ACK，发布成功不代表飞控受理。真正 XY 速度/Z 位置仍需后续显式轴模式，不能用此补丁冒充完成。
