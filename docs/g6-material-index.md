# G6 模型开发与精度材料索引

已定位本机的模型二次开发、代码生成与传感器标定资料。模型开发用途有厂家说明支撑；当前尚未找到绑定 e0 SLX 11.8、覆盖全部验收量的物理精度预算表，也未找到单独说明该模板源码/二进制再分发范围的条款。资料存在、工作流说明、工具许可和数值验收分别记录，不互相替代。

机器索引：[index.json](../validation/g6-material-index-01/index.json)，包含23份PDF、773页的关键词页序，以及20份标定脚本/数据和5份模型/工具文件的完整路径、大小及SHA256。PDF文本以NFKC规范化后检索，避免兼容汉字和连字漏检。关键三页已渲染核对；未修改或执行原厂脚本，原始PDF/文本副本留在本机私有工作目录。

## 优先阅读：模型开发与生成

页码均为PDF页序，从1开始；例如《Intro.pdf》第3页的印刷页号为2。

| 材料 | 精确位置 | 已核实内容 | 用于当前工作的边界 |
| --- | --- | --- | --- |
| [模型开发工作流](<E:/rflysimtools/RflySimAPIs/4.RflySimModel/Intro.pdf>) | PDF第3页，第2.1节；第5页 | 厂家说明提供二次开发模板、生成C/C++并移植到其他嵌入式系统；列出免费版包含的模板类别 | 是本地开发用途和流程的直接依据；不是全文件再分发许可证 |
| [e0最小模板说明](<E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/Readme.pdf>) | 第1页标题与文件清单；第2–3页；第5–10页 | 标明Simulink模块支持二次开发，直接指向Exp1_MinModelTemp.slx/init，介绍生成代码/DLL与SITL运行 | 与所选模板路径直接关联；实际SLX/init哈希另行绑定，不能把相邻旧ZIP当作新生成产物 |
| [Simulink生成C++教程](<E:/rflysimtools/RflySimAPIs/4.RflySimModel/0.ApiExps/2.UserDefinedC++/2.GenC++/Readme.pdf>) | 第6页、第9页 | ert.tlc、C++及Windows/Linux/嵌入式目标；说明生成ert_main.cpp、模型cpp/h | 可据此实现可审阅生成入口；没有执行不透明的GenerateModelDLLFile.p |
| [本机MathWorks软件协议](<D:/matlab/install date/license_agreement.txt>) | 文件开头与后续Program Offering Guide | 该文本的主体是MathWorks及其程序/许可类型 | 需与本机实际工具checkout分别核验；不能代替RflySim模板的来源说明 |

对应身份：模型工作流PDF `0af3660d6188535943e848cdbc2dcd06a40702cc4c164a4ed4f4a30931cffb68`；e0说明书 `3ddc08409d8fd6f7f41b5185f73162d9eeae1e504acb31ff981c6d0c75bec942`；C++教程 `a26cba0d41706f998f97a2bd41d20111856896d52e57b99dd492f20b2a9b0caa`。

所选[SLX](<E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/Exp1_MinModelTemp.slx>) SHA256仍为`c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392`，[init](<E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/Exp1_MinModelTemp_init.m>)仍为`9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991`。当前复用ZIP的生成源自报model version 11.0，而既有SLX审查为11.8；资料索引不消除该版本差异。

## 已找到的标定资料和数据

| 材料 | 位置/规模 | 可用于 | 尚未证明 |
| --- | --- | --- | --- |
| [传感器标定和测量模型](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/第07讲_传感器标定和测量模型V2.pdf>) | 56页；第6–13页加速度计，第45页GPS模型，第52页相机标定工具 | 建立传感器模型与误差项的来源说明 | 不是e0模型各输出的验收预算；第39页VLP-16指标不能直接用作当前模型的精度 |
| [传感器标定实验](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/第07讲_实验三_传感器标定实验.pdf>) | 23页；第3页区分外部基准标定与自动标定 | 标定方法、实验步骤与可重复分析设计 | 没有当前e0载具的测量不确定度和完整动力学验收门槛 |
| [加速度计二进制数据](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/e3.1/e_acc_A.bin>) | 440,488字节；MWLOG；18,353条，每条6个single；完整记录无尾部残片 | 教学标定算法输入，配套脚本说明前3维加速度、后3维特征点 | 未绑定当前载具/传感器序列号、场地与测量不确定度；不是当前仿真的独立实测基准 |
| [磁力计二进制数据](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/e3.3/rawdataFile/e3_m_A.bin>) | 2,896字节；MWLOG；240条，每条3个single；无尾部残片 | 磁力计标定示例输入 | 同上，不能仅由记录数推导当前模型精度 |
| [加速度计拟合脚本](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/e3.1/calLM.m>) | 源码读取，未执行 | LM拟合、g=9.8参考、原始/校正残差、生成Ka9_8/ba9_8 | g=9.8是脚本设定，不是独立计量证明；教学TODO也不视作已完成验收 |
| [已有拟合结果](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/e3.1/calP9_8.mat>)、[原始特征](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/e3.1/AccRaw.mat>)、[加速度数据](<E:/rflysimtools/RflySimAPIs/5.RflySimFlyCtrl/1.BasicExps/e3-SensorCalib/e3.1/accdata.mat>) | MAT v5文件头与SHA已记录 | 下一步核查变量、拟合残差和数据关联 | 本轮没有运行MATLAB或读取这些MAT变量，不把文件名当作内容验证 |

加速度计原件SHA256：`7c46edaf32c1da6d45469d9ebbbeee0d2b3efbe5fb08c823993a5504df69380e`；`e3.1/rawdataFile/e_acc_A.bin`与其字节相同，只计一次数据。磁力计原件：`8ce38a6c0b5b10d2562994c7df87ccdd7db8cf63bf59f1da19f72af53e1370de`。MWLOG头部时间落在2000年，记录为未验证设备时钟值，不能据此认定真实采集日期。MAT文件头日期在2023年，也不能替代采集来源证明。

## 第一方线上补充入口

- [RflySim/CopterSim](https://github.com/RflySim/CopterSim)：作者README提供Simulink运行、编译C代码与嵌入式生成步骤；其模型是Multicopter_vPC.slx，不能自动与本机e0 SLX 11.8绑定。
- [RflySim/RflyExpCode](https://github.com/RflySim/RflyExpCode)：作者说明其e3为传感器标定教学实验，部分设计练习需要补全。与本机教学材料的用途一致，尚未逐文件核对版本。
- [RflySim/RflySimDT](https://github.com/RflySim/RflySimDT)：README描述实飞/仿真数据、15维传感器与运动量，以及MAE/RMSE等指标。是进一步寻找物理参考的候选入口；本轮未下载数据、核验其来源/适用许可或把其阈值套到e0。

这些仓库页面没有提供可直接绑定本机e0哈希的许可条款。公开可访问、作者提供开发步骤与再分发授权是不同证据，不互相推定。

## 对推进工作的影响

此前#70主要依据文件名搜索，不能继续概括为“没有本地开发用途资料”：已找到直接的厂家二次开发、生成和移植说明。下一步生成入口可以按这些工作流继续设计并绑定来源；实际工具许可checkout、生成/编译退出和新源审核仍要实做，现有`.p`不透明生成器未运行。

精度侧已有可用的传感器方法和教学数据，但它们不能自动构成当前e0动力学的全量G6预算。需要先选择具体可观测量、参考来源与适用域，再形成可解释的误差分析/验收合同；不修改R1零容差记录，也不拿旧失败差值乘系数作为新预算。

检索边界：选定的23份安装/模型/标定PDF，SDK相关目录的许可/标定文件名与文本搜索，项目现有合同/证据，以及上述作者仓库。未声称搜索了整台机器、采购邮件或未提供的合同。未打开许可证密钥文件，未联系第三方，未修改厂商安装或发送硬件命令。
