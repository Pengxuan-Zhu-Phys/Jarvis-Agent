# TUI Design

Jarvis-Agent ships two terminal UIs that share one command router:

- `jarvis_agent.textual_tui` — the primary Textual "workbench" UI.
- `jarvis_agent.tui.TerminalUI` — a plain `input()` loop used as a fallback when
  Textual is not installed or `--plain` is passed.

Both route every line through `TerminalUI.dispatch`, so command behavior stays
identical across the two front-ends. The Textual layer only adds presentation,
animation, streaming, and interaction; it never re-implements command logic.

## Layout

The Textual screen uses three CSS layers (`base`, `popup`, `composer`) so the
docked prompt and its overlays float above the scrolling workspace.

```
┌ topbar ────────────────────────────────────────────────────────────┐
│ ⎇ branch [worktree]   ~/path/to/project        1.2K / 2.0K   0 3 ⌄  │
├──────────────────────────────────────────────────────────────────────┤
│ todo-panel   (collapsed by default, toggled from the topbar)          │
│ turn-history (ListView: one row per turn, expandable)                 │
│ hero         (logo-monitor + home-panel, shown on the home page)      │
│ log          (selectable model-output pane, 1fr)                      │
│                                                                        │
│                                 [ notice ]  [ output-metrics ]         │
│                                 [ thinking spinner ]                   │
│                                 [ 👻 👻 👻 ]     [ clock ]             │
│                                 [ suggestions popup ]                  │
│ ❱ composer (PromptTextArea) ─────────────────────  model · backend    │
└──────────────────────────────────────────────────────────────────────┘
```

Region responsibilities:

| Region | Widget id | Role |
| --- | --- | --- |
| Top bar | `topbar` | Git branch / worktree, repo path, context meter, to-do toggle |
| Context meter | `context-info` | `used / limit` tokens; hover shows a filled percentage bar |
| To-do panel | `todo-panel` | Placeholder for future agent planning; toggled from the top bar |
| Turn history | `turn-history` | One selectable row per user turn; collapses to the current turn, expands on click / `Ctrl+H` |
| Hero | `hero` | Animated logo monitor plus the home page copy |
| Output | `log` | Selectable model output; wraps manually to the pane width |
| Composer | `composer` | Prompt input with a docked model badge subtitle |
| Overlays | `notice`, `thinking`, `output-metrics`, `pacman-ghosts`, `ghost-clock`, `suggestions` | Docked, transient status floating above `log` |

## Interaction model

- **Submit**: `Enter` sends the prompt; `Shift+Enter` inserts a newline and grows
  the composer up to `PROMPT_MAX_LINES` (5) before scrolling.
- **Slash picker**: typing `/` opens the `suggestions` popup filtered by prefix.
  `Up`/`Down` move, `Tab` completes the highlighted command, `Enter` or a click
  runs it. Suggestions work mid-line, not only at column 0
  (`slash_suggestion_context`).
- **Model picker**: completing `/model` swaps the popup to the model list; choose
  with `Up`/`Down`+`Enter`, a click, or the number keys `1`/`2`.
- **History**: `Ctrl+H` pins the full turn list; a click expands it; `Esc`
  collapses it. Long or multi-line prompts get a `▸`/`▾` toggle. Selecting a turn
  replays its stored output, metrics, and context-token count.
- **Clipboard**: selecting text auto-copies via the terminal's OSC52 write and
  flashes `Copied selection`; clicking the repo path copies the project root.
- **Busy guard**: while the model is generating, new submissions are rejected with
  a `notice`, and history replay is paused.

## Rendering pipeline

The model backend returns the whole response at once (see "Model execution" in
[ARCHITECTURE.md](ARCHITECTURE.md)), so the UI simulates live output:

1. `start_llm_request` starts a spinner and runs `TerminalUI.dispatch` on a daemon
   thread, marshaling the result back with `call_from_thread`.
2. `start_response_stream` stores the full text and reveals it character-by-character
   on a `0.03s` interval (`RESPONSE_STREAM_SECONDS_PER_CHAR`), showing an elapsed
   timer and an estimated tokens/sec.
3. `write_wrapped_output` wraps text to the current pane width by cell width and
   caches the raw text so `reflow_output` can re-wrap on resize without data loss.
4. A trailing `[metrics] ...` block emitted by the MLX backend is split off
   (`split_output_metrics_detail`), compacted, shown in `output-metrics`, and the
   real `context:` token count updates the meter.

Because the "stream" is cosmetic, the tokens/sec and elapsed figures during
responding are display estimates, not backend measurements.

## Animation

- **Splash / logo monitor**: `render_logo_monitor_frame` runs a small state
  machine — rows reveal top-to-bottom (`SPLASH_REVEAL_FRAMES`), then each half
  animates as a histogram of `*_MONITOR_SERIES` widths (`SPLASH_MONITOR_FRAMES`),
  then settles into the real Jarvis logo (`final_logo_widths`). The left half is
  white-on-blue, the right half yellow-on-dark-blue, matching the `Jarvis -v`
  branding.
- **Pac-man ghosts + clock**: a decorative `ping_pong_offset` marquee and a live
  wall clock docked near the composer.
- **Spinners**: Braille frames while "thinking", arc frames while "responding".

## Branding source

Branding is resolved once per session by `load_jarvis_branding`:

1. `Jarvis -v` output (preferred), with ANSI and the logo dot-prefix stripped.
2. the Jarvis-HEP `jarvishep/card/logo` asset (in the project or a sibling
   `Jarvis-HEP` checkout),
3. a built-in fallback pattern and banner.

The home panel gradient-colors the version lines with `TEXT_GRADIENT_COLORS`.

## Fallback UI

`TerminalUI.run` prints a static startup page (`startup_page`) and reads lines in
a loop. It supports the same commands but with no animation, streaming, popups, or
clipboard integration. This is the reference implementation of command behavior;
the Textual UI is a presentation layer on top of it.

## Known limitations

- The whole Textual `App` subclass is defined inside `run_textual_ui`, so it cannot
  be imported or unit-tested directly; current tests assert on router behavior and
  on module-level helper functions.
- `CONTEXT_LIMIT_TOKENS` is a fixed `2048`, so the context meter does not reflect
  the model's real context window.
- Response "streaming" is simulated; true token streaming needs a persistent model
  backend (see [ROADMAP.md](ROADMAP.md)).
