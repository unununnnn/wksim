# #42 真实地面站界面交接验收

票据于2026-09-08 17:15:39 UTC关闭并读回CLOSED/COMPLETED：[主代理验收评论](https://github.com/unununnnn/wksim/issues/42#issuecomment-5589037445)。

2026-09-09，用户明确“全程你自己确认即可”，主代理按[最新授权](2026-09-09-gcs-automation-authorization.md)自行操作真实受控WksimGCS。双栈完成地面确认、原任务飞行、地面站切走模式、撤销旧输出、旧请求拒绝、新的显式接管、新任务和落地；独立物理/原始报文审计通过。执行者为助手自动化，未记录为用户亲手点击。初始human命名的文件/阶段保留作历史标识。

## 真实成功证据

| 项目 | PX4 | ArduCopter |
| --- | --- | --- |
| 证据目录（validation/gcs-handoff-20260909下） | px4-human-10 | ap-human-01 |
| run_id | gcs-px4-8845a11c1ab2 | gcs-arducopter-8b4123f2d57e |
| control_epoch | e3a662695f6e42a69a462e5e7972fe9b | 27f2cace6ca54130a13460f1f5e44e6d |
| 实际GUI切换 | Offboard→Hold | Guided→Brake |
| 原始地面站报文 | SET_MODE，target22，base145，custom50593792 | COMMAND_LONG176，target241/1，param1=1，param2=17 |
| QGC来源 | 255/190 | 255/190 |
| Windows正向包 / 原生源成功发送包 | 95,804 / 95,817 | 84,888 / 84,888 |
| 成功反向包 | 390 | 578 |
| 释放期物理高度范围 | 2.9450–2.9972m | 2.9662–3.0224m |
| 释放期物理时间推进 | 6.32s | 7.18s |
| 新接管最大物理位置/偏航误差 | 0.09109m / 0.008519rad | 0.06213m / 0.009712rad |
| 新保持原生输出样本 | 57 | 22 |
| 结果 | runtime/formal/Windows driver均pass | runtime/formal/Windows driver均pass |

两场复用已准入的独立四旋翼、原生DDS Control与实际FC，均非promotion-flight；固件、消息、模型、运行器和工具SHA随formal/report.json及runtime结果保存。WksimGCS5.1.4.0的exe SHA256仍为134b9b6db4dec56d00707e406e5f8ff20ded25cfba8f5579e2447f1acbd6ace7。独立预检只允许私有UDP14560→127.0.0.1:14570，并核对六种AutoConnect关闭；其他地面站和硬件未接入。

主代理通过实际窗口枚举、激活、截图定位模式菜单。原按钮为500ms DelayButton，短点击/drag/Return未完成确认；随后对已核验的前台自建进程/窗口进行0.8秒定向鼠标按下与释放，QGC原确认逻辑完成并产生上表MAVLink。工具没有构造飞控模式报文，确认开关保持启用。AP的Brake最初隐藏，仅通过菜单编辑设为可见；固定固件版本提示经确认关闭，未升级固件。

每场authorized-gui-hold.json保存actor、PID/内核创建时间、exe/前台窗口验证、截图尺寸/点击位置、按压时间和run/epoch。原生截图为px4-hold.jpg（SHAd6021c04641e439c7d6b8958af7f92d6913b070f56b47ba4d16da8434732cccf）、ap-brake.jpg（SHA8bee430c75d5eeede37c71ffb42cc269f5623c152521c8f6ad72353728c01a0f），均保留接口原始字节。

切走后实际公开事件为external_mode_left_no_automatic_reacquisition，控制状态回到INIT，持续至少2墙钟秒无新的任务原生位置输出，同时物理继续且保持离地。重复旧setup、旧move及错误epoch分别拒绝，未重新接管。新请求文件含当前run/epoch/nonce，完整原子交付后才发新的COMMAND_CONTROL；此时公共request_id=5（旧自动release用过一个额外setup，原接管审计默认6保留，仅对本次明确传入实际新请求5）。新保持参考来自当前离home、非零yaw的实际状态，没有回到初始起飞点或重放旧任务。

## 原始审计和收尾

主代理独立审计脚本validation/gcs-handoff-20260909/audit.py重算物理高度/位置/偏航窗口、源时间严格推进、原生输出区间、公共请求/nonce、GUI进程身份、真实MAVLink解码及源码身份。Windows发送的每个正向原始包必须是原生成功发送序列的有序子序列；不声称零丢包，PX4有13个源包未出现在Windows发送记录中。

人工等待试验曾超过旧8192项内存摘要上限。Observer现在为实际GCS会话逐包追加gcs-forward-hashes.jsonl，并记录自身文件摘要和完整计数；旧内存集合保持原上限。独立审计先核对该文件的生产者SHA，再核对完整序号/数量与Windows原始包。真实套接字测试覆盖内存上限后继续记录、重复超量包及文件篡改拒绝。

反向只按relay真正成功提交的原始包累计 `4字节大端长度+bytes` SHA256，并与Observer实际发往钉定FC的计数/摘要相等：PX4为d9d6a6f05cbf72f12f7be3df7cf1f5ace8a6ad4bb15494d7156f191e4df070f2，AP为232c672d2f2cfeebfb56adf813a06f6f5497e1cbf0bc369ca7c269d5144ec4be。GUI显示、回包、控制撤销及物理完成分别成立，不以点击成功替代动作完成。

两场独立审计各重复两次，输出字节一致：PX4审计SHA39fdb317dbf2d5c3aea4aa378d38582090e344462cc4208f35eecf0d9c8a7615；AP审计SHAa41c8375962753e097010979fa0f4e339692fab48dc25fee4c312e997f02b872。实际执行源另按运行记录哈希封存于accepted-sources/及manifest.json，避免后续源码变化冒充本轮版本。

收尾顺序为落地→桥停止请求/精确nonce确认→runtime退出FC/Agent/物理/Control/Observer。两场均safe_landing、children_reaped且cleanup_errors为空；Linux wrapper/validator/relay的PID/start_ticks检查无残留，Windows GUI的PID/创建时间复核无残留，当前无WksimGCS进程。GUI由自有Process对象关闭，必要时精确Kill；两场记录forced_close=true，PowerShell未取得退出码，明确记作null，不能称GUI自然退出0。没有按名称终止其他用户进程。

## 可复现命令

在Windows项目根使用新的OUTPUT目录：

```powershell
python -X utf8 -B tools/validate_contained_gcs.py --stack px4 --manual-handoff --execute --output OUTPUT
python -X utf8 -B tools/request_gcs_takeover.py --output OUTPUT --action start_flight
# 到达GUI交接阶段，通过实际QGC菜单完成Hold；随后：
python -X utf8 -B tools/request_gcs_takeover.py --output OUTPUT --action takeover
```

AP换为 `--stack arducopter`，GUI选Brake。模式菜单坐标必须来自当次真实截图，不能复用本报告坐标；hold_gcs_button.py还会拒绝前台/进程/创建时间/尺寸变化。普通操作者也可亲自长按确认。每个人工/自动决定窗口上限300墙钟秒，独立物理总量上限3600仿真秒，外层1200墙钟秒；仅通过显式独立task_factory选择延长预算，默认任务仍600仿真秒。既有180秒活动墙钟看门狗按已存在的operator_wait_seconds排除实际等待段，状态新鲜度、原生解锁和动力学步进未放宽。

## 失败保留与回归

PX4 human-01在FC启动前因误用/root遥测目录被正式/tmp契约拒绝；02/03/08到航点后未收到有效界面长按模式报文而失败；04–07在地面确认阶段超时，未起飞。窗口是否可见/是否在前台和确认超时交织，不能把这些失败归咎于用户操作；后续直接用窗口接口激活并读取真实画面，且用户授权全程自动化。09的飞行/交接/落地已pass，但先关FC导致桥退出1，整轮driver仍failed；新增落地后的桥停止握手，10复跑完整通过。全部旧目录、日志和原始失败状态保留；失败源码并非每版都完整封存，旧hash不冒充当前源。最终两场的执行源已全部独立核对。

最终全量回归465项（436通过、29跳过），旧预检11通过，日志validation/session-product-checks-tCpOXvJ7/。Windows原子决定CLI4通过/1个WSL dialect条件跳过，私有ROS/实际套接字及接管测试均通过；独立审计适配只改变本次已核对的新接管请求编号，未放宽任何物理门槛。更早的双栈空中断桥且物理继续证据仍由[受控GCS基础报告](2026-09-08-gcs-promotion-report.md)承担。

本报告闭合#42的地面站观察/控制交接范围，支持后续#48首期产品集成审查；不完成Full、联合倍率、RC、数值基线或硬件分支。
