# #25 独立 Hex X 源模板模型候选

2026-09-09 JST。新增 [build_hex_model_candidate.py](../tools/build_hex_model_candidate.py) 提供固定 Hex X 配置的保存、导入校验、独立构建与静态响应验证；**7 项纯检查和预冻结协议的 18 项 native 静态检查通过**。候选继承固定 Quad X 生成源的质量、惯量、电机、旋翼、阻力、环境和初态；只把唯一的 `ModelParam_uavType` initializer 从 3 改为 5。它不是任何真实六旋翼的标定结果，也不是六旋翼双栈飞行或 UE 显示交付。

生产 `model.py`、`model.cpp`、`model_parameters.py`、默认来源 pin、飞控/混控器/适配器和 UE 均不修改。没有引入通用组件框架。工具复用现有严格 JSON/哈希与 native 16 输入、120 输出、1 ms ABI。

## 来源与不可变配置

来源和六电机顺序依据 [静态接缝报告](2026-09-09-hex-model-seam.md)。构建前再次校验 ZIP SHA256 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`、全部五个原始成员哈希和原包装器 SHA256 `3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c`；实读源表 `d[4]=6`、列优先索引和六个输入/RPM 映射。22 个具名参数的原始 initializer 都必须唯一且等于模板值。最终源字节仅一处 ASCII `3→5`。

配置 schema 为 `wksim.hex-source-template.v1`，默认名字 `hex-x-source-template`。配置保存完整 22 项值和单位、几何、来源、1 ms 运行边界、名称及其 canonical SHA256 身份。唯一允许的用户差异是合法配置名称，名称也参与身份；质量 `1.515 kg`、惯量对角 `[0.0211,0.0219,0.0366] kg·m²`、半径 `0.225 m` 和其余动力参数全部不可变。导入拒绝重复 JSON 键、非有限数、额外字段、修改参数/映射/pin/身份。保存不覆盖已有文件。

`ModelParam_3DType` 仍是源值 3；配置中的 `hex_visual_3DType=null` 明确表示未知。不能把源 3DType 当成已验证的六旋翼显示枚举。

构建产物在 Linux 用户的 `~/wksim-hex-candidate-private/build-*` 独立持久目录中产生：原始 cpp、参数化 cpp、原始四个头、独立 wrapper、具名配置、build-request/build manifest、编译日志和新 `.so`。目录以仅用户访问的权限创建。manifest 保存原始/修改源码、包装器、配置、库的 SHA256，编译器、命令和构建器身份。厂商生成源码不进入仓库或公开证据目录。

加载前验证全部产物哈希、精确参数化 recipe、独立 wrapper recipe 与配置身份，再通过独立 C 导出读取所有 22 项实际 generated static 参数。读回发生在 `wk_model_create` / `initialize()` 之前；native create 内也逐项比较冻结值。错误配置、错误库名/哈希和错误 readback 被拒绝。native 与 Python 同时拒绝 6..15 任一非零输入。每个进程只允许一个载具生命周期；关闭后再次创建也必须换新进程。

## 预先冻结的验证协议

[protocol.json](../validation/hex-model-candidate-20260909/protocol.json) 在首次 native 实验前生成，SHA256 `1a3c2c2e14978068817a08e7a124d60e94332a7c095bf730a62b91292f2d9f6b`。协议固定九个串行新进程：零输入、六路等值、六个单电机扰动、等值冷重启。每个进程 200 或 210 个 1 ms tick，无飞控、ROS、网络或 UE。

六路等值输入为 0.6，预热 200 ms 后分别将一个电机增加 0.01，保持 10 ms。对原始 `VehileInfo60d[27:30]` 机体角速率做时间差分并减去等值基线，以 FRD 角加速度核对源公式：roll=`−R·sin(angle)·Ct·ω²`，pitch=`R·cos(angle)·Ct·ω²`，yaw=`−Cm·ω²·source_spin`。

| 输入下标 | 角度 ° | 源旋向 | 预声明 roll / pitch / yaw 响应符号 |
| ---: | ---: | ---: | --- |
| 0 | 90 | +1 | − / 0 / − |
| 1 | 270 | −1 | + / 0 / + |
| 2 | 330 | +1 | + / + / − |
| 3 | 150 | −1 | − / − / + |
| 4 | 30 | −1 | − / + / + |
| 5 | 210 | +1 | + / − / − |

协议阈值包含：等值六路 RPM 均超过 100、路间差不超过 `1e−8`；单路扰动 RPM 增量超过 0.1、其他路增量绝对值不超过 `1e−8`；非零角加速度符号乘积超过 `1e−6 rad/s²`，名义零轴不超过该电机最大轴响应的 2%。这些是短时开环方向检查，不是气动力精度阈值或飞行包线。静止/等值角速率、未用 native RPM 输出 22:24、每进程生命周期拒绝和冷重启逐 tick 全 120 输出一致性也单独检查。完整命令、120 输出、实际参数回读、PID 和身份均保留。

## 使用

Ubuntu-22.04 WSL 中，以本仓库为当前目录：

```bash
python3 tools/build_hex_model_candidate.py save --output "$HOME/my-hex-template.json"
python3 tools/build_hex_model_candidate.py protocol --output "$HOME/my-hex-protocol.json"
hex_library=$(python3 tools/build_hex_model_candidate.py build --config "$HOME/my-hex-template.json")
python3 tools/build_hex_model_candidate.py run \
  --library "$hex_library" \
  --config "$(dirname "$hex_library")/config.json" \
  --protocol "$HOME/my-hex-protocol.json" \
  --output "$HOME/hex-static-new-run"
```

`run` 要求协议内冻结的默认具名配置；其他名称可以独立构建，但不得冒用该协议身份。结果目录必须不存在，失败保留原始轨迹和日志；不会自动放宽协议。此入口不接入默认生产模型。

## 验证状态

`python validation/test_hex_model_candidate.py -v`：7 项纯检查通过，含本机精确 ZIP 的实际单字节参数化、不可变配置导入/拒绝、初始化前 guard、未用/非有限/越界输入、错误配置/库在加载前拒绝以及源推导符号。测试不编译或加载 native 模型。

在静态协议冻结并由主代理审阅后，执行一次轻量 native 构建和九个串行进程，工具输出报告 18 项检查通过。但随后的归档调用发现 `/tmp/wksim-model-_5x06vco`、`/tmp/wksim-hex-static-20260909` 和配置路径均已消失，未能保留其原始轨迹。没有前后 boot-id 对照，不能确认 WSL 生命周期或其他原因；首轮工具摘要仅为诊断历史，**不作为完整验收证据**。见[首次证据丢失记录](../validation/hex-model-candidate-20260909/first-attempt-evidence-loss.json)。

随后单独放行一次补证：未改协议 SHA/阈值/输入/物理/包装器，工具改用 Linux 持久私有构建目录，并增加各 subprocess 实际退出码/耗时记录；同一调用内直接把数值轨迹和构建元数据归档至 [run2](../validation/hex-model-candidate-20260909/run2/evidence-index.json)。第二轮 18/18 检查通过，无实验阈值调整。编译器为 `g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0`，9 个串行 PID 为 685–693、退出码全部 0，累计 worker 墙钟时间 `0.917083227 s`。总计两次构建、18 个短 native worker；未启动 FC/ROS/UE，结束后资源释放。

| 第二轮产物 | 身份 |
| --- | --- |
| 私有库 | `/root/wksim-hex-candidate-private/build-ihnane6f/libwksim_hex_candidate.so` |
| 库 SHA256 | `b10ef333129b44ce41d2d8d944a1e3d1161db9201bb1aea9eca88e726a5a7c9c` |
| 配置身份 | `sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a` |
| 参数化 cpp SHA256 | `9c5c7537d400adbd8bf759089d941d43322d36b5178046542feda0d80a6c8bc8` |
| 独立 wrapper SHA256 | `31c56a35ca8ae2a9d03e0e36b83083e3970578ea108bcae8d80f14c448d08161` |
| 实际构建器 SHA256 | `865cd979f5921019c13950a220d82756557190be57520e1e42f92b378a7595e6` |
| summary.json SHA256 | `9cbe31f0acc8a4315ddeb6eaaf0828021e74a2a5d243fb58094ae8a1b1196753` |

原始 JSON 数值轨迹及元数据约 4.9 MB，未包含生成源码。初始化前实际读回 `uavType=5`、mass=`1.515 kg`、源 3DType=3 和全部固定参数；六路等值 RPM 都是 `5042.61203500094`。每个单路扰动只改变该电机 RPM `+30.019359470426934`，其他五路增量全部 0。各输入对应的差分角加速度为：

| 输入 | roll / pitch / yaw，rad/s²（展示舍入） |
| ---: | --- |
| 0 | `−0.32128924 / +0.00001605 / −0.01362891` |
| 1 | `+0.32128924 / +0.00001605 / +0.01362891` |
| 2 | `+0.16065861 / +0.26807246 / −0.01362893` |
| 3 | `−0.16063081 / −0.26808851 / +0.01362889` |
| 4 | `−0.16065861 / +0.26807246 / +0.01362893` |
| 5 | `+0.16063081 / −0.26808851 / −0.01362889` |

名义零俯仰轴的微小耦合响应满足预声明 2% 阈值，其余轴全部满足方向阈值。9 个进程每次都分别拒绝 10 个未用输入通道（Python/native）及第二次创建/关闭后重建；冷启动重复全 120 输出逐 tick 完全一致。完整值、负例和实际退出记录见 [summary](../validation/hex-model-candidate-20260909/run2/summary.json)、[process-completion](../validation/hex-model-candidate-20260909/run2/process-completion.json) 和各命名轨迹。

本轮只通过固定源模板的六通道 native 静态响应。双栈闭环、UE 六旋翼表达、真实机架标定、R1/G6 和 #25 完整验收仍不在该结论内。
