# #9 厂商 DLL ABI 推迟边界与分支隔离（PROPOSED，非决策）

2026-09-14。本文与机器可读合同 `docs/plan/9-vendor-abi-defer-boundary.json`（schema `wksim.9-vendor-abi-defer-boundary.v1`）成对交付，离线自测为 `validation/test_issue_9_defer_boundary.py`。

**性质**：本记录是**提议（PROPOSED）**，`authority = proposal_only`、`effective = false`。它不是 ADR，不替代任何所有者决定：**既没有关闭也没有拒绝 #9**，#26/#29 不因它关闭，任何依赖边都不因它满足。它只做一件事：把“厂商 DLL ABI 半边推迟、原生 `wk_model_*` 路径继续可用”这条**分支隔离**写进**已跟踪**文件，使该声明不再只存在于未跟踪的协调文件中。

## 1. 检出身份（实测）

| 项 | 值 |
| --- | --- |
| HEAD | `768526aafa1e48c342c5c8840a9154e8ed90f68d` |
| 分支 / 远端 | `main`，`origin/main == 768526a` |
| 基线祖先 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0 |

## 2. 观察（证据层）

### 2.1 厂商 DLL ABI：官方来源不可得

`docs/plan/9-abi-environment-accepted.md:18-36` 与 `docs/plan/9-abi-environment-evidence.md` 记录：旧/新 ABI 均未批准，且**无可审阅对象**。本记录按 8 项 ABI 条目复核，**8/8 在官方来源中 Absent**（C 原型、调用约定、导出端 float/double 宽度、返回/错误契约、缓冲所有权与生命周期、生命周期状态机、线程隔离契约、许可与再分发权）。工程上唯一可执行的处置是**带解锁条件的推迟**；`:28-34` 的五项前置仍是唯一入口条件，缺一不可。

### 2.2 新观察到的三方地形形状矛盾（仅作阻塞项）

只读复核 `E:\rflysimtools\RflySimAPIs\RflySimSDK\ctrl\DllSimCtrlAPI.py`（SHA256 `0a2a30e91fe55590aec198f1e852a6d45d6aa34c029557de62880d0b81cf5420`，未加载、未执行、未修改）后，同一文件内地形通道出现**三处彼此不一致的形状**：

| 面 | 位置 | 观测形状 | 维数 |
| --- | --- | --- | --- |
| 包装器文档字符串 | `:783` | `ii15f` | 15 |
| UDP pack 与填充调用 | `:790`、`:795` | `ii20f` | 20 |
| ctypes 导出声明 | `:1276` | `double[15]` | 15 |

同一文件同时声称 15 个、20 个与 `double[15]`，且**没有任何来源裁决哪一个面权威**。因此该矛盾在本记录中**只登记为阻塞项**（`blocker_id = B-9-TERRAIN-THREE-WAY-SHAPE`），**不据此拒绝、不据此关闭**任何票。它阻塞的是依赖厂商通道的 #27/#28/#73/#74/#76/#77/#78；它**不阻塞** #26 与 #29。

对 wksim 原生侧的影响是 `none`：`Simulator/wksim_core/model.cpp:91` 对本方导出强制 `terrain_count != 15` 即拒绝，`Simulator/wksim_core/model.py:153-164` 同样要求 15 维。原生 `double[15]` 是**自洽**的；但“原生 `double[15]` 可映射到厂商地形通道”**仍未被证明**，本记录不作该断言。

### 2.3 原生 `wk_model_*` ABI 路径可用且已审查

`Simulator/wksim_core/model.cpp:53-94` 导出 `wk_model_create` / `wk_model_destroy` / `wk_model_initial_state` / `wk_model_step` / `wk_model_step_with_terrain`，`noexcept` 且显式返回码（`0` 成功、`1` 参数非法、`2` 模型错误、`3` 非有限状态）；`Simulator/wksim_core/model.py:113-132` 声明 argtypes/restype，`:153-184` 走地形路径。已跟踪探针 `validation/lunar-29-terrain-reset-c8f05c6e/result.json` 记录该接缝 `status=passed`（其 native I/O 为确定性 stub）。

该路径**不涉及**厂商 DLL ABI（`docs/plan/26-current-source-ac-evidence-20260912.md:177`）。两条轨的媒体文件集合不相交，记录于合同 `observed.native_vendor_isolation`。

### 2.4 票面观察（只读快照）

`gh issue view --repo unununnnn/wksim` 只读读取：`#9 OPEN [wayfinder:grilling]`；`#26/#27/#28/#29 OPEN [ready-for-agent]`；`#73 OPEN [wayfinder:task, needs-triage]`；`#74/#76/#77/#78 OPEN [wayfinder:task, ready-for-agent]`。这是**当时状态快照**，不声称未来状态，也未做任何写操作。

## 3. 所有者决定（未作出）

`owner_decision.state = not_made`，`made_by = recorded_utc = decision_text = null`。观察到的所有者证据（三条，全部 pin 到已跟踪文件）**支持推迟并支持原生路径可用**，但其中**没有任何文本表示永久放弃厂商 DLL 路径**。因此：

| 判定 | 状态 |
| --- | --- |
| 推迟（defer，带解锁条件） | **有证据支持** |
| 拒绝（reject / `wontfix` / 永久放弃） | **未决定** |
| 关闭（#9 或任一派生票） | **未决定** |
| 接受（任何一半的验收声明） | **未决定** |

合同的 `owner_decision.must_not_be_inferred_from_this_record` 逐条列出不得从本记录推断的结论。

## 4. 依赖与票面保存

| 票 | 父依赖 | 本记录的作用 |
| --- | --- | --- |
| #9 | 无 | **保持 OPEN**；两半（环境已批准侧 / DLL 未批准侧）无单一票面动作可关闭 |
| #26 | #9 | **保持 OPEN**；`open_dependency_on_9 = true` |
| #27 / #28 | #9 | **保持 OPEN**；推迟不满足依赖 |
| #29 | #9, #17, #23 | **保持 OPEN**；厂商推迟不影响环境半边 |
| #73 / #74 / #76 / #77 / #78 | #9 | **保持 OPEN**；推迟不满足依赖 |

合同 `observed.open_dependency_edges_preserved` 与 `policy.must_remain_open` 逐票固化该表；`policy.closure_class = rejection_class = not_decided` 阻止任何“已关闭/已拒绝”的解读。

## 5. 建议（未执行）

`recommendation` 全部为**建议**，`proposed_actions` 六项全为 `false`：

- **R1** 厂商 DLL ABI 半边保持带五项前置的推迟；**R2** 全部受影响票保持 OPEN；**R3** 把分支隔离写入已跟踪文档（即本文）。
- **标签建议（未执行）**：`#9` 加 `ready-for-human`（保留 `wayfinder:grilling`）；`#27/#28/#74/#76/#77/#78` 由 `ready-for-agent` 改为 `needs-info`（替代方案：沿用 `#73` 的 `needs-triage`）；`#73` 保留 `needs-triage`。
- **禁止标签**：对 `#27/#28/#73/#74/#76/#77/#78` 使用 `wontfix` —— 拒绝尚未决定。
- **评论建议（未执行）**：向 `#9` 记录官方来源可得性表与三方地形矛盾；向 `#73` 交叉引用本推迟边界。

## 6. 失败边界（fail closed）

`evidence_policy.fail_closed_on` 列出 19 类触发即拒绝的条件，由 `validation/test_issue_9_defer_boundary.py` 逐条断言。要点：

1. **精确 schema**：每一层的键集合精确匹配，未知键、缺失键、重复键均拒绝；重复键与非有限常量在解析期即失败。
2. **小写摘要**：全部 pin 的 SHA256 必须为小写 64 位十六进制；工作树字节与 **HEAD blob** 双向核对。
3. **决策性 pin 必须已跟踪**：`committed_repository_artifact` 类 pin 若未跟踪、不在 HEAD 树中、或摘要漂移，一律失败。
4. **未跟踪文件永不作权威**：`environment-acceptance.json`、本次审计报告与 `evidence.json`、`ds-interface-decision-packet`、`acceptance-frontier.json` 均登记为 `tracked = false` 的 host-bounded 缺口，只能作为上下文；宿主外部 pin 的 `authority` 必须是 `context_only`，一旦被提升为决策性即失败。
5. **无拒绝/关闭/验收声明**：布尔单位、自由文本（`claim_text`）与各动作标志共同约束；出现未经否定的拒绝/关闭/验收措辞即失败。
6. **保留开放依赖**：每个 `satisfied_by_this_defer` 必须为 `false`，每条依赖边必须 `OPEN`，受影响集合与不受影响集合漂移即失败。
7. **原生/厂商隔离**：两侧 pin 集合不得相交，原生 pin 不得指向宿主厂商路径，原生声明不得声称对 legacy 厂商 ABI 的兼容。
8. **地形矛盾仅作阻塞**：三方形状必须齐全且不得被改写为同形；其 `blocks` 只能是厂商依赖集，把 #26/#29 加入即失败。

宿主边界：若某台机器没有厂商安装，`host_external_read_only` pin 的摘要复核记为“不可核对”，但该 pin 永远只是上下文，不影响任何决策性结论。本记录不加载任何 DLL。

## 7. 非声称

未运行 native/model/UE/ROS/DDS/FC/SITL/MATLAB/构建，未触碰 #83，未加载或修改厂商 DLL 与安装，未对 GitHub 做任何写操作，未 `git add/commit/push`，未编辑任何既有文件；仅新建本文、同名 JSON 与离线自测三个文件。本记录**不**替代 #6/G6 数值预算，**不**改变 R1 `numerical_failed` 与 #20/#33 RateUnmet，**不**评估 #29 的坡面/接触动力学证明。
