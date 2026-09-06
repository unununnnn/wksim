# Ubuntu 22.04：ROS 2 Humble / Micro XRCE-DDS 2.x 最小引导调研

调查日期：2026-09-05（Asia/Tokyo）。目标目录：`C:/Users/PC/Documents/odid编译/wksim`；目标发行版：WSL `Ubuntu-22.04`。

本次仅执行本机只读检查、官方资料与包索引读取、`apt-get -s` 模拟；只以 `apply_patch` 新增本文件。未执行 bootstrap、apt 更新/安装、构建、飞控或 Agent 启动，未读取授权密钥，未提交、推送或修改 Issue。research 技能要求后台 agent；当前会话没有子代理工具，因此本文件由本调研任务直接完成，不表示主任务的 ArduCopter 实现已完成。[research 技能][SKILL]

收束时的主线状态：主代理已通报 AP/PX4 独立模型均通过起飞、悬停、航点、降落，接下来补齐 ROS2/DDS 依赖。本研究未独立复核主线运行，主线证据另见[物理集成报告](2026-09-05_sitl-physics-report.md)。本有界研究未安装软件；下文二进制只读快照不能替代未来DDS构建的配置检查。

## 可以立即交给实现任务的结论

1. **ROS/DDS 补齐可沿用主线已通过的物理闭环。** 本次检查的 ArduCopter 4.7.0 SITL ELF 包含 `SITL::JSON::recv_fdm/output_servos/update`；官方将 JSON 定义为通过 UDP 对接外部物理后端的接口。现有 `pymavlink 2.4.49` 也可复用。本调研自身证明的是这些静态复用条件；主线飞行通过情况来自上面的用户进度通知。[本机 L2、L3](#l2-飞控与-python-复用证据)、[官方 JSON 接口][APJSON]
2. **Humble 优先使用 Agent 2.4.2，并链接 Humble 自带的 Fast DDS / Fast CDR。** 当前官方 Jammy amd64 索引为 Fast DDS **2.6.12**、Fast CDR **1.0.29**；PX4 v1.17 文档将 Humble 对应到 Agent 2.4.2。不要直接把独立构建示例中的 2.4.3 当作 Humble 库版本组合。[官方包索引][INDEX]、[PX4 版本表][PXAGENT]
3. **保留现有脚本的无 GUI 路线，分阶段补齐。** `ros-humble-ros-base`、`ros-humble-rmw-fastrtps-cpp`、`python3-colcon-common-extensions` 可作为实用起点；双原生 DDS 准备再加 `ros-humble-geographic-msgs`、`ros-humble-micro-ros-msgs`、`libspdlog-dev`。Asio 只在重建 Fast DDS 的独立源码分支需要显式补装，不是推荐的 Humble 二进制库复用分支的直接依赖。[脚本][SCRIPT]、[ROS 安装文档源码][ROSINSTALL]、[包索引][INDEX]、[Agent 构建定义][A242]、[Fast DDS 依赖][FASTINSTALL]
4. **先分别保留 PX4 standalone Agent 与 AP micro-ROS Agent 入口。** AP 官方使用 micro-ROS Agent；其 Humble 分支内部选择 Micro XRCE-DDS Agent 2.4.2 并使用系统 DDS 库。两者可以复用同一份隔离构建的 2.4.2 核心，但不能仅凭核心版本相同就宣布入口、图发现或服务行为等价。[AP 安装说明][APINSTALL]、[micro-ROS SuperBuild][MRSUPER]、[micro-ROS 图管理源码][MRGRAPH]
5. **本次检查的旧 AP 二进制不能作为 AP_DDS 成品使用。** 其生成配置明确是 `AP_DDS_ENABLED=0`，而检查的 PX4 产物已编入 uXRCE-DDS。若继续使用这份 AP 产物，则需单独构建 DDS；主线新产物是否已启用 DDS，本调研未复核。[本机 L2](#l2-飞控与-python-复用证据)、[AP DDS 构建说明][APREADME]

## 本机状态与已有脚本核对

| 项目 | 2026-09-05 只读结果 | 影响 / 一手证据 |
| --- | --- | --- |
| 目标系统 | Ubuntu 22.04.5 LTS / Jammy，x86_64，WSL2；默认用户 root，`LANG=C.UTF-8` | 符合 Humble Jammy 二进制路线；Universe 已启用，无需重复加源或改 locale。[L1](#l1-系统与-apt-只读记录)、[ROS 文档][ROSINSTALL] |
| ROS / 构建前端 | `/opt/ros` 不存在；没有 `ros2`、`colcon`、`rosdep`、`MicroXRCEAgent` 的 PATH 命中；未安装 `ros2-apt-source` | 当前 apt 模拟找不到脚本中的三个 ROS/colcon 包，先配置官方源才可能得到有效安装计划。[L1](#l1-系统与-apt-只读记录) |
| 系统编译工具 | build-essential 12.9ubuntu3、GCC/G++ 11.4.0、CMake 3.22.1、Ninja 1.10.1、Git 2.34.1、Python 3.10、pip、curl、wget、patch、pkg-config 已有 | 满足 Agent 的 CMake ≥3.16 与 C/C++ 工具要求，不必重装整套 AP/PX4 开发环境。[L1](#l1-系统与-apt-只读记录)、[Agent CMake][A242] |
| 已有开发库 | `libssl-dev 3.0.2-0ubuntu1.29`、`libtinyxml2-dev 9.0.0+dfsg-3`、python3-dev、setuptools | 可复用；Fast DDS 包要求的 `libstdc++6 >=12` 也已由本机 12.3.0 满足，GCC 编译器版本与运行库版本需区分。[L1](#l1-系统与-apt-只读记录)、[包索引][INDEX] |
| 缺口 | 未安装 libasio-dev、libspdlog-dev；未发现 Java/javac、Gen、Agent 的 PATH 命中或限定目录命中 | spdlog 用于下文免 superbuild 的 Agent 构建；Java/Gen 仅在 AP_DDS 重编阶段补充。[L1](#l1-系统与-apt-只读记录)、[L4](#l4-只读模拟与包体量)、[AP 安装说明][APINSTALL] |
| apt 健康 | `apt-mark showhold`、`dpkg --audit` 均无输出；systemd/udev/systemd-sysv 均为 249.11-0ubuntu3.22 | 没有发现冻结包或 dpkg 未完成状态；仍需审核未来精确安装模拟，不能把此结果理解为任意安装都不会变更系统包。[L1](#l1-系统与-apt-只读记录)、[apt 手册][APT] |
| 原脚本 | 20 行，`bash -n` 成功；要求 Ubuntu22.04/root，有失败即退出、下载超时/重试、`--no-remove --no-install-recommends` | 语法检查未执行脚本；脚本会实际安装源包、更新 apt、非交互安装三个根包，不能作为只读探针调用。[脚本][SCRIPT]、[L1](#l1-系统与-apt-只读记录) |

脚本内 URL 与官方 release asset 完全相符；本次 GitHub 官方 API 的 `latest` 仍为 **1.2.0**，发布于 **2026-04-23T03:22:14Z**。Jammy 源包大小 **4,424 bytes**，官方 API 提供 SHA-256：`767884cf4ed03116b9d64438930a832ed854147ae435279a7924dfdf60f94433`。本次核对的是发布元数据，未下载并校验该 `.deb` 的实际字节。[Release][RELEASE]、[官方 Release API][RELEASEAPI]

原脚本不足以完成原生 DDS：不构建 Agent/消息/AP_DDS，不校验下载文件的 SHA-256，不显示安装前模拟，也不固定 ROS 包的确切版本；只检测源包是否安装，没有核验已装源包版本或源是否被禁用。它也没有添加 Universe 或检查 locale，不过这两项在本机已经满足。`--no-remove` 遇到删除方案会中止，但不能阻止依赖升级；建议按下面分步命令执行并保存未来安装版本清单。本次不改脚本。[脚本][SCRIPT]、[apt 手册][APT]、[源配置文档][ROSSOURCE]、[L1](#l1-系统与-apt-只读记录)

## 最小必要包与体量估算

建议区分以下三层；“根包”指显式传给 apt 的名字，不等于最终新增包数。[官方包索引][INDEX]、[ros_core 定义][CORE]、[ros_base 定义][BASE]

| 层级 | 显式根包 / 源码 | 用途 |
| --- | --- | --- |
| 当前脚本：实用无 GUI 起点 | `ros-humble-ros-base ros-humble-rmw-fastrtps-cpp python3-colcon-common-extensions` | 包括核心通信、CLI、消息生成，并比 ros_core 增加 rosbag2、geometry2、URDF 等；适合后续日志验收。[BASE]、[CORE]、[SCRIPT] |
| 本文推荐：双 DDS 准备 | 上面三个 + `ros-humble-geographic-msgs ros-humble-micro-ros-msgs libspdlog-dev` | AP 地理消息、micro-ROS wrapper 消息依赖，以及系统 spdlog；AP/PX4 自定义消息仍需对应源码构建。[INDEX]、[MRPACKAGE]、[A242]、[APINTERFACES] |
| 更小候选：先只验证消息/通信 | `ros-humble-ros-core ros-humble-rmw-fastrtps-cpp python3-colcon-ros python3-colcon-bash python3-colcon-package-selection ros-humble-tf2-msgs ros-humble-geographic-msgs ros-humble-micro-ros-msgs`，另加 `libspdlog-dev` | 裁掉 ros_base 的额外功能和多数 colcon 扩展；仍保留本文构建命令的 Bash 环境及包选择插件。后续需要 bag/tf2 工具时应显式补包；这是裁剪建议，未实装验证。[INDEX]、[CORE]、[BASE] |
| AP_DDS 重编阶段 | `default-jdk-headless`；ArduPilot fork 的 Gen `v4.7.0`；现有 AP 源码的隔离副本 | 不属于仅构建 Agent 的依赖。Gen 的 Gradle 项目包含 Java 编译任务，选择带 javac 的 headless JDK；本机候选为 OpenJDK11。[APINSTALL]、[GENBUILD]、[GENWRAPPER]、[L4](#l4-只读模拟与包体量) |

推荐路线无需显式安装 `ros-humble-desktop`、RViz、Gazebo、MAVROS、全套 `ros-dev-tools` 或源码版 Fast DDS；这是根据此次任务边界和上述依赖作出的裁剪，不表示这些组件在其他任务中没有用途。`rosdep`/`vcs` 也不是下文显式 clone/CMake/colcon 命令的前置条件；以后执行 AP 官方完整工作区流程才按该流程补齐。[ROSINSTALL]、[A242]、[APINSTALL]、[项目任务边界][WAYFINDER]

本次读取官方 `Packages.gz` 到内存，按 `Depends/Pre-Depends` 递归统计 ROS 仓库中的包：OR 候选优先选该索引内的包，不解析版本约束、Provides 或已安装状态。**以下是静态索引体量，不是实际 apt 安装计划，也不是完整系统新增体积。** Ubuntu 侧依赖、已有包复用、索引下载、源码和构建目录均另计；本次没有将 ROS 索引写入 apt。[官方索引][INDEX]、[计算记录 L4](#l4-只读模拟与包体量)

| 根包集合 | ROS 仓库内闭包 | `.deb` 合计 | Installed-Size 合计 | 未展开的 Ubuntu 依赖名 |
| --- | ---: | ---: | ---: | ---: |
| 原脚本三个根包 | 216 | 12.94 MiB | 86.24 MiB | 62 |
| 推荐路线的五个 ROS/colcon 根包，不含系统 spdlog | 218 | 13.21 MiB | 90.09 MiB | 62 |
| 上述更小候选的八个 ROS/colcon 根包 | 165 | 10.65 MiB | 76.25 MiB | 46 |

系统补包的真实模拟更确定：`libasio-dev` 为 **1 个新增包**、352,164 bytes 下载、4,510 KiB 安装；`libspdlog-dev` 带来 **5 个新增包**，合计 974,584 bytes / 4,410 KiB，包含 catch2、libfmt-dev、libfmt8、libspdlog1。二者一起为 6 个包；`default-jdk-headless` 为 7 个包。各次模拟均为 0 升级、0 删除；这些数字基于本次现有 apt 缓存，正式执行须重新模拟。[L4](#l4-只读模拟与包体量)

## 安全 apt 模拟与实际执行命令

下面是提供给实现任务的执行建议，**本调研未执行其中的写操作**。先在 PowerShell 进入正确发行版；后续 Bash 段按顺序运行。当前默认 root，命令仍保留 `sudo` 以便普通用户使用。[本机发行版记录 L1](#l1-系统与-apt-只读记录)

```powershell
wsl -d Ubuntu-22.04
```

### 1. 现在即可执行的只读预检

模拟不下载、不安装、不验证 maintainer scripts 的实际效果；它基于当时的 dpkg/apt 状态且不加锁。加源前 ROS 包找不到是预期结果，不能把失败模拟当成安装计划。[apt 手册][APT]、[本次结果 L4](#l4-只读模拟与包体量)

```bash
cat /etc/os-release
dpkg --print-architecture
locale
test ! -d /opt/ros && printf '%s\n' '/opt/ros absent'
dpkg --audit
apt-mark showhold
apt-cache policy systemd udev systemd-sysv libstdc++6
apt-cache policy ros2-apt-source ros-humble-ros-base
apt-get -s -V -o Debug::NoLocking=1 --no-remove --no-install-recommends \
  install libspdlog-dev
apt-get -s -V -o Debug::NoLocking=1 --no-remove --no-install-recommends \
  install ros-humble-ros-base ros-humble-rmw-fastrtps-cpp \
  python3-colcon-common-extensions
```

### 2. 安装阶段才执行：校验并配置官方 ROS 源

以下会下载文件并安装 `ros2-apt-source`，改变 apt 配置；它不是只读检查。使用脚本已固定的、此次核实仍存在的 release，并先校验官方 digest。安装 `.deb` 本身与 `apt-get update` 都是实际写操作；`apt-get -s` 只覆盖标注为模拟的那一行。[官方源配置][ROSSOURCE]、[Release API][RELEASEAPI]、[apt 手册][APT]

```bash
set -e
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 22.04
test "$(dpkg --print-architecture)" = amd64
ros_bootstrap_tmp=$(mktemp -d /tmp/wksim-ros-source.XXXXXX)
ros_source_deb="$ros_bootstrap_tmp/ros2-apt-source_1.2.0.jammy_all.deb"
curl --fail --location --retry 2 --connect-timeout 15 --max-time 120 \
  https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.2.0/ros2-apt-source_1.2.0.jammy_all.deb \
  --output "$ros_source_deb"
printf '%s  %s\n' \
  767884cf4ed03116b9d64438930a832ed854147ae435279a7924dfdf60f94433 \
  "$ros_source_deb" | sha256sum --check --strict
dpkg-deb --field "$ros_source_deb" Package Version Architecture Depends
sudo apt-get -s -V --no-remove --no-install-recommends install "$ros_source_deb"
```

审阅上面的本地源包模拟后，执行源安装和索引更新；保留 apt 默认签名验证。[APT]、[ROSSOURCE]

```bash
sudo apt-get -V --no-remove --no-install-recommends install "$ros_source_deb"
sudo apt-get -o Acquire::Retries=2 \
  -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 \
  -o APT::Update::Error-Mode=any update
```

### 3. 同一组根包先模拟、后实际安装

检查模拟输出的新增包、升级、降级、`Remv` 和破损依赖。ROS 官方特别提示早期 Jammy 的 systemd/udev 组合可能引发关键包删除；本机已是较新的 249.11 更新，但实际依赖方案仍以模拟为准。这里不给全系统 `upgrade/dist-upgrade`，若出现意外核心包变动，先查明具体版本约束。[ROS 安装警告][ROSINSTALL]、[APT]、[L1](#l1-系统与-apt-只读记录)

```bash
ros_targets=(
  ros-humble-ros-base
  ros-humble-rmw-fastrtps-cpp
  python3-colcon-common-extensions
  ros-humble-geographic-msgs
  ros-humble-micro-ros-msgs
  libspdlog-dev
)
apt-cache policy "${ros_targets[@]}" ros-humble-fastrtps ros-humble-fastcdr
sudo apt-get -s -V --no-remove --no-install-recommends install "${ros_targets[@]}"
```

实际安装沿用同一数组，保留交互确认；`--no-remove` 对删除方案直接拒绝，不加入允许删除、降级或未认证包的选项。[APT]

```bash
sudo apt-get -V --no-remove --no-install-recommends install "${ros_targets[@]}"
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 pkg prefix rclcpp
ros2 pkg prefix rmw_fastrtps_cpp
ros2 pkg prefix geographic_msgs
ros2 pkg prefix micro_ros_msgs
dpkg-query -W ros2-apt-source ros-humble-ros-base \
  ros-humble-rmw-fastrtps-cpp ros-humble-fastrtps ros-humble-fastcdr \
  python3-colcon-common-extensions libspdlog-dev
```

这些查询只验收包与路径；不能代替 DDS 通信、服务、重连或真实飞行闭环验收。[ROSINSTALL]、[项目验收边界][WAYFINDER]

## Agent 版本、构建与 DDS 一致性

| 组件 | 此次固定版本 / SHA | 原生 DDS 含义 |
| --- | --- | --- |
| Humble apt 库 | Fast DDS `2.6.12-1jammy.20260723.233918`；Fast CDR `1.0.29-1jammy.20260226.010952`；RMW Fast RTPS C++ `6.2.10-1jammy.20260724.002510` | 以安装后的 dpkg 版本复核；本文索引快照不保证未来版本不变。[INDEX] |
| Micro XRCE-DDS Agent | `v2.4.2` → `57d086216d01ec43121845d385894a25987f8a2c` | `USE_SYSTEM` 开关允许 Fast DDS major 2 / Fast CDR major 1；适合复用 Humble。[A242]、[Agent tag API][A242REF] |
| 2.4.2 默认 superbuild | Fast DDS `2.12.x`、Fast CDR `v1.1.1`、spdlog `v1.9.2` | 即使 Agent tag 固定，默认底层也不等于 Humble；`2.12.x` 还是浮动分支。[A242]、[Agent SuperBuild][A242SUPER] |
| 2.4.3 默认 superbuild | Fast DDS `2.14.x`、Fast CDR `2.2.x`；系统模式也要求 Fast CDR major 2 | 不能直接链接 Humble 的 Fast CDR 1；版本差异不能仅用“都是 Agent 2.x”抹平。[Agent 2.4.3 CMake][A243] |
| AP micro-ROS Agent | `humble` → `c93ee764e0d2ef4907aeb29233c68cb5f4b56976` | 内部 SuperBuild 固定 2.4.2，system Fast DDS/CDR 为 ON，CED/P2P 为 OFF；其 package.xml 的 3.0.6 是 wrapper 自身版本，不是底层 XRCE Agent 3.x。wrapper 另有 ROS graph 管理。[MRSUPER]、[MRPACKAGE]、[MRGRAPH] |
| AP DDS Client | 本机子模块 `97175304425c5bee87c6fddd99de1ef8d0c394dc`，CMake 声明 2.4.1 | 使用 AP 固定的 fork/提交；不能要求 Client 与 Agent 小版本数字完全相同。[L2](#l2-飞控与-python-复用证据)、[AP Client 源码][APCLIENT] |
| PX4 DDS Client | 本机子模块 `711aef423edd1820347b866d1e4164832df35d04`，CMake 声明 2.4.0 | PX4 v1.17 官方使用 Agent 2.4.2 的 ROS/Humble 组合；不能由子模块数字推断 Agent 应降到 2.4.0。[L2](#l2-飞控与-python-复用证据)、[PXAGENT] |

### 推荐构建：复用 Humble 库，固定核心，隔离前缀

以下是完成上面安装后的构建建议，本次未执行。新目录位于 WSL Linux 文件系统；`mktemp` 保证不覆盖现有 AP/PX4 checkout。禁用 superbuild，令缺依赖直接报错；系统 logger 使用刚安装的 spdlog，不额外 clone DDS/CDR/logger。安装范围仅为新目录，不执行 `sudo make install` 或全局 `ldconfig`。[A242]、[Agent 包配置][A242CONFIG]、[AP 关于全局库混用的警告][APINSTALL]

```bash
set -e
source /opt/ros/humble/setup.bash
dds_work=$(mktemp -d /root/wksim-dds-validation.XXXXXX)
mkdir -p "$dds_work/src"
git clone --branch v2.4.2 --depth 1 \
  https://github.com/eProsima/Micro-XRCE-DDS-Agent.git \
  "$dds_work/src/Micro-XRCE-DDS-Agent"
test "$(git -C "$dds_work/src/Micro-XRCE-DDS-Agent" rev-parse HEAD)" = \
  57d086216d01ec43121845d385894a25987f8a2c
cmake -S "$dds_work/src/Micro-XRCE-DDS-Agent" -B "$dds_work/agent-build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/opt/ros/humble \
  -DCMAKE_INSTALL_PREFIX="$dds_work/agent-install" \
  -DUAGENT_SUPERBUILD=OFF \
  -DUAGENT_USE_SYSTEM_FASTDDS=ON \
  -DUAGENT_USE_SYSTEM_FASTCDR=ON \
  -DUAGENT_USE_SYSTEM_LOGGER=ON \
  -DUAGENT_FAST_PROFILE=ON \
  -DUAGENT_CED_PROFILE=OFF \
  -DUAGENT_P2P_PROFILE=OFF \
  -DUAGENT_BUILD_TESTS=OFF \
  -DUAGENT_BUILD_USAGE_EXAMPLES=OFF
cmake --build "$dds_work/agent-build" --parallel 2
cmake --install "$dds_work/agent-build"
env LD_LIBRARY_PATH="$dds_work/agent-install/lib:${LD_LIBRARY_PATH:-}" \
  ldd "$dds_work/agent-install/bin/MicroXRCEAgent"
```

审阅 CMake 的 `fastcdr_DIR/fastrtps_DIR/spdlog_DIR` 和上面的 `ldd`：DDS/CDR 应解析到 Humble，Agent 核心应在专属前缀，不能出现 `not found` 或另一套 DDS 路径。这是 ABI/装载一致性检查，尚不能证明线上的 DDS QoS、类型和服务映射正确。[A242CONFIG]、[APINSTALL]

### AP wrapper 与消息：复用同一个核心，不让 wrapper 再构建另一份

micro-ROS Agent 添加了参与者、writer、reader、requester/replier 的图管理回调，因此保留 AP 官方入口有实际依据。下面显式关闭它自己的 superbuild，并通过 prefix 找到上一步核心；`--base-paths` 只选 AP 消息目录，避免把 AP 的整个测试/SITL workspace 带进来。[MRGRAPH]、[MRCMAKE]、[AP 消息构建定义][APMSG]

```bash
git clone --branch humble \
  https://github.com/micro-ROS/micro-ROS-Agent.git \
  "$dds_work/src/micro-ROS-Agent"
git -C "$dds_work/src/micro-ROS-Agent" checkout --detach \
  c93ee764e0d2ef4907aeb29233c68cb5f4b56976
ap_source=/root/aerotwinsim-ap-native/source/ardupilot
colcon --log-base "$dds_work/colcon-log" build \
  --base-paths "$dds_work/src/micro-ROS-Agent/micro_ros_agent" \
               "$ap_source/Tools/ros2/ardupilot_msgs" \
  --build-base "$dds_work/colcon-build" \
  --install-base "$dds_work/ros-install" \
  --packages-select micro_ros_agent ardupilot_msgs \
  --executor sequential \
  --cmake-args -DBUILD_TESTING=OFF -DMICROROSAGENT_SUPERBUILD=OFF \
  "-DCMAKE_PREFIX_PATH=$dds_work/agent-install;/opt/ros/humble"
source "$dds_work/ros-install/setup.bash"
ros2 pkg prefix micro_ros_agent
ros2 interface show ardupilot_msgs/srv/ArmMotors
env LD_LIBRARY_PATH="$dds_work/agent-install/lib:${LD_LIBRARY_PATH:-}" \
  ldd "$dds_work/ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent"
```

PX4 自定义消息包在此次限定目录搜索中未发现。官方 `PX4/px4_msgs` 的 `release/1.17` 分支此次解析到 `86d8239e962f6939e05c3737784f60c02fa884db`，可作后续 clone 候选；仍需逐项核对本机 PX4 `msg/`、`dds_topics.yaml` 和已编入产物的消息版本，再锁定，不以分支名匹配代替 schema 检验。[L3](#l3-限定搜索与未发现项)、[px4_msgs 官方 ref][PXMSGREF]、[PX4 DDS 说明][PXAGENT]

### AP_DDS 重编是独立缺口

官方 4.7+ 指定 ArduPilot fork 的 Gen **v4.7.0**，不是 Agent 4.7。此 tag 此次解析到 `b8840058b81c87e1169a5a0ed4744d7b3dc99e0b`，使用 Gradle 7.6 wrapper，包含 `compileJava`；本机没有 Java/Gen。未来先模拟/安装 `default-jdk-headless`，再在新目录 clone 固定 Gen、`./gradlew assemble`，临时加入该 shell 的 PATH。只在独立 AP 构建目录执行 `./waf configure --board sitl --enable-DDS` 和 `./waf copter`，核实实际产物配置；不要在当前复用的 AP JSON 构建目录直接重编。上述均未执行。[APINSTALL]、[GENBUILD]、[GENWRAPPER]、[Gen tag API][GENREF]、[APREADME]、[L2](#l2-飞控与-python-复用证据)

AP `Tools/ros2/ros2.repos` 即使位于 4.7.0 checkout，也把 ArduPilot 指向 `master`、Agent 指向 `humble`；盲目 `vcs import` 会重新拉取浮动版本。应保留现有 AP 源码 SHA，只引入缺失依赖，并固定各自提交。[本机 ros2.repos][APREPOS]、[APINSTALL]

未来运行 AP_DDS 时还需确认 `DDS_ENABLE=1`；编译进模块与运行时启用是两个条件。AP 文档中早期 Integration Service 用于服务映射的方案已不再需要，不应因 README 开头的旧架构描述而额外安装它。[APREADME]

### 通信验收前必须分清的风险

| 风险 | 建议与尚未证明的部分 | 一手依据 |
| --- | --- | --- |
| 库 ABI 与 RTPS 协议混为一谈 | 能配置/能动态加载不等于互通；两个独立进程的 DDS 库版本差异也不自动等于不兼容。先统一 Humble 库以减少变量，再实际验证发现、遥测、服务和重连。 | [A242]、[A243]、[APINSTALL] |
| 只固定顶层 tag | 默认 superbuild 的 DDS 分支可浮动；本建议关闭 superbuild，记录 dpkg 版本和 Agent SHA。若必须无 ROS 独立构建，应另锁 Fast DDS/CDR/foonathan/spdlog 的实际提交。 | [A242]、[A242SUPER] |
| 同一 Agent 2.x 被误认为同一入口 | PX4 `MicroXRCEAgent` 与 AP `micro_ros_agent` 保留各自入口；建议未来先独立进程，PX4 8888、AP 2019 分端口，检查占用后再启动。本次没有监听或启动操作。 | [PXAGENT]、[APREADME]、[MRGRAPH] |
| 端口隔离被误认为 ROS 图隔离 | DDS domain、namespace、XRCE 客户端标识以及各 topic/service 的类型都要一致或按实例隔离；改 UDP 端口本身不能隔离同一 DDS domain 的 topic。 | [PXAGENT]、[APREADME]、[MRGRAPH] |
| IDL / QoS / 语义不一致 | 分别固定 px4_msgs 与 AP 消息；按发布端 QoS 验证订阅，分别测 topic 和服务。AP 页面标明存在 experimental 接口及可编译裁剪项；不能把列出话题当成命令完成。 | [PXAGENT]、[APINTERFACES]、[APMSG] |
| ROS 与物理接口混为一谈 | JSON 仍是 AP 与自主物理核心的物理链路；DDS 是任务/状态链路。沿用主线已通过的独立物理闭环接入 DDS，并为新增的 DDS 任务控制单独收集双飞控运行证据。 | [APJSON]、[WAYFINDER]、[本地运行边界][BOUNDARY] |

## 本轮交付与未验证点

- 已交付官方源 URL/digest、Agent 2.4.2 与 AP wrapper/Gen 的版本依据、本机缺口、有限 apt 模拟和可复制的后续命令。报告中的 7 个 Bash 代码块已通过 `bash -n`，引用标签检查通过；原 bootstrap 脚本 SHA-256 未改变。语法检查不代表安装或构建成功。
- **最终 apt 新增包数、总下载量、升级方案未确定。** 本机未配置 ROS 源，ROS 安装模拟只返回找不到包；表内 ROS 体量是官方索引的静态统计，必须在正式加源并更新后重新解算。[L4](#l4-只读模拟与包体量)
- **Agent、wrapper、消息和 AP_DDS 的本文构建命令均未执行。** 指定组合有上游源码和版本表依据，但本机编译、动态库装载、DDS 发现、类型/QoS、服务与重连尚未验证；不能据主线原有飞行通过结果宣布 DDS 已通过。[A242]、[MRSUPER]、[PXAGENT]、[APINTERFACES]
- **主线新产物的 DDS 编译能力未复核。** `AP_DDS_ENABLED=0` 只对应 L2 中列出的旧构建路径与哈希，不外推到其他产物。独立模型飞行通过由用户确认，本报告未读取或重跑该批验收证据。[L2](#l2-飞控与-python-复用证据)

本轮没有其他待执行的研究动作；后续安装、构建与 DDS 联调由主线实施任务接续。

## 可复核的本机一手记录

以下记录均由本次工具直接返回，集中保留在本文件，不另写日志。来源是本机 dpkg 数据库、apt 缓存、源文件、生成配置和 ELF 符号，不以旧调研的结论代替本次检查。

### L1 系统与 apt 只读记录

```text
wsl --list --verbose:
  Ubuntu-22.04       Running  2
  RflySim-20.04      Stopped  2
/etc/os-release: Ubuntu 22.04.5 LTS; VERSION_CODENAME=jammy
uname -m: x86_64
id -un: root
locale: LANG=C.UTF-8
test -d /opt/ros: false
apt sources metadata: Ubuntu jammy/main/universe/updates/security/backports;
                      OSRF gazebo ubuntu-stable jammy; no ROS source
apt-mark showhold: no output
dpkg --audit: no output
systemd / systemd-sysv / udev: 249.11-0ubuntu3.22
libstdc++6: 12.3.0-1ubuntu1~22.04.3
g++: 11.4.0
cmake: 3.22.1-1ubuntu1.22.04.2
build-essential: 12.9ubuntu3
libssl-dev: 3.0.2-0ubuntu1.29
libtinyxml2-dev: 9.0.0+dfsg-3
bash -n tools/bootstrap-humble-validation.sh: exit 0
script SHA-256:
38ebbdaf4893ac8698452129e48feed4aaea0b1302527c3ad4789141e7e258d7
```

核查仅读取 apt 源的 `deb/URIs/Suites/Components` 元数据，没有读取授权密钥或签名私钥。缺包判断结合 `dpkg-query -W`、`command -v` 与限定目录搜索；不声称全磁盘绝无其他安装副本。

### L2 飞控与 Python 复用证据

| 直接检查的路径 | 证据 |
| --- | --- |
| `/root/aerotwinsim-ap-native/source/ardupilot` | HEAD `1511f27194f1dcc3728270883047bdf022b3fd53`；`git tag --points-at HEAD` 包含 `Copter-4.7.0`；`ArduCopter/version.h` 为 V4.7.0。`git describe` 选了同 SHA 的 `APMrover2-stable` 标签，不能据此误判为 Rover。 |
| 上述路径的 `build/sitl/bin/arducopter` | 5,647,040 bytes，x86-64 ELF，未剥离符号；SHA-256 `9daf4ca71d32c2d48d292dac5d7432fc2137b1c75770868a1b8c1ee175534f24`。 |
| 上述路径的 `build/c4che/sitl_cache.py` | 精确抽取为 `AP_DDS_ENABLED=0`、`'enable_DDS': False`；ELF 中 `AP_DDS_Client::` 符号计数 0。源码默认宏不是本产物编译开关的替代证据。 |
| 上述 AP ELF 的 `readelf -Ws` + `c++filt` | 命中 `SITL::JSON::JSON`、`set_interface_ports`、`recv_fdm`、`parse_sensors`、`output_servos`、`update`。没有运行该 ELF。 |
| AP `modules/Micro-XRCE-DDS-Client` | 子模块 SHA `97175304425c5bee87c6fddd99de1ef8d0c394dc`；其 CMake 声明 2.4.1。 |
| `/opt/aerotwinsim/src/px4-d6f12ad1` | HEAD `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`；`v1.17.0-dirty`，保留已有改动。 |
| 上述 PX4 的 `build/px4_sitl_default/bin/px4` | 56,963,184 bytes；SHA-256 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`；存在 `uxrce_dds_client_main`。 |
| 上述 PX4 的 `build/px4_sitl_default/px4_boardconfig.h` | `CONFIG_MODULES_UXRCE_DDS_CLIENT 1`。 |
| PX4 `src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client` | SHA `711aef423edd1820347b866d1e4164832df35d04`；其 CMake 声明 2.4.0。 |
| `/opt/aerotwinsim/src/px4-unified-clean-20260821` | 同一 PX4 HEAD，`git describe` 为 v1.17.0；限定深度没有找到 SITL 二进制，可作为干净源码候选。 |
| `/root/ardupilot-Copter-4.7.0-ZeroOneX9-build` | HEAD `6228ac0f56f59790a2cb7db0b52d87d1b0294197`，存在 `build/ZeroOneX9/bin/arducopter`；本轮未把它认定为可直接复用的 SITL。 |
| 系统 Python3 用户安装 | `python3 -B -m pip show pymavlink`：2.4.49，`/root/.local/lib/python3.10/site-packages`；`find_spec` 定位到该包。没有运行 MAVLink 连接。 |

上述路径和 SHA 证明本机材料及静态能力；源码 checkout 与既有二进制是否完全对应，仍应由后续构建清单/运行证据绑定，不能仅据相邻文件推断。

### L3 限定搜索与未发现项

本轮对 `/root`、`/opt/aerotwinsim`、`/usr/local` 最深 6 层，按精确名字查询 Agent、Gen、`px4_msgs`、`ardupilot_msgs`、`mavproxy.py`；只命中两个 AP checkout 内的 `ardupilot_msgs` 及一个 IDL 目录。PATH 中也无 Agent、Gen、Java/javac、ROS/colcon。发现 `/opt/aerotwinsim/venv` 等既有 venv，但此次可确定的 pymavlink 位于上面的系统 Python 用户目录；未证明所有 venv 的依赖相同。

### L4 只读模拟与包体量

执行方式均为 `wsl -d Ubuntu-22.04 -- bash --noprofile --norc`，模拟参数为 `apt-get -s -o Debug::NoLocking=1 --no-remove --no-install-recommends install ...`。

```text
原脚本三个根包：
  E: Unable to locate package ros-humble-ros-base
  E: Unable to locate package ros-humble-rmw-fastrtps-cpp
  E: Unable to locate package python3-colcon-common-extensions
libasio-dev：
  0 upgraded, 1 newly installed, 0 to remove and 53 not upgraded.
libspdlog-dev：
  catch2 libfmt-dev libfmt8 libspdlog-dev libspdlog1
  0 upgraded, 5 newly installed, 0 to remove and 53 not upgraded.
libasio-dev + libspdlog-dev：
  0 upgraded, 6 newly installed, 0 to remove and 53 not upgraded.
default-jdk-headless：
  ca-certificates-java default-jdk-headless default-jre-headless java-common
  libpcsclite1 openjdk-11-jdk-headless openjdk-11-jre-headless
  0 upgraded, 7 newly installed, 0 to remove and 53 not upgraded.
```

Ubuntu 包大小来自本机 `apt-cache show`：Asio 352164 bytes / 4510 KiB；spdlog 五包合计 974584 bytes / 4410 KiB。ROS 闭包来自下列官方 HTTP 索引的内存解析，原始统计为：原脚本 `216 / 13572920 bytes / 88313 KiB`；推荐五根包 `218 / 13855736 bytes / 92249 KiB`；core 候选 `165 / 11165156 bytes / 78085 KiB`。该 HTTP 索引仅作研究估算，本次没有独立验其签名；实际安装必须由 apt 获取并验签。HTTPS 访问该索引在本次 Windows 请求中 TLS 失败；未关闭 TLS 校验或修改系统证书。[官方索引][INDEX]

## 官方一手来源索引

文中 `[L1–L4]` 是本次直接观测；其余优先链接到上游文档、固定 tag/SHA 的源码和官方发布 API。ROS 文档网页本次被站点保护拒绝，故使用同一官方维护仓库的 Humble 文档源码。分支或包仓库的“当前版本”仅适用于本次调查时间。

[SKILL]: C:/Users/PC/.codex/skills/research/SKILL.md
[SCRIPT]: ../tools/bootstrap-humble-validation.sh
[BOUNDARY]: ./sitl-runtime-proposal.md
[WAYFINDER]: https://github.com/unununnnn/wksim/issues/1
[ROSINSTALL]: https://github.com/ros2/ros2_documentation/blob/humble/source/Installation/Ubuntu-Install-Debs.rst
[ROSSOURCE]: https://github.com/ros2/ros2_documentation/blob/humble/source/Installation/_Apt-Repositories.rst
[RELEASE]: https://github.com/ros-infrastructure/ros-apt-source/releases/tag/1.2.0
[RELEASEAPI]: https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/tags/1.2.0
[INDEX]: http://packages.ros.org/ros2/ubuntu/dists/jammy/main/binary-amd64/Packages.gz
[APT]: https://manpages.ubuntu.com/manpages/jammy/man8/apt-get.8.html
[CORE]: https://github.com/ros2/variants/blob/humble/ros_core/package.xml
[BASE]: https://github.com/ros2/variants/blob/humble/ros_base/package.xml
[A242]: https://github.com/eProsima/Micro-XRCE-DDS-Agent/blob/v2.4.2/CMakeLists.txt
[A242REF]: https://api.github.com/repos/eProsima/Micro-XRCE-DDS-Agent/git/ref/tags/v2.4.2
[A242SUPER]: https://github.com/eProsima/Micro-XRCE-DDS-Agent/blob/v2.4.2/cmake/SuperBuild.cmake
[A242CONFIG]: https://github.com/eProsima/Micro-XRCE-DDS-Agent/blob/v2.4.2/cmake/packaging/Config.cmake.in
[A243]: https://github.com/eProsima/Micro-XRCE-DDS-Agent/blob/v2.4.3/CMakeLists.txt
[FASTINSTALL]: https://fast-dds.docs.eprosima.com/en/v2.6.10/installation/sources/sources_linux.html
[PXAGENT]: https://docs.px4.io/v1.17/en/middleware/uxrce_dds
[PXMSGREF]: https://api.github.com/repos/PX4/px4_msgs/git/ref/heads/release/1.17
[APINSTALL]: https://ardupilot.org/dev/docs/ros2-install.html
[APINTERFACES]: https://ardupilot.org/dev/docs/ros2-interfaces.html
[APREADME]: https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.0/libraries/AP_DDS/README.md
[APREPOS]: https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.0/Tools/ros2/ros2.repos
[APMSG]: https://github.com/ArduPilot/ardupilot/blob/Copter-4.7.0/Tools/ros2/ardupilot_msgs/package.xml
[APCLIENT]: https://github.com/ArduPilot/Micro-XRCE-DDS-Client/blob/97175304425c5bee87c6fddd99de1ef8d0c394dc/CMakeLists.txt
[APJSON]: https://ardupilot.org/dev/docs/sitl-with-JSON.html
[MRSUPER]: https://github.com/micro-ROS/micro-ROS-Agent/blob/c93ee764e0d2ef4907aeb29233c68cb5f4b56976/micro_ros_agent/cmake/SuperBuild.cmake
[MRCMAKE]: https://github.com/micro-ROS/micro-ROS-Agent/blob/c93ee764e0d2ef4907aeb29233c68cb5f4b56976/micro_ros_agent/CMakeLists.txt
[MRPACKAGE]: https://github.com/micro-ROS/micro-ROS-Agent/blob/c93ee764e0d2ef4907aeb29233c68cb5f4b56976/micro_ros_agent/package.xml
[MRGRAPH]: https://github.com/micro-ROS/micro-ROS-Agent/blob/c93ee764e0d2ef4907aeb29233c68cb5f4b56976/micro_ros_agent/src/agent/Agent.cpp
[GENREF]: https://api.github.com/repos/ArduPilot/Micro-XRCE-DDS-Gen/git/ref/tags/v4.7.0
[GENBUILD]: https://github.com/ArduPilot/Micro-XRCE-DDS-Gen/blob/v4.7.0/build.gradle
[GENWRAPPER]: https://github.com/ArduPilot/Micro-XRCE-DDS-Gen/blob/v4.7.0/gradle/wrapper/gradle-wrapper.properties
