# #62 `20-rate-epoch-1` 1× 第一个独立 epoch 失败交接

## 票据与边界

- GitHub：#62 `[Luna] 1× 第1个独立60秒epoch：运行一次并原始审计`
- 稳定键：`20-rate-epoch-1`
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`821223e docs: freeze measured 1x host scheduling candidate for #61`
- 只执行本票第 1 个 epoch；没有启动 epoch-2，也没有重试该飞行。

## 准确命令与冻结身份

```text
wsl -d Ubuntu-22.04 -u root -- taskset -c 0-7 /usr/bin/python3 -B validation/20-rate-candidate-profile/run-one.py 1
```

- run ID：`rate61-cpu8-20260909-e1-e2561e27`
- 输出根：`/root/wksim-rate61-cpu8-e1-e2561e27`
- 证据目录：`validation/lunar-20-epoch-1/case`
- 候选：`rate61-linux-cpuset8-v1`
- candidate.json SHA256：`d75673b8e941f141d1fc23a379fa18e4ef690c610dc9b27e6e80145827b9b8b3`
- run-one wrapper SHA256：`ef009db501247ab80d09bff8d43006cda5acfc29c3e72c0324d314ec6dd9d925`
- 固定 CPU 集：`0..7`
- 内部即时 resource preflight 退出码：`0`

## 实际结果

- 外层运行失败：`RuntimeError('Ground readiness failed: faulted')`。
- manager 退出码：`1`；生成了 1 个 epoch 目录，但没有满足 60 秒连续空中窗口。
- run/result：`status=failed`，错误为 `Owned joint epoch interrupted`；状态阶段为 `failed`。
- 运行后 `remaining_manager_group=[]`，WSL 进程快照无该 run、PX4、ArduCopter、模型、Agent、ROS 或 task 残留；原始输出目录和结果文件保留。
- 此失败不构成 1× 性能通过，不能打开 epoch-2；#62 必须保持 OPEN。

## 原始倍率审计

前置 #61 合同给出的命令含 `--mode steady`，但当前 `tools/audit_joint_rate.py --help` 明确只接受 `--output` 和 `--require-epochs`。该原命令已原样保存并返回：

- 退出码：`2`
- 错误：`unrecognized arguments: --mode steady`

基于当前实际入口去掉未知参数后，仅做一次等价审计：

```text
source /opt/ros/humble/setup.bash; source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash; source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash; source /root/wksim-ros2-MUlZd0/install/local_setup.bash; source /root/wksim-joint-control-FVMjak/install/local_setup.bash; /usr/bin/python3 -B tools/audit_joint_rate.py validation/lunar-20-epoch-1/case --require-epochs 1 --output validation/lunar-20-epoch-1/audit-corrected.json
```

- 退出码：`1`
- 审计结果：`status=failed`，`FileNotFoundError`，因为 ground readiness 在产生正式 `flow.json` 前已失败；没有伪造审计输入或 PASS。
- 两次命令、stdout、结果 JSON 和 `tools/audit_joint_rate.py --help` 的实际输出均保留在本票活动证据目录。

## 证据位置与哈希

- 活动交接目录：`validation/lunar-62-6cafe442f40b4e499f035d282ac6ec99`
- run 原始证据：`validation/lunar-20-epoch-1/case`，包含 experiment、preflight、service、wrapper、status、result、epoch truth/wire/rate/clock/CDR/原生日志和进程 maps。
- `run-one.stdout.log` SHA256：`5352f7ec124c4c7a0a1136e995b6662c9d4eea0a9ded981f10f688c76bf221f8`
- `validation/lunar-20-epoch-1/case/wrapper.json` SHA256：`060e54dcb6af8b9208bd21521c4c40caea32de5a827a129b67bb853e86a81fba`
- `validation/lunar-20-epoch-1/case/run/result.json` SHA256：`e23404eac09fc9723322750e5021a8983ad90f4907d4237e489a9f1c3f9d612a`
- `audit.stdout.log` SHA256：`e066b6ca391fac592a9d7b219c0f6769edb16593ee16635c3f1fc10d28abdcf`
- `audit-corrected.stdout.log` SHA256：`5a41d005f1624b313f44db58f01077a909f838656c0688d1a7f6b27b6d4973e6`
- `validation/lunar-20-epoch-1/audit-corrected.json` SHA256：`86d5f7494761dc6d94aae19e351dc8d1ac4f15ba5df85bd1a8817005b2eabdd1`

## 完成判定

本票完成条件未满足：没有通过 100ms 监督和 10s/60s 率窗口独立审计。按指南应保持 #62 `OPEN`，移除 `ready-for-agent`、添加 `needs-triage`，等待 Astra 针对 ground readiness/faulted 接缝提供修复或新冻结合同后再考虑下一次运行。原始预算、CPU 候选和失败原件保持不变。
