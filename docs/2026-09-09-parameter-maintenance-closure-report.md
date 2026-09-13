# #43 参数维护与真实飞控重启验收

票据已于2026-09-08 15:29:04 UTC关闭并读回CLOSED/COMPLETED：[主代理验收评论](https://github.com/unununnnn/wksim/issues/43#issuecomment-5587651586)。

2026-09-09，主代理完成双栈参数读写、真实FC重启、旧信封拒绝、新任务飞行、落地恢复原值及独立原始审计。入口是 `tools/run-wksim-parameter-mission.sh`，流程与边界见[操作说明](2026-09-08-parameter-maintenance-workflow.md)。没有替换固定固件、放宽原生解锁/时间戳/地面门槛，也没有修改默认模型或联合倍率合同。本文支持#43的最小白名单切片；Full其余控制/参数/机型义务仍保留。

## 可复现入口和白名单

在WSL Ubuntu-22.04 root、项目根执行。每次使用新的run-id与不存在的/root/wksim-*输出根；该命令明确执行两次标准单航点任务，各自起飞、[2,3,3] ENU航点、持续到达核验、降落。以下示例配置与本次实际输入的JSON内容相同（行尾规范为LF），仅CLI覆盖run-id：

```sh
bash tools/run-wksim-parameter-mission.sh \
  --config Simulator/wksim_runtime/examples/parameter-arducopter.json \
  --run-id parameter-maintenance-ap-20260909-03 \
  --output-root /root/wksim-parameter-maintenance-ap-20260909-03 \
  --value 3.1 --restore-original
bash tools/run-wksim-parameter-mission.sh \
  --config Simulator/wksim_runtime/examples/parameter-px4.json \
  --run-id parameter-maintenance-px4-20260909-02 \
  --output-root /root/wksim-parameter-maintenance-px4-20260909-02 \
  --value 4 --restore-original
```

上列目录已保留，复跑应换新ID/目录，不删除原证据。AP只开放WP_SPD [3,10]m/s、0.1步；PX4只开放MPC_XY_CRUISE [3,5]m/s、整数步。AP范围在首次真实写入之前冻结，以允许恢复实读原值10；不暴露任意参数。二者原生参数设置无需通过重启才能回读新值，本切片额外验证重启持久性。GET可如实返回网格外原值，但找不到无损恢复映射就拒绝SET。未知名称、非有限值、类型/网格错误和过期/非地面/活动任务/旧代次均拒绝。

AP SetParameters收到真实successful，另发GetParameters确认存储值；3.1的真实float32值为3.0999999046325684。PX4 PARAM_VALUE只记固定peer/sysid/component/name/type下的观测，另发PARAM_REQUEST_READ确认；它没有request_id，不冒充COMMAND_ACK或强因果回应。未测试这些参数改变现有GUIDED/OFFBOARD任务实际速度；特别MPC_XY_CRUISE属于自主任务参数，不能据本次飞行声称Offboard速度已改变。

## 成功运行与原始证据

| 项目 | AP 03 | PX4 02 |
| --- | --- | --- |
| 原值→目标→重启独立GET→恢复GET | 10→3.0999999046→3.0999999046→10 | 5→4→4→5 |
| 旧/新FC PID | 918 / 1228 | 1061 / 1863 |
| 旧control_epoch | 0f718ed54ac046b3a239b08f6b64e0cf | e28b77c84ee84fa4bd978b4a449b57bd |
| 新control_epoch | 350489ae274949c2a72ea71e3e3f8d83 | 9cfbad660db945229ae4dac2b2045e80 |
| 拒绝后原生零输出窗口 | 1.008219930s | 1.001961434s |
| 前/后物理最小航点误差 | 0.016239 / 0.007119m | 0.035243 / 0.041047m |
| 完整阶段 | 2 pass，均落地、收尾 | 2 pass，均落地、收尾 |

每个事务根的parameter-maintenance.json包含两个正式runtime结果，before/after各有prometheus.jsonl、truth.jsonl、原生FC/Agent/Control日志和参数证据。固定AP提交1511f27194f1dcc3728270883047bdf022b3fd53加已准入补丁，实际固件SHA256为083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de；PX4提交d6f12ad1c4f70ad3230afd7d86e971421e02fef4加已准入修改，实际固件93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a。完整源码、模型、消息包、Agent、Control及运行器身份已逐阶段记录并独立核验前后一致。

AP保留同一eeprom.bin；PX4保留同一parameters.bson及backup，只有明确绑定原厂资源根的etc/test_data别名获准存在，审计不跟随它们复制数据。停旧FC并确认子进程退出后才关闭并重新持有同一UUID租约；重启前后参数文件的路径、inode、size、hash以及目录/marker身份完全一致，未复制、清零或恢复默认。恢复完成后的文件hash另存，不要求它与目标值阶段相同。

新Task在首次spin前拒收旧epoch状态，等新发现、定位、地面和真实原生订阅匹配完成。before实际发送的MOVE采用一次serialize→Publisher.publish(bytes)，原CDR原样保存；after反序列化逐字段核对并重新publish同一bytes。两栈均得到精确wrong_run_or_control_epoch，request_id=4，新会话高水位保持0，之后的新Task从请求1开始显式接管、飞行。原生观察器每主题实际匹配1个固定Control发布者，拒绝后至少1秒持续新鲜地面状态且零运动样本；[匹配检查](2026-09-09-ros-subscription-match.md)另有真实QoS不匹配负例。恢复原值只发生在第二次落地之后，以新的operation_id、当前epoch/native_generation和新参数通道进行。

独立审计 `validation/parameter-maintenance-20260909/audit.py` 不调用产品参数通道或准入结论，重算物理日志、逐条ground authority、GET/SET/独立GET顺序、原生读值、原字节重放、存储身份、阶段源码与进程清理。成功证据分别归档在ap-03-audit/、px4-02-audit/；manifest列源路径、字节数与SHA256。每个审计重复两次字节一致，audit.json SHA256为：

- AP：77831e64729c9648a6b19ea0c4d0e12d4ecd4046d18c2a801ee7a2e6f5c815b6。
- PX4：12e068ae039f0979e0ee69c77bc8c9f9e574aa70e3d871b6c9b8c99ef7d53e44。

两个成功事务的16条子进程记录均已reaped且returncode已知，cleanup_errors为空；只读检查未发现同时匹配完整argv和运行cwd的进程。历史记录没有/proc start-time，因此不把PID数字本身或系统其他进程作为历史身份证明，不执行全局清理。

## 保留的失败及修正

| 运行 | 实际结果和处理 |
| --- | --- |
| AP 01，目标4 | before飞行pass；after没有liveliness匹配事件而超时，未发旧MOVE、未进行第二次飞行或恢复。改为公共RCL真实匹配计数，并以实际QoS正反测试核验。 |
| AP 02，目标3.1 | before飞行pass；after真实匹配完成，但重建CDR的对齐填充字节不同而拒绝。离线反序列化字段完全一致；改为保留第一次实际发送bytes并原样重发。失败没有冒充字节通过。 |
| PX4 01，目标4 | before pass，after重启回读和旧命令拒绝通过，第二次MOVE后墙钟回拨，LAND头比MOVE早267975421ns，原有out_of_order_command_stamp正确拒绝；整轮failed，无自动补写或时间戳钳制。新目录同实现复跑PX4 02通过。 |

以上失败的独立参数目录、原生文件、pending_restore=true和完整日志仍保留。failed报告current_value=null，只保留last_readback，不将旧观测称为当前已知状态。它们不影响默认运行参数目录，也没有被后续成功样本覆盖。先前六轮读/写probe及一次时钟失败另经[历史独立审计](2026-09-09-parameter-probe-evidence-audit.md)。

主机墙钟跳变仍是已知环境可靠性限制；本轮通过不证明该问题消失。未知写入、失去地面权限、代次变化或未完成落地时均停止；失败场景不自动恢复原值，也不在空中实施后续重启。

## 回归与验收边界

`bash tools/check-session-product.sh`：458项中429通过、29跳过；旧预检11通过，日志validation/session-product-checks-0IK6eUmt/。其中协议6项、真实fcntl存储10项、runtime接缝3项、维护流程8项及真实隔离FastDDS匹配/serialized publish检查通过。CLI PX4值4.5实际被拒绝，未创建输出根。前两种实现失败对应源码已归档，成功阶段源码快照与当前源一致。

本轮验收覆盖已锁定白名单、真实回复和准确生效状态报告、隔离且落地后的自有FC重启、旧代次失效、新发现/定位/显式接管、完整操作和失败交付。没有扩大到任意参数、物理硬件、飞控控制律调参效果或Full全部功能；#32真实倍率、#23/G6预算、#42人工交接以及其他开放票仍须各自完成。
