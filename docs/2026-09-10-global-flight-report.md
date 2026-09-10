# 双栈全球航点与 home 换代：真实运行验收

从 `e075d0d` 继续。本轮完成 v2 双栈全球航点、AMSL/相对高度、真实 home 修改撤权、旧目标拒绝及显式新请求恢复，两场均降落上锁并通过独立原始审计。当前是显式实验候选；默认生产配置未提升，#47 仍保留 #23 数值前置，Full、G6、倍率及规划/相机未因此完成。

## 最终结果

| 工况 | PX4 | ArduCopter |
| --- | --- | --- |
| 最终运行 | `d8bc659871d44a18a1846cc5a4412245`（px4-08） | `834e4b7a51b44793a2eafc885640a91e`（ap-05） |
| 物理1ms步 | 45,832 | 78,418 |
| 原始DDS记录 | 15,540 | 16,604 |
| 全球原生发布关联 | 527 | 521 |
| 最大轴倾角 | 0.035911 rad | 0.045326 rad |
| 新home/旧目标/新请求/落地 | PASS | PASS |

[最终矩阵](../validation/47-global-flight/final-matrix.json)核对当前全部运行源码、安装控制源码、原始归档与独立审计SHA，保留12场原始运行及预检拒绝记录。固定场景原点来自实际模型参数，AP另与原生`--home`输入核对。全球目标的原始经纬度/AMSL独立计算物理目标；初次与恢复目标均满足0.5m/0.5m/s持续2秒，起飞后保持5秒，最终物理高度<=0.3m且原生上锁。

两栈使用同一Control `/root/wksim-joint-control-jW617Y/build.json`，SHA256 `b8b21a27974e35f273549b78c875b76a9451a8eb987be60a333fdc4211694f69`。PX4额外使用原生home保活 `/root/wksim-px4-home-8ch55V/home-build-v2.json`，SHA256 `7432f25cde2c28515312696070bf27d9f577cd617ece44a5f2c741e601449cef`；AP沿用准入原生候选。没有通过改旧baseline来放行新固件。

`tools/run-global-flight.sh --stack <px4|arducopter> --run-id <新hex32> --control-manifest <上述Control路径> --control-sha256 <上述SHA> --output-root <新的/root/wksim-global-flight-目录> --home-change` 为实际入口。PX4另传 `--px4-home-manifest` 和 `--px4-home-sha256`；加`--preflight`只检查不飞行。`validation/47-global-flight/audit-command.sh <run-directory> <新的外部audit.json>`执行独立审计。所有占位内容须替换，最终实际参数与原始argv在每场result中。

## 交付复核：固定场景原点

`px4-07`、`ap-04`已运行完整home变更和新请求恢复。原审计记录保留，但`px4-07`的通过已被更严格的datum复核撤回：它把首个含噪声GPS测量当成场景真值原点。该场景差值只有厘米级，仍不满足明确基准要求，不能用0.5m飞行预算掩盖来源错误。`px4-07-datum-reaudit.json`记录明确拒绝。

新增`tools/global_origin_probe.cpp`用实际生成头文件构建，只读查询实际加载库的参数表，并按原包装的create/destroy执行初始化。读回GPS原点`40.1540302/116.2593683`、环境高度参数`-50`，由固定源公式`-z-envAltitude`确定原点AMSL为50m。初始有噪声GPS样本继续独立保留，不能赋给scene origin。探针、生成源/头、库及编译命令都绑定到datum proof，原厂材料仅本机读取。

AP原点本来来自真实`--home`输入；新入口另核对它与模型固定原点一致。基准修复后的px4-08与ap-05及最终审计已通过，未覆盖旧档案或调整物理误差预算。

## 已完成的 AP 基础工况

运行 `61341c9f94fc459d889ca248c6a5fe44`，Control `/root/wksim-joint-control-omuYiq/build.json`，SHA256 `26b0600f32f3e559594d801fd1cf1970d4111c4dff0f2d65eb76d62212a46ca3`。完整起飞、5秒保持、home 附近 E=5m/N=3m/相对高度3m目标、连续2秒目标保持、越界拒绝、同目标AMSL输入、降落上锁。

独立审计重解码15,686条CDR、关联456次全球原生发布、核验75,091个1ms物理步及原始执行器输入。物理目标从原始全球坐标和场景基准独立计算为 ENU `[5.005573117902509, 3.0033416185409334, 2.97]`，不是从已转换的local设定值反推。最大轴倾角0.045594224rad；沿用0.5m/0.5m/s/2秒门槛，未调整预算。

证据：`validation/47-global-flight/ap-03/`。前两次起飞前失败分别是ROS参数JSON未作为YAML字符串传递、Humble回调不提供GID，原件在`ap-01/`、`ap-02/`。原始Linux运行目录均保留。该场不覆盖真实home变更/旧目标失效，不能据此关闭#47。

## 接口与真实消息边界

- `/uav1/prometheus/v2/global_command`：JSON包含原始全球目标、home-relative或AMSL、两秒命令租期、完整home/origin身份和RunSession请求信封。原有运动接管/导航/模式门控继续执行；未知高度基准拒绝。
- `/uav1/prometheus/v2/global_reference`：仅在原生位置、home及原点通过校验后公布ready。原生GID使用已有Humble CDR take接口读取，禁止用发现图推测样本来源。
- PX4全球结果明确通过原点投影到TrajectorySetpoint NED；AP保持原生FRAME_GLOBAL_REL_ALT/map/0x9F8。全球目标不经过普通local输出修整。清理/失效不自动重投影或重新接管。
- PX4消息包含合法的无效参考/未限幅NaN字段。记录保留原始CDR，不要求与控制无关的全部字段可转成严格JSON；真实控制所需经纬高/有效位仍必须通过有限性与导航检查。
- 固定HomePosition.msg实际为`uint32 update_count`，已将纯转换模块错误的8位上限修为原生32位，并验证最大值与回绕撤权。数值预算未变。

## PX4 已观察到的问题与候选

`px4-01`与`px4-03`均发生原生消息NaN日志序列化错误，随后全球reference等待超时并安全降落。它们不是全球飞行通过，也不能单凭该超时证明home过期。首次进度描述中的home归因已撤回，以本段及原件为准。

从两场**独立原始DDS记录**提取：未加保活的home相邻源时间最大间隔4.344秒；原生保活候选最大0.504秒。数值见`*-observation-facts.json`，不把改动的发布表上限当作实测周期。

原生候选`/root/wksim-px4-home-8ch55V`只改HomePosition.cpp，在权威owner内每500ms重新观测/发布当前home，保留真实修改计数。原生原件时间语义没有被Python缓存重打戳替代。完整源码树比较、编译、无Gazebo动态依赖与生成bin/etc清单由`tools/px4_home_candidate.py`封存。

首次封存错误地比较ldd随机加载地址，导致预检拒绝、没有启动载具。v2比较稳定依赖并保存原始依赖日志SHA；旧manifest没有覆盖。`px4-seal-v2-comparison.json`证明固件、完整source和build.log完全相同。

后续`px4-04/05`发现同一原生timestamp内HomePosition真实update_count可增加：原始DDS确认该字段变化。修复按原生计数识别换代并撤销旧目标，同时保留原接收时刻，不延长租期。typed字段比较忽略CDR填充字节，NaN仍不被用于控制基准。

`px4-06`真实修改home后正确撤权，但直接重新接管遇到原生Offboard-loss LAND/failsafe而失败。修复先通过公开请求进入原生保持，再发显式任务接管；没有关闭failsafe或延长全球租期。原始失败及降落记录保留。

AP初次home审计错误地把GCS接口`Location::set_alt_m(float)`的乘法按double解释。固定源证明此处先做float乘100再转cm，而DDS全球适配器明确使用double乘100；审计分开模拟两种原生转换后通过，旧审计拒绝记录在ap-04目录。

## 回归与剩余门槛

当前68项控制/真实消息/GNSS回归完成（独立C++ oracle在该调用明确跳过，另行执行）；28项运行/隔离/proof/操作报文回归通过。固定源oracle的16项及60个双栈数值用例另行归档，误差门槛未改。基础审计四项负例与完整home审计均保留；后者PX4四项通过，AP三项通过，纯PX4的场景原点缺失负例明确不适用于AP。

本批原生全球工况已验收。仍待生产候选提升与父票依赖收口；规划/相机、ABI、G6、联合倍率及其他Full账本项目继续推进。未修改旧GNSS/RC/电机故障通过证据，未关闭未完成父票。新模块按已知源路径直接读取，外部FC/模型依赖以源码/构建哈希和实际运行核验，不冒称源图已覆盖新增实现。
