"""Ядро агентного harness: цикл «модель → инструменты → модель»."""

import json
import time
import logging
from datetime import datetime

from google import genai
from google.genai import types

from .config import (
    API_KEYS, HISTORY_LIMIT, LOG_PATH, MODELS, STEP_LIMIT, SYSTEM_INSTRUCTION,
)
from .masking import mask
from .tools import TOOLS, TOOL_MAP

logger = logging.getLogger("shelly.agent")
logger.setLevel(logging.INFO)
_file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_file_handler)
logger.propagate = False


class ModelUnavailable(Exception):
    """Все модели и ключи перегружены или временно недоступны."""


def _is_unavailable(exc):
    text = str(exc).lower()
    return any(x in text for x in ("503", "unavailable", "high demand", "429", "resource_exhausted"))


def human_error(exc):
    """Переводит техническую ошибку Gemini в понятное пользователю сообщение."""
    text = str(exc)
    low = text.lower()
    if any(x in low for x in ("503", "unavailable", "high demand", "overload")):
        return (
            "Gemini сейчас под наплывом посетителей (503). Прошла все ключи и модели — "
            "ни одна не ответила. Подожди минуту и позови снова; выдумывать ответ я не стану."
        )
    if any(x in low for x in ("429", "resource_exhausted", "quota", "rate limit")):
        return (
            "У ключей Gemini закончилась квота (429). Проверь GEMINI_API_KEYS в .env "
            "или добавь ещё один ключ — я уже перебрала все."
        )
    if any(x in low for x in ("401", "403", "api_key_invalid", "permission_denied", "unauthorized")):
        return "Ключ Gemini не прошёл проверку. Проверь GEMINI_API_KEYS в .env."
    if any(x in low for x in ("504", "deadline_exceeded", "timeout", "timed out")):
        return "Gemini не ответил вовремя. Попробуй ещё раз — сеть иногда тоже устаёт."
    return f"ошибка: {text}"


class Agent:
    def __init__(self, confirm=None, on_thinking_start=None, on_thinking_stop=None,
                 on_tool=None, on_tool_done=None, on_retry=None):
        if not API_KEYS:
            raise RuntimeError("Нет ключей Gemini в .env (GEMINI_API_KEYS)")
        self.clients = [genai.Client(api_key=k) for k in API_KEYS]
        self.key_index = 0
        self.history = []
        self.confirm = confirm
        self.on_thinking_start = on_thinking_start
        self.on_thinking_stop = on_thinking_stop
        self.on_tool = on_tool
        self.on_tool_done = on_tool_done
        self.on_retry = on_retry

        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=t.name, description=t.description,
                    parameters=types.Schema(**t.parameters),
                ) for t in TOOLS
            ])],
            temperature=0.3,
        )

    def _request(self, stream=False, on_delta=None):
        """Перебирает модели и ключи; 503 внутри потока тоже считается ошибкой модели.

        Поток читается целиком внутри попытки: иначе 503 приходит уже после того,
        как generate_content_stream вернул генератор, и перебор моделей не работал.
        """
        last = None
        saw_overload = False
        for model in MODELS:
            for attempt in range(len(self.clients)):
                i = (self.key_index + attempt) % len(self.clients)
                try:
                    if stream:
                        generator = self.clients[i].models.generate_content_stream(
                            model=model, contents=self.history, config=self.config
                        )
                        pending = []
                        result = self._read_stream(generator, pending.append)
                    else:
                        result = self.clients[i].models.generate_content(
                            model=model, contents=self.history, config=self.config
                        )
                    self.key_index = i
                    if stream and on_delta:
                        for delta in pending:
                            on_delta(delta)
                    return result
                except Exception as e:
                    last = e
                    if _is_unavailable(e):
                        saw_overload = True
                        if self.on_retry:
                            self.on_retry(model)
                        time.sleep(min(0.5 * (2 ** attempt), 2))
                    else:
                        time.sleep(0.3)
        if saw_overload and _is_unavailable(last):
            raise ModelUnavailable(str(last)) from last
        raise last

    def _generate(self):
        return self._request(stream=False)

    def _generate_stream(self, on_delta):
        return self._request(stream=True, on_delta=on_delta)

    def _read_stream(self, stream, on_delta):
        """Собирает поток в один Content, отдавая куски текста наружу по мере прихода."""
        texts = []
        call_parts = []
        for chunk in stream:
            if not chunk.candidates:
                continue
            content = chunk.candidates[0].content
            for part in content.parts or []:
                text = getattr(part, "text", None)
                if text:
                    texts.append(text)
                    if on_delta:
                        on_delta(text)
                if getattr(part, "function_call", None):
                    call_parts.append(part)
        parts = ([types.Part(text="".join(texts))] if texts else []) + call_parts
        return types.Content(role="model", parts=parts) if parts else None

    def _trim_history(self):
        if len(self.history) <= HISTORY_LIMIT:
            return
        removed = len(self.history) - HISTORY_LIMIT + 2
        self.history = self.history[:2] + self.history[removed:]
        logger.info("История урезана до %d сообщений", len(self.history))

    def _dispatch(self, name: str, args: dict) -> dict:
        tool = TOOL_MAP.get(name)
        if not tool:
            return {"error": f"Неизвестный инструмент: {name}"}
        try:
            result = tool.handler(**args, confirm=self.confirm) if "confirm" in tool.handler.__code__.co_varnames \
                else tool.handler(**args)
        except Exception as e:
            result = {"error": str(e)}
        logger.info("tool=%s args=%s result=%s", name,
                    mask(json.dumps(args, ensure_ascii=False)),
                    mask(json.dumps(result, ensure_ascii=False)[:1000]))
        return result

    def send(self, text: str, stream: bool = False, on_stream=None) -> str:
        """Прогоняет агентный цикл. При stream=True куски текста идут в on_stream."""
        self._trim_history()
        self.history.append(types.Content(
            role="user", parts=[types.Part(text=text)]
        ))

        for _ in range(STEP_LIMIT):
            step_text = []

            def on_delta(delta, buffer=step_text):
                buffer.append(delta)
                if on_stream:
                    on_stream(delta)

            if self.on_thinking_start:
                self.on_thinking_start()
            try:
                try:
                    if stream:
                        content = self._generate_stream(on_delta)
                    else:
                        response = self._generate()
                        content = response.candidates[0].content if response.candidates else None
                except Exception as e:
                    if _is_unavailable(e) and not isinstance(e, ModelUnavailable):
                        raise ModelUnavailable(str(e)) from e
                    raise
            finally:
                if self.on_thinking_stop:
                    self.on_thinking_stop()

            if not content:
                return "(пустой ответ модели)"

            self.history.append(content)
            parts = content.parts or []
            calls = [p for p in parts if getattr(p, "function_call", None)]

            if not calls:
                # Промежуточные реплики до инструментов в итоговый ответ не попадают.
                return "\n".join(p.text for p in parts if getattr(p, "text", None))

            responses = []
            for part in calls:
                fc = part.function_call
                args = dict(fc.args or {})
                if self.on_tool:
                    self.on_tool(fc.name, args)
                try:
                    result = self._dispatch(fc.name, args)
                finally:
                    if self.on_tool_done:
                        self.on_tool_done(fc.name, args)
                responses.append(types.Part(function_response=types.FunctionResponse(
                    name=fc.name, response=result,
                )))
            self.history.append(types.Content(role="user", parts=responses))

        return "Слишком много шагов подряд — остановилась, чтобы не уехать не туда."
