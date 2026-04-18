# ctx — Portable LLM Session Context

> *Git for LLM context.* Snapshot a dying session, brief the next LLM in 30 seconds, anywhere.

A small, local-first CLI that distills a long LLM coding session into a compact, instructional briefing you can paste into any other LLM (ChatGPT, Claude, Cursor, a fresh session) and keep working without redoing finished parts.


## Install

Requires Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...   # optional; without it, distillation runs in low-confidence offline mode
```

## Quickstart

```bash
cd your-project
ctx init
ctx pack                              # snapshot the most recent Claude Code session
ctx prime --target chatgpt --copy     # primer on the clipboard — paste into ChatGPT
```

## Commands

| Command | What it does |
|---|---|
| `ctx init` | Create a `.ctx/` directory in the current project. |
| `ctx pack` | Ingest the most recent LLM session, distill it, update `current.md`. |
| `ctx prime --target chatgpt [--copy] [--write PATH]` | Render a copy-pasteable briefing. |
| `ctx status` | Task / Status / Next step / Confidence from the current snapshot. |
| `ctx log` | Table of every session packed. |
| `ctx diff <session-id>` | Print the snapshot of a past session. |

MVP ships with one ingestor (`claude-code`) and one adapter (`chatgpt`).

## How it works

Five stages, each with one job:

```
Ingestor → Distiller → Storage → Composer → Adapter
```

- **Ingestor** reads `~/.claude/projects/*.jsonl` into a normalized transcript.
- **Distiller** (Claude Sonnet) compresses it into a snapshot with per-section **confidence**.
- **Storage** is `.ctx/` — plain markdown and JSON, hand-editable.
- **Composer** wraps the snapshot in role framing + anti-repetition guards.
- **Adapter** renders the briefing for one target LLM.


