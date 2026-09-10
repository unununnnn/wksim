# Claude：PX4 land 观测心跳候选（最小原生 cadence 切片）

5–15 分钟交付，**未编译、未运行 PX4/SITL/UE**；主会话审查后预约原生构建（agy 持有一次构建配额）。
本切片只交一个最小候选：同一原生 owner（LandDetector）把 VehicleLandDetected 的**最大发布间隔**
从 1s 改为 200ms；状态变化仍立即发布；不改检测算法、不重打任何 Python 缓存时间戳、不提升默认
profile、不动 2s 新鲜度检查。旧工具（home/state 构建与 sealer）**未改动**，land 工具是独立参数化副本。

## 交付物（本切片仅写这 4 个文件）

- `patches/px4/0004-land-observation-cadence.patch` — 单一 hunk：`LandDetector.cpp` 发布门槛
  `1_s`→`200_ms` ＋注释。由 git diff 规范生成；在 WSL 隔离单文件副本上通过
  `git apply --check` / `apply` / `apply --reverse --check`（应用后 :152-166 区域人工核对正确）。
- `tools/build-px4-land-cadence.sh` — 隔离构建入口：基线
  `/root/wksim-px4-state-ONa1Kw/src`（commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，只读校验），
  `mktemp -d /root/wksim-px4-land-XXXXXX` 独立 root，tar 复制（排除 build）→ apply --check → apply →
  `make px4_sitl_default` → `ldd` → seal。基线不改。
- `tools/px4_land_candidate.py` — seal/校验：root 必须匹配 `/root/wksim-px4-land-*`；完整
  `source_snapshot` 基线+候选且断言 delta == `{src/modules/land_detector/LandDetector.cpp}`；
  逆向 patch 检查；ldd 缺失/禁用依赖拒绝；枚举 bin+etc 运行时 artifact；版本化 `land-build.json`
  清单以 `'x'` 写入（绝不覆盖）；记录 patch/builder/sealer 三者 sha256。
- 本文件。

## 已实测接收间隔（原生 1Hz 未改代码，观察器原件）

来源：`tools/observe_px4_setup.py` 只观察记录，原回调/决策只跑一次。

- **02**（`validation/40-aruco-flight-scene-02/run/epochs/444400922fa742148154d1e92f6586e6/px4-setup-observer.jsonl`）：
  稳态 land 接收墙钟间隔 ≈2.000–2.002s；**最大 ≈2.0054s**（received 65.756501915→67.761937528）。
  相邻稳态 receipt 的 `timestamp_us` 步进恰为 +1,000,000us ⇒ 原生 1Hz 发布、0.5 倍率下墙钟 2s。
  COMMAND_CONTROL 决策（request_id 3，evaluated 146.978724327）：land 新鲜度 **True**，
  stale_seconds=2.0，age=**1.661430798s** ⇒ 余量仅 ≈0.339s。
- **03**（`validation/40-aruco-flight-scene-03/run/epochs/3604073ff2b94dc5938972d7cd95e092/px4-setup-observer.jsonl`）：
  同型。最大间隔 ≈2.0050s（55.657394461→57.662414510）；COMMAND_CONTROL（136.787018518）
  land age=**1.570330100s** ⇒ 余量 ≈0.430s。
- 两场均在**原始 1Hz** 代码下真实完成飞行与退出；上述只是接收间隔实测，不是任何失败的归因。

## 源码可导致（固定源静态核验，未编译）

- `src/modules/land_detector/LandDetector.cpp`（commit d6f12ad1）：发布门槛在 :156
  `hrt_elapsed_time(&_land_detected.timestamp) >= 1_s`；:157-162 的状态变化条件**绕过**该间隔
  （状态变化立即发）；:181 刷新原生 `hrt_absolute_time()` 时间戳后 :182 由同一 owner 发布；
  :43 `using namespace time_literals;` ⇒ `200_ms` 字面量合法。独立核对与派发描述一致。
- `src/modules/uxrce_dds_client/dds_topics.yaml:59-61` `/fmu/out/vehicle_land_detected`
  `rate_limit: 5.` ⇒ 200ms 恰好对齐既有 DDS 5Hz 上限，不超限。
- 机理：0.5 倍率下原生 1s 发布间隔 ⇒ 墙钟接收间隔 ≈2.0s，与控制侧固定 **2s 墙钟**新鲜度预算同量级；
  决策时刻的 land age 可逼近 2.0s（实测 1.661s/1.570s）。改 200ms 后同倍率下接收间隔 ≈0.4s，
  age 上界同量级收窄。**这仅说明源码可产生贴边间隔，不证明任何具体拒绝由它造成。**

## 旧失败尚未归因

case5 场景 01 的 `SET_CONTROL_MODE` 拒绝（`missing_home_or_landed_state`，Control FVMjak）
**不被本候选追溯解释**：01 无观察器记录，02/03 在原代码下成功。本候选只是把 land 观测的发布
余量从贴边（最差 ≈2.005s 间隔对 2s 预算）拉到 ≈0.4s 量级，供主会话决定是否构建验证。

## 边界与下一步（主会话决定）

- 未编译、未运行；未改固件基线/配置/物理/日志缓冲/门槛/预算/默认 profile；未 commit/push；未嵌套。
- `patches/px4/README.md` 登记**未做**（不在本切片写入白名单），留给主会话。
- 审查通过后由主会话预约执行 `tools/build-px4-land-cadence.sh`（agy 原生构建配额），
  产物清单 `land-build.json` 落在独立 `/root/wksim-px4-land-*` root 内。

## Sealer 强化与离线测试（第二轮，构建前）

应主会话要求修复"单文件 delta＋逆向检查不足以保证唯一实际改动"：

- `px4_land_candidate.py` 新增 `expected_patched_source()`：在临时目录把**基线
  LandDetector.cpp 原始 bytes ＋该唯一 patch** 用 `git -c core.autocrlf=false apply`
  重建出预期镜像，候选文件必须**逐字节严格相等**——该文件其它任意位置的改动
  （即使不影响逆向检查）一律 `Patched land source mismatch` 拒绝。autocrlf 显式关闭，
  身份判定不随宿主 git 配置漂移。
- 清单显式记录 `expected_sources`（目标文件预期 sha256）与 `dependency_policy`
  （`not found` 缺失拒绝、`lib(?:gz-|gazebo|ignition|matlab)` 禁用模式），产物身份为
  bin+etc 全量 `file_identity`＋二进制 sha256＋完整 ldd 列表＋build/dep 日志 sha256。
- CLI 增加 `check <manifest> --sha256 <sha>`（seal 行为不变）。
- 新增 `validation/test_px4_land_candidate.py`（12 项全过，微型真实 git 仓库夹具、
  toy patch 由真实 `git diff` 生成，不启 SITL/UE/ROS、不碰真实 PX4 源）：
  seal→check 往返（含 expected_sources/dependency_policy/artifacts 断言）、
  **目标文件远离 hunk 处篡改被拒**（本修复的回归测试）、未打 patch、额外源改动、
  基线 commit 漂移、禁用/缺失依赖、manifest 不可覆盖（第二次 seal 抛
  FileExistsError）、checksum 不符、seal 后删产物被 check 发现、root 策略、
  版本化清单名强制。

## 构建执行（本轮唯一原生构建配额，主会话授予，已完成）

- 同一后台任务（harness id `b3329n0yk`）一次完成，exit code **0**；未重复启动 builder。
  `make -j4 px4_sitl_default` 完整编译 `[1109/1109]`，链接 `bin/px4` 成功
  （build.log 尾部为链接记录）。apply 阶段的 `type 100644, expected 100755` 仅为文件
  模式提示，内容与身份判定不受影响。
- 私有 root：`/root/wksim-px4-land-7RjMjQ`（PX4 源码与二进制保留在此，未外拷）。
- Seal（构建脚本末尾自动执行）：`land-build.json`
  sha256 `45c5332cf06a84952189fcf2eabc5d2e15fde9236c704a5c3d6318e7f5dcb3ac`。
  通过项：delta == `{LandDetector.cpp}`、**expected-bytes 严格相等**（基线+唯一 patch
  重建镜像）、逆向 patch 检查、ldd 缺失/禁用依赖检查、bin+etc 产物身份。
- `check(manifest, sha256)`：`verified=true`，候选二进制
  sha256 `6b694224aaf9febda8a47c2f19575c4885ade9b63df48423795102a97eb5cb7a`，
  与对 `bin/px4` 直接 `sha256sum` 一致；check 内部重跑完整 snapshot 比对未变。
- 公开证据（x-mode 新目录，无覆盖）：`validation/px4-land-cadence-01/`
  - `land-build.json`（45c5332c…b3ac）、`build.log`（af94fdc1…7d13）、
    `dependency-check.log`（bf39356d…f0bc）、`0004-land-observation-cadence.patch`
    （5337c0a0…78ed）、`build-px4-land-cadence.sh`（56ba7c25…6673）、
    `px4_land_candidate.py`（b4097ad5…dbf87）、`test_px4_land_candidate.py`
    （a3b15fb5…a80e）。
- 未启动 SITL/UE/ROS，未做任何运行/飞行验证；默认 profile 与 sealed 基线未改。
  构建配额已交还主会话。
