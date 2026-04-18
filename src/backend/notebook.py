"""Notebook view backend: spawns `claude -p` and streams stream-json over SSE.

One subprocess per user message. Session memory is carried via `claude --resume
<session_id>`. The session id is persisted per-run under
`runs/<run_id>/notebook/session.json`; the rendered transcript is appended to
`runs/<run_id>/notebook/transcript.jsonl` so the conversation survives a page
reload.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SEED_TEMPLATE = """You are the project coordinator for an AutoR research run.

Working directory: {run_root}
Project thesis: {thesis}
Current run status: {run_status}

Stage progress:
{stage_progress}

Guidance:
- Ground every answer in the run's on-disk state. Prefer reading files in
  this run directory or the repository root over guessing.
- When the user asks to iterate or execute, invoke the AutoR modules via
  Bash (e.g. `python main.py --stage <name>` from the repo root) or edit
  the appropriate file directly. The old 6-stage pipeline UI is still
  active, so approvals and reruns can also be triggered from there; your
  file-system actions stay in sync with that UI automatically.
- Keep responses concise and narrate progress via tool calls, not long
  prose. The user sees every tool call inline in the notebook view.

User's message follows.
"""


def _load_notebook_paths(run_root: Path) -> dict[str, Path]:
    notebook_dir = run_root / "notebook"
    return {
        "notebook_dir": notebook_dir,
        "session_file": notebook_dir / "session.json",
        "transcript_file": notebook_dir / "transcript.jsonl",
    }


def load_session_id(run_root: Path) -> str | None:
    paths = _load_notebook_paths(run_root)
    session_file = paths["session_file"]
    if not session_file.exists():
        return None
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    session_id = data.get("session_id")
    return session_id if isinstance(session_id, str) and session_id else None


def save_session_id(run_root: Path, session_id: str) -> None:
    paths = _load_notebook_paths(run_root)
    paths["notebook_dir"].mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "last_active": time.time(),
    }
    existing_file = paths["session_file"]
    if existing_file.exists():
        try:
            existing = json.loads(existing_file.read_text(encoding="utf-8"))
            if "created_at" in existing:
                payload["created_at"] = existing["created_at"]
        except (OSError, json.JSONDecodeError):
            pass
    payload.setdefault("created_at", payload["last_active"])
    existing_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_transcript(run_root: Path) -> list[dict]:
    paths = _load_notebook_paths(run_root)
    transcript_file = paths["transcript_file"]
    if not transcript_file.exists():
        return []
    events: list[dict] = []
    for line in transcript_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def append_transcript(run_root: Path, event: dict) -> None:
    paths = _load_notebook_paths(run_root)
    paths["notebook_dir"].mkdir(parents=True, exist_ok=True)
    with paths["transcript_file"].open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def reset_notebook(run_root: Path) -> None:
    paths = _load_notebook_paths(run_root)
    for key in ("session_file", "transcript_file"):
        candidate = paths[key]
        if candidate.exists():
            candidate.unlink()


def build_seed_prompt(
    run_root: Path,
    thesis: str,
    run_status: str,
    stages: list[dict],
) -> str:
    if stages:
        lines = []
        for stage in stages:
            slug = stage.get("slug", "?")
            status = stage.get("status", "?")
            title = stage.get("title") or slug
            lines.append(f"- {slug} ({status}): {title}")
        stage_progress = "\n".join(lines)
    else:
        stage_progress = "- (no stages yet)"
    return SEED_TEMPLATE.format(
        run_root=str(run_root),
        thesis=thesis or "(not specified)",
        run_status=run_status or "(unknown)",
        stage_progress=stage_progress,
    )


@dataclass
class NotebookContext:
    run_root: Path
    repo_root: Path
    thesis: str
    run_status: str
    stages: list[dict]


class ClaudeNotFoundError(RuntimeError):
    pass


def _resolve_claude_binary() -> str:
    claude = shutil.which("claude")
    if not claude:
        raise ClaudeNotFoundError(
            "claude CLI not found on PATH. Install Claude Code to use the Notebook view."
        )
    return claude


def stream_message(
    context: NotebookContext,
    message: str,
) -> Iterator[dict]:
    """Spawn `claude -p` and yield each parsed stream-json event.

    Yields dicts with shape:
      {"type": "event", "data": <parsed claude event>}
      {"type": "error", "detail": str}
      {"type": "done"}
    """
    claude_bin = _resolve_claude_binary()
    session_id = load_session_id(context.run_root)
    is_new_session = session_id is None

    cmd: list[str] = [
        claude_bin,
        "-p",
        message,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--add-dir",
        str(context.repo_root),
    ]

    if is_new_session:
        seed = build_seed_prompt(
            run_root=context.run_root,
            thesis=context.thesis,
            run_status=context.run_status,
            stages=context.stages,
        )
        cmd.extend(["--append-system-prompt", seed])
    else:
        cmd.extend(["--resume", session_id])

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(context.run_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        yield {"type": "error", "detail": f"Failed to spawn claude: {exc}"}
        yield {"type": "done"}
        return

    append_transcript(
        context.run_root,
        {"type": "user", "text": message, "ts": time.time()},
    )
    yield {"type": "event", "data": {"type": "user_echo", "text": message}}

    stderr_buffer: list[str] = []

    def _drain_stderr() -> None:
        if proc.stderr is None:
            return
        for raw in proc.stderr:
            stderr_buffer.append(raw)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    new_session_id: str | None = None
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if (
                is_new_session
                and new_session_id is None
                and event.get("type") == "system"
                and event.get("subtype") == "init"
            ):
                sid = event.get("session_id")
                if isinstance(sid, str) and sid:
                    new_session_id = sid
            append_transcript(context.run_root, event)
            yield {"type": "event", "data": event}
    finally:
        proc.wait()
        stderr_thread.join(timeout=1.0)

    if new_session_id is not None:
        save_session_id(context.run_root, new_session_id)

    if proc.returncode != 0:
        detail = "".join(stderr_buffer).strip() or f"claude exited with code {proc.returncode}"
        yield {"type": "error", "detail": detail}

    yield {"type": "done"}
