# DS-D · ds-model-closure-20260912 历史语境绑定与取代登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时 HEAD `cc42c19f1b06538cf5bfd326d7dcd11f7b1ed6a5`。

## 0. 本文件的地位

本文件只做两件事：把下述历史文件**按字节绑定**为历史语境，并登记其后的取代事实。它自身不构成 #26 的验收、批准、收口或复核记录；被绑定的历史文件同样**不再**构成这些。一切"当前是否满足/是否可关闭"的判定必须由当前权威（主代理/主会话/人类裁决）基于**当下**的工件重新作出。

## 1. 历史语境绑定（字节级）

| 项 | 值 |
| --- | --- |
| 被绑定文件 | `docs/coordination/ds-model-closure-20260912.md` |
| SHA256 | `a869117ff88c3e594fb44240b8970ee463aaedd39dca67e578b80f03dbe51d28` |
| 大小 | 15346 bytes |
| 写作时其 HEAD | `7126d4d774a33c7d4b2504b9931a93ac27d7fa51`（已验证为当前 HEAD 的祖先，`git merge-base --is-ancestor` exit 0） |
| 性质 | **历史语境（historical context only）**。DS-D 槽在 2026-09-12 对清单 pin 的只读交叉核验快照 |

**非权威声明**：该文件的任何结论、条件（§5 条件 A–E）、判定表或"收口条件"均**不**是当前的权威、批准、验收或收口状态。引用它只能作为"当时观察到了什么"，不能作为"现在是什么状态"。其 §7"明确不得据此声称的结论"对**以它为依据**的任何后续声称继续适用。

## 2. 经本次复核仍然稳定的事实（read-only 重算，HEAD `cc42c19f`）

### 2.1 六个清单 pin（`docs/plan/26-closure-readiness-manifest.json` acceptance_evidence，6/6 命中）

| 清单验收项 | 路径 | SHA256（重算=pin） |
| --- | --- | --- |
| source_chain | `docs/2026-09-10-generated-e0-lifecycle.md` | `60a223620e7fc96b519bfa383fd1712c40386b99ed5812f6d2262c3b644a3d7a` |
| source_chain | `validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json` | `85c40213cec0f349d36664c5621bb53c46ad96f9756cdd4eaa2bb97a7b2acc67` |
| matlab_license_actual_checkout | `validation/codegen-e0/short-cycle-codegen-01/codegen-report.json` | `e5f32bd2890137591b61eba72fe0b21893fef578fd0a57094baf8fe92398f822` |
| matlab_free_lifecycle | `validation/codegen-e0-lifecycle-01/audit.json` | `3d5c7896de10d10521ff4a1881eaffc8c96e73b196be72f9a044f2fc1aed346d` |
| vendor_materials_controlled | `validation/codegen-e0/short-cycle-codegen-01/summary.json` | `42bc11a2a55fc26542cb52d34fc22d7ae8b3c6fc66deec19708aa232eb910f7c` |
| delivery_identity | `validation/codegen-e0-build-short-cycle-01/build-manifest.json` | `0669730aeff54012e70c55e8fc1d103cfeb00cc33ec5b3147144df847fc7aa1c` |

### 2.2 三个生成源码 pin（`work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw/`，3/3 命中）

| 生成文件 | SHA256（重算=pin） |
| --- | --- |
| `Exp1_MinModelTemp.cpp` | `2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274` |
| `Exp1_MinModelTemp.h` | `7601dbd721f0502e4bd67758d86cc21abf8e5c9568a31fb3160283df1df8c4bc` |
| `rtwtypes.h` | `1b08664b70d40d08ee2952ca47254bd16a9e045be8b5edc9781fe620fb7c199f` |

### 2.3 wrapper `model.cpp` 自 `7126d4d7` 起未变

- `Simulator/wksim_core/model.cpp` 当前 SHA256 `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290`，4070 bytes。
- `git log 7126d4d7..HEAD -- Simulator/wksim_core/model.cpp` 为空：其后无提交改动该文件。
- `git show 7126d4d7:...` 与 `git show HEAD:...` 导出重算均为 `150ddf3b…`，与工作树一致。
- 注意：清单 pin 的 wrapper 仍是旧版 `3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c`（1864 bytes）。**pin 与当前 wrapper 不同**这一点本身仍是稳定事实，但其处置已由 §3 取代项 2 完成。

## 3. 取代登记（supersessions）——以下各项取代历史文件的对应表述

1. **full-acceptance-report 已存在**：历史文件称 `docs/plan/full-acceptance-report.md` "当前不存在"。现已存在并入库（SHA256 `daded67206356478badc508cb9a72544054bf7a0c69dff5477042c77c1caf514`，31086 bytes，写作时点值）。历史文件 §7"不得用本文件替代 full-acceptance-report"所指的缺口已被该报告填补；历史文件不再充当任何替代品。
2. **条件 B 已被执行并分离**：历史文件 §5 条件 B（当前 wrapper 与生命周期重核，B1/B2 二选一）所指的 current-wrapper 处置**已执行**，并产生**独立入库的 current-wrapper 证据**：`validation/codegen-e0-build-current-wrapper-01/` 与 `validation/codegen-e0-lifecycle-current-wrapper-01/`（两目录共 22 个 git 跟踪文件）。旧 `.so`（`7da68532…`，87312 bytes）身份未因此改写；新证据另立身份——这正是历史文件条件 B 要求的分离。
3. **条件 E 的映射已大体供给**：历史文件 §5 条件 E（子票→父 AC 映射表）所要求的映射，已由 `docs/plan/26-current-source-ac-evidence-20260912.md`（SHA256 `4070bf4bdb87e60a9ad1eb45d8f1512e2bdfbf060cba3e9d94ec13dbbb544a79`，写作时点值）大体供给。"子票关闭不等于父票 AC 全满足"的原则仍适用。
4. **`68c6965b` 是行尾伪影**：历史文件 §3.2 记录的 HEAD 内容哈希 `68c6965bb52c37afb68c6881ba948787b701698a9f3ae85f509c6694a29ff2d5` 是当时 `git show` 导出环节的**行尾转换伪影**，不是文件内容身份。当前导出与工作树一致为 `150ddf3b…`（§2.3）。任何引用"两个 wrapper 哈希（150ddf3b 与 68c6965b）"的表述应更正为"只有一个当前 wrapper 身份 `150ddf3b…`；`68c6965b` 无对象"。

**取代路径**：历史文件条件 B → 上述 current-wrapper 证据目录 + full-acceptance-report；条件 E → `26-current-source-ac-evidence-20260912.md`；§3.2 的 `68c6965b` → 本文件 §3.4；"报告不存在" → `docs/plan/full-acceptance-report.md`。

## 4. 仍开放的观察项（要求当前权威处置；不是决定，也不是已解除）

以下来自历史文件的观察**仍然开放**，本文件仅登记，不裁决：

- **A · 合同阻塞结论的显式处置**：`26-generation-contract.md` 的 `blocked_source_authorization_and_generation_entry` 是否已解除/仍有效，需要带 superseded/retained 标记的显式处置。**仍缺**该标记。历史文件条件 A 未被本文件关闭。
- **C · 主代理 AC5 复核记录**：#26 AC5 要求的具名主代理复核工件（被复核 pin 清单、结论、复核者、时间）。历史文件自陈其非主代理复核；**本文件同样不是**。仍需当前主代理产生。
- **D · 形式依赖（#9）**：清单交付侧的形式依赖状态需以**当下**实时查询为准；本文件不引用任何时点的 GitHub 状态作为 timeless 事实，也不据此判定依赖已解除或仍阻塞。任何解除需人工裁决或书面替代决策（如 native `wk_model_*` C ABI 路线替代）。

上述三项的处置权在当前权威（主代理/主会话/人类），不在本文件，也不在被绑定的历史文件。

## 5. 后续离线测试 seam（offline-test seam）

后续任何离线复核可按以下步骤重演本文件的绑定与取代判定，无需网络、无需执行模型/MATLAB/构建：

1. **字节绑定**：`sha256sum docs/coordination/ds-model-closure-20260912.md` == `a869117f…be51d28` 且 size == 15346。若不等，则绑定失效，需重新建立。
2. **六个清单 pin**：对 §2.1 六个路径重算 SHA256，逐一等于表列值（6/6）。
3. **三个生成源码 pin**：对 §2.2 三个 `work/…/Exp1_MinModelTemp_ert_rtw/` 文件重算，逐一等于表列值（3/3）。
4. **model.cpp 不变性**：`sha256sum Simulator/wksim_core/model.cpp` == `150ddf3b…`；`git log 7126d4d774a33c7d4b2504b9931a93ac27d7fa51..HEAD -- Simulator/wksim_core/model.cpp` 为空；`git show 7126d4d7:Simulator/wksim_core/model.cpp | sha256sum` == `150ddf3b…`。若哈希变化，说明 wrapper 自 `7126d4d7` 后首次漂移，需重开 current-wrapper 处置。
5. **祖先关系**：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 与 `git merge-base --is-ancestor 7126d4d774a33c7d4b2504b9931a93ac27d7fa51 HEAD` 均 exit 0。
6. **取代工件存在性**：`docs/plan/full-acceptance-report.md`、`docs/plan/26-current-source-ac-evidence-20260912.md` 存在且被 `git ls-files` 跟踪；`git ls-files validation/codegen-e0-build-current-wrapper-01/ validation/codegen-e0-lifecycle-current-wrapper-01/` 非空（写作时 ≥22 个文件）。
7. **非权威措辞检查**：本文件与被绑定文件不得在任何后续文档中被表述为 "acceptance"、"approval"、"closure"、"accepted by"、"closes condition A/C/D" 等权威措辞；条件 A/C/D 只能以"开放观察项，待当前权威处置"的措辞引用。

任何一步失败均表示本登记过期，应以当时权威的工件重建登记，而不是沿用本文件结论。

## 6. 边界

- 本文件为只读核验产物：未修改被绑定文件、清单、合同或任何既有共享文档；未运行模型、验证器、构建；未读取厂商字节；未查询实时 GitHub 状态（§4-D 刻意如此，以免快照被当作 timeless）。
- 本文件创建后即成为静态工件；其 SHA256 与行数在交付报告中给出，后续以此检测自身是否被篡改。
