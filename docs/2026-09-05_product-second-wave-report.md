# 第二批：独立并发与控制重启隔离

2026-09-05，#13“两个独立实验同时运行且互不干扰”和#14“控制节点重启后的旧命令隔离”通过主代理实现复核、真实双飞控试验与当前源码审计，于14:00:01 UTC按completed关闭并读回，见[状态与评论](plan/completions/status.json)。130项自动化检查无跳过，双栈UE5.5回归通过。**不是完整项目交付，也不代表联合时钟、空中重启或失联恢复通过。**

Prometheus来源基线仍为 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`，已跟踪源码无修改；新增实现和证据留在本机，未提交/推送混合工作区或厂商资源。依据[已批准规格](plan/full-migration-spec.md)与[Goal](plan/goal-objective.md)，原Wayfinder不改写或关闭。

## 使用与复现

新版安装 `/root/wksim-ros2-2egljG` 的[Humble构建](../validation/prometheus-ros2-cOa3jfhT/result.json)通过。保留47个原schema，新增3个wksim包络类型；8个控制Python文件在仓库、构建副本和安装候选间一致。旧安装 `/root/wksim-ros2-0viK3f`、旧准入和飞行证据未替换。接口、常规入口和显式地面重启配置见[会话手册](wksim-control-session.md)，候选/overlay见[准入手册](wksim-control-profile.md)。

在WSL Ubuntu-22.04仓库根依次执行：

```bash
python3 tools/validate_product_isolation.py --control-protocol session_v1
bash tools/run-control-restart-validation.sh arducopter /root/wksim-ros2-2egljG
bash tools/run-control-restart-validation.sh px4 /root/wksim-ros2-2egljG
bash tools/check-session-product.sh
```

每次飞行分配新run_id、输出目录和私有net/IPC/mount namespace。正式runtime、安装控制节点、真实FC与自主物理执行闭环；负例接缝只注入错误公共请求和一次记录过的PX4 ACK，观察器不代发原生飞行控制。Windows仓库根顺序运行UE回归，不能并行占用UDP19060：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 tools/validate_product_visual.py --stack arducopter --control-protocol session_v1
& 'D:/date/miniconda/python.exe' -X utf8 tools/validate_product_visual.py --stack px4 --control-protocol session_v1
```

只读审计现有证据，不启动飞控或UE：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 tools/audit_product_epoch.py --isolation validation/product-isolation-64k66y71/acceptance.json --epochs validation/product-epoch-nuimpt4w/acceptance.json validation/product-epoch-wzuq0gkv/acceptance.json --visuals validation/product-visual-arducopter-x9jn7w5h/result.json validation/product-visual-px4-23qahva6/result.json
```

[最终审计](../validation/product-second-wave-20260905/audit.json)与[机器清单](../validation/product-second-wave-20260905/manifest.json)保存真实路径和SHA256。未来源码变化时当前哈希审计应拒绝，不可改写历史证据。

## 真实试验

| 场景 | ArduCopter | PX4 |
| --- | --- | --- |
| 新版并发 | 3321条停机门真值；最高2.991m；最近航点0.0227m；66.40s | 1682条；最高3.176m；最近航点0.0630m；33.62s |
| 控制进程重启 | PID136507→136596；FC136506、物理136498不变；物理42.02→44.78s | PID136880→137101；FC136667、物理136659不变；物理4.16→7.18s |
| 重启后任务 | 最高3.006m；最近航点0.00315m；正常降落 | 最高3.144m；最近航点0.0251m；正常降落 |
| UE新版回归 | 854次Actor回读；显示断流时物理继续8.94s | 366次回读；显示断流时物理继续9.04s |

高度/最近误差只是摘要，仍执行原起飞、驻留、速度、姿态与落地条件，不是新数值等价预算。停机门快照之后，物理在清理期间还追加地面记录；审计保留并检查它们，不要求日志总行数伪装成快照行数。

[并发证据](../validation/product-isolation-64k66y71/acceptance.json)：重复PX4 run_id、不同输出根被拒绝exit2，没有第二运行目录。PX4正常清理后AP从42.46s继续至66.40s。两者net/IPC namespace和shm device不同；载具、DDS、XRCE、端口、输出和显示端点均有预约。它们是两个独立计时实验，不是联合场景。

重启证据：[AP](../validation/product-epoch-nuimpt4w/acceptance.json)、[PX4](../validation/product-epoch-wzuq0gkv/acceptance.json)。公开命令、事件与状态贯穿run/epoch/request身份。旧代次ARM/MOVE、其他run和旧无包络输入被拒绝，地面不新增原生设定值或解锁。当前代次重复包络及重复MOVE ID尝试把目标改成`[8,8,3]`也被拒绝；旧的合法悬停目标仍持续输出，AP两次观察10/9条、PX4为11/10条相同目标。正常保活不等于重放被拒绝的新目标。

PX4跨进程原生identity为200/1至200/7，无复用；实际旧ACK被新进程拒绝。与同命令新pending的竞争、重复/回退ACK时间和进度由边界测试补充。ArduCopter的真实本地RMW延迟服务器先返回旧响应，新Future仍未完成；新响应返回才完成新请求。这不是对真实FC服务器的任意回复延迟注入；实际FC服务在进程重启后的正常调用由飞行证明。

## 回归、显示与清理

[session-tests.log](../validation/session-product-checks-iHRYgtvM/session-tests.log)：122项、11.668s，无跳过；[旧准入测试](../validation/session-product-checks-iHRYgtvM/legacy-preflight-tests.log)：8项、0.327s，无跳过。包括新3类型CDR、双栈原生关联/回退、持久计数、公共RMW、延迟AP服务、当前候选准入、运行和隔离。旧测试使用旧overlay，证明兼容基线未被替换；fixture不算飞行证据。

UE沿用5.5.4二进制，SHA256 `8ff466fbd1eb6489b7e8ac29209bbb7885cf7c876ee97dbcc314ebf41dc00b4a`。AP最大位置误差8.31e-10cm、四元数1.87e-8；PX4为5.79e-5cm、9.06e-7。原2e-4cm/2e-6门槛未放宽。各10个非法显示探针无错误ACK；累计拒绝AP27、PX4 10，AP额外自然重复/迟到包不冒称定向探针。

主代理实际看过双栈LIVE、STALE及恢复图：[AP断流](../validation/product-visual-arducopter-x9jn7w5h/frames/frame-0008.png)、[AP恢复](../validation/product-visual-arducopter-x9jn7w5h/frames/frame-0009.png)、[PX4断流](../validation/product-visual-px4-23qahva6/frames/frame-0004.png)、[PX4恢复](../validation/product-visual-px4-23qahva6/frames/frame-0005.png)。机体/旋翼/城市可见，但仍是接入几何体，材质和光照有明显缺陷，不代表高保真资产或碰撞完成。

最终检查26个WSL自建进程组、8个Windows自建PID均无残留；原用户PID828的start_ticks=19268、命令行未变。只清理自己创建的进程，没有硬件操作或全局kill。UE/桥被主动终止返回1。AP旧control被主动TERM后遇到Humble已失效context的WaitSet异常、返回1；进程已回收并释放锁，新进程与飞行成功。该关停日志缺陷保留，不声称全部优雅exit0，也不把失败清理叫安全降落。

## 失败与未验证项

[首个重启试验](../validation/product-epoch-nw09nebn/acceptance.json)在supervisor核验前被Task清空地面状态而失败。修正为先核验/回收、再清空旧会话缓存，补充回归后复跑。旧数据未改。早期缺wksim_msgs及测试导入路径失败已修正，最终已构建候选24项原生/会话检查通过。

审计初版错误假设“日志总行数等于停机门快照”，将header=0的启动无效状态视为完整源样本，并未处理启动采样None；对照原始日志后修正。当前审计核对有效原生源样本的接收时间不因重复发布刷新，并验证追加清理样本仍在地面，不放宽新鲜度或物理阈值。

只验证显式解锁前地面重启；空中策略、任意时刻冷/热重启、联合时钟和硬件仍有门槛。新包络身份可在原始JSONL和任务报告查阅；旧离线工具未新增epoch筛选界面，未知时钟映射仍未知。原生回退保守锁存失效，重排包可能使任务停止。协作锁/计数不是本机恶意改写防护或远程认证。

## 记忆与继续位置

Codebase Memory刷新并持久化于13:34:47 UTC：56,975节点/161,724边。精确查询定位Task.restart_on_ground、RunSession.accept/native_identity，随后读取源文件。五个相关Python路径无记录解析缺口，freshness仍metadata_changed；tools/docs排除，外部WSL源不在此图中，图规模不等于功能覆盖率。

4个子代理均显式gpt-6-astra/low，实际turn_context含继续工作均核验；分工为隔离、原生适配、RMW测试和准入，无嵌套。主代理维护包络/生命周期、真实测试与审计。to-spec/to-tickets保留批准切片及阻塞图；codebase-design/ponytail将身份和预约集中在标准库边界；docs-generator将实飞、fixture、失败和未验证项分别归档。

下一前沿是[#15 单机多航点任务与取消闭环](https://github.com/unununnnn/wksim/issues/15)。MATLAB#5、首期/数值#6、联合调度/失联#8、插件/环境#9保持开放，父图#1和规格#10不关闭。[Full扩展义务](plan/full-scope-expansion.md)不删除，Goal保持active。
