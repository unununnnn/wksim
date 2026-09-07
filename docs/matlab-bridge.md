# 可选 MATLAB TCP/JSON 桥

实现范围对应已批准 #5 / 实施 #41（本地票据31）：状态/日志、有限实验配置、既有 Prometheus 高层航点任务与取消/暂停/恢复。基础 MATLAB tcpclient 通过独立 Windows 本机桥访问当前最高产品接缝 ConsoleServer HTTP。桥不拥有 Workspace、ROS、飞控、物理循环或 keepalive；关闭客户端或桥不会发送取消、停止或恢复。操作台自身按原有产品方式保持运行。

草案曾提出桥放 WSL；当前最高产品 HTTP 入口在 Windows，因此本切片选择同机 Windows 回环代理，避免另造 WSL 任务入口。仅监听 127.0.0.1，不开放远程地址、不修改防火墙、不代理任意 URL。桥启动时获取并内部持有操作台 CSRF；该值不出现在协议响应中。连接会话身份用于旧请求隔离，不是对本机用户的身份认证。

## 启动与使用

在仓库根目录分别运行；操作台已有实例时复用其端口：

~~~powershell
python -B -m Simulator.wksim_console.server --port 8765
python -B -m Simulator.wksim_matlab.server --console-port 8765 --port 8766
~~~

MATLAB 当前目录或路径中加入本仓库 matlab 目录：

~~~matlab
addpath('C:/Users/PC/Documents/odid编译/wksim/matlab');
c = WksimClient(8766);
r = c.request('configs', struct());
assert(r.ok);
p = struct('name', 'matlab-task', 'stack', 'px4', ...
    'run_id', 'matlab-task', 'mission', r.result.defaults.px4.mission, ...
    'expected_revision', '');
saved = c.request('config.save', p);
assert(saved.ok);
selector = struct('name', p.name, 'revision', saved.result.revision);
check = c.request('preflight', selector);
assert(check.ok);
% Poll this exact preflight job until its actual status is pass.
state = c.request('status', struct('job_id', check.result.id));
% Only after pass; this starts a real experiment with the same configuration.
startParams = selector;
startParams.preflight_id = check.result.id;
% flight = c.request('start', startParams);
% c.request('status', struct('job_id', flight.result.id), flight.result.run_id);
c.close();
~~~

上述示例主动调用 preflight；协议联测脚本不调用 preflight/start。start 返回任务记录及新 run_id；这仅表示操作台的启动受理，必须查询任务实际状态/结果。初次保存 expected_revision 为空字符串；覆盖需要读取并提交准确 SHA256。MATLAB 单航点请使用 cell 包装以编码为 JSON 数组，例如 mission.waypoints = {waypoint}；多航点 struct 数组亦可。

## 协议 v1

请求是 UTF-8 JSON 对象加 LF，恰好包含：

~~~json
{"version":1,"request_id":"r1","session_id":null,"run_id":null,"method":"hello","params":{}}
~~~

每个新 TCP 连接先 hello，获得新 session_id、bridge_instance 和限额。其余请求带该 session_id；每连接 request_id 不能复用。request_id/run_id 为1–64位 ASCII 字母/数字/下划线/短横线，首字符字母或数字；job_id 为32位小写十六进制。针对某个任务的请求必须带实际 run_id；预检任务尚无仿真运行，run_id 为 null。

响应含 version、request_id、run_id、session_id、bridge_instance、observed_unix_s、ok，以及 result 或 error={code,message}。observed_unix_s 是桥所在 Windows 墙钟，不是物理时间。状态结果保持公开入口的 live.raw/run_id/control_epoch/native_generation、source_clock、原始时间和 freshness/年龄，不将 FC boot、ROS、WSL monotonic 与 Windows 时钟混为一个时钟，也不伪造上游没有提供的权威物理时间。当前公开独立任务状态中物理时间若缺失，应保持未知；终态 truth 日志的 time 是已记录物理时间。

| method | params（全部字段必须准确匹配） | 公开 HTTP 接缝 |
|---|---|---|
| hello | 空对象，身份均 null | 本桥握手，无写入 |
| configs | 空对象 | GET /api/bootstrap，过滤 CSRF/运行路径 |
| config.save | name, stack, run_id, mission, expected_revision | POST /api/configs |
| preflight | name, revision | POST /api/preflight |
| start | name, revision, preflight_id | POST /api/start，with_view固定false |
| runs | 空对象 | GET /api/runs |
| status | job_id | GET /api/runs/{job_id} |
| result | job_id | GET /api/runs/{job_id}/result |
| logs | job_id, stream, offset, limit | GET /api/runs/{job_id}/evidence |
| cancel | job_id, mission_id | POST /api/runs/{job_id}/cancel |
| mission.action | job_id, mission_id, action_token, action, control_epoch, native_generation | POST /api/runs/{job_id}/mission-action |

config.save 仅允许选择 px4/arducopter、实验 run_id、既有 mission 契约；运行路径、模型库、能力集等全部取桥启动时操作台提供的固定默认值。不得从 MATLAB 修改模型库、脚本、DDS/PX4 路径、套接字、关机或 UE 控制。start/preflight 重新读取保存配置、核验 revision，并逐字段确认只有 run_id/mission 与固定模板不同。配置依然经公开 validate_config 与操作台校验；ArduCopter 是否可运行还需实际预检准入。

mission 使用公开 version=1、cancel_policy=land、1–8航点：ENU XYZ 米（x/y ±20、z 1–10），或 body_flu 位移米（每轴±10）；yaw_rad ±π，dwell_s 2–10。FLU 由正式任务在当前姿态/位置解析，目标仍受既有 ENU 边界约束。start 复用正式航点任务发出 Prometheus 高层控制；不开放原始任意命令、速度/加速度/姿态命令或全球坐标命令。mission.action 仅接受当前公开 action_offer 中 pause/resume，完整携带 mission/epoch/native/token；native_generation 限0..2^53−1以避免 MATLAB double 身份丢精度。cancel 走既有降落策略。提交成功不等于飞控 ACK，更不等于物理完成；以终态反馈和独立飞行证据判断。

logs 仅允许终态任务的 prometheus/dds/truth/telemetry 流；offset 0..10000000、limit 1..100。运行中的公开状态本身保留有限 live.events 和 phases 日志。result 和日志中非有限记录沿用公开入口的显式标记/raw_json，不将其转换为有效测量值。

## 边界与失败语义

输入最多65536字节（不含LF），响应最多1MiB（不含LF）；每连接最多4096请求，同时最多8连接。每个帧10秒墙钟限时，包括慢速碎片；上游HTTP连接读写5秒超时。无响应/半帧超时直接断开；超长帧回复 frame_too_large 后断开。MATLAB 客户端7秒请求截止时间后关闭本连接，不重连、不重试。

非法/重复字段、非法UTF-8/JSON、NaN/Infinity/1e999、错误类型/版本、超出白名单都明确拒绝。unknown_method/unsupported_command 表示无该操作；stale_session/stale_run/stale_config/duplicate_request 表示身份或版本不能使用；product_rejected 保留公开产品拒绝；outcome_unknown 表示上游传输失败，写入可能已生效。response_too_large 也不能被当作写入未生效。

重连仅重新握手，旧 session 请求无法执行；桥不缓存待发送命令、不补发或重放，客户端也不自动重试。重新连接后人为生成新请求仍属于新操作，须先查询状态/结果确认原操作结局；本协议没有跨会话“恰好一次”承诺。桥关闭不触发上游 shutdown/cancel，也不改变主仿真时间或 keepalive。

## 本机实际验证与仍未验证

2026-09-07 JST 实际命令：

~~~powershell
python -B -m unittest validation.test_wksim_matlab -v
python -B tools/validate_matlab_protocol.py --output validation/matlab-bridge-20260907-run1
~~~

3项 Python 检查全部通过：真实TCP+真实ConsoleServer配置落盘、碎片/粘包、重复请求拒绝且不生成重放文件、路径注入拒绝、JSON/非有限/UTF8/帧边界、超时/重连且零实验任务。

本机真实 MATLAB 执行版本9.13.0.2049777 (R2022b)，PCWIN64，license('test','MATLAB')=1，-wait -batch退出0。WksimClient 经真实HTTP完成配置落盘；MATLAB tcpclient 实测碎片/粘包、旧会话/重复ID、未知方法、非法JSON/NaN/溢出数字/重复键/非法UTF8/超长帧拒绝。实际无SITL/UE作业启动，来源SHA256和命令/运行身份见 [report.json](../validation/matlab-bridge-20260907-run1/report.json)，MATLAB结果见 [matlab-result.json](../validation/matlab-bridge-20260907-run1/matlab-result.json)，HTTP原始审计见 [http-actions.jsonl](../validation/matlab-bridge-20260907-run1/console/http-actions.jsonl)。

本机MATLAB已有启动路径发出过期目录警告，并自动运行RflySim配置刷新：日志称安装路径由C:/PX4PSP改为E:/rflysimtools、更新CmakeInfo.mat与编译链配置文件并删除配置变更标记。本桥/测试未直接请求或修改厂商安装文件；这是实际启动环境的副作用，未回滚不明外部改动，也不能称本次启动完全隔离。原始 [matlab.stdout.log](../validation/matlab-bridge-20260907-run1/matlab.stdout.log) 为GB18030文本，保留事实。没有启动前外部文件清单/哈希，无法声称知道完整改动集合。

后续已修复测试启动方式：在本次证据目录创建仅输出标记的私有 `startup.m`，通过 `-sd` 指定该目录，并在执行协议前断言 `which('startup')` 为该文件。这里使用 MATLAB 的[初始工作目录选项](https://www.mathworks.com/help/matlab/ref/matlabwindows.html)和[当前目录名称优先规则](https://www.mathworks.com/help/matlab/search-path.html)；不修改全局 MATLAB/RflySim 配置、原启动脚本或许可。实际隔离重跑退出0，标记 `WKSIM_TASK_STARTUP_ONLY` 已记录，全部基础tcpclient协议检查再次通过，见[隔离运行报告](../validation/matlab-bridge-20260907-isolated/report.json)和[原始输出](../validation/matlab-bridge-20260907-isolated/matlab.stdout.log)。这不消除首轮已发生的外部配置更新，也不替代后续飞控/UE集成验收。

只读定位到 C:/Users/PC/Documents/MATLAB/startup.m（SHA256 38afddfde634da712d964772d20b61883035fe5c0462a91b1588e654bb537e37），其注册成功分支执行 UpdateMatlab；当前 PSP_PATH=E:/rflysimtools，对应 E:/rflysimtools/RflySimAPIs/RflySimSDK/simulink/UpdateMatlab.p 存在。该路径归因来自启动源码与原始日志，未通过运行时which调用追踪确认。首次启动cwd为本仓库根目录，未指定-sd；完整argv已归档。后续主线应先采用任务私有启动目录/启动脚本隔离并验证实际效果，本轮没有再次启动或修改厂商/用户startup文件。

此证据仅证明真实MATLAB协议及公开配置路径。尚未由本切片验证 MATLAB 触发实际预检/起飞/航点/暂停/恢复/取消/日志回看、飞行中断开后主SITL继续、ArduCopter/PX4双栈或G5整体通过；这些真实飞控资源由主线串行安排。本地协议/配置通过不能关闭#41或替代G5。
