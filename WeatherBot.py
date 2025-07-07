import logging
import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from flask import Flask, request, abort
import git  # Для автоматических обновлений из GitHub

# ===== ОБЯЗАТЕЛЬНЫЕ ИЗМЕНЕНИЯ ДЛЯ PYTHONANYWHERE =====

# 1. Добавляем Flask приложение для обработки вебхуков
app = Flask(__name__)

# 2. Используем переменные окружения вместо хардкода
TELEGRAM_TOKEN = os.getenv("6614f8a1f5bb42ff885181823250707")
WEATHERAPI_KEY = os.getenv("8169594634:AAFdGPBKHaoT1cosQqyGhZtD5bWUadaeWq0")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # Секретный ключ для защиты вебхука

# 3. Добавляем прокси для исходящих запросов (требование PythonAnywhere)
PROXY_URL = "http://proxy.server:3128"  # Стандартный прокси PythonAnywhere

# 4. Инициализируем бота с прокси
bot = Bot(token=TELEGRAM_TOKEN, proxy=PROXY_URL)
dp = Dispatcher()

# ===== КОНЕЦ ОБЯЗАТЕЛЬНЫХ ИЗМЕНЕНИЙ =====

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Эмодзи для разных типов погоды
WEATHER_EMOJI = {
    'Sunny': '☀️',
    'Clear': '☀️',
    'Partly cloudy': '⛅',
    'Cloudy': '☁️',
    'Overcast': '☁️',
    'Mist': '🌫️',
    'Fog': '🌁',
    'Light rain': '🌦️',
    'Moderate rain': '🌧️',
    'Heavy rain': '⛈️',
    'Light snow': '❄️',
    'Moderate snow': '❄️',
    'Heavy snow': '❄️',
    'Thunderstorm': '⛈️',
}


def get_weather_emoji(condition: str) -> str:
    """Получение эмодзи для погодного условия"""
    for key, emoji in WEATHER_EMOJI.items():
        if key.lower() in condition.lower():
            return emoji
    return '🌤️'


async def get_weather_data(city: str) -> dict:
    """Получение данных о погоде через WeatherAPI с обработкой ошибок"""
    try:
        url = f"http://api.weatherapi.com/v1/current.json?key={WEATHERAPI_KEY}&q={city}&lang=ru"
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Проверка HTTP ошибок
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к WeatherAPI: {e}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        return None


def format_weather_message(data: dict) -> str:
    """Форматирование данных о погоде в читаемое сообщение"""
    try:
        location = data['location']
        current = data['current']

        city = location['name']
        country = location['country']
        temp = current['temp_c']
        feels_like = current['feelslike_c']
        condition = current['condition']['text']
        wind = current['wind_kph']
        humidity = current['humidity']
        pressure = current['pressure_mb']

        weather_emoji = get_weather_emoji(condition)

        return (
            f"{weather_emoji} <b>Погода в {city}, {country}</b>\n\n"
            f"🌡️ <b>Температура:</b> {temp}°C (ощущается как {feels_like}°C)\n"
            f"☁️ <b>Состояние:</b> {condition}\n"
            f"💨 <b>Ветер:</b> {wind} км/ч\n"
            f"💧 <b>Влажность:</b> {humidity}%\n"
            f"📊 <b>Давление:</b> {pressure} мбар"
        )
    except KeyError as e:
        logger.error(f"Ошибка формата данных: {e}")
        return "⚠️ Ошибка обработки данных о погоде"
    except Exception as e:
        logger.error(f"Неизвестная ошибка форматирования: {e}")
        return "⚠️ Произошла непредвиденная ошибка"


# Обработчики команд бота
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🌤️ Привет! Я бот погоды, использующий WeatherAPI.\n"
        "Просто отправь мне название города, и я пришлю текущий прогноз погоды.\n\n"
        "Например: <i>Москва</i> или <i>London</i>",
        parse_mode="HTML"
    )


@dp.message(lambda message: message.text)
async def handle_weather_request(message: Message):
    city = message.text.strip()

    if len(city) > 50:
        await message.answer("❌ Название города слишком длинное. Максимум 50 символов.")
        return

    await bot.send_chat_action(message.chat.id, "typing")

    weather_data = await get_weather_data(city)

    if weather_data is None:
        await message.answer("🔌 Ошибка подключения к сервису погоды. Попробуйте позже.")
        return

    if 'error' in weather_data:
        error_msg = weather_data['error'].get('message', 'Неизвестная ошибка')
        await message.answer(f"⚠️ Ошибка: {error_msg}")
        return

    weather_message = format_weather_message(weather_data)
    await message.answer(weather_message, parse_mode="HTML")


# ===== ВЕБХУК-РЕЖИМ ДЛЯ PYTHONANYWHERE =====

# 5. Путь для вебхука с секретным ключом
WEBHOOK_PATH = f"/{WEBHOOK_SECRET}"


@app.route(WEBHOOK_PATH, methods=['POST'])
async def webhook():
    """Основной обработчик входящих обновлений от Telegram"""
    if request.method == "POST":
        # Получаем и проверяем секретный ключ
        if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
            logger.warning("Неверный секретный токен вебхука!")
            abort(403)

        # Обрабатываем обновление
        update = types.Update(**request.json)
        await dp.feed_update(bot, update)
        return "ok", 200
    return "Method Not Allowed", 405


@app.route('/')
def home():
    """Простая проверочная страница"""
    return "Weather Bot is running!", 200


# 6. Добавляем обработчик для автоматических обновлений из GitHub
@app.route('/update', methods=['POST'])
def update():
    """Автоматическое обновление кода из репозитория GitHub"""
    # Проверка секрета GitHub (рекомендуется добавить в настройках вебхука)
    if request.method == 'POST':
        repo = git.Repo('/home/yourusername/mybot')  # Укажите ваш путь
        origin = repo.remotes.origin
        origin.pull()

        # Перезагрузка приложения через touch WSGI-файла
        os.system('touch /var/www/yourusername_pythonanywhere_com_wsgi.py')

        return "Updated successfully", 200
    return "Method not allowed", 405


# 7. Обработчик ошибок Flask
@app.errorhandler(500)
def server_error(e):
    logger.exception("Серверная ошибка")
    return "Internal server error", 500


if __name__ == "__main__":
    # 8. Установка вебхука при запуске приложения
    logger.info("Устанавливаем вебхук...")

    # Формируем полный URL вебхука
    WEBHOOK_URL = f"https://yourusername.pythonanywhere.com{WEBHOOK_PATH}"

    # Удаляем предыдущий вебхук и устанавливаем новый
    bot.delete_webhook()
    bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET  # Защита от несанкционированного доступа
    )

    logger.info(f"Вебхук установлен на: {WEBHOOK_URL}")

    # 9. Запускаем Flask-приложение
    app.run(host='0.0.0.0', port=5000, debug=False)