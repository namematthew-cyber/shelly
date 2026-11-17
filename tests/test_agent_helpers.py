from types import SimpleNamespace

from shelly.agent import Agent, _is_unavailable, human_error


def test_unavailable_detection():
    err = "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}"
    assert _is_unavailable(err)
    assert _is_unavailable("429 RESOURCE_EXHAUSTED")
    assert not _is_unavailable("ordinary failure")


def test_human_error_messages():
    assert "503" in human_error(Exception("503 high demand"))
    assert "429" in human_error(Exception("429 quota exceeded"))
    assert "Ключ Gemini" in human_error(Exception("401 api_key_invalid"))
    assert "вовремя" in human_error(Exception("504 deadline_exceeded"))
    assert human_error(Exception("something odd")).startswith("ошибка:")


def test_read_stream_collects_text_and_deltas():
    def chunk(text):
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(
            parts=[SimpleNamespace(text=text, function_call=None)]
        ))])

    deltas = []
    agent = Agent.__new__(Agent)
    content = agent._read_stream([chunk("При"), chunk("вет!")], deltas.append)
    assert deltas == ["При", "вет!"]
    assert content.parts[0].text == "Привет!"


def test_send_returns_only_final_text(monkeypatch):
    from google.genai import types

    agent = Agent.__new__(Agent)
    agent.history = []
    agent.on_thinking_start = agent.on_thinking_stop = None
    agent.on_tool = agent.on_tool_done = None
    monkeypatch.setattr(agent, "_trim_history", lambda: None)
    monkeypatch.setattr(agent, "_dispatch", lambda name, args: {"exit_code": 0})
    monkeypatch.setattr(agent, "_open_stream", lambda: object())

    pre_tool = types.Content(parts=[
        types.Part(text="Сейчас запущу uptime."),
        types.Part(function_call=types.FunctionCall(
            name="run_command", args={"command": "uptime"},
        )),
    ])
    final = types.Content(parts=[types.Part(text="Всё штатно.")])
    contents = iter([pre_tool, final])
    monkeypatch.setattr(agent, "_read_stream", lambda stream, on_delta: next(contents))

    assert agent.send("проверь сервер", stream=True) == "Всё штатно."
