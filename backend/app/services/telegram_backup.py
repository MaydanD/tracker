"""Small HTTPS transport. Never propagate URLs, tokens or Telegram descriptions."""
import http.client
import json
import uuid

from app.core.errors import AppError


class TelegramError(AppError):
    code = "telegram_error"
    status_code = 502


# Generic fallback messages that are safe to show — they never contain the URL,
# token, or any Telegram-internal detail.  We distinguish check vs. send so the
# user understands whether their data was actually transmitted.
_TIMEOUT_CHECK = (
    "Telegram не ответил во время проверки подключения. "
    "Проверьте интернет и повторите попытку."
)
_TIMEOUT_SEND = (
    "Нет ответа Telegram. Проверьте интернет. "
    "Отправка могла завершиться: перед повтором проверьте чат."
)


def call(token, method, fields=None, document=None, *, _operation="send"):
    """Call a Telegram Bot API method.

    *_operation* is either ``"check"`` or ``"send"`` and controls the generic
    fallback error message shown when the connection itself fails — so the user
    is never told "отправка могла завершиться" after a connection-check call.
    """
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (fields or {}).items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    if document is not None:
        filename, raw = document
        if len(raw) > 50 * 1024 * 1024:
            raise TelegramError("Архив превышает лимит Telegram 50 МБ. Скачайте копию на компьютер.")
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\nContent-Type: application/zip\r\n\r\n'.encode() + raw + b'\r\n')
    # Telegram answers an empty multipart body (nothing but the closing
    # boundary) with 400 and *no* body at all — which cannot be told apart from
    # a network failure and made a field-less getMe fail every time.  When there
    # is nothing to send, send no body instead.
    if parts:
        parts.append(f'--{boundary}--\r\n'.encode())
        body = b"".join(parts)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    else:
        body = b""
        headers = {}
    connection = http.client.HTTPSConnection("api.telegram.org", timeout=45)
    try:
        connection.request("POST", f"/bot{token}/{method}", body=body, headers=headers)
        response = connection.getresponse()
        try:
            payload = json.loads(response.read(1024 * 1024))
        except ValueError:
            # A rejection without a JSON envelope is Telegram refusing the
            # request, not silence: fall back to the status-based message.
            payload = {}
        code = payload.get("error_code", response.status)
        if response.status == 200 and payload.get("ok") is True:
            return payload["result"]
        message = {
            401: "Telegram отклонил токен бота. Проверьте токен в настройках.",
            404: "Telegram не нашёл бота. Проверьте токен.",
            400: "Telegram отклонил запрос. Проверьте идентификатор чата и начните диалог с ботом.",
            403: "Бот не может писать в этот чат. Разблокируйте бота и начните с ним диалог.",
            429: "Telegram ограничил частоту запросов. Повторите попытку позже.",
        }.get(code, "Telegram временно недоступен. Повторите попытку позже.")
        raise TelegramError(message)
    except TelegramError:
        raise
    except Exception:
        # HTTP exceptions can contain the secret-bearing URL — never propagate.
        raise TelegramError(_TIMEOUT_CHECK if _operation == "check" else _TIMEOUT_SEND) from None
    finally:
        connection.close()


def check(token, chat_id):
    """Verify that the bot token is valid and the bot can write to *chat_id*.

    Uses sendChatAction (``typing``) instead of sendMessage so that the check
    does not litter the user's chat with test messages.  sendChatAction returns
    a real 403/400 if the bot is blocked or the chat is invalid, which is all
    we need to confirm write access.
    """
    call(token, "getMe", _operation="check")
    chat = call(token, "getChat", {"chat_id": chat_id}, _operation="check")
    if chat.get("type") != "private":
        raise TelegramError("Укажите идентификатор личного чата с ботом.")
    # sendChatAction confirms write access without posting a visible message.
    call(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"}, _operation="check")


def send(token, chat_id, raw, moment):
    call(token, "sendDocument", {
        "chat_id": chat_id, "caption": f"Tracker — резервная копия от {moment:%d.%m.%Y}",
    }, (f"tracker-backup-{moment:%Y-%m-%d}.zip", raw))
