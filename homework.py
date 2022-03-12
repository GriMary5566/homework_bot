import json
import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Dict

import requests
import telegram
from dotenv import load_dotenv

import exceptions

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s  [%(name)s]  [%(levelname)s]  %(message)s'
)
logger.addHandler(handler)
handler.setFormatter(formatter)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_TIME = 600
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

PREV_HOMEWORK_STATUSES: Dict[str, str] = {}


def send_message(bot, message):
    """Отправка сообщения ботом."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f'Бот отправил сообщение "{message}".')
    except telegram.TelegramError:
        logger.error(f'Бот не смог отправить сообщение "{message}".')


def get_api_answer(current_timestamp):
    """Получаем ответ на запрос к эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        status = response.status_code
        if status != HTTPStatus.OK:
            logger.error(
                f'Сбой в работе программы: Эндпоинт {ENDPOINT} недоступен.'
                f'Код ответа API: {status}'
            )
            raise requests.exceptions.HTTPError(
                f'Эндпоинт {ENDPOINT} недоступен.'
            )
        return response.json()
    except json.decoder.JSONDecodeError:
        logger.error('Формат ответа API отличается от JSON')
        raise Exception('Формат ответа API отличается от JSON')
    except requests.exceptions.RequestException as error:
        logger.error(f'Ошибка при запросе к основному API: {error}')
        raise Exception(f'Ошибка при запросе к основному API: {error}')


def check_response(response):
    """Проверка ответа API на корректность."""
    if type(response) is not dict:
        logger.error(
            'Сбой в работе программы: Ответ API имеет тип данных, '
            'отличный от dict'
        )
        raise TypeError('Ответ API имеет тип данных, отличный от dict')
    homeworks = response.get('homeworks')
    if homeworks is None:
        logger.error(
            'Сбой в работе программы: Ответ API не содержит ключ "homeworks"'
        )
        raise KeyError('Ответ API не содержит ключ "homeworks"')
    if type(homeworks) is not list:
        logger.error(
            'Сбой в работе программы: Значение ключа "homeworks" '
            'не является списком'
        )
        raise TypeError('Значение ключа "homeworks" не является списком')
    return homeworks


def parse_status(homework):
    """Проверка статуса домашней работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_STATUSES:
        logger.error(f'Статус работы {homework_status} недопустим')
        raise KeyError(f'Статус работы {homework_status} недопустим')
    if homework_name in PREV_HOMEWORK_STATUSES:
        if PREV_HOMEWORK_STATUSES[homework_name] == homework_status:
            raise exceptions.HomeworkError(
                f'Статус работы {homework_name} не изменился'
            )
    PREV_HOMEWORK_STATUSES[homework_name] = homework_status

    verdict = HOMEWORK_STATUSES.get(homework_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    for token in tokens:
        if token is None:
            logger.critical(
                'Отсутствует обязательная переменная окружения: '
                f'{token}. Программа принудительно остановлена'
            )
            return False
    return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    prev_error = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if len(homeworks) != 0:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            current_timestamp = response.get('current_date')
        except exceptions.HomeworkError as error:
            logger.debug(error)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if message != prev_error:
                send_message(bot, message)
                prev_error = message
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
