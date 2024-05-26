import json
import traceback
import requests
from werkzeug.exceptions import HTTPException
from flask import jsonify
from datetime import datetime
from config import TELEGRAM_TOKEN, TELEGRAM_URL, TELEGRAM_CHAT_ID


def escapte_special(message: str) -> str: 
    for el in ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        message = message.replace(el, '\\' + el)
    return message

def send_telegram_message(message: str) -> requests.Response:
    response: requests.Response = requests.get(
        url=f'{TELEGRAM_URL}/bot{TELEGRAM_TOKEN}/sendMessage', 
        params={
            'chat_id': TELEGRAM_CHAT_ID, 
            'text': message, 
            'parse_mode': "MarkdownV2"
        })
    return response


def handle_exception(e):
    time = escapte_special(str(datetime.now()))
    error_name = escapte_special(type(e).__name__)
    error_body = escapte_special(str(e))

    message = f'*{error_name}: {error_body}*\n\nTime: {time}\n\n'

    tb = escapte_special(traceback.format_exc())
    message += f"```python\n{tb}```"

    response = send_telegram_message(message)

    if not response.json()['ok']:
        message = '*ErrorHandler error*\n\n'
        message += f'```json\n{response.json()}```'
        send_telegram_message(message)

    print(e)

    if isinstance(e, HTTPException):
        return e

    return jsonify({'result': 'error', 'reason': str(e), 'traceback': str(traceback.format_exc())}), 500
