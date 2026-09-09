# #109 / 45-ap-native — 原生候选完成

实际会话已从本任务 turn_context 元数据核验 `gpt-6-astra / low`，无子代理；见 model-settings.json。

## 交付与结果

- 合同：`docs/plan/45-ap-gnss-native-contract.md`。
- 候选、生成器与检查器：本目录 `SIM_WksimGNSS.h`、`build.py`、`probe.py`、`check.py`、`header_test.cpp`、`check_audit.py`、`archive.py`。
- 成功构建：`/root/wksim-ap-gnss-109-20260909-05/build/sitl/bin/arducopter`。configure/build均退出0；原始日志、完整继承diff、24592个源码文件SHA及symlink身份已归档到同名子目录。相对封存manifest只有 SIM_JSON.cpp/SIM_GPS.cpp 改动，另新增候选头文件，无缺失条目。
- 原生正例：`/root/wksim-ap-gnss-109-ground-05`，完整原件已归档至本目录同名子目录。真实AP进程处理8000个连续1ms JSON，40个原生GPS样本、259个完整UBX包（含被抑制候选）；计划前实际写6816字节，`[4000,6000)`抑制4260字节且实际写0，恢复后实际写4686字节。tick4000/6000均有原始传感器/字节记录；position/IMU/velocity/quaternion保持完整固定地面真值。父进程确认最后一帧后TERM，原生退出0，无强杀。
- 主GPS三次启动代次分别在tick10/1945/3165记录。每代一次空历史样本拒绝；计划内与恢复段均使用第3代的新鲜采集来源，没有重打GPS源时间。4000/6000 tick对应延迟端点3800/5800ms与HAL3999000/5999000us，原始质量为有fix、10星；UBX TOW独立解码保留。
- 13项原生C++逻辑检查通过，零跳过（tests-04）。4项真实AP拒绝负例通过，均在注入错误后退出109：错run、错epoch、重复tick、错误timestamp。6项原始证据篡改负例全部被审计拒绝：缺终态、换epoch、删tick、删整组GPS写入、中断区间实际写入、损坏UBX字节。合计23项检查及1场原生地面正例，逻辑夹具与真实原生证据分开。

## 身份

- 正例run：`0e65ceb5f42a404f90ed88132547a221`；epoch：`9850414f2cf54a119d4b720f1adcdcb9`；vehicle=1。
- 二进制SHA256：`48062a2cc8f73c502174561c544730e9adc736b77819a513c48f40eab0c94478`。
- 参数SHA256：`dabd5c6a0af2bace7c031c360db697567daa49c530c7bbc6f46f7683668bc53f`。
- 候选头SHA256：`67a70a07f379e096670355e551ca7d79539be10593177b1462b74b21576d53a9`。
- 运行器SHA256：`beb9446a5477837ffb1238aef0c3ef20bbe73f8ae57c2bfaa48b2a0c052a5c87`。
- 基线AP提交：`1511f27194f1dcc3728270883047bdf022b3fd53`；包含已有DDS/整数时钟/退出补丁，完整差分与源码清单见构建归档。封存原生源未修改。

## 准确命令

从wksim根在WSL Ubuntu-22.04/root执行（Windows入口是在下列命令前使用 `wsl -d Ubuntu-22.04 -u root --`）。所有case目录均新建；重查已有结果可直接读审计与哈希，重跑必须另取新目录。

```bash
python3 validation/45-ap-gnss-candidate/build.py /root/wksim-ap-gnss-109-20260909-05
python3 validation/45-ap-gnss-candidate/check.py /root/wksim-ap-gnss-109-tests-04
unshare --net --ipc --mount --propagation private bash -c 'ip link set lo up && mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm && exec python3 validation/45-ap-gnss-candidate/probe.py /root/wksim-ap-gnss-109-20260909-05 /root/wksim-ap-gnss-109-ground-05'
unshare --net --ipc --mount --propagation private bash -c 'ip link set lo up && mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm && exec python3 validation/45-ap-gnss-candidate/probe.py /root/wksim-ap-gnss-109-20260909-05 /root/wksim-ap-gnss-109-negative-run-01 --fault run'
unshare --net --ipc --mount --propagation private bash -c 'ip link set lo up && mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm && exec python3 validation/45-ap-gnss-candidate/probe.py /root/wksim-ap-gnss-109-20260909-05 /root/wksim-ap-gnss-109-negative-epoch-01 --fault epoch'
unshare --net --ipc --mount --propagation private bash -c 'ip link set lo up && mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm && exec python3 validation/45-ap-gnss-candidate/probe.py /root/wksim-ap-gnss-109-20260909-05 /root/wksim-ap-gnss-109-negative-duplicate-01 --fault duplicate'
unshare --net --ipc --mount --propagation private bash -c 'ip link set lo up && mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm && exec python3 validation/45-ap-gnss-candidate/probe.py /root/wksim-ap-gnss-109-20260909-05 /root/wksim-ap-gnss-109-negative-timestamp-01 --fault timestamp'
python3 validation/45-ap-gnss-candidate/check_audit.py /root/wksim-ap-gnss-109-ground-05 /root/wksim-ap-gnss-109-audit-tests-01
```

每场manifest保存完整ArduCopter argv、参数SHA、run/epoch、PID/proc stat/boot_id、退出码；native.tsv保留JSON原文hex、GENERATION、GPS_Data、WARMUP、WRITE原包与写入返回值。wire.jsonl保留实际UDP输入/输出。archive-hashes.json固定归档原件。篡改副本仍在audit-tests-01的WSL目录，仓库保留生成器、原件及6项结果，未污染正例。

## 失败历史和边界

- build-01：浮点直接比较触发AP的`-Werror=float-equal`，退出1；日志与候选头已保留。后续改为原生浮点检查。
- ground-01 / build-02：tick201、HAL200000、延迟timestamp0，退出109。确认GPS更新在stop_clock前，候选改用模型真值tick调度并分别记录HAL相位。
- ground-02 / build-03：tick1946空历史，退出109。确认backend启动时刻不固定，后续冻结整数200ms生成网格。
- ground-03 / build-04：tick2000同实例出现新空历史，退出109。实读串口工厂确认重开会创建新GPS对象；候选新增真实代次身份及计划开始后的重建拒绝。
- ground-04 / build-05：tick4385自动探测重开串口，退出109。保护保持启用；随后按AP_GPS原生探测条件冻结 `GPS1_TYPE=2/GPS_AUTO_CONFIG=0/GPS_DRV_OPTIONS=4`，在新ground-05验证成功。旧参数和失败原包保留。
- 首次归档器把2个目录symlink误列为missing；后续归档显式处理symlink，最终构建清单无missing。最初记录未重写。

候选仅支持封存版本、规范化本地JSON、5Hz主UBLOX与本票固定计划/预算。原生SerialDevice写入证明模拟串口buffer接受字节，不证明GPS驱动消费/定位恢复。地面真值是固定输入夹具，未执行解锁或飞行；不宣称#45、#112、#121、R1、RateUnmet、Full或G0–G6通过。资源和进程均按新case隔离，没有全局WSL关停或按名称清理。

本子票两项完成条件均已有原生候选、准确命令、逐包原始证据、源码/配置身份、检查结果和失败边界；只更新/关闭#109。

收尾复核：112个归档文件逐一重新计算SHA256，全部匹配各case的archive-hashes.json；当前候选头及probe.py SHA与真实正例manifest一致。Git只暂存本票合同与专用证据，排除Python缓存。
