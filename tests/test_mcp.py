"""Drive `clarity mcp` as a real subprocess over STDIO with raw JSON-RPC."""

import json
import subprocess
import sys

import pytest

EM = "—"


class Session:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "clarity.cli", "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.frames: list[dict] = []
        self.raw_stdout: list[str] = []
        self._id = 0

    def send(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}

        if params is not None:
            msg["params"] = params

        if not notify:
            self._id += 1
            msg["id"] = self._id

        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

        return None if notify else self._id

    def read_response(self, req_id):
        while True:
            line = self.proc.stdout.readline()

            if not line:
                raise AssertionError("server closed stdout: " + self.proc.stderr.read())

            self.raw_stdout.append(line)
            frame = json.loads(line)
            self.frames.append(frame)

            if frame.get("id") == req_id:
                return frame

    def call(self, method, params=None):
        return self.read_response(self.send(method, params))

    def tool(self, name, arguments):
        frame = self.call("tools/call", {"name": name, "arguments": arguments})

        return frame["result"]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


@pytest.fixture
def session():
    s = Session()
    init = s.call(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    )
    assert "result" in init, init
    s.send("notifications/initialized", notify=True)

    yield s

    s.close()


def payload(result):
    if "structuredContent" in result and result["structuredContent"]:
        sc = result["structuredContent"]

        return sc.get("result", sc)

    return json.loads(result["content"][0]["text"])


def test_exactly_three_tools_are_listed(session):
    tools = session.call("tools/list")["result"]["tools"]

    assert sorted(t["name"] for t in tools) == ["check_text", "list_rules", "score_text"]


def test_check_text_returns_findings_and_score(session):
    data = payload(session.tool("check_text", {"text": f"He left {EM} quickly."}))

    assert any(f["rule"] == "em-dash" for f in data["findings"])
    assert data["findings"][0]["source"] == "<text>"
    assert data["score"] < 100
    assert "readability" in data


def test_check_text_accepts_a_yaml_config_override(session):
    text = "We need more synergy."
    cfg = "watchlist:\n  - {term: synergy, max_per_1k: 0}"
    data = payload(session.tool("check_text", {"text": text, "config": cfg}))

    assert [f["rule"] for f in data["findings"] if f["category"] == "watchlist"] == ["synergy"]


def test_check_text_bad_config_is_a_tool_error_not_a_crash(session):
    result = session.tool("check_text", {"text": "hi", "config": "rules: [{id: x}]"})

    assert result["isError"] is True
    assert session.proc.poll() is None


def test_score_text_returns_a_score(session):
    data = payload(session.tool("score_text", {"text": "The build passed. We shipped it."}))

    assert data["score"] == 100


def test_list_rules_lists_every_rule(session):
    rules = payload(session.tool("list_rules", {}))

    assert {"em-dash", "intensifier", "false-agency"} <= {r["id"] for r in rules}
    assert {"id", "category", "severity", "confidence", "max_per_1k"} <= set(rules[0])


def test_stdout_carries_only_json_rpc_frames_and_logs_go_to_stderr(session):
    session.tool("check_text", {"text": "Really?"})
    session.close()

    assert session.raw_stdout
    assert all(f.get("jsonrpc") == "2.0" for f in session.frames)
    assert all(line.lstrip().startswith("{") for line in session.raw_stdout)
