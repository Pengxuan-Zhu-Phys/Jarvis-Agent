# Jarvis-Agent 技术设计（Technical Design）

状态：v1.0（对应 `docs/DESIGN.md` v1.2）
日期：2026-07-02
定位：DESIGN.md 回答 **做什么、为什么**；本文档回答 **怎么建**——模块到文件、接口到签名、数据到 schema、算法到步骤。实现语言 Python ≥ 3.11，并发模型 asyncio。代码示例是接口契约，不是最终实现；实现时字段与签名以本文档为准，偏离需回写。

---

## 1. 现状代码审计（2026-07-02，src 共 ~4,000 行 + textual_tui 子包）

| 模块 | 现状（关键符号） | 处置 |
| --- | --- | --- |
| `config.py` (329) | `AgentConfig/ModelConfig/IndexConfig`；`agent_state.json` 每次 `load_config` 重写并静默覆盖 TOML | **扩展**：新增 `[runtime] [context] [permissions] [flywheel]` 配置节（§12）；state 改显式覆盖（§12.3） |
| `tui.py` (268) | `TerminalUI.dispatch(raw) -> TUIResponse` 同步路由；`with_agent_system_prompt` 字符串拼接；`dispatch_natural_language` 走 `engine.ask_model` | **保留为命令门面**：斜杠命令继续走 dispatch；自然语言路径改为提交 `AgentLoop.run_turn`（§5）；`TUIResponse` 保留用于同步命令 |
| `workflows/engine.py` (54) | `WorkflowEngine`：`index_summary/explain_file_prompt/review_yaml/ask_model` 同步门面 | **逐步退役**：各能力工具化后（`index_query`、`yaml_module_validate`），engine 变薄直至删除；`ask_model` 由 runtime 取代 |
| `model/base.py` (59) | `ModelBackend(Protocol).generate(prompt) -> GenerationResult`（同步、无会话） | **保留为降级契约**；新增 `runtime.ChatBackend`（§4）为主契约 |
| `model/mlx.py` (88) | `MLXBackend`：一次性 `subprocess.run(mlx_lm.generate)`，无超时默认，冷加载 | **包装进** `runtime/subprocess_backend.py` 作降级链末端；补默认超时 |
| `agent_actions.py` (63) | 关键词意图表 + `[ACTION: INDEX]` 标记协议 | **退役**（M1 工具调用取代标记协议）；关键词检测保留为无工具后备 |
| `session.py` (116) | `SessionStore`：单文件 JSONL（kind/text），全量读入内存 | **扩展**：v2 增加事件流文件与消息快照（§11.4）；旧格式只读兼容 |
| `protocol/` (196) | 10 个 frozen 事件 + `validate_event` + `EventBus`（弱引用订阅，`publish` 后同步 drain） | **兼容扩展**：新增 `StopRequested` 控制事件（§13）。**审计发现：`StopRequested`/`request_stop` 在代码中零命中——TUI_udpate_plan 的 Stop 特性未落地**，DESIGN §3.2 的"已实现"表述已修正，落到 M1 |
| `project/` (~800) | `ProjectIndexer.build`、`CodebaseIndex`（JSON v1.0）、Python/C++ 提取器 | **扩建**：`roles` 字段（§9.1，index schema v1.1）、Fortran/Makefile 提取器、引用分桶增量 |
| `hep/` (69+69) | `review_yaml_file`（语法级）、`build_explain_file_prompt` | `yaml_assistant` 成为 `yaml_module_validate` 的 L1 语法层（§9.5）；`prompts.py` 并入 `prompts/` 包 |
| `textual_tui/` (~2,600) | `JarvisAgentApp`（1,287 行）：`start_llm_request` 在 **daemon 线程**跑 dispatch、`call_from_thread` 回主线程、模拟流 | **保留**；M0 把线程模型换成 asyncio task + EventBus 订阅（§13.2），模拟流改真流 |
| `training/mlx_lora.py` | 打印 `mlx_lm.lora` 命令 | **扩建**为 `flywheel/adapters.py` 的命令层（M6） |
| `tests/` (9 个文件) | 路由/配置/协议/输出块/流式/转录均有覆盖 | 全部保持绿；新模块按 §15 配测试 |

迁移策略：**绞杀者模式**。新代码在 `agent/ runtime/ tools/ gateway/ info/ prompts/ skills/ flywheel/` 生长；`TerminalUI.dispatch` 与 protocol 事件是两条不动的缝合线——TUI 不感知内部替换。

## 2. 目标包布局

```
src/jarvis_agent/
  agent/
    loop.py              # AgentLoop.run_turn；步数/预算守卫；取消          (M1)
    context.py           # ContextManager: assemble/settle/T0–T5           (M1 T0/T1, M3 全量)
    ledger.py            # TokenLedger 分区记账 + usage 校准               (M1)
    taskframe.py         # TaskFrame 解析/渲染/更新                        (M1)
  runtime/
    types.py             # ChatMessage/ToolCall/ToolSpec/Usage/ChatEvent   (M0)
    backend.py           # ChatBackend Protocol + RetryPolicy + CancelToken (M0)
    mlx_server.py        # MlxServerBackend：托管 mlx_lm.server + SSE      (M0)
    subprocess_backend.py# 现 MLXBackend 的降级包装                        (M0)
    remote.py            # RemoteBackend 外援（显式开启）                  (M4+)
  tools/
    base.py              # Tool ABC / ToolContext / ToolOutcome / SafetyMeta (M1)
    registry.py          # schema 导出、两段校验、并行批执行                (M1)
    fs.py                # fs_read fs_glob fs_grep artifact_read            (M1)
    shell.py             # shell_run                                        (M1)
    task_tools.py        # task_update ask_user                             (M1)
    index_tools.py       # index_query info_search                          (M1/M2)
    dossier_tools.py     # dossier_get dossier_update                       (M2)
    subagent.py          # agent_spawn                                      (M3)
    skill_tool.py        # skill                                            (M4)
    slha.py              # slha_read slha_diff                              (M4)
    yaml_module.py       # yaml_module_render/validate, proposal_edit       (M4)
    hep_run.py           # jarvis_hep_dryrun                                (M4)
  gateway/
    exec.py              # ExecutionGateway                                 (M1)
    permissions.py       # PermissionEvaluator                              (M1)
    rules.py             # settings.json 规则加载/匹配                      (M1)
    danger.py            # 危险命令正则清单                                 (M1)
    journal.py           # Journal JSONL                                    (M1)
    artifacts.py         # ArtifactStore                                    (M1)
  info/
    classify.py          # 文件角色分类器                                   (M2)
    dossier.py           # Dossier 模型 + Provenance                        (M2)
    search.py            # InfoSearch 排序管道                              (M2)
    memory.py            # 记忆文件/MEMORY.md/召回                          (M2)
    kb/                  # loader.py + jarvis-hep schema 数据               (M4)
  prompts/
    system.py            # 七层系统提示词组装（{{占位符}} 注入）            (M1)
    jarvismd.py          # JARVIS.md 层级发现 + @include + rules/*.md       (M2)
  skills/
    model.py loader.py   # SKILL.md 解析 / 双源发现 / 预算降级              (M4)
  flywheel/
    trace.py             # TraceRecorder（M1 起默认开启）                   (M1)
    harvest.py curate.py datasets.py adapters.py                            (M6)
  protocol/ project/ hep/ textual_tui/ tui.py cli.py config.py session.py  # 既有
```

## 3. 核心数据类型（`runtime/types.py`，全部 frozen+slots）

内部统一 OpenAI chat 格式（DESIGN §6.1.2）：

```python
Role = Literal["system", "user", "assistant", "tool"]

@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str            # 原始 JSON 字符串。不预解析——飞轮训练样本要求逐字节保留（DESIGN §9.3.3）

@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()   # 仅 assistant
    tool_call_id: str | None = None         # 仅 tool，必填
    name: str | None = None                 # 仅 tool：工具名

@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any]           # JSON Schema（由 registry 从 args dataclass 导出）

@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int = 0

# 流事件（backend → loop 的内部事件，与 protocol 渲染事件不同层）
@dataclass(frozen=True, slots=True)
class TextDelta:        text: str
@dataclass(frozen=True, slots=True)
class ToolCallsReady:   calls: tuple[ToolCall, ...]     # finish_reason == "tool_calls"
@dataclass(frozen=True, slots=True)
class UsageReport:      usage: Usage
@dataclass(frozen=True, slots=True)
class StreamEnd:        finish_reason: str              # "stop" | "tool_calls" | "length"
@dataclass(frozen=True, slots=True)
class BackendFailure:   kind: str; message: str; recoverable: bool

ChatEvent = TextDelta | ToolCallsReady | UsageReport | StreamEnd | BackendFailure
```

工具层类型（`tools/base.py`）：

```python
class Tier(StrEnum):    READ = "read"; WRITE = "write"; EXEC = "exec"

@dataclass(frozen=True, slots=True)
class SafetyMeta:
    read_only: bool
    destructive: bool = False
    concurrency_safe: bool = False    # fail closed：默认不可并行

@dataclass(frozen=True, slots=True)
class ToolOutcome:
    ok: bool
    digest: str                       # 进上下文的唯一内容，≤ ledger 当前工具预算
    artifact_id: str | None = None
    data: Mapping[str, Any] | None = None
```

## 4. 模型运行时（`runtime/`）

### 4.1 契约

```python
class CancelToken:
    """包装 asyncio.Event；.cancelled 属性 + .raise_if_cancelled()。
    由 TUI 的 Stop 控制置位；gateway 据此 kill 进程组。"""

class ChatBackend(Protocol):
    def id(self) -> str:                      # "mlx:Qwen3-Coder-30B@hep-adapter-3"，进 trace 版本戳
    def context_window(self) -> int: ...
    async def chat(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec],
        *, cancel: CancelToken,
    ) -> AsyncIterator[ChatEvent]: ...
```

### 4.2 `MlxServerBackend` 生命周期

1. 启动：`mlx_lm.server --model <repo> --port 0`（子进程，进程组）；端口写 scratch 下的 port 文件；首个 `GET /v1/models` 成功即 ready（超时 120s——首次加载权重慢）。
2. 崩溃恢复：chat 中连接断开 → 重启一次 server → 重放本次请求；再失败 → 发 `BackendFailure(recoverable=False)`，降级链切 `subprocess_backend`（UI 显示 degraded）。
3. 退出：atexit + `StopRequested` 双钩子 terminate 进程组。
4. 窗口探测：优先读本地 HF 缓存内该模型 `config.json` 的 `max_position_embeddings`（含 rope_scaling 折算）；`[runtime].context_window` 配置项可覆盖；两者皆无 → 32768 保守默认。

### 4.3 SSE 解析状态机

OpenAI 流格式，按 chunk 处理：`delta.content` → `TextDelta`；`delta.tool_calls[i]` 按 index 在 `dict[int, _PartialCall]` 中累积 `id/name/arguments` 片段；`finish_reason == "tool_calls"` → 拼装并发 `ToolCallsReady`；`usage` chunk → `UsageReport`；`[DONE]` → `StreamEnd`。thinking 块（`reasoning_content` 或 `<think>` 标签）在流中透传给 UI 但**不写入 messages 历史**（DESIGN §6.1.2）。

### 4.4 RetryPolicy

```python
recoverable = {429, 500, 502, 503} | {ConnectionError, TimeoutError}
permanent   = {400, 401, 404, 422}
delay(n)    = min(1.0 * 2**n, 30.0) + uniform(0, 1.0)   # n = 0..3，最多 4 次
```
可恢复错误在 backend 内静默重试（DESIGN §3.2 错误扣留）；永久错误立刻 `BackendFailure(recoverable=False)`。

### 4.5 tool-call 解析修复（本地模型可靠性）

主路径：server 原生 `tool_calls`。修复路径：`finish_reason == "stop"` 但文本含 `<tool_call>...</tool_call>`（Qwen 模板泄漏）或孤立 ```json 块 → 一次宽松提取；提取后 `json.loads` 校验。仍失败 → 合成 `ToolOutcome(ok=False, digest="tool call malformed; expected schema: ...")` 回喂，计入步数。**修复路径的样本会被飞轮收割为格式训练数据（DESIGN §9.4 能力 1）。**

## 5. Agent Loop（`agent/loop.py`）

```python
class AgentLoop:
    def __init__(self, backend, registry, ctxmgr, trace, emit, approval_fn, cfg): ...
    async def run_turn(self, user_text: str, *, cancel: CancelToken) -> None
```

`run_turn` 算法（行号即实现顺序）：

```
 1  emit(UserPrompt(user_text));  episode = trace.begin(turn)
 2  messages = ctxmgr.assemble(user_text)          # 唯一允许 T5 压缩的时点（轮边界）
 3  for step in 1..cfg.max_steps(24):
 4      cancel.raise_if_cancelled()
 5      buffer = "";  calls = None
 6      async for ev in backend.chat(messages, registry.specs(), cancel=cancel):
 7          TextDelta      → emit(AssistantTextDelta); buffer += ev.text
 8          ToolCallsReady → calls = ev.calls
 9          UsageReport    → ctxmgr.ledger.calibrate(ev.usage); trace.record_call(...)
10          BackendFailure(recoverable=False) → emit(Error); goto 17
11      if calls is None: break                     # 终止条件：无 tool_call（DESIGN §3.2）
12      outcomes = await registry.execute_batch(calls, ctx)      # §6.3
13      messages += [assistant(buffer, calls), *[tool(o, c.id) for ...]]   # 消息对纪律
14      ctxmgr.between_steps(messages)              # T2/T3 在步间生效；T5 绝不在此发生
15      if ctxmgr.over_budget(): emit(Status("context pressure")); break-with-taskframe
16  else: 步数耗尽 → task_update(pending=...) 后停（DESIGN §3.2）
17  emit(AssistantTextEnd, Metrics(ledger.snapshot()))
18  ctxmgr.settle();  trace.end(episode, signals=auto_signals())
```

取消语义：`CancelToken` 在第 4/6/12 行检查点生效；responding 中触发 → 保留部分文本 + `⏹ Interrupted`；工具执行中触发 → gateway kill 进程组，未启动的调用丢弃，已完成的 outcome 保留入 messages（保持消息对完整后再退出）。

## 6. 工具系统（`tools/`）

### 6.1 Tool ABC 与上下文

```python
class Tool(ABC):
    name: ClassVar[str]; description: ClassVar[str]
    Args: ClassVar[type]              # @dataclass；registry 反射导出 JSON Schema
    tier: ClassVar[Tier]; safety: ClassVar[SafetyMeta]
    def run(self, args: Args, ctx: ToolContext) -> ToolOutcome    # 同步；registry 放 to_thread

@dataclass
class ToolContext:
    cfg: AgentConfig; project_root: Path
    gateway: ExecutionGateway; artifacts: ArtifactStore
    index: CodebaseIndex | None; dossier: DossierStore | None
    read_registry: dict[Path, ReadStamp]   # read-before-edit：path → (mtime, spans)
    emit: Callable[[AgentEvent], None]; session_id: str; digest_budget: int
```

### 6.2 校验两段式

1. schema 校验：registry 依 `Args` dataclass 做类型/必填/枚举检查，失败 → `ok=False` 带期望 schema；
2. 业务校验：工具内（路径存在、行区间合法…），失败 → `ok=False` 带可行动建议（最近路径提示等）。
任何一段都**不抛异常**（errors are data，DESIGN §7.1）。

### 6.3 `execute_batch` 算法

```
输入 calls（同一响应内的全部 tool_call，保序）
1 对每个 call：PermissionEvaluator.evaluate(tool, args, ctx)      # §7.1
    deny → ToolOutcome(ok=False, digest=拒绝理由)（占位，不执行）
    ask  → await approval_fn(request)；拒 → 同上
2 全部通过项若均 safety.concurrency_safe 且 tier==READ：
    asyncio.gather(to_thread(run), cap=4)
  否则：按原序串行
3 每个 outcome：len(digest) > budget → artifacts.spill() 改写 digest（T1）
4 emit ToolCallStarted / ToolResult 对；返回保序 outcomes
```

### 6.4 工具参数表（首版 18 个，args 字段级）

| 工具 | Args | tier / safety |
| --- | --- | --- |
| `fs_read` | `path:str, start:int=1, end:int|None`（强制 `end-start ≤ 400` 行、64KB 上限） | read / ro+cs |
| `fs_glob` | `pattern:str, max:int=200` | read / ro+cs |
| `fs_grep` | `pattern:str, glob:str="**/*", max:int=100`（正则，越界截断提示） | read / ro+cs |
| `index_query` | `kind:Literal["def","refs","file_symbols","search"], name:str` | read / ro+cs |
| `info_search` | `query:str, scope:Literal["code","dossier","kb","facts","all"]="all", k:int=5` | read / ro+cs |
| `artifact_read` | `id:str, start:int=1, end:int|None` | read / ro+cs |
| `dossier_get` | `section:str`（点路径，如 `io.inputs`） | read / ro+cs |
| `dossier_update` | `section:str, patch:str(YAML), provenance:Provenance`（无 provenance 拒绝） | write / 非cs |
| `task_update` | `patch:str(YAML: goal/phase/plan/pending 任意子集)` | write / 非cs |
| `shell_run` | `cmd:str, cwd:str=".", timeout:int=120` | exec / 非ro |
| `slha_read` | `path:str, blocks:list[str]|None` | read / ro+cs |
| `slha_diff` | `a:str, b:str` | read / ro+cs |
| `yaml_module_render` | `dossier:str, out:str, choices:str(YAML)` | write / 非cs |
| `yaml_module_validate` | `path:str` | read / ro+cs |
| `proposal_edit` | `path:str, old:str, new:str`（唯一匹配；0 或 >1 命中失败） | write / 非cs |
| `jarvis_hep_dryrun` | `config:str, mode:Literal["install","single-point"]` | exec / 非ro |
| `agent_spawn` | `description:str, prompt:str, type:str="general"` | 随子代理 / 非cs |
| `skill` | `name:str, args:str=""` | read / ro |

read-before-edit 实现：`fs_read`/`dossier_get` 向 `ctx.read_registry` 写 `(realpath, mtime)`；`proposal_edit`/`dossier_update` 执行前校验目标已读且 mtime 未变，否则 `ok=False, digest="file changed on disk; re-read before editing"`。

## 7. 权限与执行网关（`gateway/`）

### 7.1 `PermissionEvaluator.evaluate(tool, args, ctx) -> Decision`

```python
@dataclass(frozen=True)
class Decision: verdict: Literal["allow","deny","ask"]; reason: str; rule: str | None

求值顺序（短路，deny 优先）：
1 mode gate: plan 模式 → 非 read 且目标 ≠ plan_file → deny
             dontAsk 模式 → 后续所有 ask 降级为 deny
2 deny 规则（project → user 顺序合并后统一先评）
3 allow 规则
4 exec 类：danger.py 正则命中 → ask（destructive 工具恒 ask）
5 会话白名单（本会话已批准的 (tool, pattern) 对）→ allow
6 默认：read→allow；write→allow(+journal)；exec→ask
```

### 7.2 规则文件（`rules.py`）

`~/.jarvis/settings.json` 与 `<project>/.jarvis/settings.json`：

```json
{ "permissions": {
    "allow": ["fs_read", "shell_run(make*)", "shell_run(./run *)"],
    "deny":  ["shell_run(make clean*)", "fs_grep(**/secrets/**)"] } }
```
模式仅支持**前缀匹配**（尾 `*`）或全等；`shell_run` 的 pattern 作用于空白规范化后的命令串。两文件规则合并共存，deny 集先评。

### 7.3 `danger.py` 首版清单（正则，Unix 面）

`rm -rf|-fr`、`sudo `、`git push --force|-f`、`git reset --hard`、`> /dev/`、`mkfs|dd if=`、`kill|pkill|killall`、`shutdown|reboot`、`curl|wget .* \| (ba)?sh`、`chmod -R 777`、包管理全局写（`pip install`（无 `--user/--target`）…）。承认覆盖有限——纵深靠监禁（§7.4）。

### 7.4 `ExecutionGateway.run(cmd, cwd, timeout, cancel) -> ExecResult`

1. jail：`realpath(cwd)` 必须以 {project_root, `<project>/.jarvis/workspace`, scratch} 之一为前缀，否则拒绝（不进危险检测，直接 deny）；
2. env allowlist：`PATH HOME LANG TERM` + `[permissions].extra_env`；
3. `asyncio.create_subprocess_shell(..., start_new_session=True)`；cancel/timeout → `killpg`；
4. stdout/stderr 流式写 `ArtifactStore`（§7.6），内存只保 tail ring buffer（200 行）；
5. 返回 `ExecResult(rc, duration_s, artifact_id, tail)`；journal 记录后返回。

### 7.5 Journal（`journal.py`，`.jarvis/journal.jsonl`）

```json
{"ts":"2026-07-02T10:31:05","seq":12,"kind":"exec","cmd":"make init","cwd":"&PROJ/.jarvis/workspace/NTools",
 "rc":0,"duration_s":41.2,"artifact":"a3f9…","session":"20260702-103000","decision":"allow:rule=shell_run(make*)"}
```
`journal://<ts>#<seq>` 即 dossier provenance 的引用格式。

### 7.6 ArtifactStore（`artifacts.py`）

`.jarvis/artifacts/<sha256[:12]>/{payload, meta.json}`；`meta.json = {tool, cmd?, created, bytes, lines, mime}`。`spill(text|stream) -> artifact_id`；`read(id, start, end)` 供 `artifact_read`。容量策略：LRU 按目录 mtime，超 `[context].artifact_cap_mb`（默认 2048）清最旧且无 journal 引用者。

## 8. 上下文管理（`agent/context.py`、`ledger.py`）

### 8.1 TokenLedger

```python
class TokenLedger:
    sections: dict[Section, int]        # P0..P4 当前占用
    window: int                         # backend.context_window()
    calib: float = 1.0                  # usage 校准系数
    def estimate(text) -> int:          # ceil(len(chars)/4 * calib)
    def calibrate(usage: Usage):        # calib = 实际 prompt_tokens / 上轮估算，EMA(0.3) 平滑
    def utilization() -> float          # 上轮真实 prompt_tokens / window
```

### 8.2 `assemble(user_text) -> list[ChatMessage]`

```
1 if utilization ≥ 0.80: T5 压缩（§8.4）        # 唯一时点
2 P0 = prompts.system.build(cfg)                 # 七层，会话内缓存（前缀稳定）
3 P1 = taskframe.render()                        # ≤1.5K，超限自截 pending 之外各栏
4 P2 = 显式检索结果（本轮工具喂入，不自动注入）
5 P3 = 历史 messages（含既往摘要块，经 T2/T3 改写后）
6 断言 sum ≤ window - P4_reserve(6K)；违反 → 依序再触发 T3 → T5 → 报 Error
```

### 8.3 T0–T5 实现约定

每层是纯函数 `apply(state: CtxState) -> CtxState`（`CtxState = (messages, ledger, artifacts_meta)`），幂等、无 IO（T1 落盘除外，经注入的 store 接口）、单测直接构造 state 断言。触发参数全部落 `[context]` 配置节（§12.2），DESIGN §4.2 的表为默认值。T3 去重键 = 工具名+规范化参数（`fs_read` 同 path 不同区间视为同键，保最新）。

### 8.4 T5 压缩子调用

`backend.chat(messages=[summarize_prompt, 待压跨度渲染文本], tools=[])`——无工具的一次性小调用。输出必须是五栏 YAML（decisions/facts/state/pending/discarded）；解析失败重试一次；再失败 → 降级：不压缩，改为把最老跨度整体 T1 落盘 + 占位（宁可丢上下文不可丢结构）。摘要块以 `role=user, content="[COMPACTED]\n<yaml>"` 形式入 messages，并写 session。

## 9. 信息系统（`info/`）

### 9.1 文件角色分类器（`classify.py`）

规则序列（首命中即定，全部可单测）：路径 glob（`SAMPLES/**`→sample、`doc*/**`→doc、`bin/**`+可执行位→run-script）→ 文件名（`Makefile|CMakeLists.txt|configure`→build-script）→ 扩展名 → 内容嗅探（首 4KB：`^\s*(BLOCK|DECAY)\s+`→SLHA 样例、`^#!`→script、`^\s*PROGRAM\s`→fortran-main）。输出写入 index JSON 新增顶层字段 `"roles": {"<relpath>": "<role>"}`，schema 版本 1.0→1.1（读取端对缺失字段容错，向后兼容）。

### 9.2 Dossier（`dossier.py`）

dataclass 树按 DESIGN 附录 A；`Provenance(kind, ref, confidence)` 校验：`kind∈{file,command,doc,model-inference,user}`；`ref` 格式 `path:line` | `journal://ts#seq` | `artifact://id`。存储 `<project>/.jarvis/dossier/<package>.yaml`。`DossierStore.get(section: str)`（点路径）/`update(section, patch: dict, provenance)`：节级合并写 + 全文件原子替换（tmp+rename）+ mtime 检查。`confidence=="high"` 且 `kind=="command"` 时校验 journal 引用存在。

### 9.3 InfoSearch（`search.py`）

```
query → 并行四路（按 scope 过滤）：
  code:    index.symbols 精确名 (score 100) / 前缀 (80) / 引用 (60) / fs_grep 关键词 (40)
  dossier: 节名与正文关键词 (70)
  kb:      规则条目关键词 (65)
  facts:   memory description 关键词 (50)
→ 合并排序取 k，每条 Snippet(text ≤ 400 chars, ref, layer, score)
```
嵌入检索留接口（`rank_hook`）不实现（DESIGN §5.4 决策）。

### 9.4 记忆（`memory.py`）

目录 `~/.jarvis/projects/<sha256(cwd)[:16]>/memory/`；frontmatter 解析与 skills 共用 `_frontmatter.py`。`rebuild_index()` 每次写后重建 MEMORY.md（≤200 行/25KB，超限尾栏提示）。`recall(query) -> list[MemoryHit]`：将清单（name+description）交 backend 无工具小调用选 ≤5 个 id，输出 JSON list 校验；>1 天条目的 digest 前缀加 staleness 告警行。

### 9.5 `yaml_module_validate` 三级实现

- L1 语法：现 `hep.yaml_assistant.review_yaml_file`；
- L2 结构：对照 `kb/jarvis-hep/<ver>/schema.yaml`（required keys、类型、枚举——Sampling.Method 合法值等）；
- L3 语义 lint（每条独立函数 + 独立测试）：
  `V1` `&J`/`@PackID` 宏合法性；`V2` `clone_shadow=true ⇒ path 含 @PackID`；`V3` 变量闭合：`inputs_vars ∪ LogL_free_symbols ⊆ sampling_vars ∪ outputs_vars`；`V4` `required_modules` 引用存在且无环；`V5` `source`/`default_yaml_path` 路径存在（相对 `&J` 展开）；`V6` installation 命令中 `${source}/${path}` 已定义；`V7` SLHA entry 类型（int 或 `[int,int]`）；`V8` 重复变量名；`V9` `save_dir` 可写；`V10` expression 可被 sympy 解析（依赖可选，缺则跳过并注记）。
输出 `data={"errors":[...], "warnings":[...]}`，每条含 `rule_id, path, message`。

## 10. 子智能体、技能与 Plan 模式

### 10.1 `agent_spawn`（`tools/subagent.py`）

```
1 registry_child = registry.filter(AGENT_TYPES[type].allowed_tools) - {agent_spawn}   # 禁嵌套
2 ctxmgr_child = ContextManager.fresh(P0=agent_type_prompt)     # 完全隔离
3 loop_child = AgentLoop(同 backend, registry_child, ctxmgr_child, trace(子episode), buffer_emit)
4 await loop_child.run_turn(prompt, cancel=父 token)            # 串行，同一事件循环
5 return ToolOutcome(digest=buffer[-2000:], data={"usage": …})  # usage 归并父 ledger 账单
```
内建类型定义与 `.jarvis/agents/*.md`（frontmatter：`name/description/allowed-tools`，项目级覆盖用户级）由 `skills/_frontmatter.py` 同一解析器处理。

### 10.2 技能（`skills/`）

`Skill(name, description, when_to_use, allowed_tools, user_invocable, body_path)`；`loader.discover()` 只读 frontmatter；`resolve(name, args) -> str` 惰性读正文并做 `$ARGUMENTS`/`${SKILL_DIR}` 替换（不支持 `` !`cmd` ``——安全裁剪）。清单注入预算三级：<2K token 全量、<1K 仅内建、<400 仅名字。用户路径 `/name args` 与模型 `skill` 工具共用 `resolve`。

### 10.3 Plan 模式

状态四元组挂在 AgentLoop：`pre_plan_mode / plan_file(~/.jarvis/plans/plan-<session>.md) / base_p0 / context_cleared`。`enter_plan()`：存 pre 模式、切 `PermissionMode.PLAN`、P0 追加规划约束层。`exit_plan()`：读 plan 文件 → `approval_fn(plan_text) -> Literal["clear_exec","exec","manual","revise"]`（回调注入，CLI/Textual/测试各自实现）→ 按 DESIGN §8 Phase C 四选项处置；`clear_exec` 清 P3 后切 `acceptEdits`。

## 11. 数据飞轮存储格式（`flywheel/trace.py`，M1 起生效）

### 11.1 TraceRecord（`~/.jarvis/traces/<session>/<turn>-<step>.json`）

```json
{"v":1,"ts":"…","session":"20260702-103000","turn":3,"step":2,
 "backend":"mlx:Qwen3-Coder-30B-A3B-4bit@base",
 "versions":{"prompt":"p1","kb":null,"dossier":"sha1:…","protocol":1},
 "messages_ref":"artifact://…",            // 组装后 messages 全文落工件，trace 存引用
 "response":{"content":"…","tool_calls":[{"id":"…","name":"fs_read","arguments":"{…}"}],
             "finish_reason":"tool_calls","repaired":false},
 "usage":{"prompt_tokens":8123,"completion_tokens":211,"cached_tokens":6100}}
```

### 11.2 Episode 与信号

`<session>/episode-<turn>.json`：`{"steps":[…],"phase":"B","signals":[{"kind":"validate_pass","value":true,"ref":"journal://…"},{"kind":"user_feedback","value":"good"}]}`。`trace.attach_signal()` 由 validate/dryrun 工具、审批回调、`/feedback` 命令调用。`/incognito`：session 级 flag，TraceRecorder 变 no-op。

### 11.3 数据集记录（M6，`datasets/<name>@<ver>/train.jsonl`）

```json
{"messages":[…],"meta":{"src":"session/turn","signals":["validate_pass"],"capability":2,
 "backend":"…","scrubbed":true,"kb_ver":"…"}}
```

### 11.4 会话存储 v2

`~/.jarvis/sessions/<id>.events.jsonl`（protocol 事件序列化：`{"type":"ToolResult","fields":{…}}`）+ `<id>.messages.json`（末态消息数组快照，供快速 `--resume`）。旧 `sessions.jsonl` 只读兼容，`/resume` 优先新格式。

## 12. 配置 schema

### 12.1 `.jarvis-agent.toml` 扩展（全默认值即本文档各节数字）

```toml
[runtime]
backend = "mlx-server"            # mlx-server | mlx-subprocess | remote
model = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
adapter = ""                      # flywheel adapter 路径，空为 base
context_window = 0                # 0 = 自动探测
max_tokens = 4096
temperature = 0.2

[context]
reserve_output = 6144
tool_digest_budget = 1024
compact_at = 0.80                 # T5
tighten_at = [0.50, 0.70]         # T2
snip_at = 0.60                    # T3
idle_compact_s = 300              # T4
artifact_cap_mb = 2048

[permissions]
mode = "default"                  # default | plan | acceptEdits | dontAsk
exec_timeout_s = 120
install_timeout_s = 1800
extra_env = []

[flywheel]
trace = true                      # /incognito 会话级关闭
```

### 12.2 `agent_state.json` v2（显式覆盖）

```json
{"version":"2.0","override":{"model":"…","adapter":"…","set_by":"/model","ts":"…"}}
```
读取规则：仅当 `override` 存在才覆盖 TOML 的对应字段；`load_config` **不再无条件重写此文件**（现状 bug 修复）；`/status` 每字段标注来源 `toml|state|default`。

## 13. 协议扩展与 TUI 适配

### 13.1 事件（v1 兼容——消费者忽略未知类型即向后兼容）

新增 `StopRequested(timestamp, reason="user")`：控制事件，**不加入** `AgentEvent` 渲染 union 与 `_AGENT_EVENT_TYPES`（`validate_event` 拒收，TranscriptView 永不消费）——按 TUI_udpate_plan 原设计，M1 随 CancelToken 一起落地。渲染事件复用现有 10 个：工具流量走 `ToolCallStarted/ToolResult/LogLine`，分区占用走 `Metrics(summary, detail=json)`。审批交互（权限 ask、plan 四选项）**不走事件总线**，走注入的 `approval_fn` 回调（同步于 loop，UI 层实现各自的对话框）。

### 13.2 TUI 线程模型迁移（M0）

现状：`start_llm_request` 起 daemon 线程跑同步 dispatch，`call_from_thread` 回灌。目标：Textual 自带 asyncio loop——`start_llm_request` 改为 `asyncio.create_task(agent_loop.run_turn(...))`；`TranscriptView` 经 EventBus 订阅（既有 consume 不变）；模拟流参数（`RESPONSE_STREAM_SECONDS_PER_CHAR`）删除，`AssistantTextDelta` 直接驱动。斜杠命令仍走同步 `dispatch`（快路径，不进 loop）。

## 14. 错误分类学

| 类型 | 定义位置 | 处理 | 用户可见 |
| --- | --- | --- | --- |
| 工具失败 | `ToolOutcome(ok=False)` | 回喂模型自纠，不中断 | ToolResult 块（红标） |
| 权限拒绝 | `Decision(deny)` → outcome | 同上 | 同上 + journal |
| 可恢复后端错 | `BackendFailure(recoverable=True)` | backend 内退避重试，静默 | 仅 Status 提示 |
| 永久后端错 | `BackendFailure(recoverable=False)` | 终止本轮，降级链评估 | Error 块 |
| 网关拒绝（jail 逃逸等） | `GatewayDenied` → outcome | 回喂 | ToolResult 块 |
| 配置错误 | `ConfigError`（启动期） | fail fast | CLI 错误退出 |
| 内部不变量破坏（消息对失配、预算断言） | `assert`/`InvariantError` | 崩溃并保存会话 | Error + 会话已存提示 |

## 15. 测试映射

| 模块 | 测试文件 | 关键用例 |
| --- | --- | --- |
| runtime/types+backend | `test_runtime_types.py` | frozen/slots；SSE 状态机喂 chunk 序列断言事件流；tool_calls 片段拼装 |
| mlx_server | `test_mlx_server.py` | 假 HTTP server：重试分级、崩溃重启一次、窗口探测 fallback |
| tools/registry | `test_tool_registry.py` | schema 导出、两段校验失败为 data、并行 cap=4、含非 cs 工具整批串行 |
| gateway | `test_gateway.py` | jail 前缀表、killpg on cancel、journal 行 schema、danger 正则表逐条 |
| permissions | `test_permissions.py` | 模式×tier 矩阵、deny 优先、前缀 pattern、会话白名单 |
| context | `test_context.py` | T0–T5 各纯函数幂等；utilization 触发表；轮边界断言（步间无 T5） |
| taskframe/dossier | `test_dossier.py` | 点路径 get/update、provenance 校验、mtime 冲突拒绝 |
| yaml_module | `test_yaml_validate.py` | V1–V10 逐条正反例（用 NTools.yaml 变异体） |
| flywheel/trace | `test_trace.py` | 记录 schema、incognito no-op、signal 附加 |
| loop（集成） | `test_agent_loop.py` | 假 backend 脚本化事件流：终止条件、消息对、步数上限、取消点、修复路径 |
| 功能清单 v1（M1 验证门，真模型手测） | `docs/checklists/M1.md` | ≥10 项：含 "构建探测端到端"、"plan 模式写非 plan 文件被拒且返回 ToolResult 而非异常"、"Stop 中断流保留部分文本" |

既有 9 个测试文件保持绿是每次合入的门（沿用 TUI 重构的 gate 纪律）。

## 16. M0/M1 文件级工作分解（PR 粒度）

**M0（依赖：无）**
1. `runtime/types.py` + 测试；2. `runtime/backend.py`（Protocol/Retry/CancelToken）+ 测试；3. `runtime/mlx_server.py` + 假服务器测试；4. `runtime/subprocess_backend.py` 包装现 MLXBackend（+默认超时）；5. `config.py` `[runtime]` 节 + `agent_state` v2 显式覆盖 + `/status` 来源标注；6. TUI 线程模型迁移（§13.2）+ 真流验证；7. `protocol` 加 `StopRequested` + Stop 控制 UI（补上 TUI_udpate_plan 未落地部分）。

**M1（依赖：M0）**
1. `tools/base.py + registry.py` + 测试；2. `gateway/`（六文件）+ 测试；3. `fs.py/task_tools.py/shell.py` 工具 + 测试；4. `agent/ledger.py + taskframe.py`；5. `prompts/system.py` 七层 v1；6. `agent/context.py`（assemble + T0/T1）；7. `agent/loop.py` + 集成测试；8. `flywheel/trace.py`；9. `tui.dispatch` 自然语言路径接 loop、`agent_actions` 标记协议退役；10. `index_query` 工具化；11. 功能清单 `docs/checklists/M1.md` 编写并全项通过。

M2–M6 按 §2 布局中的里程碑标注展开，进入前先在本文档补充对应节的细化（本文档随里程碑滚动更新，每次更新 bump 小版本）。
