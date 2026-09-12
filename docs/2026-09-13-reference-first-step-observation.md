# G6参考端首步观测

主会话在独立MATLAB R2022b进程中执行了三次新诊断。最终run-03实际取得四个刚体积分器的连续状态与导数double hex，未修改旧R1模型、输入或预算。这不是G6通过，目标端对照仍未完成。

## 原件与绑定

证据位于validation/coordination/g6-reference-probe-20260913。execution-01/02/03保存调用脚本、实际探针源快照、输入检查、进程和退出记录；run-01/02/03保留原始JSON。仅提交这些选取件，不提交cache/codegen中的模型或工具箱材料。

- 模型SHA：c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392。
- 初始化脚本SHA：9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991。
- C3G输入SHA：721c88bf3f621923b98bb43251c50bae7817106a984be64345c0528d34d3adcf。
- 最终执行探针SHA：fecb5bf740bf774a24b50f2cb8f59330657f8f0a0608fd023813f4ec6b8c23a7。
- 38项使用中的冻结身份匹配；旧run_numerical_conformance.py编排器已更新，但本诊断不调用它，差异明确记录。前后输入字节无变化，探针执行源也未变。

三次MATLAB进程均exit 0，结束后未发现MATLAB进程。第一次取得事件但返回的是UDD数据对象；第二次证明主输出不受监听影响，但isobject判断挡住了UDD Data访问。第三次直接按文档化Data属性读取，保留前两次partial原件。

## 实际观测

四个积分器为刚体四元数、角速度、位置与机体系速度。每个均出现4次PostDerivatives，实际时点为0、0.0005、0.0005、0.001；按事件顺序区分两个同时间中间观测，不仅凭时间合并。

共72个事件：20 PreOutputs、20 PostOutputs、16 PreDerivatives、16 PostDerivatives；无丢弃。四块的ContStates.Data与Derivatives.Data全部可读取为double，合计每级13个状态分量。RuntimeObject方法返回Simulink UDD对象，不能用isobject/isprop判断其数值访问能力。

Sensor30、GPS30和Vehicle60的t=0、t=0.001共240个主输出值，与冻结C3G对应f64文件逐位一致，差异数均为0。参考端监听未改变这一段主输出。

纯离线复算另用观测到的参考导数，按目标源码原括号顺序计算一次ODE4加权更新，13个分量与观测到的参考末态一致。它仅说明这些参考导数下该表达式可重现末态；不是目标二进制执行证据，不能排除目标导数、上游状态或输出编码的差异。

## 实现保护与剩余工作

输出目录原子新建，JSON使用Java CREATE_NEW；模型原回调保留，临时listener和路径清理，缓存/生成物限定在新输出目录，模型关闭不保存。捕获量封顶10000事件；有事件不再被自动标为complete，原始报告保持partial。

还需构建并执行目标端首步trace，对照各级状态/导数和三项最早分歧输出。R1仍有5684项零预算失败；本观测不能代替完整数值验收。
