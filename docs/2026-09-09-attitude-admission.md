# #34 独立姿态候选只读准入

2026-09-09。新增 `tools/attitude_candidate.py`，提供 `admit(stack, run_id)`；stack 仅 `px4`、`arducopter`。真实 WSL Ubuntu 22.04 验证覆盖未 source 候选环境的 PX4 准入，以及 source 候选之后的 AP 准入，均返回 `ok=true`。准入期间没有启动 FC、模型、ROS 节点、GCS，也没有构建、提交或 Issue 操作。

本次委派会话 `01a0840d-7e6d-7791-a922-51c0950b33dd` 经主代理核验为 `gpt-6-astra/high` 后收到 RELEASE；无嵌套代理。按 ponytail 技能复用既有完整源码快照、mixed/PV 溯源和固定共享资源检查。所有新实现均在 tools/validation，生产代码、默认 profile、旧安装和已有 pins 未改动。

## 明确绑定

| 项目 | 路径 / SHA256 |
| --- | --- |
| 原生 AP | `/root/wksim-ap-attitude-hejigg76/attitude-build.json` / `bd8257094e6ab21034e7e6982835d833441d22582c0324b22fe8aa13fa0a4fe4` |
| 主机 Control | `/root/wksim-attitude-control-x3_2v4wb/attitude-control-build.json` / `95078a02b863b0307832ae9eb8aad6025a6dd0a88b34506983ae5e3cd43cf8d0` |
| 离线验证 | `attitude-control-verification.json` / `4ed5331deac4a20b2fac59d0545df8e5de10ecf6535b4b6d485f94fea30c662c` |
| AP 消息 overlay | `/root/wksim-ap-attitude-msgs-qOmnF9fT`；完整文件集由 AP 构建清单封存 |
| 本次补充 Control 安装 seal | 52 个文件的排序 JSON 映射 SHA256 `e92ff7938ddbe7c41c19a6ce1774bdb99e5ec493c50dac0f71cb0891ba8b7416` |
| reviewed stage 清单 | `work/ap-attitude-stage-20260909/stage-manifest.json` / `9d838af80767b8617e3c36003175b9595863efd67c15d47671abe822946fe213` |
| 飞行预算 | `work/ap-attitude-stage-20260909/flight-budget.json` / `9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f` |

AP 检查包括完整 Git/submodule 源快照、精确 0006 补丁、mixed→PV→旧 AP 来源、修改前后 reviewed 文件集合、全部生成 DDS 文件、整个新消息 overlay、构建与 codec 产物、退出值、候选 hwdef 及生成的 attitude opt-in。旧 mixed 基线和候选实际二进制均重算 SHA。新消息清单原本包含 12 个构建时 pycache，准入按原 seal 包含它们；验证进程统一 `-B` 禁止更新缓存。

Control 检查封存 OEv 源包/安装包及构建输入，匹配候选整个包的前后哈希，要求只有 reviewed stage 的四个文件改变。候选安装的全部 9 个 Python 模块须与候选树一致，两份 retained reverse-proof 整包须恢复 OEv，已封存 21 项测试结果及测试来源/原生 guard 来源/日志须全部相符。额外的 52 文件安装树 seal 将生成的入口、ament 和 setup 脚本也绑定到本次独立候选。

这里没有要求“候选源码等于当前仓库源码”。准入关系明确为 sealed OEv + 精确 reviewed patch = 指定新候选；当前仓库相关验证工具及运行依赖另记 SHA。准入开始到完成之间还复核已加载的项目 Python 依赖没有改变。

## 环境和返回值

旧 `joint_quad_dds_v1` 的 `_fixed_resources` 在清空继承 PYTHONPATH/AMENT/链接环境的独立 subprocess 中，按其原 setup_files 真正运行。它仍检查封存旧 AP/PX4、旧 Control、模型库/源码/归档、固定消息、DDS agents 和已封存飞行证据。没有读取失败生产 preflight 后放行，没有改写旧飞行配置，没有调用生产 preflight。旧 profile 仅作为固定共享资源描述符。

候选另起干净的只读导入 subprocess，按以下顺序 source：Humble → DDS/PX4 消息 → MUlZd0 common 消息 → 新 AP attitude 消息 → x3_2v4wb Control。检查实际 Python 模块、ament 前缀和动态库搜索顺序，并通过真实生成类型的序列化往返加载 type support。若调用进程已经 source 候选 Control，则同样检查调用进程自身的导入；也提供 `check_active_overlays()` 供运行器显式调用。

`admit` 返回：

- `ok/reasons`：失败时保留空 config/setup_files，禁止部分成功被运行器使用。
- `config`：严格基础配置，明确 candidate 路径、`session_v1` 和 `attitude_thrust_v1`；不带生产 `runtime_profile`。
- `library/setup_files`：固定模型库和上述有序 overlay 列表。
- `identities.ap/px4`：实际磁盘二进制路径和 SHA；`model_build`：固定模型构建身份；`control`：源/安装文件、构建及验证身份；`native`：原生/生成/overlay/来源 seal。
- `identities.baseline`：真实固定资源检查结果与 agents；`candidate_imports/active_process_imports`：子进程和当前进程导入证据；预算、stage、setup 和项目 Python 依赖 SHA 分别记录。

`children_created=0` 表示未创建运行节点，检查期间确有 Python/bash/Git 只读验证子进程。`production_admitted=false`、`flown=false` 保留实验边界；磁盘身份不是实际飞行进程已加载身份。运行器仍需独占资源、实际 loaded-binary 证明、GUID_OPTIONS/GUID_TIMEOUT 读回和冻结预算规定的标定/阶跃/恢复/真值验收。

## 验证

`python3 -B validation/test_attitude_candidate.py`：9 项通过。覆盖非法 stack/run_id 的早拒绝、基础配置显式候选、错误 SHA/重复键/非有限 JSON、完整文件集合/篡改/路径逃逸、reviewed patch 以外改动、cache/内部 symlink 边界、干净 baseline subprocess 和失败拒绝、资源失败不得产出配置、错误 active overlay 的无导入拒绝。

实际资源验证使用 `python3 -B tools/attitude_candidate.py --stack px4 --run-id attitude-admission-check` 等入口；AP 则在上述五个 setup_files 已 source 的环境中调用 `admit('arducopter', ...)`，确认 `active_process_imports` 非空，9 个 Control 模块和新 AP 类型路径均正确。开发时首次 AP overlay 集合比对因漏含已封存 pycache 而拒绝；改为按原清单包含 cache 后通过。没有放宽 checksum 或跳过文件。一次外层 PowerShell 命令引号错误在 Python 解析时退出，没有进入准入或启动节点。
