#!/usr/bin/env python3
"""Feishu/Lark <-> Codex bridge.

Architecture:
    lark-cli event consume  ->  filter/dedupe  ->  SQLite queue  ->  codex exec
                                                                   |
                                              progress / final text -> lark-cli

Only Python 3 standard library is required.  `lark-cli` and `codex` are the
external executables.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable

FEISHU_DOMAINS = ("localhost", "127.0.0.1", "10.0.0.0/8", "172.16.0.0/12",
                  "feishu.cn", "larksuite.com", "feishucdn.com")
DEFAULT_ERROR_TEXT = "(助手没有返回文本内容)"
MAX_PROGRESS_TEXT = 180


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class Config:
    home: Path
    owner_id: str
    workdir: Path
    agent_kind: str = "codex"
    codex_bin: str = "codex"
    lark_cli_bin: str = "lark-cli"
    lark_profile: str = ""
    model: str = ""
    sandbox: str = "workspace-write"
    max_concurrency: int = 1
    task_timeout: int = 1800
    group_mode: str = "off"
    allowed_chats: set[str] = field(default_factory=set)
    bot_open_id: str = ""
    session_scope: str = "chat"
    progress: bool = True
    progress_batch_seconds: float = 60.0
    progress_batch_items: int = 10
    reply_format: str = "markdown"
    max_reply_bytes: int = 3500
    allow_danger: bool = False
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.home / "state.db"

    @property
    def log_dir(self) -> Path:
        return self.home / "logs"

    @property
    def memory_dir(self) -> Path:
        return self.home / "memory"

    @property
    def pid_path(self) -> Path:
        return self.home / "bridge.pid"

    def lark_args(self, *args: str) -> list[str]:
        base = [self.lark_cli_bin]
        if self.lark_profile:
            base += ["--profile", self.lark_profile]
        return base + list(args)

    def feishu_env(self) -> dict[str, str]:
        env = os.environ.copy()
        parts: list[str] = []
        for raw in (env.get("no_proxy") or env.get("NO_PROXY") or "").split(","):
            raw = raw.strip()
            if raw and raw not in parts:
                parts.append(raw)
        for domain in FEISHU_DOMAINS:
            if domain not in parts:
                parts.append(domain)
        value = ",".join(parts)
        env["no_proxy"] = value
        env["NO_PROXY"] = value
        return env


def _parse_env_value(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        parts = shlex.split(raw, comments=True)
    except ValueError:
        return raw.strip().strip('"').strip("'")
    return " ".join(parts)


def load_config(home: Path) -> Config:
    path = home / "config.env"
    values: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, raw = line.split("=", 1)
            values[key.strip()] = _parse_env_value(raw)

    def pick(name: str, default: str = "") -> str:
        return values.get(name, os.environ.get(name, default))

    def pick_alias(names: tuple[str, ...], default: str = "") -> str:
        """Resolve aliases within the config file before falling back to env."""
        for name in names:
            if name in values:
                return values[name]
        for name in names:
            raw = os.environ.get(name)
            if raw is not None:
                return raw
        return default

    def pick_int(name: str, default: int) -> int:
        try:
            return int(pick(name, str(default)))
        except ValueError:
            return default

    def pick_float(name: str, default: float) -> float:
        try:
            return float(pick(name, str(default)))
        except ValueError:
            return default

    def pick_bool(name: str, default: bool) -> bool:
        raw = pick(name, "1" if default else "0").strip().lower()
        return raw in ("1", "true", "yes", "on", "y")

    agent_kind = pick_alias(("AGENT_KIND",), "codex").strip().lower() or "codex"
    default_bin = "omp" if agent_kind == "omp" else "codex"
    bin_key = "OMP_BIN" if agent_kind == "omp" else "CODEX_BIN"
    raw_workdir = pick_alias(
        ("WORKDIR", "OMP_WORKDIR"), str(Path.home() / "workspace")
    ) or str(Path.home() / "workspace")
    workdir = Path(raw_workdir).expanduser()
    cfg = Config(
        home=home,
        owner_id=pick("OWNER_ID"),
        workdir=workdir,
        agent_kind=agent_kind,
        codex_bin=pick_alias(("AGENT_BIN", bin_key), default_bin) or default_bin,
        lark_cli_bin=pick_alias(("LARK_CLI_BIN", "LARK_BIN"), "lark-cli") or "lark-cli",
        lark_profile=pick("LARK_PROFILE", "").strip(),
        model=pick_alias(("AGENT_MODEL", "CODEX_MODEL", "OMP_MODEL"), ""),
        sandbox=pick("SANDBOX", "workspace-write"),
        max_concurrency=max(1, pick_int("MAX_CONCURRENCY", 1)),
        task_timeout=max(30, pick_int("TASK_TIMEOUT", 1800)),
        group_mode=pick("GROUP_MODE", "off").strip().lower(),
        allowed_chats={x.strip() for x in pick("ALLOWED_CHATS", "").split(",") if x.strip()},
        bot_open_id=pick("BOT_OPEN_ID", ""),
        session_scope=pick("SESSION_SCOPE", "chat").strip().lower(),
        progress=pick_bool("PROGRESS", True),
        progress_batch_seconds=max(1.0, pick_float("PROGRESS_BATCH_SECONDS", 60.0)),
        progress_batch_items=max(1, pick_int("PROGRESS_BATCH_ITEMS", 10)),
        reply_format=pick("REPLY_FORMAT", "markdown").strip().lower(),
        max_reply_bytes=max(500, pick_int("MAX_REPLY_BYTES", 3500)),
        allow_danger=pick_bool("ALLOW_DANGER", False),
        log_level=pick("LOG_LEVEL", "INFO").strip().upper(),
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: Config) -> None:
    errors: list[str] = []
    if cfg.agent_kind not in ("codex", "omp"):
        errors.append("AGENT_KIND 必须是 codex/omp")
    if not cfg.owner_id.startswith("ou_"):
        errors.append("OWNER_ID 必须形如 ou_xxx")
    if cfg.group_mode not in ("off", "owner", "mention", "all"):
        errors.append("GROUP_MODE 必须是 off/owner/mention/all")
    if cfg.group_mode == "mention" and not cfg.bot_open_id.startswith("ou_"):
        errors.append("GROUP_MODE=mention 时必须配置 BOT_OPEN_ID")
    if cfg.sandbox not in ("read-only", "workspace-write", "danger-full-access"):
        errors.append("SANDBOX 必须是 read-only/workspace-write/danger-full-access")
    if cfg.sandbox == "danger-full-access" and not cfg.allow_danger:
        errors.append("SANDBOX=danger-full-access 时必须显式设置 ALLOW_DANGER=1")
    if cfg.session_scope not in ("chat", "thread"):
        errors.append("SESSION_SCOPE 必须是 chat/thread")
    if cfg.reply_format not in ("markdown", "text"):
        errors.append("REPLY_FORMAT 必须是 markdown/text")
    if not cfg.workdir.exists():
        errors.append(f"WORKDIR 不存在: {cfg.workdir}")
    if errors:
        raise ValueError("; ".join(errors))


def setup_logging(cfg: Config, console: bool) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(cfg.log_dir / "bridge.log", maxBytes=10 * 1024 * 1024,
                            backupCount=5, encoding="utf-8")
    ]
    if console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
        handlers=handlers,
        force=True,
    )


# ---------------------------------------------------------------------------
# SQLite state
# ---------------------------------------------------------------------------

class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init()

    def _init(self) -> None:
        with self.lock, self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    chat_id TEXT,
                    created_at INTEGER,
                    seen_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_key TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    cwd TEXT,
                    model TEXT,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_cwd (
                    session_key TEXT PRIMARY KEY,
                    cwd TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    session_key TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    pid INTEGER,
                    created_at INTEGER NOT NULL,
                    started_at INTEGER,
                    ended_at INTEGER,
                    result TEXT,
                    error TEXT,
                    event_json TEXT NOT NULL DEFAULT '{}',
                    cwd TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, id);
                """
            )
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(tasks)")}
            if "event_json" not in columns:
                self.conn.execute("ALTER TABLE tasks ADD COLUMN event_json TEXT NOT NULL DEFAULT '{}'")
            if "cwd" not in columns:
                self.conn.execute("ALTER TABLE tasks ADD COLUMN cwd TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    def mark_seen(self, message_id: str, chat_id: str, created_at: int) -> bool:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO messages(message_id, chat_id, created_at, seen_at) "
                "VALUES(?, ?, ?, ?)",
                (message_id, chat_id, created_at, self.now_ms()),
            )
            return cur.rowcount > 0

    def cleanup_seen(self, days: int = 7) -> None:
        cutoff = self.now_ms() - days * 86400 * 1000
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM messages WHERE seen_at < ?", (cutoff,))

    def get_session(self, key: str) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM sessions WHERE session_key = ?", (key,)
            ).fetchone()

    def set_session(self, key: str, thread_id: str, cwd: str, model: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO sessions(session_key, thread_id, cwd, model, updated_at) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(session_key) DO UPDATE SET "
                "thread_id=excluded.thread_id, cwd=excluded.cwd, "
                "model=excluded.model, updated_at=excluded.updated_at",
                (key, thread_id, cwd, model, self.now_ms()),
            )

    def clear_session(self, key: str) -> None:
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM sessions WHERE session_key = ?", (key,))

    def get_cwd(self, key: str, default: Path) -> Path:
        with self.lock:
            row = self.conn.execute(
                "SELECT cwd FROM chat_cwd WHERE session_key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        path = Path(str(row["cwd"]))
        if path.is_dir():
            return path
        # The directory disappeared (e.g. removed tmp dir); fall back safely.
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM chat_cwd WHERE session_key = ?", (key,))
        return default

    def set_cwd(self, key: str, cwd: Path) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO chat_cwd(session_key, cwd, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(session_key) DO UPDATE SET "
                "cwd=excluded.cwd, updated_at=excluded.updated_at",
                (key, str(cwd), self.now_ms()),
            )

    def enqueue(self, message_id: str, session_key: str, chat_id: str, prompt: str,
                event_json: str = "{}", cwd: str = "") -> int:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO tasks(message_id, session_key, chat_id, prompt, "
                "created_at, event_json, cwd) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (message_id, session_key, chat_id, prompt, self.now_ms(), event_json, cwd),
            )
            if cur.rowcount:
                return int(cur.lastrowid)
            row = self.conn.execute(
                "SELECT id FROM tasks WHERE message_id = ?", (message_id,)
            ).fetchone()
            return int(row["id"]) if row else 0

    def next_task(self) -> dict[str, Any] | None:
        with self.lock, self.conn:
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self.conn.execute(
                "UPDATE tasks SET status = 'running', started_at = ? "
                "WHERE id = ? AND status = 'queued'",
                (self.now_ms(), row["id"]),
            )
            updated = self.conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (row["id"],)
            ).fetchone()
            return dict(updated) if updated else None

    def finish_task(self, task_id: int, status: str, result: str = "", error: str = "") -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE tasks SET status = ?, ended_at = ?, result = ?, error = ? WHERE id = ?",
                (status, self.now_ms(), result[:20000], error[:2000], task_id),
            )

    def recover_running(self) -> int:
        """Requeue tasks left in running state by a crash/restart."""
        with self.lock, self.conn:
            cur = self.conn.execute(
                "UPDATE tasks SET status='queued', started_at=NULL WHERE status='running'"
            )
            return cur.rowcount

    def queue_len(self) -> int:
        with self.lock:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status='queued'").fetchone()
            return int(row["n"])

    def running_tasks(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status='running' ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]

    def status_summary(self) -> dict[str, Any]:
        with self.lock:
            counts = {
                row["status"]: int(row["n"])
                for row in self.conn.execute(
                    "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
                ).fetchall()
            }
            sessions = int(self.conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"])
        return {"tasks": counts, "sessions": sessions, "queue": self.queue_len()}

    def close(self) -> None:
        with self.lock:
            self.conn.close()


# ---------------------------------------------------------------------------
# Event model / filtering
# ---------------------------------------------------------------------------

@dataclass
class Event:
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    sender_type: str
    message_type: str
    content: str
    create_time: int
    thread_id: str = ""
    root_id: str = ""
    mentions: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "Event":
        def text(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        create_time = data.get("create_time") or data.get("timestamp") or 0
        try:
            create_time = int(create_time)
        except (TypeError, ValueError):
            create_time = 0
        if 0 < create_time < 10**12:  # tolerate seconds
            create_time *= 1000

        mentions = data.get("mentions") or []
        if not isinstance(mentions, list):
            mentions = []

        return cls(
            message_id=text(data.get("message_id") or data.get("id")),
            chat_id=text(data.get("chat_id")),
            chat_type=text(data.get("chat_type")),
            sender_id=text(data.get("sender_id")),
            sender_type=text(data.get("sender_type")),
            message_type=text(data.get("message_type")),
            content=text(data.get("content")),
            create_time=create_time,
            thread_id=text(data.get("thread_id")),
            root_id=text(data.get("root_id")),
            mentions=[m for m in mentions if isinstance(m, dict)],
            raw=data,
        )


def mentions_bot(ev: Event, cfg: Config) -> bool:
    if not cfg.bot_open_id:
        return False
    return any(str(m.get("id", "")) == cfg.bot_open_id for m in ev.mentions)


def accept_event(cfg: Config, ev: Event, started_ms: int) -> tuple[bool, str]:
    if not ev.message_id or not ev.chat_id:
        return False, "缺少 message_id/chat_id"
    if ev.sender_type and ev.sender_type != "user":
        return False, f"忽略非用户消息 sender_type={ev.sender_type}"
    if ev.create_time and ev.create_time < started_ms - 60_000:
        return False, "忽略启动前的历史消息"
    if ev.chat_type == "p2p":
        if ev.sender_id != cfg.owner_id:
            return False, "忽略非主人私聊"
        return True, "ok"
    if ev.chat_type == "group":
        if cfg.group_mode == "off":
            return False, "群聊未启用"
        if cfg.allowed_chats and ev.chat_id not in cfg.allowed_chats:
            return False, "群聊不在白名单"
        if cfg.group_mode == "owner":
            if ev.sender_id != cfg.owner_id:
                return False, "群聊仅响应主人"
            return True, "ok"
        if cfg.group_mode == "mention" and not mentions_bot(ev, cfg):
            return False, "群聊未 @机器人"
        return True, "ok"
    return False, f"忽略未知 chat_type={ev.chat_type}"


def strip_mentions(ev: Event, text: str) -> str:
    for mention in ev.mentions:
        key = mention.get("key")
        if key:
            text = text.replace(str(key), "")
    text = re.sub(r"@_user_\d+", "", text)
    return text.strip()


def session_key_for(cfg: Config, ev: Event) -> str:
    if cfg.session_scope == "thread":
        return ev.thread_id or ev.root_id or ev.chat_id
    return ev.chat_id


def session_key_for_cwd(base_key: str, cwd: Path) -> str:
    """Keep an independent Codex thread per chat/thread and directory."""
    return f"{base_key}\x1f{cwd}"


def parse_command(text: str) -> tuple[str, str] | None:
    """Parse slash commands only.  Plain text (including Chinese) is a task."""
    value = text.strip()
    if not value.startswith("/"):
        return None
    try:
        parts = shlex.split(value)
    except ValueError:
        parts = value.split()
    if not parts or not parts[0].startswith("/"):
        return None
    name = parts[0][1:].strip().lower()
    if not name:
        return None
    return name, " ".join(parts[1:]).strip()


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def chunk_text(text: str, max_bytes: int) -> list[str]:
    """Split text on line boundaries, never splitting a UTF-8 code point."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return [""]
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    chunks: list[str] = []
    buf = ""
    for line in text.split("\n"):
        candidate = line if not buf else buf + "\n" + line
        if len(candidate.encode("utf-8")) <= max_bytes:
            buf = candidate
            continue
        if buf:
            with_newline = buf + "\n"
            if len(with_newline.encode("utf-8")) <= max_bytes:
                chunks.append(with_newline)
            else:
                chunks.append(buf)
            buf = ""
        if len(line.encode("utf-8")) <= max_bytes:
            buf = line
            continue
        piece = ""
        for ch in line:
            if len((piece + ch).encode("utf-8")) > max_bytes:
                if piece:
                    chunks.append(piece)
                piece = ch
            else:
                piece += ch
        buf = piece
    if buf:
        chunks.append(buf)
    return chunks or [""]


def clip(text: str, limit: int = MAX_PROGRESS_TEXT) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# Feishu client
# ---------------------------------------------------------------------------

class FeishuClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.env = cfg.feishu_env()

    def _run(self, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.cfg.lark_args(*args),
            capture_output=True,
            text=True,
            env=self.env,
            timeout=timeout,
        )

    @staticmethod
    def _ok(proc: subprocess.CompletedProcess[str]) -> bool:
        if proc.returncode != 0:
            return False
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return True
        return payload.get("ok") is not False

    def send(self, chat_id: str, text: str, reply_to: str = "",
             markdown: bool = False, idempotency_key: str = "") -> bool:
        chunks = chunk_text(text, self.cfg.max_reply_bytes)
        total = len(chunks)
        ok_all = True
        for index, chunk in enumerate(chunks, 1):
            prefix = f"[{index}/{total}]\n" if total > 1 else ""
            body = prefix + chunk

            # Prefer replying to the source message; fall back to a plain send
            # if the message no longer exists or the reply API rejects it.
            markdown_modes = [True, False] if (markdown and self.cfg.reply_format == "markdown") else [False]
            attempts: list[tuple[bool, bool]] = []
            for use_markdown in markdown_modes:
                if reply_to:
                    attempts.append((True, use_markdown))
                attempts.append((False, use_markdown))

            sent = False
            last_error = ""
            for use_reply, use_markdown in attempts:
                content_args = ["--markdown", body] if use_markdown else ["--text", body]
                if use_reply:
                    args = ["im", "+messages-reply", "--as", "bot",
                            "--message-id", reply_to, *content_args]
                else:
                    target = "--user-id" if chat_id.startswith("ou_") else "--chat-id"
                    args = ["im", "+messages-send", "--as", "bot",
                            target, chat_id, *content_args]
                if idempotency_key:
                    key = f"{idempotency_key}-{index}"
                    args += ["--idempotency-key", key[:50]]

                for attempt in range(3):
                    try:
                        proc = self._run(args)
                    except Exception as exc:  # noqa: BLE001
                        last_error = str(exc)
                    else:
                        if self._ok(proc):
                            sent = True
                            break
                        last_error = (proc.stderr or proc.stdout or "").strip()
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                if sent:
                    break
                if use_markdown:
                    logging.warning("markdown 发送失败，回退纯文本: %s", clip(last_error, 300))
            if not sent:
                ok_all = False
                logging.error("发送飞书消息失败 chat=%s: %s", chat_id, clip(last_error, 500))
        return ok_all


# ---------------------------------------------------------------------------
# Codex runner
# ---------------------------------------------------------------------------

@dataclass
class CodexResult:
    ok: bool
    text: str
    thread_id: str = ""
    exit_code: int = -1
    error: str = ""
    canceled: bool = False


class CodexRunner:
    def __init__(self, cfg: Config, state: State):
        self.cfg = cfg
        self.state = state

    def _build_prompt(self, ev: Event, text: str, cwd: Path) -> str:
        safe_chat = re.sub(r"[^A-Za-z0-9_.-]", "_", ev.chat_id)
        memory_file = self.cfg.memory_dir / f"{safe_chat}.md"
        return (
            "你是通过飞书与主人对话的 AI 编程助手。\n\n"
            "[消息元数据]\n"
            f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- 会话类型: {ev.chat_type}\n"
            f"- chat_id: {ev.chat_id}\n"
            f"- 发送者: {ev.sender_id}\n"
            f"- message_id: {ev.message_id}\n\n"
            "[用户消息]\n"
            f"{text}\n\n"
            "[运行约定]\n"
            f"- 工作区: {cwd}\n"
            f"- 长期记忆文件: {memory_file}（需要记住时写入；没有内容时可忽略）\n"
            "- 最终答复会直接发到飞书，请简洁、分点；长内容会自动分片。\n"
            "- 删除、重置、推送、发布等高风险操作，先在答复中说明并等待确认，不要直接执行。\n"
        )

    def _build_args(self, prompt: str, thread_id: str, last_file: Path,
                    cwd: Path) -> tuple[list[str], Path]:
        if self.cfg.agent_kind == "omp":
            args = [self.cfg.codex_bin, "--mode", "json"]
            if thread_id:
                args += ["--resume", thread_id]
            if self.cfg.model:
                args += ["--model", self.cfg.model]
            args.append(prompt)
            return args, cwd
        if thread_id:
            # `codex exec resume` does not accept -C/--add-dir/-s; set the
            # working directory via Popen and pass sandbox through config.
            args = [self.cfg.codex_bin, "exec", "resume", thread_id,
                    "--json", "--skip-git-repo-check",
                    "-c", f'sandbox_mode="{self.cfg.sandbox}"',
                    "-c", "approval_policy=never",
                    "-o", str(last_file)]
        else:
            args = [self.cfg.codex_bin, "exec",
                    "--json", "--skip-git-repo-check",
                    "-C", str(cwd),
                    "-s", self.cfg.sandbox,
                    "-c", "approval_policy=never",
                    "-o", str(last_file),
                    "--add-dir", str(self.cfg.home)]
        if self.cfg.model:
            args += ["-c", f"model={self.cfg.model}"]
        args.append(prompt)
        return args, cwd

    def _terminate(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    def run(self, task: dict[str, Any], ev: Event, text: str,
            cancel_event: threading.Event,
            on_progress: callable | None = None) -> CodexResult:
        base_key = task["session_key"]
        raw_cwd = str(task.get("cwd") or "")
        cwd = Path(raw_cwd) if raw_cwd else self.state.get_cwd(base_key, self.cfg.workdir)
        if not cwd.is_dir():
            logging.warning("工作目录不存在，回退到 %s: %s", self.cfg.workdir, cwd)
            cwd = self.cfg.workdir
        session_key = session_key_for_cwd(base_key, cwd)
        session = self.state.get_session(session_key)
        if session is None and cwd == self.cfg.workdir:
            # One-time migration from the pre-/cd schema (chat id as key).
            legacy = self.state.get_session(base_key)
            if legacy and (not legacy["cwd"] or Path(str(legacy["cwd"])) == cwd):
                session = legacy
                self.state.set_session(session_key, str(legacy["thread_id"]), str(cwd),
                                       str(legacy["model"] or ""))
        thread_id = str(session["thread_id"]) if session else ""
        used_resume = bool(thread_id)
        last_file = self.cfg.home / f"last_message_{task['id']}.txt"
        try:
            last_file.unlink()
        except FileNotFoundError:
            pass

        prompt = self._build_prompt(ev, text, cwd)
        args, cwd = self._build_args(prompt, thread_id, last_file, cwd)
        logging.info("启动 %s task=%s resume=%s thread=%s cwd=%s",
                     self.cfg.agent_kind, task["id"], used_resume,
                     thread_id or "-", cwd)

        try:
            proc = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
                env=os.environ.copy(),
            )
        except Exception as exc:  # noqa: BLE001
            return CodexResult(ok=False, text="", error=f"启动 {self.cfg.agent_kind} 失败: {exc}")

        out_queue: queue.Queue[str | None] = queue.Queue()
        err_lines: list[str] = []

        def pump_stdout() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                out_queue.put(line)
            out_queue.put(None)

        def pump_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                clean = line.rstrip()
                err_lines.append(clean)
                logging.info("%s stderr: %s", self.cfg.agent_kind, clean)

        threading.Thread(target=pump_stdout, name="codex-stdout", daemon=True).start()
        threading.Thread(target=pump_stderr, name="codex-stderr", daemon=True).start()

        final_messages: list[str] = []
        captured_thread = ""
        error = ""
        canceled = False
        deadline = time.monotonic() + self.cfg.task_timeout
        reporter = (
            ProgressReporter(on_progress, self.cfg.progress_batch_seconds,
                             self.cfg.progress_batch_items)
            if (on_progress and self.cfg.progress) else None
        )

        try:
            while True:
                reporter and reporter.tick()
                if cancel_event.is_set():
                    canceled = True
                    error = "任务已停止"
                    self._terminate(proc)
                    break
                if time.monotonic() > deadline:
                    error = f"任务超时（{self.cfg.task_timeout}s）"
                    self._terminate(proc)
                    break
                try:
                    line = out_queue.get(timeout=0.5)
                except queue.Empty:
                    reporter and reporter.tick()
                    if proc.poll() is not None:
                        break
                    continue
                if line is None:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except ValueError:
                    logging.debug("非 JSON 输出: %s", clip(line, 300))
                    continue

                kind = payload.get("type")
                if self.cfg.agent_kind == "omp":
                    if kind == "session":
                        captured_thread = str(payload.get("id") or "")
                    elif kind == "message_end":
                        message = payload.get("message") or {}
                        if message.get("role") == "assistant":
                            content = message.get("content") or []
                            value = "".join(
                                str(part.get("text") or "")
                                for part in content
                                if isinstance(part, dict) and part.get("type") == "text"
                            ).strip()
                            if value:
                                final_messages.append(value)
                    elif kind == "agent_end":
                        for message in reversed(payload.get("messages") or []):
                            if not isinstance(message, dict) or message.get("role") != "assistant":
                                continue
                            content = message.get("content") or []
                            value = "".join(
                                str(part.get("text") or "")
                                for part in content
                                if isinstance(part, dict) and part.get("type") == "text"
                            ).strip()
                            if value:
                                final_messages.append(value)
                                break
                    elif kind == "tool_execution_start":
                        tool_name = str(payload.get("toolName") or "tool")
                        args_value = payload.get("args") or {}
                        if (tool_name == "bash" and isinstance(args_value, dict)
                                and args_value.get("command")):
                            reporter and reporter.send(f"✅ 执行：{clip(str(args_value['command']))}")
                        else:
                            try:
                                detail = json.dumps(args_value, ensure_ascii=False)
                            except (TypeError, ValueError):
                                detail = str(args_value)
                            reporter and reporter.send(f"🔧 {tool_name}：{clip(detail)}")
                    elif kind == "tool_execution_end":
                        if payload.get("isError"):
                            reporter and reporter.send(
                                f"⚠️ 工具失败：{clip(str(payload.get('toolName') or 'tool'))}"
                            )
                    elif kind in ("error", "turn.failed"):
                        err = payload.get("error") or payload.get("message") or payload
                        error = str(err)
                    continue

                item = payload.get("item") or {}
                item_type = item.get("type")
                if kind == "thread.started":
                    captured_thread = str(payload.get("thread_id") or "")
                elif kind == "item.completed":
                    if item_type == "command_execution":
                        command = clip(item.get("command", ""))
                        code = item.get("exit_code")
                        if code in (None, 0):
                            reporter and reporter.send(f"✅ 执行：{command}")
                        else:
                            reporter and reporter.send(f"⚠️ 退出码 {code}：{command}")
                    elif item_type == "file_change":
                        paths = []
                        for change in item.get("changes") or []:
                            if isinstance(change, dict):
                                paths.append(str(change.get("path", "")))
                        reporter and reporter.send(f"📝 修改：{clip(', '.join(p for p in paths if p))}")
                    elif item_type == "mcp_tool_call":
                        reporter and reporter.send(
                            f"🔌 调用：{clip(str(item.get('server', '')) + '.' + str(item.get('tool', '')))}"
                        )
                    elif item_type == "agent_message":
                        value = str(item.get("text") or "").strip()
                        if value:
                            final_messages.append(value)
                elif kind == "turn.failed":
                    err = payload.get("error") or {}
                    error = str(err.get("message") or err) if isinstance(err, dict) else str(err)
                    break
                elif kind == "error":
                    error = str(payload.get("message") or payload)
        finally:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._terminate(proc)
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
            if reporter is not None:
                reporter.flush()

        exit_code = proc.returncode if proc.returncode is not None else -1
        if not canceled and not error and exit_code != 0:
            error = f"{self.cfg.agent_kind} 退出码 {exit_code}: {clip(' | '.join(err_lines[-3:]), 500)}"

        text_out = ""
        if last_file.exists():
            try:
                text_out = last_file.read_text(encoding="utf-8").strip()
            except OSError:
                text_out = ""
            try:
                last_file.unlink()
            except OSError:
                pass
        if not text_out and final_messages:
            text_out = final_messages[-1].strip()
        if not text_out and not error and not canceled:
            text_out = DEFAULT_ERROR_TEXT

        if captured_thread:
            self.state.set_session(session_key, captured_thread, str(cwd), self.cfg.model)

        result = CodexResult(
            ok=not canceled and not error,
            text=text_out,
            thread_id=captured_thread or thread_id,
            exit_code=exit_code,
            error=error,
            canceled=canceled,
        )

        # Resume can fail after a model/config change or a deleted thread.
        if (used_resume and not result.ok and not result.text
                and re.search(r"session|thread|resume|not found|no such", error, re.I)):
            logging.warning("resume 失败，清除会话并用新 thread 重试: %s", clip(error, 300))
            self.state.clear_session(session_key)
            retry_task = dict(task)
            retry_task["session_key"] = base_key
            retry_task["cwd"] = str(cwd)
            return self.run(retry_task, ev, text, cancel_event, on_progress)

        return result


class ProgressReporter:
    """Group progress events into compact batches.

    Codex can execute dozens of commands per task.  Sending one Feishu message
    per command is noisy, so events are flushed when a batch is full, when the
    time window elapses, or when the task finishes.
    """

    def __init__(self, callback: callable, interval: float = 60.0,
                 max_items: int = 10):
        self.callback = callback
        self.interval = max(1.0, float(interval))
        self.max_items = max(1, int(max_items))
        self.items: list[str] = []
        self.last_flush = time.monotonic()

    def send(self, text: str, force: bool = False) -> None:
        if text and (not self.items or text != self.items[-1]):
            self.items.append(text)
        if len(self.items) >= self.max_items:
            self.flush()
        elif force:
            self.flush()

    def tick(self) -> None:
        if self.items and time.monotonic() - self.last_flush >= self.interval:
            self.flush()

    def flush(self) -> None:
        if not self.items:
            return
        items = self.items
        self.items = []
        self.last_flush = time.monotonic()
        lines = [f"{index}. {item}" for index, item in enumerate(items, 1)]
        text = f"🧾 执行摘要（{len(items)} 项）\n" + "\n".join(lines)
        try:
            self.callback(text)
        except Exception:  # noqa: BLE001
            logging.exception("进度发送失败")


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class Worker(threading.Thread):
    def __init__(self, index: int, cfg: Config, state: State, feishu: FeishuClient,
                 runner: CodexRunner, stop_event: threading.Event):
        super().__init__(name=f"worker-{index}", daemon=True)
        self.cfg = cfg
        self.state = state
        self.feishu = feishu
        self.runner = runner
        self.stop_event = stop_event
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        while not self.stop_event.is_set():
            task = self.state.next_task()
            if task is None:
                self.stop_event.wait(0.5)
                continue
            self.cancel_event.clear()
            self._process(task)

    def _process(self, task: dict[str, Any]) -> None:
        try:
            ev = Event.from_raw(json.loads(task.get("event_json") or "{}"))
        except (TypeError, ValueError):
            ev = None
        if ev is None or not ev.message_id:
            ev = Event(
                message_id=task["message_id"], chat_id=task["chat_id"], chat_type="p2p",
                sender_id=self.cfg.owner_id, sender_type="user", message_type="text",
                content=task["prompt"], create_time=0,
            )
        text = task["prompt"]
        self.feishu.send(task["chat_id"], f"🤖 开始处理：{clip(text, 100)}", markdown=False,
                         idempotency_key=f"ack-{task['id']}")
        result = self.runner.run(
            task, ev, text, self.cancel_event,
            on_progress=lambda message: self.feishu.send(task["chat_id"], message),
        )
        if result.canceled:
            self.state.finish_task(task["id"], "canceled", result.text, result.error)
            self.feishu.send(task["chat_id"], "⏹ 任务已停止。", markdown=False,
                             idempotency_key=f"stop-{task['id']}")
        elif result.ok:
            self.state.finish_task(task["id"], "done", result.text, "")
            self.feishu.send(task["chat_id"], result.text or DEFAULT_ERROR_TEXT,
                             reply_to=task["message_id"], markdown=True,
                             idempotency_key=f"done-{task['id']}")
        else:
            self.state.finish_task(task["id"], "failed", result.text, result.error)
            self.feishu.send(
                task["chat_id"],
                f"❌ 任务失败：{result.error or '未知错误'}",
                reply_to=task["message_id"], markdown=False,
                idempotency_key=f"fail-{task['id']}",
            )


class WorkerPool:
    def __init__(self, cfg: Config, state: State, feishu: FeishuClient,
                 runner: CodexRunner, stop_event: threading.Event):
        self.workers = [
            Worker(i, cfg, state, feishu, runner, stop_event)
            for i in range(cfg.max_concurrency)
        ]

    def start(self) -> None:
        for worker in self.workers:
            worker.start()

    def cancel_all(self) -> None:
        for worker in self.workers:
            worker.cancel()

    def join(self, timeout: float = 10) -> None:
        for worker in self.workers:
            worker.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Event consumer supervisor
# ---------------------------------------------------------------------------

class ConsumerSupervisor:
    def __init__(self, cfg: Config, state: State, feishu: FeishuClient,
                 pool: WorkerPool, stop_event: threading.Event):
        self.cfg = cfg
        self.state = state
        self.feishu = feishu
        self.pool = pool
        self.stop_event = stop_event
        self.proc: subprocess.Popen[str] | None = None
        self.started_ms = int(time.time() * 1000)

    def _start(self) -> subprocess.Popen[str]:
        args = self.cfg.lark_args("event", "consume",
                                  "im.message.receive_v1", "--as", "bot")
        return subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
            env=self.cfg.feishu_env(),
        )

    def _wait_ready(self, proc: subprocess.Popen[str]) -> bool:
        lines: queue.Queue[str] = queue.Queue()

        def pump_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                clean = line.rstrip()
                logging.info("event stderr: %s", clean)
                lines.put(clean)

        threading.Thread(target=pump_stderr, name="event-stderr", daemon=True).start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not self.stop_event.is_set():
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:
                    return False
                continue
            if "[event] ready" in line:
                return True
            if proc.poll() is not None:
                return False
        return False

    def run(self) -> None:
        backoff = 2
        while not self.stop_event.is_set():
            logging.info("启动飞书事件监听")
            try:
                proc = self._start()
            except Exception as exc:  # noqa: BLE001
                logging.exception("启动事件监听失败: %s", exc)
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 60)
                continue
            self.proc = proc
            if not self._wait_ready(proc):
                logging.error("事件监听未就绪，%ss 后重试", backoff)
                self._terminate(proc)
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 60)
                continue
            backoff = 2
            logging.info("事件监听已就绪")
            assert proc.stdout is not None
            output: queue.Queue[str | None] = queue.Queue()

            def pump_stdout() -> None:
                try:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        output.put(line)
                except Exception:  # noqa: BLE001
                    logging.debug("事件 stdout 读取结束", exc_info=True)
                finally:
                    output.put(None)

            threading.Thread(target=pump_stdout, name="event-stdout", daemon=True).start()
            try:
                while not self.stop_event.is_set():
                    try:
                        line = output.get(timeout=1)
                    except queue.Empty:
                        if proc.poll() is not None:
                            break
                        continue
                    if line is None:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        logging.warning("事件不是 JSON: %s", clip(line, 300))
                        continue
                    self.handle(payload)
            finally:
                self._terminate(proc)
                self.proc = None
            if not self.stop_event.is_set():
                logging.warning("事件监听退出，%ss 后重连", backoff)
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 60)

    def _terminate(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        # Closing stdin is the documented graceful shutdown for `event consume`.
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                proc.terminate()
            except ProcessLookupError:
                return
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    def stop(self) -> None:
        self.stop_event.set()
        if self.proc is not None:
            self._terminate(self.proc)

    def handle(self, payload: dict[str, Any]) -> None:
        ev = Event.from_raw(payload)
        ok, reason = accept_event(self.cfg, ev, self.started_ms)
        if not ok:
            logging.debug("忽略消息 %s: %s", ev.message_id, reason)
            return
        if not self.state.mark_seen(ev.message_id, ev.chat_id, ev.create_time):
            logging.debug("重复消息 %s，忽略", ev.message_id)
            return

        text = strip_mentions(ev, ev.content)
        if not text:
            return
        logging.info("收到消息 chat=%s sender=%s type=%s len=%s",
                     ev.chat_id, ev.sender_id, ev.message_type, len(text))

        command = parse_command(text)
        if command:
            self._handle_command(command[0], command[1], ev)
            return

        session_key = session_key_for(self.cfg, ev)
        cwd = self.state.get_cwd(session_key, self.cfg.workdir)
        task_id = self.state.enqueue(ev.message_id, session_key, ev.chat_id, text,
                                     json.dumps(ev.raw, ensure_ascii=False), str(cwd))
        if task_id <= 0:
            return
        if self.state.running_tasks():
            position = self.state.queue_len()
            self.feishu.send(ev.chat_id, f"📥 已排队（第 {max(position, 1)} 位）",
                             reply_to=ev.message_id, markdown=False,
                             idempotency_key=f"queue-{task_id}")

    def _handle_command(self, name: str, arg: str, ev: Event) -> None:
        base_key = session_key_for(self.cfg, ev)
        cwd = self.state.get_cwd(base_key, self.cfg.workdir)
        session_key = session_key_for_cwd(base_key, cwd)
        if name == "help":
            agent_label = "omp" if self.cfg.agent_kind == "omp" else "Codex"
            text = (
                f"🤖 {agent_label} 飞书机器人\n\n"
                f"命令必须以 `/` 开头；普通文本会作为任务交给 {agent_label}。\n\n"
                "`/pwd`：显示当前工作目录\n"
                "`/cd <path>`：切换工作目录（每个目录独立会话）\n"
                "`/status`：查看任务、队列和当前线程\n"
                "`/new`：清除当前目录的对话上下文\n"
                "`/stop`：终止当前任务\n"
                "`/help`：显示本帮助"
            )
        elif name == "pwd":
            text = f"📂 当前目录：`{cwd}`"
        elif name == "cd":
            raw = arg.strip()
            if not raw:
                text = f"📂 当前目录：`{cwd}`\n用法：`/cd <path>`"
            else:
                target = Path(os.path.expanduser(raw))
                if not target.is_absolute():
                    target = cwd / target
                try:
                    target = target.resolve()
                except OSError:
                    target = target.absolute()
                if not target.exists():
                    text = f"❌ 目录不存在：`{target}`"
                elif not target.is_dir():
                    text = f"❌ 不是目录：`{target}`"
                elif not os.access(target, os.R_OK | os.X_OK):
                    text = f"❌ 无法进入目录（权限不足）：`{target}`"
                else:
                    self.state.set_cwd(base_key, target)
                    text = f"📂 已切换工作目录：`{target}`\n该目录使用独立会话。"
        elif name == "status":
            running = self.state.running_tasks()
            current = running[0] if running else None
            summary = self.state.status_summary()
            session = self.state.get_session(session_key)
            parts = [
                "📊 状态",
                f"- 当前目录：`{cwd}`",
                f"- 运行中任务：{len(running)}",
                f"- 排队任务：{summary['queue']}",
                f"- 会话线程：{str(session['thread_id'])[:12] + '…' if session else '无'}",
            ]
            if current:
                parts.append(f"- 当前：# {current['id']} {clip(current['prompt'], 80)}")
            text = "\n".join(parts)
        elif name == "new":
            self.state.clear_session(session_key)
            text = (f"🆕 已清除当前目录的对话上下文：`{cwd}`\n"
                    "下一条消息会开启新的 Codex thread。")
        elif name == "stop":
            self.pool.cancel_all()
            text = "⏹ 已发送停止信号。"
        else:
            text = f"未知命令：`/{name}`。发送 `/help` 查看可用命令。"
        self.feishu.send(ev.chat_id, text, reply_to=ev.message_id, markdown=True,
                         idempotency_key=f"cmd-{ev.message_id}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_check(cfg: Config) -> int:
    checks: dict[str, Any] = {
        "home": str(cfg.home),
        "config": str(cfg.home / "config.env"),
        "owner_id": cfg.owner_id,
        "workdir": str(cfg.workdir),
        "agent_kind": cfg.agent_kind,
        "agent_bin": shutil.which(cfg.codex_bin) or cfg.codex_bin,
        "model": cfg.model or f"({cfg.agent_kind} default)",
        "sandbox": cfg.sandbox if cfg.agent_kind == "codex" else "(not used)",
        "group_mode": cfg.group_mode,
        "lark_cli_bin": shutil.which(cfg.lark_cli_bin) or cfg.lark_cli_bin,
        "lark_profile": cfg.lark_profile or "(default)",
    }
    problems: list[str] = []
    for name in ("agent_bin", "lark_cli_bin"):
        if not shutil.which(str(checks[name])):
            problems.append(f"{name} 不在 PATH: {checks[name]}")
    try:
        proc = subprocess.run(cfg.lark_args("auth", "status"),
                              capture_output=True, text=True, timeout=30,
                              env=cfg.feishu_env())
        checks["lark_auth_exit"] = proc.returncode
        if proc.returncode != 0:
            problems.append("lark-cli auth status 失败")
        else:
            try:
                payload = json.loads(proc.stdout)
                bot = (payload.get("identities") or {}).get("bot") or {}
                checks["bot_status"] = bot.get("status")
                if bot.get("status") != "ready":
                    problems.append(f"飞书 bot 身份未就绪: {bot.get('status')}")
            except ValueError:
                problems.append("无法解析 lark-cli auth status 输出")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"lark-cli auth status 异常: {exc}")
    # 事件总线全局唯一：同一 app 上已有别的机器在消费时，本机永远连不上。
    # 平台只暴露 online_instance_cnt，`lark-cli event status/stop` 只能看本机，
    # 所以这里做一次短时限的真实订阅试探，把冲突提前暴露给用户。
    local_pid = read_pid(cfg)
    if pid_alive(local_pid):
        # 本机 bridge 自己就占着总线，再试探只会和自己冲突
        checks["event_bus"] = "held_by_local_bridge"
    else:
        try:
            probe = subprocess.run(
                cfg.lark_args("event", "consume", "im.message.receive_v1",
                              "--as", "bot", "--timeout", "3s"),
                capture_output=True, text=True, timeout=30, env=cfg.feishu_env(),
            )
            output = f"{probe.stdout}\n{probe.stderr}"
            if "another event bus is already connected" in output:
                match = re.search(r"online_instance_cnt=(\d+)", output)
                checks["event_bus"] = "occupied_by_another_host"
                problems.append(
                    "事件总线已被其他机器占用"
                    + (f"（online_instance_cnt={match.group(1)}）" if match else "")
                    + "：同一 app 只允许一个消费者，请先停掉那台机器上的 lark-bot / lark-cli event，"
                      "或为本机换用独立 app"
                )
            elif re.search(r"consuming as |已就绪", output):
                checks["event_bus"] = "available"
            else:
                checks["event_bus"] = "unknown"
        except Exception as exc:  # noqa: BLE001
            checks["event_bus"] = f"error: {exc}"
    checks["problems"] = problems
    checks["ok"] = not problems
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def cmd_status(cfg: Config) -> int:
    state = State(cfg.db_path)
    try:
        payload = state.status_summary()
        payload["pid"] = read_pid(cfg)
        payload["pid_alive"] = pid_alive(payload["pid"])
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        state.close()
    return 0


def read_pid(cfg: Config) -> int | None:
    try:
        return int(cfg.pid_path.read_text().strip())
    except (OSError, ValueError):
        return None


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_run(cfg: Config, console: bool) -> int:
    setup_logging(cfg, console)
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    cfg.memory_dir.mkdir(parents=True, exist_ok=True)
    existing = read_pid(cfg)
    if existing and existing != os.getpid() and pid_alive(existing):
        print(f"已有实例在运行 (pid={existing})", file=sys.stderr)
        return 1
    cfg.pid_path.write_text(str(os.getpid()), encoding="utf-8")
    state = State(cfg.db_path)
    recovered = state.recover_running()
    if recovered:
        logging.warning("发现 %s 个上次中断的任务，已重新排队", recovered)
    state.cleanup_seen()
    feishu = FeishuClient(cfg)
    runner = CodexRunner(cfg, state)
    stop_event = threading.Event()
    pool = WorkerPool(cfg, state, feishu, runner, stop_event)
    supervisor = ConsumerSupervisor(cfg, state, feishu, pool, stop_event)

    def shutdown(signum: int, _frame: Any) -> None:
        logging.info("收到信号 %s，准备退出", signum)
        # Keep the signal handler minimal: just signal the main loop.
        # Stream cleanup happens in ConsumerSupervisor.run's finally block.
        stop_event.set()
        pool.cancel_all()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logging.info("lark-bot 启动 home=%s agent=%s bin=%s profile=%s workdir=%s concurrency=%s",
                 cfg.home, cfg.agent_kind, cfg.codex_bin,
                 cfg.lark_profile or "(default)", cfg.workdir, cfg.max_concurrency)
    pool.start()
    try:
        supervisor.run()
    finally:
        # Keep the signal handler minimal: just signal the main loop.
        # Stream cleanup happens in ConsumerSupervisor.run's finally block.
        stop_event.set()
        pool.cancel_all()
        pool.join(timeout=10)
        state.close()
        try:
            cfg.pid_path.unlink()
        except FileNotFoundError:
            pass
        logging.info("lark-bot 已退出")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Feishu/Lark <-> Codex bridge")
    parser.add_argument("--home", default=os.environ.get("LARK_BOT_HOME", "~/.agents/lark-bot"),
                        help="runtime directory (default: ~/.agents/lark-bot)")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="start the bridge")
    run_parser.add_argument("--no-console", action="store_true", help="log to file only")
    sub.add_parser("check", help="validate config and connectivity")
    sub.add_parser("status", help="print queue/session status")
    args = parser.parse_args(argv)

    home = Path(args.home).expanduser().resolve()
    try:
        cfg = load_config(home)
    except Exception as exc:  # noqa: BLE001
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    if args.command == "check":
        return cmd_check(cfg)
    if args.command == "status":
        return cmd_status(cfg)
    if args.command == "run":
        return cmd_run(cfg, console=not args.no_console)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
