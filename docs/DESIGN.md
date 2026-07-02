# Jarvis-Agent 系统设计文档

状态：v1.2 草案（设计基线）
日期：2026-07-02
变更：
- v1.2 新增 §9 数据飞轮（会话历史全保真保留 → 提炼 → LoRA 微调 → 能力内化 → 上下文租金削减）；里程碑/风险章节重编号为 §10/§11，新增里程碑 M6。
- v1.1 依据《Claude Code from Scratch》(mini-claude) 教程评审（`docs/reviews/2026-07-02-claude-code-from-scratch.md`）合入 17 项采纳标准：Agent Loop 纪律、系统提示词工程（§3.3 新增）、子智能体（§3.4 新增）、上下文压缩管线 T0–T5、记忆/技能库、权限"模式×规则"、Plan-mode 关口、"剧本 + 记账"编排原则、里程碑重切与测试三层法。
范围：本文档整合并升级现有零散文档（README、ARCHITECTURE、ROADMAP、CODEBASE_INDEX_DESIGN、AGENT_EVENT_PROTOCOL、TUI 系列），给出 Jarvis-Agent 从 "TUI + 索引器脚手架" 走向 "自主 HEP 包解析 Agent" 的完整系统设计。重点覆盖五个子系统：**上下文工程（压缩）**、**信息系统**、**Local 运行时系统**、**Tool 系统**、**数据飞轮（会话保留 → 微调内化）**，以及把它们串起来的端到端流水线。

本文档不含实现代码；接口以契约形式描述，字段名与 schema 为设计草案。**工程级规格（模块布局、接口签名、数据 schema、算法步骤、文件级工作分解）见配套的 `docs/TECH_DESIGN.md`**——概念取舍以本文档为准，实现细节以 TECH_DESIGN 为准，两者冲突时先修文档再动代码。

---

## 1. 使命与验收场景（North Star）

### 1.1 使命

> 给定一个未见过的高能物理程序包（源码 tarball / git 仓库），Jarvis-Agent 能在本地深度解析其设计结构（构建系统、可执行入口、输入输出契约），并**自主生成一份可运行的 Jarvis-HEP 扫描配置（Calculator Module YAML）**，使 Jarvis-HEP 能直接调用该程序包完成参数空间扫描。

"自主" 的准确定义：Agent 驱动全部阶段（侦察 → 解析 → 生成 → 验证），人只在明确定义的关口（执行权限、物理映射低置信项、最终采纳）做批准与裁决；Agent 不得靠猜测填充任何配置字段（见 §8.5 反幻觉规则）。

### 1.2 目标产物解剖

目标产物即 Jarvis-HEP 的扫描配置。以现存的人工范例
`Jarvis-Examples/NMSSM/bin/NTools.yaml`（包装 NMSSMTools_6.2.0）为基准，一份完整产物包含：

| YAML 段 | 内容 | Agent 需要的知识来源 |
| --- | --- | --- |
| `Scan` | 扫描名、`save_dir`（`&J` 宏） | 用户意图 + 项目约定 |
| `Sampling.Variables` | 物理参数 + 先验分布（Flat/Normal…） | 用户物理目标 + 包输入参数清单 |
| `Sampling.LogLikelihood` | 似然表达式（如 `LogGauss(mHSM, 125.09, 3.0)`） | 用户物理目标 + 输出可观测量清单 |
| `EnvReqs` | OS / 依赖检查 | 包构建探测结果 |
| `Calculators.Modules[].installation` | 安装命令序列（`cp / make init / make`） | 构建系统解析 |
| `Calculators.Modules[].initialization` | 每次运行前的准备命令 | 样例工作流解析 |
| `Calculators.Modules[].execution.commands` | 运行命令（如 `./run NMSSMTools_inp.dat`） | 入口/脚本解析 |
| `execution.input[]` | 输入文件 + SLHA `block/entry` ↔ 变量映射 | 样例输入文件 + 注释 + 领域知识 |
| `execution.output[]` | 输出文件 + 提取的可观测量（xSLHA） | 参考运行的真实输出解析 |

关键难点全部集中在**映射类知识**上：`LAMBDA ↔ EXTPAR 61`、`Omegah2 ↔ ABUNDANCE 4` 这类事实必须有出处（样例文件注释、文档、一次真实运行的输出），不能由模型凭记忆生成。整个系统设计围绕 "让这类事实可采集、可存储、可引用、可验证" 展开。

### 1.3 验收基准（Benchmark）

| 基准 | 输入 | 通过标准 |
| --- | --- | --- |
| B1 Eggbox（冒烟） | Jarvis-Examples/Eggbox（纯函数型，无外部包） | 生成配置一次通过 schema 校验并跑通 1 个采样点 |
| B2 NMSSMTools（主基准） | `deps/NMSSMTools_6.2.0.tgz`，不给 Agent 看 `NTools.yaml` | 生成配置可完成安装 + 单点运行，`output` 变量非空提取；与人工版 `NTools.yaml` 的 diff 仅剩物理选择差异（变量范围、可观测量取舍） |
| B3 迁移性 | 一个未预置 profile 的 SLHA 类程序包 | Phase A–D 流水线完整走通，低置信项正确升级为人工确认 |

---

## 2. 现有文档 Review 结论与差距

### 2.1 现状盘点（已具备）

| 能力 | 现状 | 所属文档 |
| --- | --- | --- |
| 双 TUI（Textual + plain），共享命令路由 `TerminalUI.dispatch` | 完成，含流式渲染、历史、Stop 控制 | TUI_DESIGN、TUI_udpate_plan |
| UI 无关事件协议 `jarvis_agent.protocol`（v1，冻结 dataclass + EventBus） | 完成 | AGENT_EVENT_PROTOCOL、ADR-0001 |
| 代码索引：Tree-sitter（Python/C++）符号 + 引用，JSON 缓存、哈希增量 | 完成 | CODEBASE_INDEX_DESIGN |
| MLX 本地模型：`mlx_lm.generate` 单发子进程 | 可用但每次冷加载、无流式、无会话 | ARCHITECTURE |
| YAML 轻量审查（语法级）、`/explain` 提示构造 | 完成（浅层） | README |
| 会话历史 JSONL（仅可视转录，不回注上下文） | 完成（浅层） | README |
| 意图检测：关键词 → 单一 `[ACTION: INDEX]` | 原型 | ARCHITECTURE |

### 2.2 差距（本设计要补的层）

1. **没有 Agent Loop**：现在是 "一问一答 + 单个动作标记"，没有 计划 → 工具调用 → 观察 → 迭代 的循环。protocol 事件已就绪但无真实生产者。
2. **没有工具系统**：模型无法读文件、跑命令、查索引；`/index`、`/yaml` 是用户手动命令，不是模型可调用的工具。
3. **没有上下文管理**：`max_tokens=2048` 硬编码、上下文表仅是 UI 估算、无压缩/外置/恢复机制；多轮之间模型完全失忆。
4. **信息系统只有 L1**：有代码符号索引，但没有包级结构化知识（构建方式、IO 契约、参数映射），也没有 Jarvis-HEP schema 知识库。索引语言缺 Fortran——而 NMSSMTools、SPheno 等主力 HEP 包是 Fortran。
5. **没有受控执行**：解析构建系统、参考运行、验证配置都需要跑外部命令，目前完全缺位（ROADMAP Phase 3 已列出方向）。
6. 已知糙边：`~/.jarvis/agent_state.json` 静默覆盖 TOML（ARCHITECTURE 自认）、索引引用全量重建、上下文表不反映真实窗口。

结论：TUI / 协议 / 索引三块地基是好的；缺的正是本设计四大子系统 + 流水线这一层。

---

## 3. 总体架构

### 3.1 分层

```
┌────────────────────────────────────────────────────────────┐
│  呈现层   Textual TUI / plain TUI     （已有，仅消费事件）      │
├────────────────────────────────────────────────────────────┤
│  协议层   jarvis_agent.protocol       （已有，v1 事件 + Bus）   │
├────────────────────────────────────────────────────────────┤
│  Agent 层  AgentLoop：计划/工具调度/观察   ← 新增（§3.2）        │
│           ContextManager：预算/压缩/恢复  ← 新增（§4）          │
├────────────────────────────────────────────────────────────┤
│  能力层   ToolRegistry + 各 Tool          ← 新增（§7）          │
│           信息系统 L1/L2/L3               ← 扩建（§5）          │
├────────────────────────────────────────────────────────────┤
│  运行时层  ModelRuntime（持久 MLX 服务）    ← 重建（§6.1）        │
│           ExecutionGateway（受控执行）     ← 新增（§6.2）        │
│           Storage（~/.jarvis + 项目 .jarvis）（§6.3）           │
└────────────────────────────────────────────────────────────┘
```

在上述运行时分层之外还有一条**离线回路**：数据飞轮（§9）横跨所有层收集模型调用轨迹与结果信号，训练产物（LoRA adapter）经运行时层（§6.1）回注，内化兑现为上下文注入的削减（§9.4）。

设计不变量（继承并强化现有 Design Rules）：

- 模型调用只经 `ModelBackend` 契约；外部命令只经 `ExecutionGateway`。
- **一切持久决策落文件，不落聊天记忆**（dossier / task frame / journal）。
- 生成的 YAML 在通过验证前永远是 "提案"。
- 默认完全本地、离线；联网是显式工具且默认关闭。
- UI 永不实现业务逻辑：AgentLoop 产事件，TUI 只渲染。

### 3.2 Agent Loop

单轮结构（事件均走既有 protocol）：

```
UserPrompt
  → ContextManager.assemble()          # §4：按预算组装 messages
  → ModelRuntime.chat(messages, tools) # 流式
      ├─ AssistantTextDelta*           → TUI
      └─ tool_call                     → ToolRegistry.dispatch
             ├─ ToolCallStarted / LogLine / ToolResult → TUI
             └─ result digest 回注下一轮 messages
  → 循环直至无 tool_call 或达步数/预算上限
  → AssistantTextEnd + Metrics
  → ContextManager.settle()            # 蒸馏、外置、必要时压缩
```

循环纪律（首要原则：**模型决定下一步，代码只记账**——不要用代码状态机替模型做流程决策，行为问题优先改提示词而不是加代码）：

- **终止条件**：模型响应不含 tool_call 即视为本轮任务完成，循环自然退出；不设 "完成标记" 之类的额外协议。
- **消息对纪律**：每次迭代恰好追加一对消息（assistant 含 tool_call + user/tool 含结果），结果以 id 与调用严格配对；上下文压缩**只允许发生在轮边界**（用户消息已追加、API 调用未发出之间），绝不孤儿化 tool_call 对。
- **错误扣留**：可恢复错误（限流、网络、输出截断）在循环内静默退避重试（指数退避 + 抖动，见 §6.1），只有持续失败才以 `Error` 事件上浮。
- 每轮工具调用步数上限（默认 24 步）与墙钟上限，超限必须产出 "当前状态 + 未竟事项" 写入 task frame 后停下。
- `StopRequested`（TUI_udpate_plan 已规划的控制事件；2026-07-02 代码审计确认**尚未实现**，随 M0 的取消令牌一并落地，见 TECH_DESIGN §13.1）在任意 await 点生效：终止流、终止子进程（gateway 负责）、保留部分结果。
- 现有 `[ACTION: INDEX]` 标记机制退役，由真实 tool-calling 取代；关键词意图检测保留为无工具后备路径。

### 3.3 系统提示词工程

P0 分区（§4.1）的内容不是一段散文，而是**七层递进结构**（先建立的概念成为理解后文的框架）：

```
1 身份        Jarvis-Agent 是什么、为谁服务、硬边界（本地、离线、不碰未验证事实）
2 环境        {{cwd}} {{date}} {{platform}} {{git 分支/状态}} —— 模板占位符动态注入
3 做事方式    流水线阶段语义、dossier/task frame 的地位、反幻觉规则（§8.5）
4 行动准则    爆炸半径框架：可逆性 × 影响面 两维评估代替穷举规则
5 工具用法    工具偏好映射（fs_read 而非 cat、slha_read 而非手写解析）、并行规则
6 语气与风格  面向物理学家的简洁中文、引用带 path:line
7 输出效率    digest 纪律、不复述工具原文
```

关键手法（自 mini-claude 评审采纳）：

- **反模式接种**：对已知坏行为写显式禁令（"不要顺手重构无关代码"、"不要在未读 dossier 时臆断 block/entry"），负面指令比正面劝导少留自我合理化空间。
- **爆炸半径框架**：教模型判断而非查表——只读操作自由；可逆写入（dossier/proposals）低门槛；不可逆/出项目根的操作必须走关口。
- **项目指令文件 `JARVIS.md`**：从 cwd 向上层级发现（近者优先），支持 `@include` 引用与 `.jarvis/rules/*.md` 自动加载；用户/课题组用它注入包偏好、集群约定、物理惯例。
- **Recency 位**：记忆索引、技能清单、当前任务帧渲染在提示词尾部，吃 LLM 的 recency bias。
- 第 1–3 层会话内恒定（prompt cache 稳定前缀）；4–7 层随配置低频变化；动态注入只进第 2 层与尾部。

### 3.4 子智能体（fork-return）

**在 32K 实用窗口下，子智能体是第一级上下文杠杆**：把高工具流量的子任务隔离到独立上下文，主线程只收结果摘要。

- 形态：`agent_spawn(description, prompt, type)` 工具；子代理 = 换配置的同一 Agent 类实例，**上下文完全隔离**（独立消息史、独立 token 计数），产出经 outputBuffer 收集，返回 {文本摘要, token 用量}，用量归并进父账单。
- 内建类型：`explore`（只读工具集，快扫代码）、`plan`（只读 + 结构化方案输出）、`general`（全工具减 `agent_spawn`——**禁止递归嵌套**）；HEP 定制类型放 `.jarvis/agents/*.md`（YAML frontmatter：name/description/allowed-tools），项目级覆盖用户级。
- 纪律：子代理 prompt 必须**自包含**（它看不见父上下文）；权限模式继承父级（plan 模式必须向下传播）；子代理失败返回错误字符串，父级模型决定重试策略，不崩主循环。
- 典型用法（§8）：Phase B 的构建探测、IO 映射实验各自 fork 出去跑，主线程只拿 "dossier 已写入 + 一段 digest"；串行 fork-return 即可，不做 Coordinator/Swarm（本地单模型实例无并行收益，共享状态复杂度不值——mini-claude 的同款裁剪）。

---

## 4. 上下文工程（压缩）系统

**这是本地小模型场景的生死线。** 设计假设：Qwen3-Coder-30B-A3B-4bit（MoE，激活 3.3B）经 MLX 本地推理；模型原生窗口很大（256K 级），但 Apple Silicon 上 KV cache 内存与预填充速度决定了**实用窗口按 32K 设计、64K 为上限档**。所有机制以 "32K 也能完成 B2 基准" 为设计目标。

### 4.1 预算分区（Token Ledger）

每轮组装上下文时按固定分区记账（32K 档参考值）：

| 分区 | 预算 | 内容 | 稳定性 |
| --- | --- | --- | --- |
| P0 系统 + 工具 schema | ~2.5K | 身份、规则、工具定义（精简 JSON schema） | 会话内不变（利于 KV/prompt cache 前缀复用） |
| P1 任务帧 Task Frame | ~1.5K | 目标、当前阶段、计划、未决问题、关口状态 | 每阶段更新 |
| P2 知识注入 | ≤8K | 从信息系统检索的带引用片段（§5.4） | 每轮按需变化 |
| P3 对话尾部 | ≤12K | 最近 N 轮原文（含工具结果摘要） | 滚动 |
| P4 生成预留 | ≥6K | 模型输出 + 工具调用参数 | — |

分区顺序即 messages 前缀顺序，P0 恒定、P1 低频变化，最大化 `mlx_lm.server` 的 prompt cache 命中（§6.1）。**Token 记账以 server 每次返回的真实 usage 为准**（`lastInputTokenCount` 回填 ledger），字符估算（≈4 字符/token）仅作组装前的预判兜底。

### 4.2 压缩管线（T0–T5 分层升级）

采纳 mini-claude 的 "先便宜后昂贵" 升级管线（其 4 层针对 200K 窗口；此处按 32K 重定标），每次 API 调用前按序评估：

| 层 | 触发 | 动作 | 可逆性 |
| --- | --- | --- | --- |
| T0 执行期截断 | 单结果超长（>50K 字符） | **保头保尾**（头部含结构、尾部含报错——编译错误多在末尾），中缝插截断标记 | 不可逆，故必须与 T1 配合 |
| T1 大结果落盘 | 单结果 > 1K token 摘要预算 | 全文写 `.jarvis/artifacts/`（含哈希与元数据），上下文只留 digest + `artifact://<id>`；`artifact_read(id, range)` 二次拉取 | 完全可逆 |
| T2 预算收紧 | 利用率 > 50% / > 70% | 单条工具结果预算 1K → 512 → 256 token 逐级收紧，每次调用前重算 | 可逆（工件仍在） |
| T3 重复读去重 | 利用率 > 60% | 同一文件的旧读取替换为 `[已换出，可重读]` 占位（调用元数据保留），只留最新一份；最近 3 条工具结果永不动 | 可逆（可重读） |
| T4 空闲微压缩 | 空闲时长超过 prompt cache 生命期 | cache 反正已失效、保留旧结果无成本优势：清除除最近 3 条外的全部旧工具结果，元数据保留 | 可逆（可重取） |
| T5 自动压缩 | 组装后预计占用 ≥ 80% | 最老跨度蒸馏为**结构化摘要块**（schema 见下）；仅在轮边界执行（§3.2 消息对纪律），保留最近 4–6 轮原文 | 不可逆，故有 schema 强制 |

摘要块 schema 固定：

```
decisions:   [做过的决定 + 理由一行]
facts:       [学到的事实 + 出处 path:line / artifact id]
state:       [当前所处阶段、已完成步骤]
pending:     [未竟事项、被阻塞项]
discarded:   [被驱逐的可重取项引用清单]
```

驱逐总原则（贯穿 T2–T5）：

- **可重取优先驱逐（re-derivable first）**：文件内容、索引结果、命令输出驱逐时降级为一行引用，随时可再取；用户指令、用户裁决、关键决策只能进摘要块，不得丢弃。
- **元数据比数据长寿**："做过什么"（调用名 + 参数 + 结论一句）比 "返回了什么" 保留得更久——模型永远可以重新执行工具。

### 4.3 结构性机制（与管线正交）

**S1 状态外置（Externalization）。** Agent 的长期工作状态不依赖转录存活：Task Frame `.jarvis/tasks/<task-id>.md`（目标/计划/阶段/未决）每轮渲染进 P1；知识沉淀一律写 dossier（§5.2），**上下文里的 dossier 内容永远是投影，不是母本**。这使 T5 压缩低风险：压掉的要么可重取、要么已落盘。

**S2 会话恢复。** `/resume` 语义：不回放原始转录，而是 `P0 + 最新 Task Frame + 最后一个摘要块 + 最近数轮`——恢复成本与会话长度解耦。另存一份消息数组快照供快速续聊路径。

**S3 检索代替堆料。** 禁止整文件入上下文：`fs_read` 强制行区间与字节上限；代码引用以 `path:line` 片段进 P2，展开靠再次调用工具；P2 硬预算内按相关度截断。

### 4.4 量化守则（写进系统提示与 ContextManager 断言）

- 单条工具结果进入上下文 ≤1K token（T2 触发后逐级收紧）；
- P2 注入片段每条必须携带出处（path:line 或 artifact id）；
- 压缩后 "decisions/pending" 两栏不允许为空的静默丢弃；
- 压缩/换出只发生在轮边界，tool_call 对永不拆散；
- 每轮组装完成后向 UI 发 `Metrics`（真实分区占用 + 真实 usage），替换现在的估算式上下文表。

---

## 5. 信息系统

三层结构，检索统一从一个门面进出。**核心新增物是 L2 Package Dossier（包档案）——它是 "解析" 与 "生成" 之间唯一的桥。**

### 5.1 L1 代码索引（扩建现有实现）

保持 CODEBASE_INDEX_DESIGN 的 JSON + 内存模型与增量哈希机制，扩展：

1. **语言覆盖**：新增 `tree-sitter-fortran`（fixed/free form；NMSSMTools、SPheno 类包的主体），以及 Makefile / CMakeLists 的目标与变量抽取（`make` 目标名、编译产物名是 installation 段的直接原料）。
2. **文件分类器**：索引时为每个文件打角色标签：`source / build-script / run-script / sample-input / sample-output / doc / data / config`。判据：路径惯例（`SAMPLES/`、`bin/`、`doc/`）、扩展名、内容嗅探（SLHA 头 `BLOCK ...`、shebang、`PROGRAM`/`main` 入口）。分类结果是 Phase A 侦察的骨架。
3. **引用增量化**（既有 ROADMAP 项）：引用表按文件桶存储，只重建脏文件的桶。

### 5.2 L2 Package Dossier（包档案）★

每个被解析的程序包一份结构化档案：`<project>/.jarvis/dossier/<package>.yaml`。人类可读、可 diff、可手改；Agent 只能通过 `dossier_update` 工具按节写入。**YAML 生成器只读 dossier，不读原始代码**——这条单向依赖保证生成物的每个字段都有档案出处。

Schema 草案见附录 A。五个关键设计点：

1. **每条事实带出处与置信度**：`provenance: {kind: file|command|doc|model-inference|user, ref: path:line | artifact://id, confidence: high|medium|low}`。`model-inference` 且非 high 的事实在进入 YAML 前必须升级（找到文件证据或用户确认）。
2. **IO 契约是一等公民**：`io.inputs[]` / `io.outputs[]` 记录文件、格式（SLHA/xSLHA/card/namelist/csv）、以及 **参数 ↔ block/entry 映射表**（B2 基准里 22 个输入映射 + 30 余个输出映射就存在这里）。
3. **构建配方**：探测到的构建系统、目标、命令序列、产物、已验证平台。命令必须是**实际跑通过的**（带 journal 引用）才可标 `verified: true`。
4. **样例登记**：包内自带的样例输入/输出对（如 `SAMPLES/inp.dat`）。它们是映射抽取与参考运行的种子。
5. **开放问题清单**：`open_questions[]`，Phase B 结束时非空即触发人工关口。

### 5.3 L3 知识与事实库

1. **Jarvis-HEP Schema KB（随 Agent 打包，版本化）**：扫描 YAML 的形式化 schema + 语义规则——顶层段结构、`&J`/`@PackID` 路径宏语义、`clone_shadow` 行为、input `actions` 类型（`SLHA / Replace / File / Dump`）、output 类型（`SLHA / xSLHA / json`）、Sampling 方法清单（Jarvis-HEP `Sampling/` 现有 Random、Grid、CSV、多族 MCMC、Dynesty、MultiNest、Bridson 等）、`LogLikelihood` 表达式可用函数（`inner_func` 上下文）。此 KB 对 Jarvis-HEP 仓库版本敏感，须记录来源 commit，并提供从 Jarvis-HEP 源码半自动再生成的脚本位（后续工作）。附录 B 给出首版条目样例。
2. **领域惯例库**：SLHA 标准 block 语义（`MINPAR/EXTPAR/SMINPUTS/MASS/...`）、PDG 码、常见包家族指纹（"有 `run` 脚本 + `inp.dat` + `spectr.dat` ⇒ NMSSMTools 家族"）。这是打包的静态知识，帮助分类与映射提出**候选**——候选仍须落证据。
3. **记忆系统**（既有 ROADMAP "project memory store" 的落实，形态采纳 mini-claude 的文件式设计）：
   - 存储：`~/.jarvis/projects/<cwd-hash>/memory/` 下每条记忆一个 Markdown 文件，YAML frontmatter 含 `name / type / description`；四类型 `user`（用户身份与偏好）/ `feedback`（纠正与确认过的做法）/ `project`（进度、目标、截止）/ `reference`（外部资源指针）。只存**模型无法从项目现状推导**且用户批准的内容。
   - 索引：`MEMORY.md` 是有界索引（≤200 行 / 25KB），注入系统提示词尾部（recency 位）；每次写入后即时重建，索引永不承载正文。
   - 时效：超过 1 天的记忆在召回时附加 staleness 告警——"记忆是时间点观察，断言前先对照当前代码验证"。
   - 召回：sideQuery 语义召回——把记忆清单（文件名 + description）发给同一本地模型做小调用，让它选出 ≤5 条相关项，胜过关键词匹配；召回结果进 P2 且强制带出处。异步预取暂缓（本地单实例会与主生成抢算力），先做同步小调用。
4. **技能库（Skills，"AI shell scripts"）**：`SKILL.md` 格式的可复用提示词模块（frontmatter：`name / description / when_to_use / allowed-tools / user-invocable`），双来源 `~/.jarvis/skills/`（用户级）与 `<project>/.jarvis/skills/`（项目级，优先）。**渐进披露**：启动只载元数据入提示词，正文按需加载；元数据清单本身受预算三级降级。双调用路径：用户 `/name args` 或模型 `skill` 工具；高工具流量技能用 fork 模式（子代理 + `allowed-tools` 白名单）执行。**这是 HEP 领域知识的执行化载体**：流水线阶段剧本（`/recon`、`/deep-parse`、`/gen-yaml`、`/validate`）与包家族配方（"NMSSMTools 家族安装套路"、"SLHA 扰动映射实验法"）都以技能沉淀，替代硬编码工作流（§8）。

### 5.4 统一检索门面

`info_search(query, scope, k, budget)`：scope ∈ {code, dossier, kb, facts}；返回带出处的有界片段，排序规则：精确符号命中 > 路径命中 > 关键词 > （后续）向量近邻。嵌入检索**推迟**：HEP 包解析的查询多为符号/路径/块名精确型，先把确定性检索做扎实（与 ROADMAP Phase 1 "retrieval with stable path references" 一致）。

---

## 6. Local 运行时系统

### 6.1 模型运行时（重建）

现状（单发 `mlx_lm.generate` 子进程、每问冷加载、伪流式）不能支撑 Agent Loop，替换为：

1. **持久服务**：默认 `mlx_lm.server`（OpenAI 兼容 `/v1/chat/completions`），Agent 启动时拉起并托管生命周期；权重常驻、真 token 流、支持 prompt cache——与 §4.1 的稳定前缀设计配合。
2. **契约扩展**：`ModelBackend.chat(messages, tools, stream=True) → 事件流`，**内部消息与工具 schema 统一采用 OpenAI chat 格式**（mlx_lm.server 原生兼容，远程后端零转换），原 `generate(prompt)` 保留为降级路径。工具调用采用 Qwen3-Coder 的原生 function-calling 模板；解析失败时按 "文本中嵌 JSON" 宽松回退一次，再失败即报 `Error` 事件而不是猜。thinking/推理块在响应落定后即从历史滤除，不占后续窗口。
3. **真实窗口与用量**：从模型配置读取上下文长度，替换硬编码 2048；每轮真实 token 用量回填 `Metrics` 与 ledger（§4.1）。
4. **重试分级**：可恢复错误（限流 / 5xx / 网络重置）在后端内指数退避 + 抖动重试（上限封顶），永久错误（4xx 配置类）立即上浮——与 §3.2 错误扣留配合。
5. **远程外援后端（可选，默认关闭）**：同一 OpenAI 格式契约下可注册远程 API（Anthropic/OpenAI）作为 "困难步骤外援"（如 T5 压缩摘要、低置信映射复核）。开启是显式配置 + 每会话首次使用时确认，UI 常驻徽标提示 "本轮内容将离开本机"——隐私默认（§6.4）不因此松动。
6. **降级链**：server 不可用 → 单发子进程（无工具、只答问，UI 明示 "degraded"）→ 无模型（仅确定性命令可用）。
7. **配置糙边修复**：`agent_state.json` 从 "静默覆盖 TOML" 改为显式覆盖——仅记录 `/model` 的运行时切换且带 `override: true` 标记；`/status` 显示每个生效字段的来源（TOML / state / 默认）。

### 6.2 执行网关 ExecutionGateway（新增，Phase 3 承诺的落实）

所有外部命令的唯一通道（模型工具、`/index` 等内部命令一律走它）：

- **工作目录监禁**：只允许在项目根、`.jarvis/workspace/`（安装/试运行的影子目录）、系统临时目录内执行；路径逃逸直接拒绝。
- **资源约束**：每命令 timeout（默认 120s，安装类可到 30min）、输出体积上限（超限截断落工件）、并发上限。
- **权限分级**（与 §7.2 工具分级一致）：exec 级命令在 TUI 弹出命令预览 → 用户批准 / 加入会话允许清单；`rm -rf`、越狱路径、网络命令默认拒绝。
- **命令日志 Journal**：`.jarvis/journal.jsonl` 记录 {命令、cwd、rc、耗时、工件 id}；dossier 中 `verified` 类事实必须引用 journal 条目。
- **产物管理**：stdout/stderr 全文入工件库，digest 进上下文（§4.2 T1）。

### 6.3 存储布局

```
~/.jarvis/                      # 用户级
  agent_state.json              # 显式模型/adapter 覆盖（§6.1.7）
  sessions.jsonl                # 会话索引（既有）
  sessions/<id>.events.jsonl    # 会话全文 = protocol 事件流（新）
  traces/<session-id>/          # 模型调用轨迹（§9.2，SFT 最小单元；/incognito 会话除外）
  datasets/<name>@<ver>/        # 提炼后的训练数据集（train/valid/test + 逐条 provenance，§9.3）
  adapters/<name>@<ver>/        # LoRA adapter + 训练配置 + 评测报告（§9.5）
  projects/<cwd-hash>/memory/   # 记忆文件 + MEMORY.md 索引（§5.3.3）
  facts/                        # 跨项目用户确认事实
  kb/jarvis-hep/<version>/      # Jarvis-HEP Schema KB（随 Agent 分发）

<project>/.jarvis/              # 项目级
  index/codebase_index.json     # L1（既有）
  dossier/<package>.yaml        # L2 包档案
  artifacts/<hash>/             # 工具产物（日志、抓取的输出文件副本）
  tasks/<task-id>.md            # Task Frame
  journal.jsonl                 # 执行日志
  proposals/<name>.yaml         # 生成的 YAML 草案（验证通过前不出 .jarvis）
```

会话持久化格式统一为 **protocol 事件流**：UI 渲染、회放、压缩审计共用同一事实源（协议层因此成为存储 schema，`PROTOCOL_VERSION` 的演进纪律更重要）。

### 6.4 隐私与离线

默认零联网：模型本地、索引本地、执行本地。`web_fetch` 类工具设计上预留但默认不注册。这是面向 HEP 未发表研究数据的硬承诺，写入系统提示与文档。

---

## 7. Tool 系统

### 7.1 工具契约

```
Tool:
  name, description              # 面向模型，一句话 + 参数说明
  args_schema                    # JSON Schema，字段少而刚性
  tier: read | write | exec      # 权限级（§7.2）
  safety:                        # 安全元数据（采纳 mini-claude 标准）
    read_only: bool              #   不改变任何状态
    destructive: bool            #   不可逆或影响出项目根
    concurrency_safe: bool       #   可与其他安全工具并行
  run(args, ctx) -> ToolOutcome
ToolOutcome:
  ok: bool                       # false 即 "errors are data"：错误做成结果回喂模型
  digest: str                    # ≤1K token，进上下文的唯一内容
  artifact: id | None            # 全文/大对象引用
  data: dict | None              # 结构化小结果（供后续工具/断言用）
```

原则（针对本地 30B 模型的可靠性）：

- **工具少而稳（首版 ≤18 个）、参数扁平、枚举显式**；
- **errors are data, not exceptions**：任何阶段的失败（未知工具、文件不存在、权限拒绝、校验不过）一律转成 `ok=false` 的 ToolOutcome 回喂模型自纠，绝不向循环抛异常；失败文案面向模型可行动（"file not found: X, 目录下最接近的是 Y" 而非裸 traceback）；
- **同批并行**：一次响应中的多个 `concurrency_safe` 工具并行执行（上限 4——本地场景收益在 IO，不在模型侧），含非安全工具的批次整批串行；fail closed：未声明即视为不可并行、需确认；
- 每次调用自动发 `ToolCallStarted` / `LogLine` / `ToolResult` 事件——协议已就绪，无需新事件类型。

### 7.2 权限系统（模式 × 规则 × 分级）

四层检查（采纳 mini-claude："deny 优先" + 模式化策略）：**权限模式 → 规则文件 → 内建危险检测 → 会话白名单**。

工具分级（不变）：

| Tier | 行为 | 默认审批 |
| --- | --- | --- |
| read | 读文件/索引/档案/工件 | 自动放行 |
| write | 写 dossier、task frame、proposals/、facts | 自动放行 + journal 记录，UI 可见 diff |
| exec | 经 Gateway 跑命令 | 逐条预览批准；会话级允许清单；破坏性模式永远单独确认 |

权限模式（覆盖默认审批行为）：

| 模式 | 语义 |
| --- | --- |
| `default` | 上表行为 |
| `plan` | 只读：write/exec 全阻断，仅放行 plan 文件路径（§8 Phase C 关口用） |
| `acceptEdits` | write 免确认，exec 仍关口（Plan 审批通过后的执行态） |
| `dontAsk` | 非交互（CI/基准）：危险操作自动拒绝而非询问；`bypass` 等价物仅允许在 `.jarvis/workspace/` 沙箱内的基准运行使用 |

规则文件：`~/.jarvis/settings.json`（用户级）+ `<project>/.jarvis/settings.json`（项目级）各含 allow/deny 列表，规则格式 `tool_name(pattern*)`（前缀匹配）或裸 `tool_name`；**deny 永远先于 allow 求值**，支持 "先放开再收紧"（如 allow `shell_run(make*)` + deny `shell_run(make clean*)`）。内建危险检测：正则清单（`rm -rf`、`sudo`、`git push --force`、重定向 `/dev/`、`kill` 等）+ Gateway 目录监禁兜底（§6.2）；承认正则只覆盖常见面，纵深靠监禁与 journal。权限拒绝以 ToolOutcome 回喂（模型可改道），不抛错。

### 7.3 首版工具清单

| 工具 | Tier | 说明 |
| --- | --- | --- |
| `fs_read(path, start, end)` | read | 有界读文件（强制行区间/字节上限） |
| `fs_glob(pattern)` / `fs_grep(pattern, glob, max)` | read | 定位文件 / 有界文本搜索 |
| `index_query(kind, name)` | read | L1：定义/引用/文件符号/关键词（现 `CodebaseIndex` 查询的工具化） |
| `info_search(query, scope, k)` | read | L1–L3 统一检索门面（§5.4） |
| `dossier_get(section)` | read | 读包档案某节 |
| `dossier_update(section, patch, provenance)` | write | 按节写档案；无 provenance 的写入被拒绝 |
| `task_update(patch)` | write | 更新 Task Frame（目标/计划/阶段/未决） |
| `artifact_read(id, range)` | read | 二次拉取工件细节（§4.2 T1 的另一半） |
| `shell_run(cmd, cwd, timeout)` | exec | 经 Gateway 的受控执行 |
| `slha_read(path, blocks?)` | read | 解析 SLHA/xSLHA → 结构化 blocks/entries（含注释，注释是映射证据的主要来源） |
| `slha_diff(a, b)` | read | 两份 SLHA 的 entry 级差异（用于 "改一个输入参数 → 看哪个 entry 变了" 的映射实验） |
| `yaml_module_render(dossier, choices)` | write | dossier + 用户选择 → 扫描 YAML 草案（模板化骨架 + 模型填充受限槽位），写入 `proposals/` |
| `yaml_module_validate(path)` | read | 三级校验：语法 → Schema KB 结构校验 → 语义 lint（路径存在、宏用法、变量在 input/output/Sampling 间闭合、LogLikelihood 引用的变量确有来源） |
| `jarvis_hep_dryrun(config, mode)` | exec | 调 Jarvis-HEP 做安装重放 / 单点冒烟（§8 Phase D 的执行臂） |
| `proposal_edit(path, old, new)` | write | 对 proposals/ 草案做**唯一匹配**字符串替换（0 或 >1 处命中即失败）；强制 read-before-edit + mtime 外改检测。Phase D 修复循环用它做小步修订，避免整文件重渲染的漂移 |
| `agent_spawn(description, prompt, type)` | 随子代理 | fork-return 子智能体（§3.4）；子代理内工具仍逐个走权限检查 |
| `skill(name, args)` | read | 取回技能正文作为指令注入（§5.3.4）；fork 型技能内部走 `agent_spawn` |
| `ask_user(question, options)` | — | 结构化人工关口（低置信映射裁决、执行批准之外的决策类提问） |

不设 `fs_write` 通用写工具：Agent 对项目的写入面收敛为 dossier / task / proposals 三类结构化产物，从机制上杜绝 "顺手改用户代码"。`dossier_update` 与 `proposal_edit` 共同遵守 read-before-edit：未在本会话读过目标节/文件的写入被拒绝，mtime 变化（外部修改）时强制重读。

### 7.4 与既有命令的关系

`/index`、`/yaml`、`/explain` 保留为用户直呼入口，内部改为调用同一批工具实现（单一事实源不变，只是从 "router 直连实现" 变为 "router → tool"）。

---

## 8. 端到端流水线：包解析 → YAML 模块生成

**编排原则：剧本 + 记账，不是代码状态机。** 四阶段以技能剧本（`/recon`、`/deep-parse`、`/gen-yaml`、`/validate`，§5.3.4）描述做法，Agent Loop 驱动执行；代码只负责记账（task frame 记录阶段与产物）与关口强制（权限模式、验证门），不做流程控制流——"行为问题优先改提示词，不是加代码"（§3.2）。状态与产物全部落盘（dossier + task frame），任意阶段可中断续跑。

### Phase A — 侦察（Recon）

- 动作：`/index` 全量索引 + 文件分类（§5.1.2）；识别构建系统指纹（Makefile/CMake/configure）、候选可执行与 run 脚本、样例 IO 对、文档清单。
- 产物：dossier 骨架（identity / layout / build.candidates / samples / docs），全部 `confidence: medium` 以下。
- 关口：无（纯只读）。

### Phase B — 深度解析（Deep Parse）

- 构建探测：解析 Makefile 目标 → 提出安装命令序列 → **exec 关口** → 在 `.jarvis/workspace/` 影子目录真实构建 → 成功后 `build.recipe.verified=true`（引用 journal）。
- 运行接口：解析 run 脚本/入口源码，确定命令行形态与输入输出文件名模式。
- IO 契约：`slha_read` 样例输入（块/条目/注释）→ 参数映射候选；**参考运行**（exec 关口）样例输入 → 真实输出文件 → `slha_read` 输出 → 可观测量候选；歧义项用 `slha_diff` 做单参数扰动实验或查文档；仍低置信 → `open_questions`。
- 产物：完整 dossier（build / run / io.inputs / io.outputs / env）。
- **上下文分工**：构建探测、IO 映射实验这类高工具流量子任务 fork 给子智能体（§3.4）跑，主线程只收 "dossier 已更新 + digest"——32K 窗口下 Phase B 不隔离就会淹没主上下文。
- 关口：exec 批准若干次；结束时 `open_questions` 非空 → `ask_user` 逐条裁决。

### Phase C — 生成（Generate）

- 用户输入物理目标（扫哪些参数、什么范围、关心哪些观测量、似然构成）——这是 Sampling 段的授权来源。
- **Plan-mode 关口（渲染前）**：进入 `plan` 权限模式（§7.2，write/exec 阻断），Agent 基于 dossier 起草 "配置方案"（选哪些变量/范围/观测量/似然、installation 采用哪条已验证配方）写入 plan 文件；用户四选项审批——`清上下文执行`（方案已固化落盘，清掉规划过程腾出窗口）/ `带历史执行` / `人工逐步` / `继续规划`（反馈回注，留在 plan 模式迭代）。审批通过切 `acceptEdits` 模式再渲染。
- `yaml_module_render`：骨架来自 Schema KB 模板，槽位填充只允许三种来源——dossier 条目（带出处）、用户本轮选择（含已批准的 plan）、KB 默认值（在 YAML 注释中标注 `# default`）。
- 产物：`proposals/<name>.yaml` + 逐段来源对照表（渲染报告）。后续小修用 `proposal_edit` 唯一匹配替换，不整文件重渲染。

### Phase D — 验证（Validate）

1. `yaml_module_validate`：语法 / schema / 语义 lint；
2. `jarvis_hep_dryrun --install`：按 proposals 在影子目录重放 installation；
3. `jarvis_hep_dryrun --single-point`：单点冒烟，断言每个 `output` 变量被真实提取且非空；
4. 失败 → 错误 digest 回注，定位到 dossier 责任节 → 回到 B 或 C（带上失败证据）；连续失败超阈值 → 汇总报告 + 人工接管。
- 通过 → 用户最终采纳，YAML 移出 proposals 进入项目 `bin/`，dossier 相应事实升级 `confidence: high`。

### 8.5 反幻觉规则（全流水线硬约束）

> 生成 YAML 中的每一个值，必须能指回：dossier 某条带 provenance 的事实、用户的一次明确输入、或 KB 中标注的默认值。渲染报告里出现 "来源：无" 即视为缺陷，验证不予通过。

---

## 9. 数据飞轮：会话历史 → 提炼 → 微调 → 能力内化

### 9.1 目标与原理

把日常使用产生的历史数据变成模型能力，形成闭环：

```
使用（Agent 完成任务）
  → 全保真记录（事件流 + 模型调用轨迹，§9.2）
  → 结果信号标注（验证/采纳/裁决，§9.2）
  → 提炼与人工批审（"调整之后"，§9.3）
  → LoRA/DoRA 训练（§9.5）
  → 评测门（回归不退步 + 能力度量提升）
  → adapter 转正
  → 削减对应的上下文注入（§9.4 "上下文租金"）
  → 更高效的使用（回到起点）
```

双重收益，且都可度量：

1. **效率（上下文租金下降）**：原本靠提示词注入维持的知识（Schema KB、领域惯例、阶段剧本、工具用法叮嘱）内化进权重后，对应注入按 §9.4 的表逐项削减——32K 窗口里省出来的每个 token 都直接变成工作容量。
2. **可靠性（步数下降）**：工具调用格式、schema 遵从、digest 纪律内化后，解析失败与重试减少，同一任务的步数与 token 成本下降。

铁律：**内化不豁免证据**。微调改变的是候选质量与所需步数，不改变 §8.5 反幻觉规则——内化了 SLHA 惯例的模型提出映射候选更快，但每条映射仍必须落到 dossier 的 provenance 才能进 YAML。

### 9.2 全保真保留（Retention）

会话历史分两层记录，**存储永远全量、追加式**——§4 的压缩只影响上下文投影，从不删除落盘历史：

1. **事件流**（已有，§6.3）：protocol 事件 JSONL，服务 UI 回放与审计。
2. **模型调用轨迹（trace，新增）**：在 `ModelBackend.chat` 边界记录每次调用的完整四元组——组装后的 messages（含系统提示词与工具 schema 的版本引用）、模型原始响应（含 tool_call）、真实 usage、版本戳（`model@adapter / prompt_ver / kb_ver / dossier_rev`）。**轨迹是 SFT 的最小单元**：它精确保存了 "模型当时看到什么、答了什么"，事后无需重构。
3. **Episode 关联**：轨迹按轮次归组为 episode，挂接任务帧阶段与**结果信号**——自动信号（`yaml_module_validate`/`jarvis_hep_dryrun`/基准通过与否、journal 执行结果、工具调用解析成败、用户对 proposals 的修改距离）与人工信号（`ask_user` 裁决、plan 四选项审批、显式 `/feedback good|bad`、用户后续轮次中的纠正）。

隐私与体量：轨迹只存本机 `~/.jarvis/traces/`；`/incognito` 开启的会话不记录；定期归档压缩 + 容量上限（超限先淘汰无信号的旧轨迹）。

### 9.3 提炼管线（Curation——"调整之后" 的调整）

原始历史不是训练数据。收割 → 变换 → 批审三步，全部离线、可重跑：

1. **收割过滤**：只收两类 episode——(a) **verified-success**（验证通过 / 用户无改动采纳 / 基准通过）；(b) 显式构造的**修复对**（失败 → 诊断 → 修复的完整序列，作为 "错误恢复" 任务样本）。其余一概不入库（对齐 FINE_TUNING_DATA 既有守则：决不训未审输出）。
2. **变换**：
   - 匿名化：绝对路径/用户名/主机名重写为占位宏（`&HOME`、`&PROJ`），敏感数据样本直接丢弃；
   - 去噪：剪掉死胡同分支（除非构造修复对）、剥离 thinking 块；
   - 按能力目录重塑（§9.4）：一个 episode 可切出多条不同任务型样本；
   - **上下文最小化改写**：把 "靠 P2 注入才答对" 的样本改写为 "不注入也该会" 的形态（撤掉注入段、保留结论与出处引用）——这是内化的直接教学信号；
   - 去重 + **评测集去污染**：与 B1–B3 基准及回归任务集做隔离检查，命中即剔除。
3. **模板一致性（硬约束）**：训练样本的 chat template、工具 schema 序列化必须与运行时（§6.1.2）逐字节一致——模板漂移会直接毁掉工具调用可靠性的收益。
4. **人工批审**：每个数据集批次生成数据集卡（来源会话分布、信号统计、能力型配比、抽样示例），用户批准后才落 `~/.jarvis/datasets/<name>@<ver>/`（train/valid/test + 逐条 provenance：源会话、信号、各版本戳）。

### 9.4 能力目录（内化什么、兑现什么）

| 能力 | 数据来源 | 内化后削减的上下文租金 | 度量 |
| --- | --- | --- | --- |
| 1 工具调用格式与参数纪律 | 全部成功轨迹 | 提示词第 5 层的工具叮嘱、重试预算 | tool_call 解析失败率、任务步数 |
| 2 Jarvis-HEP schema 与 YAML 惯例 | validate 通过的 proposals + 渲染报告 | P2 的 Schema KB 注入（约 2K token → 指针级） | `yaml_module_validate` 一次通过率 |
| 3 SLHA / 包家族领域常识 | dossier 高置信映射 + 扰动实验轨迹 | 领域惯例库注入 | 映射实验步数（注：只加速候选，证据要求不变） |
| 4 阶段剧本执行 | 各阶段 verified-success episode | skills 正文长度（剧本可减薄为要点） | 阶段完成步数、人工干预次数 |
| 5 摘要与 digest 风格 | 被采纳的 T5 摘要块、高质量 digest | 摘要 few-shot 示例 | 压缩后信息保真抽查 |

**内化兑现规则**：某能力的 adapter 过评测门转正后，按本表削减对应注入，削减量计入 `Metrics`——飞轮的效率收益必须在 UI 可见，否则视为未兑现。

### 9.5 训练与上线（Adapter 生命周期）

- 训练：LoRA/DoRA 经 `mlx_lm.lora`（沿用既有 `lora-command` 通道，从 "打印命令" 升级为可执行工作流）；**数据集是持久资产，adapter 是派生物**——base 模型升级时从数据集重训，不迁移旧 adapter。
- 评测门：回归任务集不退步 **且** 至少一项 §9.4 度量显著提升，才可晋升；评测报告随 adapter 归档。
- 灰度与回滚：新 adapter 先 canary 若干会话（UI 徽标 + journal 标记），指标对比后转正为默认；`agent_state.json` 记录 active adapter（接 §6.1.7 显式覆盖），`/status` 可见，一键回滚到 base。
- 追溯：每个 adapter 绑定 dataset hash + 训练配置 + 评测报告（落实原 ROADMAP Phase 5 "track exact model, adapter, dataset hash" 的要求）。

### 9.6 治理红线

- 只训本机数据；数据集与 adapter 默认不出本机，导出是显式动作。
- 决不训：未验证的模型输出、评测集内容、未匿名化样本、`/incognito` 会话。
- 防自我强化：只收 verified-success 与显式修复对；每轮训练前重跑去污染；评测门挡住 "训出来的幻觉"。

---

## 10. 里程碑（修订 ROADMAP 的执行序）

### 10.1 里程碑序（垂直切片先行）

构建方法采纳 mini-claude：**M1 先交付一个能跑通简单任务的完整纵切**（loop + 核心工具 + 提示词 + 权限），之后每个里程碑横向加一个子系统——任何时刻手里都有可用系统。每个里程碑以功能清单（§10.3）过验证门后才进入下一个；"内容" 列附行数预算作为范围纪律（超预算即触发范围复审，不是硬闸）。

| 里程碑 | 内容（≈行数预算） | 验证门 |
| --- | --- | --- |
| M0 运行时整固 | 持久 MLX 服务 + 真流式 + OpenAI 格式契约 + 真实窗口/用量 + 重试分级；`agent_state` 显式覆盖（≈800） | TUI 真 token 流；上下文表为真值；断网/限流重试注入测试 |
| M1 行走骨架 ★ | Agent Loop（§3.2 纪律全量）+ 系统提示词 v1（七层）+ 8 个核心工具（fs_read/fs_glob/fs_grep/index_query/artifact_read/shell_run/task_update/ask_user）+ 权限（模式 × 规则 × Gateway × journal）+ T0/T1 压缩 + 会话快照（≈2,500） | 功能清单 v1（≥10 项，真模型）：模型自主 "读—搜—跑" 完成一次构建探测并把结论写进 task frame |
| M2 信息系统 | Fortran/Make 抽取、文件分类器、dossier schema + 工具、`info_search` 门面、JARVIS.md 层级发现、记忆系统（≈2,000） | B2 包跑完 Phase A–B，dossier 人工审读合格；记忆跨会话召回测试 |
| M3 上下文与子智能体 | T2–T5 管线、S1–S3 结构性机制、会话恢复、`agent_spawn` + 内建 explore/plan/general（≈1,200） | 32K 窗口连续 60+ 工具步不崩；恢复会话可续跑；子代理隔离与 token 归并断言 |
| M4 YAML 流水线 | Schema KB v1、slha 工具、四个阶段技能剧本、plan-mode 关口、render/validate/`proposal_edit`、dryrun 闭环（≈1,800） | B1 通过；B2 通过（§1.3 标准） |
| M5 评测与迁移 | B3 基准、功能清单全量回归表、回归任务集（接原 Phase 5）、KB 再生成脚本 | 新包走通率与人工干预次数入指标 |
| M6 数据飞轮 v1 | 轨迹收割器 + 提炼管线（匿名化/重塑/去污染/批审）+ 数据集版本化 + adapter 训练-评测-灰度-回滚通道（≈1,500） | 首个 adapter 过评测门转正；至少一项 §9.4 度量显著提升且回归集不退步；对应上下文注入完成削减并计入 Metrics |

原 ROADMAP Phase 1/2/3 的条目分别被 M2 / M4 / M1 吸收；Phase 4（LoRA 微调）由 M6 落实为常态化数据飞轮（§9），仍守 "流水线稳定、数据积累之后启动" 的次序——但**轨迹记录（§9.2）自 M1 行走骨架起即默认开启**：数据先行，飞轮后启。M6 依赖 M5 的回归任务集作为评测门，故排在其后。journal + dossier + 渲染报告 + 模型调用轨迹共同构成带出处的微调数据源（与 FINE_TUNING_DATA 的 "provenance metadata" 要求闭合）。

### 10.2 刻意不做清单（含回补条件）

范围纪律显式化（采纳 mini-claude 第 13 章方法：每项记理由与回补时机，避免 "沉默的省略"）：

| 不做项 | 理由 | 回补条件 |
| --- | --- | --- |
| MCP 接入 | 工具面刻意收敛；HEP 场景暂无外部 MCP 需求 | Jarvis-HEP 想以 MCP 服务器形态对外暴露工具时 |
| Hook 系统 | 不阐明核心问题，先不做平台化 | 出现第三方定制需求 |
| Coordinator/Swarm 多智能体 | fork-return 足够；本地单模型实例无并行收益 | 多机/多实例部署出现后 |
| LSP 集成 | HEP 主力语言 LSP 覆盖差；tree-sitter + 编译反馈够用 | 不回补（立场性拒绝） |
| Bash AST 安全分析 | 正则清单 + Gateway 监禁 + journal 已强于教程基线 | 出现监禁绕过实例 |
| 联网工具默认注册 | 隐私默认离线（§6.4） | 不回补；远程外援走 §6.1.5 专用通道 |

### 10.3 测试策略（三层法）

LLM 系统的行为不可全自动断言（mini-claude 第 14 章结论），分三层：

1. **单元测试（自动，CI）**：一切确定性部件——工具函数（含失败路径与截断）、权限求值（deny 优先、模式矩阵、模式 × 规则组合表）、压缩管线各层（给定 ledger 状态断言动作）、SLHA 解析、schema 校验、事件协议。
2. **功能回归清单（人工 + 真模型）**：每里程碑维护一张编号清单（M1 起 ≥10 项，M5 汇总为全量表），每项给**具体通过判据**（如 "启动显示 server 已连接与真实窗口大小"、"plan 模式下写非 plan 文件返回 Blocked 结果而非异常"、"子代理完成后父上下文不含子代理工具原文"）；配 `scripts/test_setup.sh` / `test_cleanup.sh` 一键构造与清理试验环境（试验包、假 dossier、规则文件）。
3. **端到端基准（§1.3）**：B1 冒烟入 CI 可行（小包 + `dontAsk` 模式 + 沙箱）；B2/B3 人工评测，记录走通率、人工干预次数、token 成本三项指标。

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 30B-4bit 工具调用可靠性不足 | 循环卡死/参数错乱 | 工具少而刚性；schema 校验 + 一次宽松重解析；步数上限；关键阶段模板化而非自由生成 |
| Fortran/古老构建系统解析困难 | Phase B 卡壳 | tree-sitter-fortran + 分类器只求 "定位"，语义靠参考运行与样例，不追求编译器级理解 |
| SLHA 映射歧义（同名异义、无注释） | 生成错误映射 | `slha_diff` 扰动实验 > 文档 > 领域 KB 候选 > 人工裁决；低置信禁止入 YAML |
| macOS/Linux 构建差异（HEP 包普遍偏 Linux） | 安装重放失败 | EnvReqs 显式记录已验证平台；失败归因区分 "配置错" 与 "平台不支持" |
| 上下文超限导致遗忘关键决策 | 流水线中途失忆 | T2–T5 驱逐原则 + S1 状态外置 + 不可重取项强制入摘要；task frame 为恢复母本 |
| Jarvis-HEP schema 演进使 KB 过期 | 校验误报/漏报 | KB 记录来源 commit；dryrun 以真实 Jarvis-HEP 为最终裁判（KB 只做快速前置校验） |
| 长会话存储与协议耦合 | 协议破坏性变更代价大 | 沿用既有纪律：`metadata` 扩展优先、版本号 + 弃用窗口 |
| 过度编排（代码状态机替模型做流程决策） | 流程僵硬、每次调整都要改代码 | "剧本 + 记账" 原则（§8）：行为问题先改提示词/技能剧本；代码只做关口与记账 |
| 远程外援泄露未发表研究数据 | 隐私违约 | 默认关闭；显式配置 + 会话首用确认 + UI 常驻徽标 + journal 记录（§6.1.5） |
| 飞轮自我强化错误（训练放大幻觉/坏习惯） | 模型质量劣化且难察觉 | 只训 verified-success 与显式修复对（§9.3.1）；评测门 + 回归集把关；adapter 可一键回滚；每轮训练前重跑去污染 |
| 微调后与 KB/剧本版本失配（内化的知识过期） | 内化知识与 Jarvis-HEP 新 schema 冲突 | 轨迹带 `kb_ver` 版本戳；KB 大版本升级触发受影响 adapter 的重评测，不过门即降级回注入模式 |

---

## 附录 A：Package Dossier Schema（草案）

```yaml
dossier_version: 1
package:
  name: NMSSMTools            # 每条叶子事实均可附 provenance
  version: "6.2.0"
  language: fortran
  license: {value: GPL-2.0, provenance: {kind: file, ref: "LICENSE:1", confidence: high}}
layout:
  roles:                      # Phase A 文件分类结果
    run-script: ["run"]
    sample-input: ["SAMPLES/inp.dat"]
    sample-output: ["SAMPLES/spectr.dat"]
    build-script: ["Makefile", "main/Makefile"]
build:
  system: make
  recipe:
    install: ["make init", "make"]
    verified: true
    provenance: {kind: command, ref: "journal://2026-07-02T10:31:05Z#12", confidence: high}
  artifacts: ["main/nmhdecay", "main/nmspec"]
run:
  entrypoint: "./run <input>"
  inputs_pattern: "*_inp.dat"
  outputs_pattern: ["*_spectr.dat", "*_omega.dat"]
  init_steps: ["cp SAMPLES/inp.dat NMSSMTools_inp.dat"]
io:
  inputs:
    - file_role: main-card
      format: SLHA
      parameters:
        - name: LAMBDA
          block: EXTPAR
          entry: 61
          meaning: "NMSSM lambda coupling"
          provenance: {kind: file, ref: "SAMPLES/inp.dat:23", confidence: high}
  outputs:
    - file_pattern: "*_spectr.dat"
      format: xSLHA
      observables:
        - name: mHSM
          block: MASS
          entry: 25
          provenance: {kind: command, ref: "artifact://ref-run-01/spectr.dat", confidence: high}
env:
  verified_platforms: ["Darwin >=10.14"]
  requires: []
open_questions:
  - "EXTPAR 124/125 (MA/MP) 与 ALAMBDA 63 互斥使用条件未确认"
```

## 附录 B：Jarvis-HEP Schema KB 条目样例（首版覆盖面）

来源：`Jarvis-Examples/NMSSM/bin/NTools.yaml`（人工范例）与 `jarvishep/Module/calculator.py`（配置消费方，KB 须随其版本再生成）。首版必须形式化的规则：

- 顶层段：`Scan{name, save_dir}` / `Sampling{Method, Variables[], "Point number", LogLikelihood[]}` / `EnvReqs{OS[], Check_default_dependencies}` / `Calculators{make_paraller, path, Modules[]}`。
- Module 必填：`name, required_modules, clone_shadow, path, source, installation[], initialization[], execution{path, commands[], input[], output[]}`；可选 `timeout, selection, modes`。
- 路径宏：`&J` = 项目根（`jarvis.project.yaml: path_markers.task_root`）；`@PackID` = worker 影子克隆 id，`clone_shadow: true` 时 `path` 必须含 `@PackID`。
- 命令内变量：`${source}` / `${path}` 在 installation/initialization 中展开。
- `input[].actions[].type ∈ {SLHA, Replace, File, Dump}`；`SLHA` 变量项 `{name, block, entry}`，entry 可为标量或 `[i, j]` 矩阵下标；带 `expression` 的变量由 `inner_func` 表达式上下文（sympy）求值。
- `output[].type` 常用 `xSLHA`（容错 SLHA 读取），变量提取同 block/entry 寻址。
- `Sampling.Method` 可用值以 `jarvishep/Sampling/` 实际注册为准（Random、Grid、CSV、多族 MCMC、Dynesty、MultiNest、Bridson 等）；`LogLikelihood.expression` 可用 `LogGauss` 等 `inner_func` 内建函数。
- 变量闭合规则（语义 lint 核心）：`Sampling.Variables` ∪ 各模块 `output` 变量 ⊇ 各模块 `input` 引用变量 ∪ `LogLikelihood` 自由符号；模块间依赖由 `required_modules` 显式声明。

## 附录 C：文档地图（本文档与既有文档的关系）

| 文档 | 角色 | 状态 |
| --- | --- | --- |
| **DESIGN.md（本文档）** | 系统级设计基线：五子系统 + 流水线 + 数据飞轮 + 里程碑 | 总纲（v1.2） |
| **TECH_DESIGN.md** | 工程级规格：现状审计、包布局、接口签名、数据 schema、算法、错误分类学、测试映射、M0/M1 工作分解 | 新增（v1.0），随里程碑滚动更新 |
| reviews/ | 外部系统评审与采纳决策记录 | 新增；首篇：2026-07-02 claude-code-from-scratch |
| ARCHITECTURE.md | 代码层模块地图与设计规则 | 保留，随 M0–M2 落地更新 |
| ROADMAP.md | 阶段清单 | 保留，执行序以 §10 为准 |
| CODEBASE_INDEX_DESIGN.md | 信息系统 L1 细节 | 保留，按 §5.1 扩展 |
| AGENT_EVENT_PROTOCOL.md | 协议层契约 | 保留；新增 "事件流即会话存储"（§6.3）职责 |
| TUI_DESIGN.md / TUI_udpate_plan.md / adr/ / refactor/ | 呈现层设计与重构记录 | 保留不动 |
| FINE_TUNING_DATA.md / MLX_QWEN3_CODER_SETUP.md | 训练与环境手册 | 保留；上游为 §9 数据飞轮（提炼守则与治理以 §9.3/§9.6 为准，本手册管数据集格式与命令） |
