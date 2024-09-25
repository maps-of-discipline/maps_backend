import json
import traceback
import requests
import werkzeug.exceptions as http_exceptions
from flask import jsonify
from datetime import datetime
from config import TELEGRAM_TOKEN, TELEGRAM_URL, TELEGRAM_CHAT_ID


def escape_special(message: str) -> str:
    for el in ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        message = message.replace(el, '\\' + el)
    return message


def create_message(e: Exception):
    time = escape_special(str(datetime.now()))
    error_name = escape_special(type(e).__name__)
    error_body = escape_special(str(e))

    message = f'*{error_name}: {error_body}*\n\nTime: {time}\n\n'

    tb = escape_special(traceback.format_exc())
    message += f"```python\n{tb}```"
    return message


def process_tg_request(message: str) -> requests.Response:
    response: requests.Response = requests.get(
        url=f'{TELEGRAM_URL}/bot{TELEGRAM_TOKEN}/sendMessage',
        params={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': "MarkdownV2"
        })

    return response


def send_tg_message(message: str):
    print('sending message ')
    response = process_tg_request(message)
    if not response.json()['ok']:
        message = '*ErrorHandler error*\n\n'
        message += f'```json\n{response.json()}```'
        process_tg_request(message)


def handle_exception(e):
    if isinstance(e, (
        http_exceptions.BadRequest,
        http_exceptions.Unauthorized,
        http_exceptions.Forbidden,
        http_exceptions.NotFound,
        http_exceptions.MethodNotAllowed,
    )):
        return e

    send_tg_message(create_message(e))

    return jsonify({'result': 'error', 'reason': str(e), 'traceback': str(traceback.format_exc())}), 500
