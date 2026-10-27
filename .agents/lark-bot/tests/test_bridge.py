from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bridge  # noqa: E402


def make_cfg(root: Path) -> bridge.Config:
    work = root / "work"
    work.mkdir(exist_ok=True)
    return bridge.Config(home=root, owner_id="ou_owner", workdir=work)


def make_event(**overrides):
    data = {
        "message_id": "om_test",
        "chat_id": "oc_test",
        "chat_type": "p2p",
        "sender_id": "ou_owner",
        "sender_type": "user",
        "message_type": "text",
        "content": "hello",
        "create_time": str(int(time.time() * 1000)),
        "mentions": [],
    }
    data.update(overrides)
    return bridge.Event.from_raw(data)


class ChunkingTests(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(bridge.chunk_text("hello", 3500), ["hello"])

    def test_chinese_is_split_on_utf8_boundary(self):
        text = "导航定位" * 500
        chunks = bridge.chunk_text(text, 100)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.encode("utf-8")), 100)

    def test_newlines_are_preserved(self):
        text = "a\nb\nc"
        self.assertEqual("".join(bridge.chunk_text(text, 4)), text)


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_owner_p2p_is_accepted(self):
        ok, _ = bridge.accept_event(self.cfg, make_event(), 0)
        self.assertTrue(ok)

    def test_other_p2p_is_rejected(self):
        ok, reason = bridge.accept_event(self.cfg, make_event(sender_id="ou_other"), 0)
        self.assertFalse(ok)
        self.assertIn("非主人", reason)

    def test_group_is_off_by_default(self):
        ok, reason = bridge.accept_event(
            self.cfg, make_event(chat_type="group", chat_id="oc_group"), 0
        )
        self.assertFalse(ok)
        self.assertIn("群聊未启用", reason)

    def test_group_mention_requires_bot(self):
        self.cfg.group_mode = "mention"
        self.cfg.bot_open_id = "ou_bot"
        ev = make_event(chat_type="group", chat_id="oc_group", sender_id="ou_other")
        self.assertFalse(bridge.accept_event(self.cfg, ev, 0)[0])
        ev.mentions = [{"id": "ou_bot", "key": "@_user_1"}]
        self.assertTrue(bridge.accept_event(self.cfg, ev, 0)[0])

    def test_app_messages_are_rejected(self):
        ok, reason = bridge.accept_event(self.cfg, make_event(sender_type="app"), 0)
        self.assertFalse(ok)
        self.assertIn("非用户", reason)

    def test_old_messages_are_rejected(self):
        ok, reason = bridge.accept_event(self.cfg, make_event(create_time="1000"), 10_000_000)
        self.assertFalse(ok)
        self.assertIn("历史", reason)

    def test_strip_mentions(self):
        ev = make_event(mentions=[{"id": "ou_bot", "key": "@_user_1"}])
        self.assertEqual(bridge.strip_mentions(ev, "@_user_1 你好"), "你好")

    def test_commands(self):
        self.assertEqual(bridge.parse_command("/status"), ("status", ""))
        self.assertEqual(bridge.parse_command("/pwd"), ("pwd", ""))
        self.assertEqual(bridge.parse_command("/CD /tmp"), ("cd", "/tmp"))
        self.assertEqual(bridge.parse_command('/cd "a b"'), ("cd", "a b"))
        self.assertIsNone(bridge.parse_command("状态"))
        self.assertIsNone(bridge.parse_command("普通任务"))
        self.assertIsNone(bridge.parse_command("/"))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = bridge.State(Path(self.tmp.name) / "state.db")

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def test_dedupe(self):
        self.assertTrue(self.state.mark_seen("om_1", "oc_1", 1))
        self.assertFalse(self.state.mark_seen("om_1", "oc_1", 1))

    def test_session_roundtrip(self):
        self.state.set_session("oc_1", "th_1", "/tmp", "model")
        row = self.state.get_session("oc_1")
        self.assertEqual(row["thread_id"], "th_1")
        self.state.clear_session("oc_1")
        self.assertIsNone(self.state.get_session("oc_1"))

    def test_cwd_roundtrip_and_missing_directory_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            default = Path(tmp) / "default"
            target = Path(tmp) / "target"
            default.mkdir()
            target.mkdir()
            self.assertEqual(self.state.get_cwd("oc_1", default), default)
            self.state.set_cwd("oc_1", target)
            self.assertEqual(self.state.get_cwd("oc_1", default), target)
            target.rmdir()
            self.assertEqual(self.state.get_cwd("oc_1", default), default)

    def test_queue_lifecycle(self):
        task_id = self.state.enqueue("om_1", "oc_1", "oc_1", "hello", "{}", "/tmp")
        self.assertGreater(task_id, 0)
        self.assertEqual(self.state.queue_len(), 1)
        task = self.state.next_task()
        self.assertEqual(task["id"], task_id)
        self.assertEqual(task["status"], "running")
        self.assertEqual(task["cwd"], "/tmp")
        self.state.finish_task(task_id, "done", "ok")
        self.assertEqual(self.state.queue_len(), 0)
        self.assertEqual(self.state.status_summary()["tasks"].get("done"), 1)


class CodexRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = make_cfg(self.root)
        self.cfg.codex_bin = str(
            Path(__file__).resolve().parent / "fakes" / "codex"
        )
        self.state = bridge.State(self.cfg.db_path)

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def test_runner_parses_events_and_saves_thread(self):
        ev = make_event()
        task = {
            "id": 1,
            "session_key": "oc_test",
            "chat_id": "oc_test",
            "prompt": "hello",
            "cwd": str(self.cfg.workdir),
            "event_json": json.dumps(ev.raw, ensure_ascii=False),
        }
        progress: list[str] = []
        result = bridge.CodexRunner(self.cfg, self.state).run(
            task, ev, "hello", threading.Event(), on_progress=progress.append
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.text, "fake done")
        self.assertEqual(result.thread_id, "fake-thread-1")
        self.assertTrue(any("执行" in item for item in progress))
        thread_key = bridge.session_key_for_cwd("oc_test", self.cfg.workdir)
        session = self.state.get_session(thread_key)
        self.assertEqual(session["thread_id"], "fake-thread-1")

    def test_build_args_and_prompt_use_session_cwd(self):
        runner = bridge.CodexRunner(self.cfg, self.state)
        cwd = self.root / "project"
        cwd.mkdir()
        prompt = runner._build_prompt(make_event(), "hello", cwd)
        self.assertIn(f"- 工作区: {cwd}", prompt)
        args, actual_cwd = runner._build_args("hello", "", self.root / "last.txt", cwd)
        self.assertEqual(actual_cwd, cwd)
        self.assertIn("-C", args)
        self.assertEqual(args[args.index("-C") + 1], str(cwd))

    def test_runner_batches_progress_events(self):
        fake = self.root / "fake-codex-multi"
        fake.write_text(
            """#!/usr/bin/env bash
cat <<'JSON'
{"type":"thread.started","thread_id":"th-multi"}
{"type":"item.completed","item":{"type":"command_execution","command":"echo one","exit_code":0}}
{"type":"item.completed","item":{"type":"command_execution","command":"echo two","exit_code":0}}
{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"a.txt"}]}}
{"type":"item.completed","item":{"type":"agent_message","text":"multi done"}}
JSON
""",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        self.cfg.codex_bin = str(fake)
        ev = make_event()
        task = {
            "id": 2,
            "session_key": "oc_test",
            "chat_id": "oc_test",
            "prompt": "hello",
            "cwd": str(self.cfg.workdir),
            "event_json": json.dumps(ev.raw, ensure_ascii=False),
        }
        progress: list[str] = []
        result = bridge.CodexRunner(self.cfg, self.state).run(
            task, ev, "hello", threading.Event(), on_progress=progress.append
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(progress), 1)
        self.assertIn("执行摘要（3 项）", progress[0])
        self.assertIn("echo one", progress[0])
        self.assertIn("a.txt", progress[0])

    def test_progress_disabled(self):
        self.cfg.progress = False
        ev = make_event()
        task = {
            "id": 3,
            "session_key": "oc_test",
            "chat_id": "oc_test",
            "prompt": "hello",
            "cwd": str(self.cfg.workdir),
            "event_json": json.dumps(ev.raw, ensure_ascii=False),
        }
        progress: list[str] = []
        result = bridge.CodexRunner(self.cfg, self.state).run(
            task, ev, "hello", threading.Event(), on_progress=progress.append
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(progress, [])


class OmpRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = make_cfg(self.root)
        self.cfg.agent_kind = "omp"
        self.cfg.codex_bin = "omp"
        self.state = bridge.State(self.cfg.db_path)

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def test_build_args_new_and_resume(self):
        runner = bridge.CodexRunner(self.cfg, self.state)
        args, cwd = runner._build_args("hi", "", self.root / "last.txt", self.cfg.workdir)
        self.assertEqual(cwd, self.cfg.workdir)
        self.assertEqual(args[0], "omp")
        self.assertEqual(args[1:3], ["--mode", "json"])
        self.assertEqual(args[-1], "hi")
        resumed, _ = runner._build_args("again", "omp-sess-1",
                                        self.root / "last.txt", self.cfg.workdir)
        self.assertIn("--resume", resumed)
        self.assertEqual(resumed[resumed.index("--resume") + 1], "omp-sess-1")

    def test_omp_event_stream(self):
        fake = self.root / "fake-omp"
        fake.write_text(
            """#!/usr/bin/env bash
cat <<'JSON'
{"type":"session","id":"omp-sess-1","cwd":"/tmp"}
{"type":"message_end","message":{"role":"user","content":[{"type":"text","text":"hello"}]}}
{"type":"tool_execution_start","toolName":"bash","args":{"command":"pwd"}}
{"type":"tool_execution_end","toolName":"bash","isError":false}
{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"final omp"}]}}
{"type":"agent_end","messages":[]}
JSON
""",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        self.cfg.codex_bin = str(fake)
        ev = make_event()
        task = {
            "id": 4,
            "session_key": "oc_test",
            "chat_id": "oc_test",
            "prompt": "hello",
            "cwd": str(self.cfg.workdir),
            "event_json": json.dumps(ev.raw, ensure_ascii=False),
        }
        progress: list[str] = []
        result = bridge.CodexRunner(self.cfg, self.state).run(
            task, ev, "hello", threading.Event(), on_progress=progress.append
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.text, "final omp")
        self.assertEqual(result.thread_id, "omp-sess-1")
        self.assertEqual(len(progress), 1)
        self.assertIn("执行摘要（1 项）", progress[0])
        self.assertIn("pwd", progress[0])
        key = bridge.session_key_for_cwd("oc_test", self.cfg.workdir)
        self.assertEqual(self.state.get_session(key)["thread_id"], "omp-sess-1")

    def test_load_config_omp_aliases(self):
        work = self.root / "omp-work"
        work.mkdir()
        (self.root / "config.env").write_text(
            "\n".join([
                "OWNER_ID=ou_owner",
                "AGENT_KIND=omp",
                "OMP_WORKDIR=" + str(work),
                "OMP_BIN=/opt/omp",
                "LARK_BIN=/opt/lark-cli",
                "LARK_PROFILE=omp-bot",
                "PROGRESS_BATCH_ITEMS=7",
            ]) + "\n",
            encoding="utf-8",
        )
        cfg = bridge.load_config(self.root)
        self.assertEqual(cfg.agent_kind, "omp")
        self.assertEqual(cfg.workdir, work)
        self.assertEqual(cfg.codex_bin, "/opt/omp")
        self.assertEqual(cfg.lark_cli_bin, "/opt/lark-cli")
        self.assertEqual(cfg.progress_batch_items, 7)
        self.assertEqual(
            cfg.lark_args("auth", "status"),
            ["/opt/lark-cli", "--profile", "omp-bot", "auth", "status"],
        )


if __name__ == "__main__":
    unittest.main()


class FakeFeishu:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.calls: list[dict] = []

    def send(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))
        self.calls.append({"chat_id": chat_id, "text": text, **kwargs})
        return True


class FakePool:
    def cancel_all(self):
        pass


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = make_cfg(self.root)
        self.state = bridge.State(self.cfg.db_path)
        self.feishu = FakeFeishu()
        self.supervisor = bridge.ConsumerSupervisor(
            self.cfg, self.state, self.feishu, FakePool(), threading.Event()
        )
        self.ev = make_event()

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def last_text(self) -> str:
        return self.feishu.sent[-1][1]

    def test_pwd_uses_default_workdir(self):
        self.supervisor._handle_command("pwd", "", self.ev)
        self.assertIn(str(self.cfg.workdir), self.last_text())
        self.assertTrue(self.feishu.calls[-1]["markdown"])

    def test_cd_changes_cwd_and_pwd_reflects_it(self):
        target = self.root / "project"
        target.mkdir()
        self.supervisor._handle_command("cd", str(target), self.ev)
        self.assertIn("已切换", self.last_text())
        self.assertEqual(self.state.get_cwd("oc_test", self.cfg.workdir), target.resolve())
        self.supervisor._handle_command("pwd", "", self.ev)
        self.assertIn(str(target.resolve()), self.last_text())

    def test_relative_cd_and_invalid_path(self):
        target = self.cfg.workdir / "sub"
        target.mkdir()
        self.supervisor._handle_command("cd", "sub", self.ev)
        self.assertEqual(self.state.get_cwd("oc_test", self.cfg.workdir), target.resolve())
        self.supervisor._handle_command("cd", "missing", self.ev)
        self.assertIn("目录不存在", self.last_text())
        self.assertEqual(self.state.get_cwd("oc_test", self.cfg.workdir), target.resolve())

    def test_unknown_slash_command_is_rejected(self):
        self.supervisor._handle_command("nope", "", self.ev)
        self.assertIn("未知命令", self.last_text())

    def test_chinese_text_is_a_task_not_a_command(self):
        self.supervisor.handle(make_event(content="状态").raw)
        self.assertEqual(self.feishu.sent, [])
        self.assertEqual(self.state.queue_len(), 1)


class ProgressReporterTests(unittest.TestCase):
    def test_flushes_when_batch_is_full(self):
        sent: list[str] = []
        reporter = bridge.ProgressReporter(sent.append, interval=9999, max_items=3)
        reporter.send("✅ 执行：a")
        reporter.send("✅ 执行：b")
        self.assertEqual(sent, [])
        reporter.send("📝 修改：c")
        self.assertEqual(len(sent), 1)
        self.assertIn("执行摘要（3 项）", sent[0])
        self.assertIn("1. ✅ 执行：a", sent[0])
        self.assertIn("3. 📝 修改：c", sent[0])

    def test_flush_sends_remaining_items_on_finish(self):
        sent: list[str] = []
        reporter = bridge.ProgressReporter(sent.append, interval=9999, max_items=10)
        reporter.send("✅ 执行：a")
        reporter.send("✅ 执行：a")
        reporter.send("✅ 执行：b")
        self.assertEqual(sent, [])
        reporter.flush()
        self.assertEqual(len(sent), 1)
        self.assertIn("执行摘要（2 项）", sent[0])
        self.assertEqual(sent[0].count("执行：a"), 1)

    def test_tick_flushes_after_interval(self):
        sent: list[str] = []
        reporter = bridge.ProgressReporter(sent.append, interval=1, max_items=10)
        reporter.send("✅ 执行：a")
        reporter.last_flush -= 2
        reporter.tick()
        self.assertEqual(len(sent), 1)


class PipelineTests(unittest.TestCase):
    def test_message_to_final_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = make_cfg(root)
            cfg.codex_bin = str(Path(__file__).resolve().parent / "fakes" / "codex")
            state = bridge.State(cfg.db_path)
            feishu = FakeFeishu()
            stop = threading.Event()
            runner = bridge.CodexRunner(cfg, state)
            pool = bridge.WorkerPool(cfg, state, feishu, runner, stop)
            supervisor = bridge.ConsumerSupervisor(cfg, state, feishu, pool, stop)
            pool.start()
            try:
                supervisor.handle(make_event().raw)
                deadline = time.time() + 10
                while time.time() < deadline:
                    if state.status_summary()["tasks"].get("done") == 1:
                        break
                    time.sleep(0.05)
                self.assertEqual(state.status_summary()["tasks"].get("done"), 1)
                texts = [text for _, text in feishu.sent]
                self.assertTrue(any("开始处理" in text for text in texts))
                self.assertTrue(any("fake done" in text for text in texts))
                summaries = [call for call in feishu.calls if "执行摘要" in call["text"]]
                self.assertEqual(len(summaries), 1)
                final = [call for call in feishu.calls if "fake done" in call["text"]][-1]
                self.assertTrue(final["markdown"])
            finally:
                stop.set()
                pool.cancel_all()
                pool.join(timeout=5)
                state.close()


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = make_cfg(Path(self.tmp.name))
        fakes = Path(__file__).resolve().parent / "fakes"
        self.cfg.lark_cli_bin = str(fakes / "lark-cli")
        self.cfg.codex_bin = str(fakes / "codex")

    def run_check(self, **env):
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, env):
            with contextlib.redirect_stdout(buffer):
                code = bridge.cmd_check(self.cfg)
        return code, json.loads(buffer.getvalue())

    def test_free_bus_passes(self):
        code, report = self.run_check(FAKE_BUS_STATE="free")
        self.assertEqual(report["event_bus"], "available")
        self.assertTrue(report["ok"])
        self.assertEqual(code, 0)

    def test_occupied_bus_is_reported_as_problem(self):
        code, report = self.run_check(FAKE_BUS_STATE="occupied")
        self.assertEqual(report["event_bus"], "occupied_by_another_host")
        self.assertFalse(report["ok"])
        self.assertEqual(code, 1)
        problem = " ".join(report["problems"])
        self.assertIn("事件总线已被其他机器占用", problem)
        self.assertIn("online_instance_cnt=1", problem)

    def test_local_bridge_suppresses_probe(self):
        self.cfg.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        code, report = self.run_check(FAKE_BUS_STATE="occupied")
        self.assertEqual(report["event_bus"], "held_by_local_bridge")
        self.assertTrue(report["ok"])
        self.assertEqual(code, 0)
