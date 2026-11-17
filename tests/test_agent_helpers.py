from types import SimpleNamespace

from shelly.config import PUBLIC_SYSTEM_INSTRUCTION
from shelly.agent import Agent, _is_unavailable, human_error


def test_public_agent_has_no_tools():
    public = Agent(public=True)
    assert public.config.tools is None
    assert public.config.system_instruction == PUBLIC_SYSTEM_INSTRUCTION

    owner = Agent()
    assert owner.config.tools is not None
    assert owner.config.system_instruction != PUBLIC_SYSTEM_INSTRUCTION


def test_public_agent_never_dispatches_tools(monkeypatch):
    import shelly.agent as mod

    called = []

    def handler(**kwargs):
        called.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(mod, "TOOL_MAP", {"run_command": SimpleNamespace(handler=handler)})

    public = Agent(public=True)
    result = public._dispatch("run_command", {"command": "uptime"})
    assert called == []
    assert "недоступны" in result["error"]

    owner = Agent()
    assert owner._dispatch("run_command", {"command": "uptime"}) == {"ok": True}
    assert called == [{"command": "uptime"}]


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
    agent.on_retry = None
    monkeypatch.setattr(agent, "_trim_history", lambda: None)
    monkeypatch.setattr(agent, "_dispatch", lambda name, args: {"exit_code": 0})

    pre_tool = types.Content(parts=[
        types.Part(text="Сейчас запущу uptime."),
        types.Part(function_call=types.FunctionCall(
            name="run_command", args={"command": "uptime"},
        )),
    ])
    final = types.Content(parts=[types.Part(text="Всё штатно.")])
    contents = iter([pre_tool, final])
    monkeypatch.setattr(agent, "_generate_stream", lambda on_delta: next(contents))

    assert agent.send("проверь сервер", stream=True) == "Всё штатно."


def test_stream_503_retries_next_model(monkeypatch):
    from google.genai import types
    import shelly.agent as agent_module

    monkeypatch.setattr(agent_module, "MODELS", ["model-one", "model-two"])
    monkeypatch.setattr(agent_module.time, "sleep", lambda _: None)

    agent = Agent.__new__(Agent)
    agent.history = []
    agent.config = None
    agent.key_index = 0
    agent.clients = [SimpleNamespace(
        models=SimpleNamespace(generate_content_stream=lambda **kwargs: object())
    )]
    retried = []
    agent.on_retry = retried.append

    results = iter([
        Exception("503 UNAVAILABLE"),
        types.Content(parts=[types.Part(text="ответ со второй модели")]),
    ])

    def fake_read(stream, on_delta):
        value = next(results)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(agent, "_read_stream", fake_read)

    content = agent._request(stream=True)
    assert retried == ["model-one"]
    assert content.parts[0].text == "ответ со второй модели"
