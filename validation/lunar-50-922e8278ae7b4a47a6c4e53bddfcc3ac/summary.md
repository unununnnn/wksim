# #50 `35-preflight` PX4 PID 只读准入摘要

## 票据与边界

- GitHub：#50 `[Luna] 执行一次 PX4 PID 只读准入`
- 稳定键：`35-preflight`
- 本票只执行一次 PX4 `--preflight`；不启动飞行，不判定 #35 的双栈闭环、物理性能或 Full 验收。
- 绑定时状态：`OPEN`，标签含 `ready-for-agent`。
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`3c037e9 Complete Hex round and publish bounded Luna handoff`

## 精确命令与运行身份

```text
bash tools/run-pid-flight.sh --stack px4 --run-id pid-px4-preflight-771c324469a6 --config Simulator/wksim_runtime/pid-flight-v1.json --output-root /root/wksim-pid-flight-pid-px4-preflight-771c324469a6 --preflight
```

- 运行时间（UTC）：`2026-09-09T07:35:16.3043098Z` 至 `2026-09-09T07:36:17.7007413Z`
- 退出码：`0`
- `Simulator/wksim_runtime/pid-flight-v1.json` SHA256：`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`
- `tools/run_pid_flight.py` SHA256：`695e59e92700045e4d7ce297f9b11127939bf833855195edac27dc961d4c430f`
- `tools/run-pid-flight.sh` SHA256：`c772423deea8dde33914f05edef5777cf116c06cbae4c008f9accaea09ae8302`
- PID 外部协议 SHA256（结果中 `external_pid.protocol_sha256`）：`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`

## 实际结果

- 解析原始输出得到 `ok=true`，`reasons=[]`。
- 配置为 `stack=px4`、`model_profile=quad_x`、`control_protocol=session_v1`。
- `production_admitted=false`、`flown=false`、`children_created=0`、`ros_nodes_started=false`。
- 预期的 `/root/wksim-pid-flight-pid-px4-preflight-771c324469a6` 输出目录不存在，符合只读准入路径。
- 运行后 WSL `ps` 快照中：该 run ID 匹配数 `0`；PX4、MicroXRCEAgent、模型、ROS 相关匹配数 `0`。运行前后快照均保留，证明本票没有启动 FC、模型或 ROS 子进程，也无需清理子进程。

## 实际身份

- PX4：`/root/wksim-px4-state-ONa1Kw/src/build/px4_sitl_default/bin/px4`；SHA256 `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a`；commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`；源文件数 `42012`。
- 模型库：`/root/wksim-private-tmp-bhi18a3s/artifacts/wksim-model-qhdy93lm/libwksim_model.so`；SHA256 `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`。
- 模型归档 SHA256：`d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`；wrapper SHA256 `3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c`；编译器 `g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0`。
- 实际导入 control：根目录 `/root/wksim-attitude-control-x3_2v4wb`；包路径 `/root/wksim-attitude-control-x3_2v4wb/install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control`；manifest SHA256 `95078a02b863b0307832ae9eb8aad6025a6dd0a88b34506983ae5e3cd43cf8d0`；verification SHA256 `4ed5331deac4a20b2fac59d0545df8e5de10ecf6535b4b6d485f94fea30c662c`；已安装 Python 文件数 `9`；installed tree SHA256 `e92ff7938ddbe7c41c19a6ce1774bdb99e5ec493c50dac0f71cb0891ba8b7416`。

## 证据与检查

票据专用证据目录：

`validation/35-pid-preflight/pid-px4-preflight-771c324469a6`

活动交接目录：

`validation/lunar-50-922e8278ae7b4a47a6c4e53bddfcc3ac`

其中保留：

- `preflight.stdout.log`：原始 stdout/stderr 捕获，SHA256 `8239b72b85ca1eaa01f6cdce75e40a6617bd867dc7188626503501b5c40c0445`。
- `preflight.parsed.json`：从原始输出 JSON 起始字节解析出的准入结果。
- `processes-before.txt` / `processes-after.txt`：运行前后 WSL 进程快照。
- `run-metadata.json`、`selection.json`、`identity-summary.json`、`artifact-sha256.json`：命令绑定、票据选择、身份摘要和证据哈希。

检查结果：

- PX4 PID `--preflight`：通过，退出码 `0`，`ok=true`。
- 运行过程没有 FC/model/ROS 子进程。
- `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check -- . ':(exclude)*.patch'`：通过。

## 完成判定与未覆盖范围

本票完成条件满足：PX4 只读准入真实通过，配置与实际安装身份已保存，原始结果和无子进程边界可复查。可以评论并关闭 #50。

本票没有证明 PX4 PID 实飞、动作完成、独立全量审计、AP 准入或 #35 父票关闭；AP 需执行独立的 #51 子票。
