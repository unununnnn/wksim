# AP P+V 候选离线可执行边界

2026-09-08。候选准备证据；#33 仍依赖 #32。本报告不改变准入、profile、pin、实飞验收或 Full 门槛。

## 执行与来源

主代理实读子代理会话 `rollout-2026-09-08T20-06-37-01a080b2-cebe-7200-910e-6ff2f97a8520.jsonl`，核验 `/root/ap_pv_boundary` 为 `gpt-6-astra` / `low` 后才开始工作，没有嵌套委派。

新增 `tools/test_ap_pv_native_boundary.py` 与专用支持文件 `tools/ap_pv_native_boundary.cpp`。只读 `/root/wksim-ap-pv-vn04950x/src`，以候选 `pv-source.json` 中逐文件 SHA256 验证 DDS、Copter 和 GlobalPosition IDL 源；实际执行后再核验三文件未变。仅复制三个来源文件到本轮证据目录。

测试从实际来源逐字截取并编译以下完整函数（不重写校验表达式或 forwarding 实现）：

- `AP_DDS_External_Control::handle_global_position_control`
- `AP_DDS_External_Control::convert_alt_frame`
- `AP_ExternalControl_Copter::set_global_position_velocity_and_yaw`
- `AP_ExternalControl_Copter::ready_for_external_control`

mask 常量直接从实际 IDL 提取。证据保存原始来源、截取函数体、输入支持文件、全源/函数体/测试程序 SHA256，以及编译器版本、编译和执行命令、退出码、stdout/stderr。

WSL Ubuntu-22.04 执行命令：

```bash
python3 /mnt/c/Users/PC/Documents/odid编译/wksim/tools/test_ap_pv_native_boundary.py
```

结果 PASS；g++ 11.4.0，C++17，`-Wall -Wextra -Werror -fsanitize=undefined,float-cast-overflow -fno-sanitize-recover=all`，编译与执行退出码均 0，无 sanitizer 输出。完整证据为 `validation/ap-pv-boundary-ea28l5nf/evidence.json`。

| 实际来源 | SHA256 |
| --- | --- |
| DDS cpp | `2e21990fd0662a62a2356819a1f9af9a899031a03dbac6279f98ed59d15349ef` |
| Copter cpp | `4fd1a5efb5d0cb88d106d74fede46b2c20744b1800f2409ce1f567110bd36828` |
| GlobalPosition IDL | `945d2756cc07bfce84af46efb9e4c4d23634b14d2a3adee91217427422f4bb76` |
| pv-source.json | `c65a91801f7488a2a239895a9d7c8f3ca2167d417180b4ff64ab2977ddf3970b` |

## 已执行断言

- 实际 handler 枚举全部 65,536 个 uint16 mask，仅 2496、2552、3520、3576 返回成功且恰好调用一次相应 ExternalControl 路径；其余全部失败且零 ExternalControl 调用。涵盖所有部分 P/V、A、force、yaw-rate 和未知位组合。
- 四个合法 mask × 三个高度帧，检查位置缩放、帧映射、纯 P/P+yaw/P+V 路径、yaw 激活和 ENU `(1,2,3)` 到 NED `(2,1,-3)`。对全部 uint8 高度帧，除 5/6/11 外拒绝；空帧及 odom/base_link/MAP/带空格帧拒绝。
- 四个合法 mask 的经纬度/高度 NaN、±Inf，以及越界经纬度、高度边界拒绝；有效 yaw NaN、±Inf 拒绝，忽略 yaw 时允许该载荷。四个常见 yaw 角检查方向转换。
- 每个速度轴 NaN、±Inf、正负 float 溢出值在 P+V 下拒绝且不调用目标；纯 P 的被忽略速度仍不影响受理。±float max 接受。
- 四个合法 mask 的 ExternalControl 空指针失败且零调用；目标方法 false 返回值传播。Copter 实际 P+V 方法经 DDS 接入后向 Guided stub 原样转发位置/速度/yaw，固定 yaw-rate 和 relative 参数符合候选调用。
- 实际 ready 方法的非 Guided、未 armed 拒绝且不调用 Location 或 Guided；有效速度/yaw 的非有限输入在转换前拒绝。Location stub 失败及其返回位置每轴非有限时不调用 Guided。忽略 yaw 时向 Guided 传 0。Guided 返回 false 穿过 Copter 和 DDS 原样传播。

## 证据边界

这是实际函数体的 C++ 可执行边界，不是完整 AP translation unit/固件构建或 SITL。声明、消息结构、Vector/Location、AP endpoint、Copter 依赖、Guided 及 `radians`/`wrap_PI` 是显式 stub。IDL 常量来自真实源，但未执行 DDS 反序列化。math stub 使用标准数学函数，因此这里验证 yaw 调用和常见方向结果，不证明真实 AP math helper 的全部边界。

“无副作用”在本测试中精确定义为拒绝时无下游 ExternalControl/Guided 调用，及指定早拒绝场景无 Location 转换调用。无法据此推断完整飞控全局状态、线程或通讯副作用。Guided 拒绝测试只证明 false 传播；不证明真实 fence 算法。Location stub 只证明转换结果/失败被尊重；没有模拟 home/origin/terrain，不证明实际地理转换。未执行真实 readiness、fence、目标 timestamp/timeout、控制律、轨迹误差或停止恢复。未运行 SITL、UE 或 MATLAB，未更改补丁、固件候选、产品代码、既有测试、pin 或 manifest。

本轮离线验证补齐已有文本 guard 的运行分支证据；候选身份准入及真实运行证据仍由独立流程承担。
