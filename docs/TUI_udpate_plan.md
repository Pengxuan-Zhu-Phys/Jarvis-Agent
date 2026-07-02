# Refactor `textual_tui.py` + formatted agent-loop output

## Context

`src/jarvis_agent/textual_tui.py` is a 1912-line file whose entire Textual app
(`JarvisAgentApp`, ~1600 lines) is defined as a **nested class inside
`run_textual_ui()`** ([textual_tui.py:68](src/jarvis_agent/textual_tui.py:68)),
purely to defer the optional Textual import. Consequences:

- The app and its widgets can't be imported or unit-tested.
- Tests compensate by reading the module as text: `test_textual_home_uses_round_dot_monitor`
  has **243 `assertIn(..., source)`** assertions over raw CSS/method strings
  ([tests/test_tui.py:206](tests/test_tui.py:206)). These pass even when code is broken
  and block dead-code removal.
- Model output is rendered as **plain text** — `Log` widget + manual cell-wrapping
  (`write_wrapped_output`, `wrap_output_text`). No markdown, code highlighting, or
  structure. For an agent loop (assistant text + tool calls + results + status), a
  structured, formatted transcript like Claude Code / Grok is essential.

Goal: move the app to module scope split into cohesive, testable units, and replace
the plain output pane with a **hybrid block-based transcript** driven by a typed
**agent-event protocol**, so a future agent loop emits events without touching UI code.

Confirmed toolkit: Textual **8.2.7** (`RichLog`, `Markdown`, `App.run_test()` pilot),
`rich.markdown.Markdown`, `rich.syntax.Syntax`. Design decisions (from user):
**hybrid transcript** (structured block widgets + a `RichLog` "Live Log" block for
long command output), **raw-live-then-format-on-settle** streaming, and **define the
event protocol now**.

## Non-goals

- No change to command behavior / the shared router `TerminalUI.dispatch`
  ([tui.py:114](src/jarvis_agent/tui.py:114)) — it stays the single source of truth.
- No real streaming backend / persistent MLX server (tracked separately in
  `docs/ROADMAP.md` Phase 0.5). The stream stays simulated; only rendering changes.
- Plain fallback UI (`TerminalUI`) unchanged.

## Target package layout

Convert `textual_tui.py` → package `src/jarvis_agent/textual_tui/`. Split by the
units the request named (layout/CSS, history, streaming, animation, git) plus the
output subsystem. Pure modules have **no Textual import** (always importable +
unit-testable); Textual view modules are imported lazily by `run_textual_ui`.

The **agent-event protocol is UI-agnostic and lives outside the Textual package**
(`src/jarvis_agent/protocol/`) so a real agent loop can emit events with zero Textual
dependency; the transcript is one consumer among future ones.

```
protocol/
  __init__.py        # re-export events + EventBus
  events.py          # PURE: frozen+slots AgentEvent dataclasses (see below)
  bus.py             # (Phase 2, minimal) EventBus over asyncio.Queue for
                     #   producer/consumer decoupling; TranscriptView subscribes
```

```
textual_tui/
  __init__.py        # import-safe. Re-exports run_textual_ui, TextualUnavailable,
                     #   and the pure helpers tests import (back-compat).
                     #   MUST NOT import app.py at top level.
  errors.py          # TextualUnavailable
  text_utils.py      # PURE: wrapping, path compaction (_compact_path/_middle),
                     #   token estimate, time labels, metrics regex/parse
                     #   (split_output_metrics*, compact_metrics,
                     #   parse_context_metric_tokens), slash_suggestion_context,
                     #   location<->index, ping_pong_offset, pacman_ghost_frame,
                     #   wrap_plain_text, _format_token_count
  gitinfo.py         # PURE: GitInfo dataclass + get_git_info + git helpers
  animation.py       # PURE render fns: logo-monitor state machine
                     #   (render_logo_monitor_frame/logo_cell_color/
                     #   current_monitor_widths + series), ghosts, spinner frames
  history.py         # TurnRecord + HistoryModel (turn list, expansion, session
                     #   list; pure logic) + HistoryPanel(ListView) view
  composer.py        # PromptTextArea + composer-height logic + SuggestionController
                     #   (slash/model picker state)
  streaming.py       # StreamController: full-text buffer, reveal tick, settle
  app.py             # JarvisAgentApp(App) at MODULE SCOPE — thin coordinator that
                     #   wires widgets + controllers + router. Textual imported
                     #   normally here (only loaded when textual present).
  styles.tcss        # CSS extracted from the inline string; App.CSS_PATH = styles.tcss
  output/
    blocks.py        # PURE: parse raw assistant text -> renderable segments
                     #   (prose -> rich.markdown.Markdown, code -> rich.syntax.Syntax)
    widgets.py       # block widgets (Textual)
    transcript.py    # TranscriptView(VerticalScroll).consume(event) — consumes the
                     #   jarvis_agent.protocol events
```

### Optional-dependency pattern (replaces the nested class)

- `__init__.py` stays import-safe; `run_textual_ui(config)` does
  `from .app import JarvisAgentApp` inside `try/except ImportError: raise TextualUnavailable`.
- `app.py` and other Textual view modules import Textual at top level normally — they
  are only imported when Textual is installed, so no per-symbol guarding is needed.
- Pure modules (`text_utils`, `gitinfo`, `animation`, `output/events`, `output/blocks`,
  and the model half of `history`) never import Textual → directly unit-testable.

## Formatted output subsystem (core deliverable)

### 1. Agent-event protocol — `jarvis_agent/protocol/events.py`

UI-agnostic, immutable typed events; `AgentEvent` is their union. This is the
contract a future agent loop (local MLX, remote Redis, or a Jarvis-HEP Worker feed)
emits and the transcript consumes. **Every event dataclass is
`@dataclass(frozen=True, slots=True)`** (repo is Python ≥3.11) with a one-line
docstring, matching the V2 frozen-event style of
`Jarvis-HEP-v2/jarvishep2/sample_logger.py::SampleLogEvent` and the typed-dataclass
convention of `sample.py::ExecutionStep` / `Sample`.

Each event carries forward-compat hooks: a module-level `PROTOCOL_VERSION = 1` and a
`metadata: Mapping[str, Any] = field(default_factory=dict)` extension point, so new
consumers/producers (e.g. `HEPStatus`, `OpCountDelta`, `ResourceSnapshot`) can be
added without breaking the union.

```python
PROTOCOL_VERSION = 1

@dataclass(frozen=True, slots=True)
class UserPrompt:
    """User turn entering the transcript."""
    text: str
    timestamp: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
# ...same decorator + docstring + metadata for each:
AssistantTextDelta(text)        # streamed chunk into the active assistant block
AssistantTextEnd()              # triggers format-on-settle
ToolCallStarted(name, args)     # e.g. index / yaml / explain
ToolResult(name, output, ok=True)
LogLine(text)                   # appended to the active LiveLog block
Status(message)                 # transient status line
Error(message)
Metrics(summary, detail="")     # [metrics] block from MLX
Summary(title, body)            # e.g. /index stats
```

Also in `events.py`:

- `AgentEvent = UserPrompt | AssistantTextDelta | ...` union, and a
  `validate_event(e: AgentEvent) -> None` (reserved-`metadata`-key / version-compat
  check). `TranscriptView.consume` calls it at entry so nothing can emit garbage.
- **Version evolution rule:** `PROTOCOL_VERSION = 1` is fixed now; consumers must
  safely ignore unknown events (`isinstance` dispatch + `getattr(e, "metadata", {})`);
  a breaking change bumps to `2` with a deprecation window, documented in
  `docs/AGENT_EVENT_PROTOCOL.md`.

`protocol/bus.py` — minimal `EventBus` on `asyncio.Queue` with `weakref` subscribers:
`subscribe(consumer)` / `unsubscribe(consumer)` / async `publish(event)`.
`TranscriptView` subscribes on `on_mount` and unsubscribes on `on_unmount` (no leak).
Keep it small — no priorities/filters until a real need appears.

### 2. Block parsing — `output/blocks.py` (pure)

- `split_segments(text) -> tuple[Segment, ...]`: split fenced ```code``` from prose.
  Return a tuple (hashable) and decorate with `functools.lru_cache` keyed on the raw
  text, so re-rendering the same block (resize, history replay) never re-parses.
- prose → `rich.markdown.Markdown(text)`; code → `rich.syntax.Syntax(body, lang,
  word_wrap=True, background_color="default")`.
- Pure, no Textual → unit-testable on segment boundaries and language detection.

### 3. Block widgets — `output/widgets.py`

- `UserBlock`, `AssistantBlock`, `ToolCallBlock`, `ToolResultBlock`, `SummaryBlock`,
  `ErrorBlock`, `StatusBlock` — `Static`-based, render Rich renderables, styled per
  type (headers/borders) like Claude Code / Grok.
- `LiveLogBlock(RichLog)` — the hybrid choice: a single embedded `RichLog` for
  streaming command / tool output, efficient for HEP jobs with thousands of lines.
- `AssistantBlock` holds a raw buffer; during stream it shows raw text; `finalize()`
  re-renders via `blocks.split_segments` (**raw live, format on settle**). `finalize()`
  caches its parsed segments on the instance (and `split_segments` is `lru_cache`d),
  so repeated renders / resize reflow reuse the parse instead of re-running
  markdown+syntax highlighting. After settle the raw text buffer is released (keep
  only the rendered segments) to bound memory in long sessions.
- **Update gating for long/high-frequency output** (op_count-style, à la V2): the
  `StreamController` and `LiveLogBlock` batch writes and flush on a throttle
  (coalesce N deltas / ~16–50ms) rather than one refresh per token, and use
  `reactive` + `watch` so only the active block repaints, not the whole transcript.

### 4. Transcript — `output/transcript.py`

- `TranscriptView(VerticalScroll)` replaces the `#log` `Log` pane.
- `consume(event: AgentEvent)` dispatches: append user/assistant/tool/summary/error
  blocks; route `AssistantTextDelta` to the active `AssistantBlock`; route `LogLine`
  to the active `LiveLogBlock`; `AssistantTextEnd`/`ToolResult` finalize.
- Preserves current selection/OSC52 copy (`screen.get_selected_text()` +
  `copy_to_clipboard`) and metrics caption / context-meter update.
- Manual `wrap_output_text` / `reflow_output` are **removed** — Rich/Textual handle
  wrapping and resize reflow.

### 5. Command → event adapter (in `app.py`)

Thin adapter turns today's `TerminalUI.dispatch` results into events; router unchanged:

- submit → `UserPrompt`; LLM path → `AssistantTextDelta`* + `AssistantTextEnd` (+ `Metrics`).
- `/index` → `ToolCallStarted("index", …)` + `Summary` (index stats).
- `/yaml`, `/explain` → `ToolCallStarted` + `ToolResult`.
- exceptions → `Error`.

Future real agent loop emits the same events directly into `TranscriptView.consume`.

## Execution rhythm (suite must stay green; one REFACTOR_NOTE per phase)

Land in four phases, in order. **Gate:** each phase ends by running
`PYTHONPATH=src python3 -m unittest discover -s tests` — it must be green before the
next phase starts. The one exception is the file-layout-coupled test
`test_textual_home_uses_round_dot_monitor`, which cannot survive the split: it is
migrated **in Phase 1** to a minimal behavioral smoke test so the gate stays honest,
with fuller behavioral/unit coverage added in Phase 4 (see Test strategy). Each phase
also produces a short `REFACTOR_NOTE.md`
(template below) recording interface changes and parity verification.

1. **Phase 1 — Package split (no behavior change).** First scaffold
   `jarvis_agent/protocol/events.py` (full dataclasses + `PROTOCOL_VERSION` +
   `AgentEvent` union + `validate_event`), even before anything consumes it, so the
   import path is stable for everyone from day one. Then create the `textual_tui`
   package; move pure
   helpers to `text_utils.py`/`gitinfo.py`/`animation.py`; move `JarvisAgentApp`
   verbatim into `app.py` at module scope; extract CSS to `styles.tcss`; lazy-import
   the app in `run_textual_ui`; re-export back-compat names from `__init__.py`.
   `cli.py` import path stays `jarvis_agent.textual_tui`. Migrate the source-string
   test `test_textual_home_uses_round_dot_monitor` to a minimal
   `App.run_test()` smoke test (app mounts; logo-monitor + version lines present),
   since it reads `textual_tui.__file__` and cannot survive the split.
   **Run tests → must be green.**
2. **Phase 2 — Output subsystem.** Add `jarvis_agent/protocol/` (events + a minimal
   `EventBus` over `asyncio.Queue`) and `output/` (blocks, widgets, transcript); swap
   `#log` `Log` → `TranscriptView`; rewire streaming to `AssistantBlock` +
   `StreamController` (throttled/batched writes, see below); wire the command→event
   adapter over the **existing** `TerminalUI.dispatch` results. Implement the
   throttled `StreamController` + `LiveLogBlock` batching **before** wiring
   `TranscriptView.consume`. End the phase with a `scripts/verify_tui_parity.py` that
   automates the key checks (markdown + fenced-code renders on settle, LiveLog append,
   OSC52 copy still works). **Run tests → must be green.**
3. **Phase 3 — Extract view modules.** Pull out `history.py`, `composer.py`,
   `streaming.py`, and animation view helpers; reduce `app.py` to a thin coordinator.
   **Run tests → must be green.**
4. **Phase 4 — Cleanup + tests.** Delete provably-dead methods (`render_turn_panel`,
   `update_turn_panel`, `render_topbar`, `render_repo_info`, `toggle_history_prompt`,
   `visible_history_turn_index`, `_compact_model_name`); replace the brittle
   source-string test with behavioral + unit tests (see Test strategy).
   **Run tests → must be green.**

### `REFACTOR_NOTE.md` per phase

Short component doc (in the V2 spirit), appended per phase under
`docs/refactor/PHASE_N_*.md`:

- **Scope** — what moved / was added this phase.
- **Interface changes** — new/changed/removed public symbols and import paths;
  back-compat re-exports.
- **Parity verification** — how behavior was confirmed unchanged (test command +
  result, plus any manual `jarvis-agent tui` / `scripts/verify_tui_parity.py` check).
- **Jarvis-HEP integration impact** — effect on the shared `protocol/` contract
  (write "None" if unaffected; the field forces the question each phase).
- **Follow-ups** — anything deferred to a later phase.

## Kickoff order (recommended)

1. First: write the full `protocol/events.py` skeleton (`PROTOCOL_VERSION`, all
   dataclasses with docstrings + `metadata`, `AgentEvent`, `validate_event`).
2. Before Phase 1 code: land the `REFACTOR_NOTE.md` template and
   `docs/adr/0001-tui-refactor-pure-view-event-protocol.md`.
3. Phase 2: implement the throttled `StreamController` + `LiveLogBlock` batching
   first, then wire `TranscriptView.consume`.
4. Right after the refactor: write `docs/AGENT_EVENT_PROTOCOL.md` and refresh
   `docs/ARCHITECTURE.md`.

## Back-compat

- `cli.py`: `from jarvis_agent.textual_tui import TextualUnavailable, run_textual_ui`
  keeps working via `__init__.py` re-exports.
- `tests/test_tui.py` helper imports (`_compact_middle_path`, `_compact_path`,
  `_format_token_count`, `_home_relative_path`, `_relative_time_label`,
  `compact_metrics`, `estimate_context_tokens`, `location_to_text_index`,
  `pacman_ghost_frame`, `parse_context_metric_tokens`, `ping_pong_offset`,
  `slash_suggestion_context`, `split_output_metrics`, `split_output_metrics_detail`,
  `text_index_to_location`, `wrap_plain_text`) preserved via `__init__.py` re-export
  from `text_utils`. `get_git_info` re-exported from `gitinfo`.

## Test strategy

- **Retire** `test_textual_home_uses_round_dot_monitor` (243 `assertIn(..., source)`
  string checks at [tests/test_tui.py:205](tests/test_tui.py:205)) — intrinsically
  tied to file layout. Replaced by a minimal `run_test()` smoke test in **Phase 1**;
  the behavioral assertions below land in **Phase 4**.
- **Add behavioral tests** using `async with JarvisAgentApp(cfg).run_test() as pilot`:
  home renders logo-monitor + version lines; submitting a prompt appends a
  `UserBlock` + `AssistantBlock`; `/index` yields a `SummaryBlock`; unknown `/x`
  yields an `ErrorBlock`; critical theming asserted via widget styles (e.g.
  selection color) rather than raw CSS strings.
- **Add unit tests** (no Textual) for `output/blocks.split_segments` (prose/code
  split, language detection, and cache identity — same text returns the cached
  segments), `output/events` construction + frozen/slots immutability
  (assert `FrozenInstanceError` on assignment, `AttributeError` on unknown attr),
  `HistoryModel`
  expansion, `animation` frame functions, and the already-pure `text_utils` helpers.
- **Golden / snapshot tests (high priority)** for complex `AssistantBlock` renders
  (markdown + fenced code): dump the settled renderable to text and hash it, so a
  `rich`/`textual` upgrade that drifts SLHA/YAML/code highlighting fails loudly.
- **(Optional, adds Hypothesis dev dep)** property tests focused on `split_segments`
  and `wrap_plain_text` first, covering the high-risk cases: very long code blocks,
  exotic Unicode, and malformed fenced code.
- **Integration (after Phase 4)** — `tests/test_agent_loop_simulation.py`: an
  `asyncio` producer emits ~50 `AssistantTextDelta` then `AssistantTextEnd` through
  the `EventBus`, asserting throttled flush, single finalize, and raw-buffer release.
- Keep all router/session tests in `TUITests` unchanged.
- **Convention for new modules:** public classes/methods get Google/NumPy-style
  docstrings; event dataclasses are self-describing via `__doc__` per §1.

## Verification

- `PYTHONPATH=src python3 -m unittest discover -s tests` — all green (minus the
  deleted source test, replaced by behavioral/unit tests).
- `python3 -c "import jarvis_agent.textual_tui"` succeeds; `python3 -c "from
  jarvis_agent.protocol.events import UserPrompt; from
  jarvis_agent.textual_tui.output.blocks import split_segments"` succeeds without
  importing the Textual view layer.
- Manual: `jarvis-agent tui --project .` → send a markdown answer (headings + fenced
  code) and confirm it renders raw while streaming then settles into formatted
  markdown + highlighted code; run `/index` and confirm a Summary block + Live Log
  behavior; `/yaml examples/hep-config.yaml` renders a ToolResult block; text
  selection still auto-copies.
- `jarvis-agent tui --plain` unchanged; simulate missing Textual (temporarily hide
  the import) → `run_textual_ui` raises `TextualUnavailable` and CLI falls back.

---

# Feature: Stop control (interrupt generation)

## Context

The refactor above is already implemented (package `textual_tui/`, `protocol/`,
`output/`). The TUI still has **no way to interrupt a running generation**. Today a
turn runs on a **daemon thread** doing a blocking `subprocess.run(mlx_lm.generate)`
in `MLXBackend` ([model/mlx.py:35](src/jarvis_agent/model/mlx.py)), then a
**simulated char reveal** (`update_response_stream`, 0.03s interval,
[app.py:949](src/jarvis_agent/textual_tui/app.py:949)) feeds `AssistantTextDelta`
into `TranscriptView.consume`. So a turn has two phases: an interruptible visible
stream (**responding**) and an uninterruptible in-flight subprocess (**thinking**).

Decisions (from user):
- **No Send button** — Enter stays the only submit (`PromptTextArea._on_key` in
  [composer.py](src/jarvis_agent/textual_tui/composer.py)).
- The Stop control **replaces the top-right clock** (`#ghost-clock`, a `Static`
  docked at the top-right of the composer): while generating, the time disappears and
  a clickable red `⏹ Stop` appears in the same slot; when idle the clock returns.
  `Esc` also stops.
- **Phased cancel:** MVP interrupts the visible stream and *detaches* the in-flight
  subprocess now; truly terminating the model process (Popen) is a follow-up.

## Behavior

- Idle: `#ghost-clock` shows the time (unchanged).
- Generating: clock slot shows red `⏹ Stop` (clickable) + `Esc` stops. It toggles
  **immediately** on generation start/end, not on the 1s tick.
- Stop during **responding**: flush the buffered stream, finalize the active
  `AssistantBlock` with a dim `⏹ Interrupted` footer (**partial text kept**), clear
  responding state, re-enable input, hide spinner, restore clock.
- Stop during **thinking**: set a cancel flag, tear down the spinner, mount a
  `StatusBlock("⏹ Interrupted")`, restore clock, re-enable input. The late-returning
  `finish_llm_request` sees the flag and drops the result. **MVP limitation:** the
  daemon subprocess keeps running to completion in the background (compute wasted;
  a second prompt can start a second process) — fixed by the Popen follow-up.

## Changes (MVP)

1. **`protocol/events.py`** — add a *control* event (frozen+slots, V2 style):
   ```python
   @dataclass(frozen=True, slots=True)
   class StopRequested:
       """User asked to interrupt the current generation (control event)."""
       timestamp: str
       reason: str = "user"          # user / timeout / error
       metadata: Mapping[str, Any] = field(default_factory=dict)
   ```
   Keep it **out of** the `AgentEvent` render union / `_AGENT_EVENT_TYPES` so
   `TranscriptView.consume` stays render-only; it is the forward-looking contract the
   real agent loop / `EventBus` will carry.
2. **`textual_tui/app.py`**:
   - `__init__`: `self._generation_cancelled = False`.
   - `start_llm_request` ([app.py:787](src/jarvis_agent/textual_tui/app.py:787)):
     reset the flag and call `self.update_ghost_clock()` right after setting
     `thinking_started_at`, so `⏹ Stop` shows instantly.
   - `update_ghost_clock` ([app.py:934](src/jarvis_agent/textual_tui/app.py:934)): if
     `is_generation_active()` render `[#ff6b6b bold]⏹ Stop[/]` (+ tooltip "Stop · Esc")
     else `current_time_label()`. `⏹ Stop` fits the existing `GHOST_CLOCK_WIDTH = 10`,
     so no width change.
   - `on_click` ([app.py:209](src/jarvis_agent/textual_tui/app.py:209)): add
     `widget_id == "ghost-clock"` → if `is_generation_active()`: `event.stop();
     self.request_stop()`.
   - `on_key` ([app.py:234](src/jarvis_agent/textual_tui/app.py:234)): add an `escape`
     branch **after** the existing suggestion/history Esc branches (so an open
     overlay dismisses first): `if event.key == "escape" and
     self.is_generation_active(): prevent/stop; self.request_stop(); return`.
   - **New `request_stop(self, reason="user")`**: build `StopRequested(...)` (future
     bus / optional session log); if `responding_started_at is not None` →
     `flush_response_stream()` + `TranscriptView.interrupt()` + clear
     `responding_started_at/response_text/response_index`; elif `thinking_started_at
     is not None` → `self._generation_cancelled = True; self.thinking_started_at =
     None` + `TranscriptView.interrupt()`; then common teardown:
     `hide_thinking_status()`, `update_ghost_clock()`, focus `#prompt`,
     `update_topbar_status()`.
   - `finish_llm_request` ([app.py:804](src/jarvis_agent/textual_tui/app.py:804)): at
     the top, `if self._generation_cancelled: self._generation_cancelled = False;
     self.thinking_started_at = None; self.hide_thinking_status(); return` — never
     stream a dropped answer.
3. **`textual_tui/output/transcript.py`** — add `interrupt(self)`: if
   `active_assistant` → `active_assistant.finalize(interrupted=True);
   active_assistant = None`; else `self.mount(StatusBlock("⏹ Interrupted"))`.
4. **`textual_tui/output/widgets.py`** — `AssistantBlock.finalize(self, interrupted:
   bool = False)`: after rendering segments, if `interrupted` append a dim
   `⏹ Interrupted` footer to the `Group` (partial text preserved via existing segments).
5. **`textual_tui/styles.tcss`** — style `#ghost-clock` Stop state (red/bold) + a
   `:hover` affordance so it reads as clickable.

## Tests

- `tests/test_protocol.py` — `StopRequested` construction + frozen/slots immutability;
  assert it is **not** accepted by `validate_event` (control event).
- Behavioral (`app.run_test()`, engine/`dispatch` stubbed so no real model): enter
  responding phase → `request_stop()` → active `AssistantBlock` finalized with the
  interrupted footer, `is_generation_active()` False, `#prompt` focused, clock text
  restored. Thinking-phase stop → `StatusBlock` mounted and a late
  `finish_llm_request` drops the result.
- `tests/test_output_blocks.py` (or widgets test) — `AssistantBlock.finalize(
  interrupted=True)` renders the footer and keeps text.

## Follow-up (true Popen cancel — frees compute)

- `model/mlx.py`: `MLXBackend.generate` uses `subprocess.Popen` and exposes the
  process/`terminate()`.
- Thread a cancel handle from the app through `TerminalUI.dispatch` →
  `WorkflowEngine.ask_model` → `MLXBackend` (a `threading.Event` cancel token or an
  `on_process_start(proc)` callback registered on the engine). `request_stop()`
  (thinking phase) calls `terminate()` so the process dies at once and no second
  concurrent subprocess can start.
- Publish `StopRequested` on `protocol.EventBus` once a real agent loop consumes it.

## Verification

- `PYTHONPATH=src python3 -m unittest discover -s tests` green.
- Manual `jarvis-agent tui --project .`: idle shows the clock top-right of the input;
  send a prompt → the slot becomes red `⏹ Stop`; click it (or press `Esc`) mid-stream
  → stream halts, block shows `⏹ Interrupted` with partial text kept, input usable,
  clock returns; press `Esc` during the "Thinking..." phase → `⏹ Interrupted` status,
  input usable.

---

# Long-term direction (backlog — beyond this refactor)

Separate tracks that build on the refactor above. **This refactor already delivers**
the "Pure + View" split, the typed `AgentEvent` protocol (versioned, UI-agnostic),
the hybrid transcript, update gating, and back-compat. The items below are follow-ups,
ordered by priority; each is its own change, not part of the 4-phase execution.

**P1 — Architecture & testability (institutionalize the pattern).**
- Make "Pure + View" a project-wide rule: all logic in pure `*_logic.py` / `protocol/`
  with zero Textual import; view layer only renders and binds, consuming events. New
  agent backends (local MLX, remote Redis, Jarvis-HEP Worker feedback) then need no UI change.
- Grow `jarvis_agent/protocol/` into the first-class contract: `EventBus` (asyncio.Queue
  pub/sub) so the real agent loop and TUI are fully decoupled; reserve `metadata` +
  `PROTOCOL_VERSION` for `HEPStatus` / `OpCountDelta` / `ResourceSnapshot`.
- Lightweight plugin/extension mechanism: a block-type registry + factory so
  Jarvis-HEP can register `HEPPlotBlock` / `SLHAViewerBlock` (sample status, likelihood
  curves, calculator progress) without forking; integrates with `output/blocks`.

**P1.5 — HEP event-extension path (non-blocking; the strategic payoff).**
- Short term: carry HEP state in the existing `metadata`, e.g.
  `{"hep": {"sample_uuid": ..., "op_count": 123, "status": "Running"}}` —
  `TranscriptView` ignores it for now.
- Then add first-class `HEPStatus` / `OpCountDelta` / `ResourceSnapshot` events.
- Provide a `jarvis_agent/protocol/hep` adapter that maps Jarvis-HEP
  `Worker.heartbeat` / `Archiver` status into standard events.
- Target: Jarvis-HEP's `monitor/dashboard.py` reuses `TranscriptView` + `protocol/`
  — one TUI framework, both products.

**P2 — Test strategy → high coverage by default.**
- Pyramid: 100% unit on pure modules; behavioral via `run_test()`/pilot; integration
  tests that drive a mocked agent loop (`asyncio` mock stream of `AssistantTextDelta`).
- Golden/snapshot tests for complex markdown+code rendering (textual dump) to catch
  style regressions; Hypothesis property tests (see Test strategy above).
- Purge every remaining brittle `assertIn(..., source)`-style test → structured assertions.

**P3 — Docs, decisions, DX (the moat).**
- `docs/ARCHITECTURE.md`: package map + data flow (`UserPrompt → Event → TranscriptView
  → Blocks`); `docs/AGENT_EVENT_PROTOCOL.md`: each event, when emitted, how consumed;
  `CONTRIBUTING.md` + `docs/DEVELOPMENT.md`: run tests / add a block type / incremental refactor.
- ADRs under `docs/adr/` for this refactor's decisions (hybrid transcript,
  raw-live-then-settle, removing the nested class) — start with
  `docs/adr/0001-tui-refactor-pure-view-event-protocol.md`.

**P3.5 — UX & resilience.**
- `styles.tcss` variables + a simple theme switch (dark / light / hep).
- `ErrorBlock` gets "Copy traceback" and, once the agent loop supports it,
  "Retry last turn".

**P4 — CI/CD & quality gates (GitHub Actions).**
- `ruff` (lint+format), `pyright`/`mypy` (strict), `pytest` with coverage ≥85%;
  **optional-dep matrix** (`pip install '.[tui]'` vs. without) plus a `textual run --dev`
  smoke so a Textual upgrade can't silently break the UI; `pip-audit` + `bandit`;
  dependabot/renovate. Perf regression benchmark (1000-line streaming + repeated
  resize) recorded under `docs/benchmarks/`.

**P5 — Performance & long-session stability.**
- Throttled/batched `TranscriptView` + `LiveLogBlock` updates (op_count-style gating);
  `reactive` + `watch` to scope repaints (partly delivered in Phase 2).
- `HistoryModel` virtual scroll + pruning (`max_turns` + `prune_strategy` keeping
  pinned + most-recent N); `LiveLogBlock` line cap with auto-rotate; release
  `AssistantBlock` raw buffers after settle (delivered); a `ResourceMonitor` panel
  (CPU/mem/token estimate) to catch a runaway agent loop that could OOM a multi-day run.
- Graceful shutdown/recovery: `Ctrl+C` saves the current session (history + partial
  transcript); later, a checkpoint mechanism aligned with Jarvis-HEP distributed checkpoints.

**P6 — Dependencies, release, community.**
- Pin Textual to a major (8.x), keep `rich` a core dep; strict semver with an
  `AgentEvent` version + deprecation window for breaking protocol changes.
- Release via hatch/flit → PyPI + GitHub Release + changelog; issue templates
  (bug/feature/performance) and a PR checklist (tests + docs + back-compat).
- Optionally split `protocol/` into a standalone `jarvis-agent-protocol` package so
  Jarvis-HEP can depend on the event definitions without pulling in the TUI.
