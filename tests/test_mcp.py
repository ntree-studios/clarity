"""Drive `clarity mcp` as a real subprocess over STDIO with raw JSON-RPC."""

import json
import subprocess
import sys

import pytest
import yaml

EM = "—"


class Session:
    def __init__(self, cwd=None, env=None, args=()):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "clarity.cli", "mcp", *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
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


def start(cwd=None, env=None, args=()):
    s = Session(cwd, env, args)
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

    return s


@pytest.fixture
def session():
    s = start()

    yield s

    s.close()


def payload(result):
    if "structuredContent" in result and result["structuredContent"]:
        sc = result["structuredContent"]

        return sc.get("result", sc)

    return json.loads(result["content"][0]["text"])


def test_the_checking_tools_are_listed_beside_the_bootstrap_tools(session):
    names = {t["name"] for t in session.call("tools/list")["result"]["tools"]}

    assert {"check_text", "list_rules", "score_text", "accept_finding"} <= names
    assert {"corpus_stats", "suggest_rules", "test_rule", "find_matches", "get_rule",
            "validate_fixtures", "write_rules", "write_fixtures"} <= names  # fmt: skip


def walk(section):
    """Every finding in a response's section tree."""
    yield from section["findings"]

    for child in section["sections"]:
        yield from walk(child)


def test_check_text_returns_findings_and_score(session):
    data = payload(session.tool("check_text", {"text": f"He left {EM} quickly."}))
    found = list(walk(data["section"]))

    assert "findings" not in data and "categories" not in data
    assert any(f["rule"] == "em-dash" for f in found)
    assert found[0]["source"] == "<text>" and found[0]["field"] == "text"
    assert data["score"] < 100 and data["score"] == data["section"]["rollup"]["score"]
    assert "readability" in data


def test_check_text_takes_a_section_tree_and_returns_it(session):
    document = {
        "id": "opening", "title": "Opening day",
        "text": f"The garden opens {EM} at last.",
        "sections": [
            {"id": "beds", "title": "Beds", "subtitle": "Twelve raised beds",
             "items": ["Build the frames in March", "Fill them with compost"]},
            {"id": "water", "title": "Water", "items": [f"Two new taps {EM} by April"]},
        ],
    }  # fmt: skip
    data = payload(session.tool("check_text", {"document": document}))
    root = data["section"]
    beds, water = root["sections"]

    assert (root["id"], root["path"], beds["path"], water["id"]) == ("opening", "", "0", "water")
    assert [f["field"] for f in root["findings"] if f["rule"] == "em-dash"] == ["text"]
    assert [f["field"] for f in water["findings"] if f["rule"] == "em-dash"] == ["items[0]"]
    assert not [f for f in beds["findings"] if f["rule"] == "em-dash"]
    span = next(f for f in water["findings"] if f["rule"] == "em-dash")["span"]
    assert document["sections"][1]["items"][0][span["start"]:span["end"]] == EM
    assert "readability" in root and "readability" not in beds  # beds has no text
    assert data["score"] == root["rollup"]["score"]


def test_check_text_wants_exactly_one_of_text_and_document(session):
    both = session.tool("check_text", {"text": "Hi.", "document": {"text": "Hi."}})
    bad = session.tool("check_text", {"document": {"kind": "slide"}})

    assert both["isError"] is True and bad["isError"] is True
    assert "unknown keys ['kind']" in bad["content"][0]["text"]


def test_check_text_accepts_a_yaml_config_override(session):
    text = "We need more synergy."
    cfg = "watchlist:\n  - {term: synergy, max_per_1k: 0}"
    data = payload(session.tool("check_text", {"text": text, "config": cfg}))

    found = walk(data["section"])

    assert [f["rule"] for f in found if f["category"] == "watchlist"] == ["synergy"]


def test_check_text_bad_config_is_a_tool_error_not_a_crash(session):
    result = session.tool("check_text", {"text": "hi", "config": "rules: [{id: x}]"})

    assert result["isError"] is True
    assert session.proc.poll() is None


def test_score_text_returns_a_score(session):
    data = payload(session.tool("score_text", {"text": "The build passed on the first run."}))

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


def test_oversize_text_is_a_tool_error_not_a_crash(session):
    result = session.tool("check_text", {"text": "a. " * 400_000})

    assert result["isError"] is True
    assert session.proc.poll() is None


def test_analyze_topics_takes_focus_keywords_and_documents_them(session):
    from pathlib import Path

    tools = {t["name"]: t for t in session.call("tools/list")["result"]["tools"]}
    assert "keywords: [str]" in tools["analyze_topics"]["description"]
    assert "focus" in tools["check_text"]["inputSchema"]["properties"]
    tree = yaml.safe_load((Path(__file__).parent / "topics" / "planted.yml").read_text("utf-8"))
    data = payload(session.tool("analyze_topics", {
        "document": tree, "focus": {"keywords": ["espresso", "kayak"]},
    }))  # fmt: skip

    assert data["focus"]["missing_keywords"] == ["kayak"]
    assert data["chunks"][0]["keywords_present"] == ["espresso"]


EASE = "Simply restart the service."
SYNERGY_WATCH = "watchlist:\n  - {term: synergy, max_per_1k: 0}\n"


@pytest.fixture
def isolated(tmp_path):
    """An empty user directory, so only the shipped config and what a test writes apply."""
    import os

    env = {**os.environ, "CLARITY_HOME": str(tmp_path / "home")}
    env.pop("CLARITY_CONFIG", None)
    env.pop("CLARITY_PROFILE", None)

    return tmp_path, env


def rules_fired(result):
    return {f["rule"] for f in walk(payload(result)["section"])}


def test_check_text_uses_the_project_clarity_folder_like_the_cli(isolated):
    tmp, env = isolated
    (tmp / "proj" / ".clarity").mkdir(parents=True)
    (tmp / "proj" / ".clarity" / "watchlist.yml").write_text(SYNERGY_WATCH)
    s = start(cwd=tmp / "proj", env=env)

    try:
        assert "synergy" in rules_fired(s.tool("check_text", {"text": "We need synergy."}))
    finally:
        s.close()


def test_server_config_flag_and_profile_argument(isolated):
    tmp, env = isolated
    (tmp / "mine").mkdir()
    (tmp / "mine" / "watchlist.yml").write_text(SYNERGY_WATCH)
    (tmp / "elsewhere").mkdir()
    s = start(cwd=tmp / "elsewhere", env=env, args=("--config", str(tmp / "mine")))

    try:
        assert "synergy" in rules_fired(s.tool("check_text", {"text": "We need synergy."}))
        shipped = rules_fired(s.tool("check_text", {"text": EASE, "profile": "technical"}))
        plain = rules_fired(s.tool("check_text", {"text": EASE, "profile": "none"}))
        assert "ease-words" in shipped and "ease-words" not in plain
        assert s.tool("score_text", {"text": EASE, "profile": "nope"})["isError"] is True
    finally:
        s.close()


def test_server_profile_flag_is_the_default_for_every_call(isolated):
    tmp, env = isolated
    s = start(cwd=tmp, env=env, args=("--profile", "technical"))

    try:
        assert "ease-words" in rules_fired(s.tool("check_text", {"text": EASE}))
    finally:
        s.close()


SWITCHED = f"The new dashboard is a testament to our team {EM} and it plays a pivotal role. " + EASE
CORPORATE = {"ai-lexicon-gpt4", "corporate-tier-a"}


def test_disable_drops_a_rule_and_a_whole_category(session):
    before = rules_fired(session.tool("check_text", {"text": SWITCHED}))
    after = rules_fired(session.tool("check_text", {
        "text": SWITCHED, "disable": ["em-dash", "corporate-vocabulary"],
    }))  # fmt: skip

    assert {"em-dash", *CORPORATE} <= before
    assert not ({"em-dash", *CORPORATE} & after)
    assert "ease-words" not in before


def test_enable_turns_on_a_rule_that_is_off_by_default(session):
    found = rules_fired(session.tool("check_text", {"text": SWITCHED, "enable": ["ease-words"]}))
    plain = payload(session.tool("score_text", {"text": SWITCHED}))["score"]
    switched = payload(session.tool("score_text", {"text": SWITCHED, "disable": ["em-dash"]}))

    assert "ease-words" in found
    assert switched["score"] >= plain


def test_disable_beats_a_profile_that_enables_the_rule(session):
    found = rules_fired(session.tool("check_text", {
        "text": SWITCHED, "profile": "technical", "disable": ["ease-words"],
    }))  # fmt: skip

    assert "ease-words" not in found


def test_unknown_disable_id_is_a_tool_error_naming_it(session):
    for tool in ("check_text", "score_text", "analyze_topics"):
        result = session.tool(tool, {"text": SWITCHED, "disable": ["em-dash", "no-such-rule"]})

        assert result["isError"] is True
        assert "no-such-rule" in result["content"][0]["text"]


def test_analyze_topics_takes_disable_and_enable(session):
    result = session.tool("analyze_topics", {
        "text": SWITCHED, "disable": ["hedges"], "enable": ["ease-words"],
    })  # fmt: skip

    assert result.get("isError") is not True


def test_usage_guide_is_a_resource(session):
    listed = {r["uri"] for r in session.call("resources/list")["result"]["resources"]}
    read = session.call("resources/read", {"uri": "clarity://guide/usage"})["result"]
    text = read["contents"][0]["text"]

    assert "clarity://guide/usage" in listed
    assert "disable" in text and "enable" in text
