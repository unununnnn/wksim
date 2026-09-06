# 控制候选的只读准入

`preflight(config)` 按 `control_protocol` 选择固定控制候选。缺省为 `legacy_v1`，显式 `session_v1` 才准入 `/root/wksim-ros2-2egljG`。返回 `ok=true` 表示当前检查通过、候选有指定场景的历史飞行证据；不表示定位就绪、任务接管或本次飞行成功。

此处仅负责准入，不启动 FC、Agent、physics、ROS 节点、UE 或子进程，不构建、不修改候选。控制进程地面重启及新包络接管由 runtime/任务流程负责，本准入没有重复运行重启 harness，也不扩大其验收结论。

## 选择与证据

| Profile | 控制 workspace | 飞行证据 |
| --- | --- | --- |
| `legacy_v1`（缺省） | `/root/wksim-ros2-0viK3f` | [PX4](../validation/px4-dds-epf9gukj/result.json)、[ArduCopter](../validation/arducopter-dds-urq9hofr/result.json) |
| `session_v1` | `/root/wksim-ros2-2egljG` | [PX4](../validation/px4-dds-egh5mte7/result.json)、[ArduCopter](../validation/arducopter-dds-mb39iyad/result.json) |

[capability-index.json](../Simulator/wksim_runtime/capability-index.json) 的 `baselines` 保留原路径、证据 SHA 和安装快照，不覆写。`control_profiles.legacy_v1` 引用这一历史基线；`session_v1` 独立保存两个结果的 SHA 和新安装快照，只替换控制 workspace、飞行结果与相关安装包，继承原 firmware/Agent/native message package 固定边界。

新证据 SHA256：

- PX4：`683e5dcd0dc5e3f7239dfee80c5e1eeb91cd29965de6502a74bd66d2f717942c`
- ArduCopter：`3b6a91981f0b85ab219bef44e25bee9aeaea974ab3165e571cd01dd283aa88b8`

选择任一栈的 session profile 都先验证两份证据。检查各自的 `status=pass`、stack、protocol、控制/DDS workspace、run/epoch、启动参数、6 条 request envelopes 与公开输入对应关系，要求 native DDS observer 的 `commands` 为空。两份证据中的 installed control source 哈希表必须一致并包含 `session.py`。固件路径、commit、二进制、Agent、模型身份及 AP 候选源码与旧证据一致；模型库使用新结果记录的构建路径，内容哈希仍固定。

随后对当前资源执行原有固件可执行性、Agent、模型库/归档/wrapper/loader/build.json、AP 源码和补丁检查。新安装的全部 8 个 control Python 文件逐项匹配飞行证据；文件集合也必须相等，并核对该 workspace 中的 control 源码副本。不会拿持续开发中的仓库 control 源码冒充已飞候选。

## 安装内容与 overlay

新 `prometheus_control`、`prometheus_msgs`、`wksim_msgs` 安装前缀保存完整内容快照：对排序后的相对文件名、NUL、文件 SHA256、换行再求 SHA256。覆盖 Python、schema（含 action）、生成接口、ELF、头文件、package.xml 和安装 hook；排除 `__pycache__` 与 `.pyc` 缓存。原 native message packages 延续已有内容快照算法，没有减项。

Python module origin、已导入子模块来源、ament 首个包前缀和 `LD_LIBRARY_PATH` 首个同名共享库都必须匹配所选安装。目录名称相似不构成准入依据；新增/遗漏/变更源码、内容变更、未知或未飞候选、缺失或篡改任一证据、协议与 workspace 交叉、错误或缺失 overlay 均拒绝，不自动回退。

安装快照是 2026-09-05 对当前已安装内容的只读检查，**不证明旧飞行当时已经全量 hash 所有运行库/schema**。新飞行结果直接记录的是全部 8 个 installed control Python 源码哈希。原 Prometheus 43 msg、3 srv、1 action 共 47 个 schema 与旧安装内容相同；新增的 3 个接口属于 `wksim_msgs`：`CommandRequest`、`SetupRequest`、`SessionState`。action 自动生成的消息不计入原 47 个接口。

## 运行只读验证

在 WSL Ubuntu-22.04 中进入本项目，先选择新 overlay：

```bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/setup.bash
source /root/wksim-ros2-2egljG/install/setup.bash
WKSIM_CONTROL_PROFILE_LIVE_RESOURCES=1 python3 -B -m unittest validation.test_wksim_control_profile validation.test_wksim_preflight -v
```

新增测试的实际候选正向检查与故障注入使用只读资源、内存替换；拦截写入及创建子进程。`-B` 避免 Python 写入缓存。未设置开关时，新增测试仍检查固定基线、两份真实证据及内存中构造的证据错误，跳过 Linux 安装资源验证。已有 preflight 测试保留原样，其中两项旧资源测试需要其独立开关，默认跳过。

2026-09-05 执行上述命令：22 项测试中 20 项通过、2 项旧资源测试跳过，退出码 0；新增 14 项全部执行通过（含各故障注入子用例）。两份新飞行证据 SHA 未变，历史 `baselines` 规范化 SHA256 仍为 `9994bef882fe47519001a44387351354d0e5f30ab3fe6aba0c060031f6467706`。

直接检查两栈（配置只在内存中补入 profile，不修改 examples）：

```bash
python3 -B - <<'PY'
from Simulator.wksim_runtime.config import load_config
from Simulator.wksim_runtime.preflight import INDEX, preflight
for stack in ('px4', 'arducopter'):
    config = load_config(INDEX.parent / 'examples' / f'{stack}.json')
    config.update(control_protocol='session_v1',
                  prometheus_workspace='/root/wksim-ros2-2egljG')
    result = preflight(config)
    print(stack, result['ok'], result['reasons'], result['children_created'])
    assert result['ok'], result['reasons']
PY
```

旧候选需在新 shell 中 source `/root/wksim-ros2-0viK3f/install/setup.bash`，使用原 examples 的 workspace，缺省或显式 `legacy_v1`。本次两栈四种组合均通过，`children_created=0`。

拒绝原因通过 `reasons` 返回：配置错误为 `invalid_config`，资源/内容不符为 `candidate_not_pinned`、`identity_mismatch`、`message_identity_mismatch` 等，overlay 不符为 `mixed_overlay`；新 profile 证据验证失败或不可读归入 `preflight_unavailable`，附具体错误。所有失败均返回 `ok=false`。

验收范围仍是六条公开输入、独立 SITL 模型与地面 DDS 重连。此检查不证明空中失联恢复、联合场景共享时钟、控制进程重启后的任务流程或完整产品通过；只反映检查时的内容及环境，不能保证检查之后资源未被其他进程修改。
