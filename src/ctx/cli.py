from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .adapters import ADAPTERS
from .composer import compose, parse_snapshot
from .config import Config
from .distiller import Distiller, DistillerError
from .ingestors import INGESTORS, ClaudeCodeIngestor
from .storage import (
    Paths,
    append_index_entry,
    ensure_initialized,
    find_project_root,
    init_project,
    load_index,
    session_basename,
    write_current,
    write_snapshot,
    write_transcript,
)


app = typer.Typer(
    help="Git for LLM context. Snapshot a session, brief the next LLM.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def _paths() -> Paths:
    return Paths(root=find_project_root())


def _version_callback(value: bool):
    if value:
        console.print(f"ctx {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass


@app.command()
def init() -> None:
    """Create a .ctx/ directory in the current project."""
    root = Path.cwd()
    paths = init_project(root)
    if not paths.config_path.exists():
        Config.write_default(paths.ctx_dir)
    console.print(f"[green]initialized[/green] {paths.ctx_dir}")


@app.command()
def pack(
    source: str = typer.Option(
        "claude-code", "--source", "-s",
        help="Ingestor to use. MVP: claude-code.",
    ),
    session_id: Optional[str] = typer.Option(
        None, "--session",
        help="Ingest a specific session id instead of the most recent.",
    ),
) -> None:
    """Snapshot the current/most-recent LLM session into .ctx/."""
    paths = _paths()
    ensure_initialized(paths)
    config = Config.load(paths.ctx_dir)

    ingestor_cls = INGESTORS.get(source)
    if ingestor_cls is None:
        err_console.print(f"[red]unknown source:[/red] {source}")
        raise typer.Exit(code=2)
    ingestor = ingestor_cls()

    if session_id and isinstance(ingestor, ClaudeCodeIngestor):
        transcript_obj = ingestor.session_by_id(paths.root, session_id)
    else:
        transcript_obj = ingestor.latest_session(paths.root)

    if transcript_obj is None:
        err_console.print(
            f"[red]no {source} session found[/red] for {paths.root}. "
            "Has this project had a Claude Code session yet?"
        )
        raise typer.Exit(code=1)

    transcript = transcript_obj.to_dict()
    transcript_path = write_transcript(paths, transcript)
    console.print(f"[dim]wrote[/dim] {transcript_path.relative_to(paths.root)}")

    project = paths.root.name
    distiller = Distiller(
        model=config.distiller_model,
        budget_tokens=config.budget_tokens,
    )
    console.print(
        f"distilling {len(transcript.get('turns') or [])} turns "
        f"with {distiller.model} (budget {distiller.budget_tokens})..."
    )
    try:
        snapshot_md = distiller.distill(transcript, project=project)
    except DistillerError as e:
        err_console.print(f"[red]distillation failed:[/red] {e}")
        raise typer.Exit(code=1)

    snapshot_path = write_snapshot(paths, transcript, snapshot_md)
    current_path = write_current(paths, snapshot_md)

    append_index_entry(paths, {
        "source": transcript["source"],
        "session_id": transcript["session_id"],
        "started_at": transcript.get("started_at", ""),
        "ended_at": transcript.get("ended_at", ""),
        "turn_count": len(transcript.get("turns") or []),
        "token_count": (transcript.get("metadata") or {}).get("token_count", 0),
        "snapshot_path": str(snapshot_path.relative_to(paths.root)),
        "transcript_path": str(transcript_path.relative_to(paths.root)),
        "packed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    console.print(f"[green]packed[/green] → {current_path.relative_to(paths.root)}")


@app.command()
def prime(
    target: Optional[str] = typer.Option(
        None, "--target", "-t",
        help="Target adapter (chatgpt, claude, cursor). Defaults to config.",
    ),
    copy: bool = typer.Option(False, "--copy", help="Copy output to clipboard."),
    write: Optional[Path] = typer.Option(
        None, "--write", help="Write output to this path instead of stdout.",
    ),
) -> None:
    """Emit a copy-pasteable briefing for the next LLM."""
    paths = _paths()
    ensure_initialized(paths)
    config = Config.load(paths.ctx_dir)

    if not paths.current_path.exists():
        err_console.print(
            f"[red]no current snapshot[/red] at {paths.current_path}. "
            "Run `ctx pack` first."
        )
        raise typer.Exit(code=1)

    target_name = target or config.default_target
    adapter_cls = ADAPTERS.get(target_name)
    if adapter_cls is None:
        err_console.print(
            f"[red]unknown target:[/red] {target_name}. "
            f"Available: {', '.join(sorted(ADAPTERS))}"
        )
        raise typer.Exit(code=2)

    snapshot = parse_snapshot(paths.current_path.read_text())
    briefing = compose(
        snapshot,
        target=target_name,
        extra_rules=config.extra_rules,
        tone=config.tone,
    )
    primer = adapter_cls().render(briefing)

    if write is not None:
        write.write_text(primer)
        console.print(f"[green]wrote[/green] {write}")
        return

    if copy:
        try:
            import pyperclip
            pyperclip.copy(primer)
            console.print(
                f"[green]copied[/green] {len(primer)} chars to clipboard "
                f"(target: {target_name})"
            )
            return
        except Exception as e:
            err_console.print(
                f"[yellow]clipboard unavailable ({e}); falling back to stdout[/yellow]"
            )

    # default: print to stdout
    typer.echo(primer)


@app.command()
def status() -> None:
    """Show what's in the current snapshot."""
    paths = _paths()
    ensure_initialized(paths)

    if not paths.current_path.exists():
        console.print("[yellow]no current snapshot[/yellow]. Run `ctx pack`.")
        raise typer.Exit(code=0)

    snapshot = parse_snapshot(paths.current_path.read_text())
    fm = snapshot.frontmatter or {}

    console.print(f"[bold]current snapshot:[/bold] {paths.current_path}")
    console.print(f"  project: {fm.get('project', '?')}")
    console.print(f"  generated: {fm.get('generated_at', '?')}")
    console.print(f"  distiller: {fm.get('distiller_model', '?')}")
    console.print(f"  budget: {fm.get('budget_tokens', '?')} tokens")

    distilled = fm.get("distilled_from") or []
    if distilled:
        for src in distilled:
            console.print(
                f"  from: {src.get('source')}:{src.get('session_id')} "
                f"({src.get('turn_count', '?')} turns, "
                f"{src.get('token_count', '?')} tokens)"
            )

    console.print()
    sections = snapshot.sections
    for name in ["Task", "Status", "Next step"]:
        if sections.get(name):
            console.print(f"[bold cyan]# {name}[/bold cyan]")
            console.print(sections[name])
            console.print()

    if sections.get("Confidence Report"):
        console.print("[bold magenta]# Confidence Report[/bold magenta]")
        console.print(sections["Confidence Report"])


@app.command("log")
def log_cmd() -> None:
    """Show session history packed into this project."""
    paths = _paths()
    ensure_initialized(paths)
    index = load_index(paths)
    sessions = index.get("sessions", [])
    if not sessions:
        console.print("[dim]no sessions packed yet[/dim]")
        return

    table = Table(title="ctx sessions", show_lines=False)
    table.add_column("packed at")
    table.add_column("source")
    table.add_column("session id")
    table.add_column("turns", justify="right")
    table.add_column("tokens", justify="right")

    for entry in sessions:
        table.add_row(
            entry.get("packed_at", ""),
            entry.get("source", ""),
            entry.get("session_id", ""),
            str(entry.get("turn_count", "")),
            str(entry.get("token_count", "")),
        )
    console.print(table)


@app.command()
def diff(session_id: str = typer.Argument(..., help="Session id to inspect.")) -> None:
    """Show the snapshot of a single session."""
    paths = _paths()
    ensure_initialized(paths)
    index = load_index(paths)
    match = next(
        (e for e in index.get("sessions", []) if e.get("session_id") == session_id),
        None,
    )
    if not match:
        err_console.print(f"[red]no session with id[/red] {session_id}")
        raise typer.Exit(code=1)

    snapshot_path = paths.root / match["snapshot_path"]
    if not snapshot_path.exists():
        base = session_basename(match.get("started_at", ""), session_id)
        snapshot_path = paths.sessions_dir / f"{base}.snapshot.md"

    if not snapshot_path.exists():
        err_console.print(f"[red]snapshot missing:[/red] {snapshot_path}")
        raise typer.Exit(code=1)

    console.print(snapshot_path.read_text())


if __name__ == "__main__":
    app()
