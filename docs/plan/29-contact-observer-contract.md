# #29 运行时静态接触观察与陈旧反馈冻结契约 (29-contact-runtime-observer)

2026-09-11。本文是 GitHub #29 的纯几何观察与运行时冻结适配器切片交付，实现已批准的环境契约（依据 `docs/plan/9-abi-environment-accepted.md` 及 2026-09-07 用户决定）。

## 一、 场景身份与哈希固定

- **场景配置文件**：`Simulator/wksim_runtime/static-scene-v1.json`
- **坐标系与单位**：公共 ENU，单位米（metre），显式原点 `[0.0, 0.0, 0.0]`。
- **几何定义**：
  - 平面：`plane_z0`，位于 `z = 0.0` m。
  - 盒体：`box_0`，中心 `[2.0, 0.0, 0.5]` m，尺寸 `[1.0, 1.0, 1.0]` m。
- **规范几何 SHA256**：
  `60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514`
  在 `ContactObserver` 初始化时严格断言；若文件不存在抛出 `scene_not_found`，哈希篡改或不符立即抛出 `scene_hash_mismatch`，禁止启动。

## 二、 接触信封与时序绑定

- **信封规范**：严格使用 `wksim.contact.v1`：
  - `scene_id`、`scene_hash`
  - `epoch`（32 位小写十六进制字符串）
  - `step`（权威物理步，整数 >= 0）
  - `sim_time_ns = step * 1_000_000`
  - `valid_from_step`、`valid_until_step`（单权威步有效，`valid_from_step == valid_until_step == step`）
  - `body_id`、`geometry_id`
  - `contact_point_enu_m`、`normal_enu`、`penetration_m`
- **单步时效**：信封仅在声明的权威仿真步有效，严禁跨步缓存、不设墙钟续期。
- **无接触语义**：`no_contact` 是该步的有效观察，返回并保存的 `envelope` 均为 `null`；它不会伪造一个缺少接触字段但自称 `wksim.contact.v1` 的对象。
- **外部信封校验**：接触信封必须字段集合完整、场景/epoch/步号/纳秒时间一致、几何属于冻结场景、向量有限且法线为单位向量；包含额外力学字段或任一字段错位均以 `contact_invalid` 冻结。

## 三、 陈旧/错位反馈显式拒绝与冻结信号 (Freeze Contract)

依据已批准环境合同第 4、14 条款，当检测到反馈异常时，观察器执行以下安全行为：
1. **异常判定类别**：
   - `foreign_epoch`：反馈的 epoch 与运行绑定的 authority epoch 不匹配。
   - `stale_feedback`：当前步号 `step <= last_step` 或信封 `current_step > valid_until_step`（陈旧反馈）。
   - `future_feedback`：信封 `current_step < valid_from_step`（超前未决反馈）。
   - `scene_hash_mismatch`：场景哈希与已冻结基线不符。
2. **冻结转移与信号**：
   - 观察器立即置 `frozen = True`，记录 `freeze_reason` 与 `freeze_step`。
   - 记录 `event: freeze` 并返回类型化冻结信号结构：
     `{"status": "freeze", "freeze": True, "reason": <reason>, "freeze_step": <step>, ...}`
   - 在冻结解除前，后续步进查询统一返回冻结信号阻断推进，禁止静默复用任何旧数据。
3. **显式恢复**：
   - 仅在已冻结状态下接收显式恢复调用 `recover(step, body_id, point_enu_m, reason=...)`；观察器先用绑定场景在不早于故障步、且严格晚于最后已接受步的位置重新查询新鲜证据，再解除冻结并记录 `event: recover`。
   - 未冻结时恢复、向后移动水位或恢复证据无效均拒绝，不能借恢复绕过单调权威步。

## 四、 物理边界与未批准范围隔离

- **纯几何观察**：本切片仅计算并输出几何穿透深度与表面接触点/法线；
- **禁止项**：
  - 严禁计算或输出接触力、冲量、弹簧刚度、阻尼、摩擦力或扳手扭矩（wrench）；
  - 严禁在 `model.py` 或物理求解器中注入未批准的穿透动力学反作用；
  - 严禁修改 `Simulator/wksim_core/joint.py`、`worker.py` 或 `model.py`。

## 五、 交付文件与离线验证

1. 观察器模块：`Simulator/wksim_runtime/contact_observer.py`
2. 单元测试：`validation/test_contact_observer.py`
3. 契约记录：`docs/plan/29-contact-observer-contract.md`
4. 离线验证命令：
   ```bash
   python -B -m unittest validation.test_contact_observer
   ```
