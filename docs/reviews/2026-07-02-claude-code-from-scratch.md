# 评审：《Claude Code from Scratch》(mini-claude) 及其对 Jarvis-Agent 的采纳决策

状态：已完成，采纳结论已合入 `docs/DESIGN.md` v1.1（注：v1.2 新增 §9 数据飞轮后，原 §9 里程碑/§10 风险重编号为 §10/§11，下文落点已按 v1.2 编号更新）
评审对象：https://diwang.info/claude-code-from-scratch/#/en/ （入口页 + 全部 14 章，2026-07-02 抓取）
评审方法：逐章通读（00 导论 → 14 测试指南），提炼其"标准 + 构建方法"，逐条对照 Jarvis-Agent DESIGN.md v1.0 做 采纳/适配/拒绝 决策。

---

## 1. 教程概况

该教程用 **~3,400–4,300 行**（TypeScript 与 Python 双实现）复刻 Claude Code 的核心架构：13 个工具、并行与流式执行、四级上下文压缩、语义记忆召回、技能系统、多智能体、MCP 接入。模块规模：`agent.ts` ~1,263 行（核心引擎）、`tools.ts` ~850、`cli.ts` ~371、`memory.ts` ~325、`skills.ts` ~175。

章节地图（每章 = 一个子系统 + 它编码的工程标准）：

| 章 | 构建物 | 编码的核心标准 |
| --- | --- | --- |
| 01 Agent Loop | 单类 Agent + async generator 循环 | 终止条件 = 响应无 tool_use；每轮消息对（assistant+tool_results）纪律；可恢复错误静默重试（error withholding）；AbortController 中断 |
| 02 Tools | 13 工具，统一契约 | **errors are data, not exceptions**（失败即 `is_error` 结果回喂模型自纠）；read-before-edit 代码级强制 + mtime 检测外部修改；edit = 唯一字符串匹配 + 引号归一化；截断保头保尾；每工具声明 安全元数据（只读/破坏性/可并发）；fail closed |
| 03 System Prompt | 7 层递进提示词 | 身份→系统→做事方式→行动→工具→语气→输出效率；**反模式接种**（负面指令消除自我合理化空间）；**爆炸半径框架**（可逆性×影响面教风险判断）；工具偏好映射（专用工具替代 bash）；`{{placeholder}}` 动态注入（env/git/CLAUDE.md 层级发现 + @include + rules/*.md）；memory/skills 放尾部吃 recency bias |
| 04 CLI & Session | one-shot + REPL 双模式 | 会话 = 消息数组直存直载（`--resume` 即恢复）；Ctrl+C 双语义；可观测性原则："Agent 自由行动，但让用户实时看见每一步"；显示截断 500 字符但历史全量 |
| 05 Streaming & 双后端 | SSE 流 + Anthropic/OpenAI 双后端 | 后端差异收敛在格式转换层；流中**提前执行**已完成的并发安全工具；重试分级（可恢复 429/503/网络 vs 永久 400/401）+ 指数退避加抖动；thinking 块出历史即滤除 |
| 06 Permissions | 4 层检查 × 5 模式 | 模式（default/plan/acceptEdits/bypassPermissions/dontAsk）→ 配置规则 → 内建危险检测 → 会话白名单；规则格式 `tool(pattern*)` 前缀匹配；**deny 先于 allow**；拒绝以工具结果回喂而非抛错；16 条正则覆盖常见危险命令（承认 80% 务实覆盖） |
| 07 Context | 分层升级压缩管线 | T0 执行期截断（50K 字符保头保尾）→ T0.5 大结果落盘（>30KB → 磁盘 + 预览，可逆）→ T1 利用率预算收紧（>50%→30K/条，>70%→15K/条）→ T2 重复读 snip（>60% 利用率去重，保最近 3）→ T3 空闲微压缩（>5 分钟空闲 = prompt cache 已失效才清）→ T4 自动压缩（~85% 触发摘要替换，**仅轮边界**执行防孤儿 tool_use）；token 记账以 API 返回为准；"元数据比数据长寿" |
| 08 Memory | 文件式记忆 + 语义召回 | 4 类型（user/feedback/project/reference）+ YAML frontmatter；MEMORY.md 索引（≤200 行/25KB）注入提示词；**sideQuery 语义召回**（把清单发给模型选 ≤5 条，胜过关键词匹配）；异步预取三闸门；>1 天记忆加时效告警 |
| 09 Skills | SKILL.md 提示词模块 | frontmatter（name/description/when_to_use/allowed-tools/user-invocable）；**渐进披露**（启动只载元数据，正文按需）；描述预算三级降级；双调用路径（用户 `/cmd` + 模型 `skill` 工具）；inline / fork 两种执行模式；`$ARGUMENTS` 等替换 |
| 10 Plan Mode | 只读规划 + 审批关口 | **双重强制**（提示词约束 + 权限层代码兜底，只放行 plan 文件路径）；plan 落盘故可清上下文执行；**四选项审批**（清上下文执行/带历史执行/人工逐步/继续规划）；审批是回调（UI 解耦）；prePlanMode 精确恢复 |
| 11 Multi-Agent | fork-return 子智能体 | 子代理 = 不同配置的 Agent 实例；内建 Explore/Plan/General 三类 + `.claude/agents/*.md` 自定义；**完全上下文隔离**，只回文本 + token 计数（归并到父账单）；prompt 必须自包含；禁递归嵌套；先做 fork-return，不做 Coordinator（共享状态复杂度不值） |
| 12 MCP | stdio JSON-RPC 客户端 | `mcp__server__tool` 三段命名内嵌路由；首次 chat 才懒连接；失败服务器静默跳过 |
| 13 对比与展望 | 全子系统对照表 + 回补路线 | **刻意不做清单**（hooks/Coordinator/LSP/prompt cache/AST 安全分析），每项给行数成本 + 不做的理由 + 何时回补（分四期，含天数估算） |
| 14 测试指南 | 19 项功能清单 | 分层：**确定性工具走单元测试；Agent 行为走人工功能清单 + 真实模型**（不 mock LLM）；每项给具体通过判据；`setup.sh`/`cleanup.sh` 一键环境 |

## 2. 提炼的构建方法论（五条）

1. **垂直切片先行**：第 1–2 章先造出"能跑的最小 agent"（loop + 6 工具），后续每章横向加一个子系统。任何时刻手里都有可用系统，而不是先铺骨架最后合体。
2. **对照式简化**："保留设计哲学，砍掉工程复杂度"——每个子系统都给出 生产实现 vs 简化实现 的对照及取舍理由（如权限：7 层 AST → 4 层正则）。简化是**有依据的裁剪**，不是无知的省略。
3. **刻意不做清单 + 回补路线图**：不做的功能逐项记录行数成本、不做理由、回补时机与顺序。范围纪律显式化。
4. **每章验证门**：每章末给验证方法与具体判据；最终沉淀为 19 项功能回归清单（判据具体到"启动显示 Connected to 'test' — 3 tools"这种粒度）。
5. **行数即范围预算**：用行数标定每个模块的复杂度上限（~3,400 行做完 13 个子系统），防蔓延。

核心工程原则（其第 13 章总结，与我们最相关的四条）：
- "Agent 本质是一个 while 循环"——一切复杂度都是这个循环的包装；
- **"Prompts over code"**——行为问题优先用更好的提示词解决，不是更多代码；模型决定下一步，代码只记账；
- 上下文管理 = 操作系统内存管理（分层换页造"无限内存"错觉）；
- 边界情况占产品化 80% 距离。

## 3. 约束校准：他们的前提 vs 我们的前提

mini-claude 依托云端 Claude（200K 窗口、强工具调用、快速 API）。Jarvis-Agent 是本地 Qwen3-Coder-30B-A3B-4bit（32K 实用窗口、工具调用可靠性打折、Apple Silicon 单实例吞吐）。因此：

| 教程标准 | 我们的重定标 |
| --- | --- |
| 200K 窗口，85% 触发压缩 | 32K 窗口，阈值整体前移（80% 触发终压），各层预算按窗口比例缩 |
| 并发安全工具最多 10 个并行 | 上限 4（工具多为本地 IO，模型侧无并发收益） |
| 模型语义判断可靠（sideQuery、自由编排） | 语义召回保留但结果强校验；关键流程用刚性 schema + 模板兜底 |
| 子智能体是"锦上添花" | 子智能体是**主要的上下文杠杆**——32K 下重任务必须隔离出去，只回摘要 |
| 双后端 = Anthropic + OpenAI | 双后端 = mlx_lm.server（OpenAI 兼容，主）+ 可选远程 API（显式开启的"外援"，隐私关口） |
| shell 30 秒超时 | 保持 120 秒默认/安装类 30 分钟（HEP 构建耗时长） |

## 4. 采纳决策表

### 4.1 直接采纳（Adopt）

| # | 标准 | 落点（DESIGN.md v1.1） |
| --- | --- | --- |
| A1 | 循环终止 = 无 tool_use；消息对纪律；可恢复错误静默重试；压缩仅在轮边界（防孤儿 tool_use） | §3.2 |
| A2 | errors are data：一切工具失败/权限拒绝 → `is_error` 结果回喂，可行动的错误文案 | §7.1 |
| A3 | 工具安全元数据（read_only/destructive/concurrency_safe）+ 并发安全工具并行执行 | §7.1 |
| A4 | 截断保头保尾（报错常在尾部，结构在头部） | §4.2 T0 |
| A5 | 分层升级压缩管线：新增 利用率预算收紧、重复读 snip、空闲微压缩（对齐 prompt cache 失效） | §4.2 T2/T3/T4 |
| A6 | token 记账以 server 返回 usage 为准，估算仅兜底 | §4.1 |
| A7 | 权限 = 模式 × 规则文件 × 危险检测 × 会话白名单；`tool(pattern*)`；deny 先于 allow；用户级+项目级 settings | §7.2 |
| A8 | 系统提示词 7 层结构 + 反模式接种 + 爆炸半径框架 + 工具偏好映射 + 动态注入 + 尾部 recency 位 | §3.3（新） |
| A9 | JARVIS.md 层级项目指令（CLAUDE.md 同构）+ @include + `.jarvis/rules/*.md` | §3.3 |
| A10 | 记忆系统具体化：4 类型 frontmatter 文件 + MEMORY.md 有界索引 + 时效告警 + 语义召回 | §5.3 |
| A11 | 技能系统：SKILL.md + 渐进披露 + 双调用 + fork 模式；**用于承载 HEP 流程剧本与包家族配方** | §5.3 / §8 |
| A12 | Plan Mode：双重强制 + plan 落盘 + 四选项审批回调；作为 Phase C 生成前的正式关口 | §8 |
| A13 | fork-return 子智能体：Explore/Plan/General + `.jarvis/agents/*.md`；完全隔离、只回摘要、token 归并、禁嵌套、prompt 自包含 | §3.4（新） |
| A14 | read-before-edit + mtime 外改检测；唯一匹配字符串替换编辑 | §7.3 `proposal_edit`、`dossier_update` |
| A15 | 测试三层法：工具单元测试 / 功能回归清单（真模型 + 具体判据 + setup/cleanup 脚本）/ 端到端基准 | §10.3（新） |
| A16 | 构建方法论：垂直切片先行、每里程碑验证门、刻意不做清单 + 回补路线 | §10 重切 + §10.2（新） |
| A17 | "Prompts over code"：流水线改为 剧本（skills）+ 记账（task frame），代码不做硬状态机控制流 | §8 编排原则 |

### 4.2 适配后采纳（Adapt）

| # | 标准 | 适配 |
| --- | --- | --- |
| B1 | 双后端抽象 | 内部消息格式统一 OpenAI chat 格式；主后端 mlx_lm.server；远程 API 作为显式开启的外援后端（隐私关口 + 明示徽标） |
| B2 | 流中提前执行安全工具 | 本地单流场景改为"批内并行"：同批并发安全工具 `gather` 执行，上限 4 |
| B3 | sideQuery 异步预取 | 召回机制采纳；异步预取推迟（本地单实例，预取会与主生成抢算力），先做同步小调用 |
| B4 | `--yolo`/bypassPermissions | 仅允许在 `.jarvis/workspace/` 沙箱内的基准测试使用，交互模式不提供 |
| B5 | 会话 = 消息数组直存直载 | 保留我们的"protocol 事件流为存储母本"，但补充恢复语义：任务帧 + 摘要 + 尾部轮次（DESIGN §4.3 S2 已定），并新增消息数组快照作为快速 `--resume` 路径 |

### 4.3 拒绝 / 暂缓（Reject / Defer）

| # | 标准 | 理由 |
| --- | --- | --- |
| C1 | MCP 接入 | 暂缓。工具面刻意收敛（≤18 个）；HEP 场景暂无外部 MCP 生态需求。回补条件：Jarvis-HEP 想以 MCP 服务器形态对外暴露工具时 |
| C2 | Hook 系统 | 暂缓（教程自己也裁了）。回补条件：出现第三方定制需求 |
| C3 | Coordinator/Swarm 多智能体 | 拒绝。fork-return 足够；本地单实例无并行收益，共享状态复杂度不值 |
| C4 | LSP 集成 | 拒绝。HEP 主力语言（Fortran/老 C++）LSP 覆盖差；tree-sitter 索引 + 编译器报错反馈够用 |
| C5 | Bash AST 安全分析 | 暂缓。正则清单 + ExecutionGateway 目录监禁/journal 的组合已强于教程基线 |
| C6 | web_fetch 默认注册 | 拒绝（隐私默认离线，DESIGN §6.4 既有决定不变） |

## 5. 已合入 DESIGN.md v1.1 的变更清单

1. §3.2 Agent Loop 补终止条件、消息对纪律、错误扣留、轮边界压缩规则；
2. 新增 §3.3 系统提示词工程（7 层 + 接种 + 爆炸半径 + JARVIS.md）；
3. 新增 §3.4 子智能体（fork-return，定位为 32K 的上下文杠杆）；
4. §4 上下文压缩重构为 T0–T5 升级管线 + 结构性机制，token 记账改真值；
5. §5.3 记忆与技能库具体化；
6. §6.1 后端契约统一 OpenAI 格式 + 远程外援 + 重试分级；
7. §7 工具契约加安全元数据与并行规则；权限升级为 模式×规则；工具清单 +3（proposal_edit / agent_spawn / skill）；
8. §8 编排原则改为"剧本 + 记账"，Phase C 前加 Plan-mode 四选项关口；
9. 里程碑重切（M1 = 行走骨架），新增刻意不做清单与测试三层法（v1.2 编号下为 §10、§10.2、§10.3）；
10. §10 风险表补"过度编排"与"远程外援隐私"两项。
