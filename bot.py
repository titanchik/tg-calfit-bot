import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from datetime import datetime
import requests

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(
    WEIGHT, HEIGHT, AGE, GENDER, ACTIVITY_LEVEL, CITY,
    LOG_WATER, LOG_FOOD, LOG_WORKOUT,
    LOG_FOOD_AMOUNT, LOG_WORKOUT_TYPE, LOG_WORKOUT_TIME
) = range(12)

# Хранение данных пользователей
users = {}


# Класс для работы с API OpenWeatherMap
class WeatherAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"

    def get_temperature(self, city):
        try:
            params = {
                'q': city,
                'appid': self.api_key,
                'units': 'metric'
            }
            response = requests.get(self.base_url, params=params)
            data = response.json()
            return data['main']['temp']
        except Exception as e:
            logger.error(f"Error getting weather: {e}")
            return None


# Инициализация API
weather_api = WeatherAPI(os.getenv('OWM_API_KEY', '01f474020efe5047728b89b3be2e4cde'))


# Расчет норм
def calculate_norms(user_data):
    # Расчет нормы воды
    water_base = user_data['weight'] * 30
    water_activity = 0  # Будем учитывать активность через тренировки

    temp = weather_api.get_temperature(user_data['city'])
    water_temp = 500 if temp and temp > 25 else 0

    water_total = water_base + water_activity + water_temp

    # Расчет нормы калорий (формула Миффлина-Сан Жеора)
    if user_data['gender'] == 'male':
        calorie_base = 10 * user_data['weight'] + 6.25 * user_data['height'] - 5 * user_data['age'] + 5
    else:
        calorie_base = 10 * user_data['weight'] + 6.25 * user_data['height'] - 5 * user_data['age'] - 161

    activity_multiplier = {
        'низкий': 1.2,
        'средний': 1.55,
        'высокий': 1.9
    }

    calorie_total = calorie_base * activity_multiplier.get(user_data['activity_level'], 1.2)

    return {
        'water': water_total,
        'calories': calorie_total
    }


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    users[user_id] = {
        'logged_water': 0,
        'logged_calories': 0,
        'burned_calories': 0,
        'food_log': [],
        'workout_log': []
    }

    await update.message.reply_text(
        "Привет! Я помогу тебе следить за водным балансом и калориями.\n"
        "Давай настроим твой профиль. Введи свой вес в кг:",
        reply_markup=ReplyKeyboardRemove()
    )
    return WEIGHT


# Обработка веса
async def weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    try:
        # Очищаем ввод от единиц измерения и лишних символов
        weight_input = update.message.text.strip().lower()
        weight_input = weight_input.replace('кг', '').replace('kg', '').replace(',', '.').strip()

        # Удаляем слэши, если они есть
        if weight_input.startswith('/'):
            weight_input = weight_input[1:]

        weight = float(weight_input)
        if weight <= 0 or weight > 300:
            raise ValueError

        users[user_id]['weight'] = weight
        await update.message.reply_text("Отлично! Теперь введи свой рост в см:")
        return HEIGHT
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректный вес (число от 1 до 300, можно с 'кг'):")
        return WEIGHT


# Обработка роста
async def height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    try:
        # Очищаем ввод от единиц измерения и лишних символов
        height_input = update.message.text.strip().lower()
        height_input = height_input.replace('см', '').replace('cm', '').replace(',', '.').strip()

        # Удаляем слэши, если они есть
        if height_input.startswith('/'):
            height_input = height_input[1:]

        height = float(height_input)
        if height <= 0 or height > 250:
            raise ValueError

        users[user_id]['height'] = height
        await update.message.reply_text("Хорошо! Теперь введи свой возраст:")
        return AGE
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректный рост (число от 1 до 250, можно с 'см'):")
        return HEIGHT


# Обработка возраста
async def age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    try:
        age = int(update.message.text)
        if age <= 0 or age > 120:
            raise ValueError
        users[user_id]['age'] = age

        reply_keyboard = [['Мужской', 'Женский']]
        await update.message.reply_text(
            "Отлично! Теперь укажи свой пол:",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        return GENDER
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректный возраст (число от 1 до 120):")
        return AGE


# Обработка пола
async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    gender = update.message.text.lower()
    if gender not in ['мужской', 'женский']:
        await update.message.reply_text("Пожалуйста, выбери пол из предложенных вариантов.")
        return GENDER

    users[user_id]['gender'] = 'male' if gender == 'мужской' else 'female'

    reply_keyboard = [['Низкий', 'Средний', 'Высокий']]
    await update.message.reply_text(
        "Какой у тебя уровень физической активности?\n"
        "Низкий - сидячий образ жизни\n"
        "Средний - умеренные тренировки 3-5 раз в неделю\n"
        "Высокий - интенсивные тренировки 6-7 раз в неделю",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return ACTIVITY_LEVEL


# Обработка уровня активности
async def activity_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    activity_level = update.message.text.lower()
    if activity_level not in ['низкий', 'средний', 'высокий']:
        await update.message.reply_text("Пожалуйста, выбери уровень активности из предложенных вариантов.")
        return ACTIVITY_LEVEL

    users[user_id]['activity_level'] = activity_level

    await update.message.reply_text(
        "В каком городе ты находишься? (Это нужно для учета температуры при расчете нормы воды)",
        reply_markup=ReplyKeyboardRemove()
    )
    return CITY


# Завершение настройки профиля
async def city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    city = update.message.text
    users[user_id]['city'] = city

    # Расчет норм
    norms = calculate_norms(users[user_id])
    users[user_id]['water_goal'] = norms['water']
    users[user_id]['calorie_goal'] = norms['calories']

    await update.message.reply_text(
        f"Профиль настроен!\n\n"
        f"Твои дневные нормы:\n"
        f"💧 Вода: {norms['water']} мл\n"
        f"🍏 Калории: {norms['calories']:.0f} ккал\n\n"
        f"Используй команды:\n"
        f"/log_water - добавить выпитую воду\n"
        f"/log_food - добавить прием пищи\n"
        f"/log_workout - добавить тренировку\n"
        f"/check_progress - проверить прогресс\n"
        f"/set_profile - изменить профиль",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# Логирование воды
async def log_water(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Сколько воды ты выпил(а) в мл?")
    return LOG_WATER


async def save_water(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    try:
        amount = int(update.message.text)
        if amount <= 0:
            raise ValueError

        users[user_id]['logged_water'] += amount
        remaining = max(0, users[user_id]['water_goal'] - users[user_id]['logged_water'])

        await update.message.reply_text(
            f"Записано: {amount} мл воды.\n"
            f"Осталось выпить: {remaining} мл"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректное количество воды (положительное число):")
        return LOG_WATER


# Логирование еды
async def log_food(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Что ты съел(а)? Укажи название продукта:")
    return LOG_FOOD


async def save_food(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    food_name = update.message.text

    # Здесь можно добавить интеграцию с API питания
    # Для примера - фиксированные значения
    food_db = {
        'яблоко': 52,
        'банан': 89,
        'куриная грудка': 165,
        'рис': 130,
        'гречка': 110,
        'овсянка': 68,
        'яйцо': 70,
        'творог': 120,
        'молоко': 42,
        'кофе': 0
    }

    calories = food_db.get(food_name.lower(), 100)  # По умолчанию 100 ккал

    users[user_id]['food_log'].append({
        'name': food_name,
        'calories': calories,
        'time': datetime.now().strftime("%H:%M")
    })

    await update.message.reply_text(
        f"Сколько грамм {food_name} ты съел(а)? (Примерно)")
    return LOG_FOOD_AMOUNT


async def save_food_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError

        last_food = users[user_id]['food_log'][-1]
        calories = last_food['calories'] * amount / 100
        users[user_id]['logged_calories'] += calories

        await update.message.reply_text(
            f"Записано: {amount}г {last_food['name']} - {calories:.1f} ккал\n"
            f"Всего сегодня: {users[user_id]['logged_calories']:.1f} ккал"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректное количество (положительное число):")
        return LOG_FOOD_AMOUNT


# Логирование тренировок
async def log_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = [['Бег', 'Ходьба'], ['Велосипед', 'Плавание'], ['Силовая', 'Йога']]
    await update.message.reply_text(
        "Какой тип тренировки?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return LOG_WORKOUT_TYPE


async def log_workout_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    workout_type = update.message.text
    context.user_data['workout_type'] = workout_type

    await update.message.reply_text(
        f"Сколько минут длилась тренировка {workout_type.lower()}?",
        reply_markup=ReplyKeyboardRemove()
    )
    return LOG_WORKOUT_TIME


async def save_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    try:
        minutes = int(update.message.text)
        if minutes <= 0:
            raise ValueError

        workout_type = context.user_data['workout_type']

        # Расход калорий для разных типов тренировок (ккал/мин)
        workout_calories = {
            'Бег': 10,
            'Ходьба': 5,
            'Велосипед': 8,
            'Плавание': 7,
            'Силовая': 6,
            'Йога': 3
        }

        calories_burned = minutes * workout_calories.get(workout_type, 5)
        users[user_id]['burned_calories'] += calories_burned

        # Дополнительная вода для тренировки
        water_extra = (minutes // 30) * 200
        users[user_id]['water_goal'] += water_extra

        users[user_id]['workout_log'].append({
            'type': workout_type,
            'minutes': minutes,
            'calories': calories_burned,
            'time': datetime.now().strftime("%H:%M")
        })

        await update.message.reply_text(
            f"Записано: {workout_type} {minutes} мин - сожжено {calories_burned} ккал\n"
            f"Дополнительно выпей {water_extra} мл воды"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректное количество минут (положительное число):")
        return LOG_WORKOUT_TIME


# Проверка прогресса
async def check_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in users:
        await update.message.reply_text("Сначала настрой профиль с помощью /set_profile")
        return

    user = users[user_id]
    water_percent = min(100, user['logged_water'] / user['water_goal'] * 100)
    calories_percent = min(100, user['logged_calories'] / user['calorie_goal'] * 100)

    # Создаем простые графики прогресса
    def create_progress_bar(percent):
        filled = '▓' * int(percent / 10)
        empty = '░' * (10 - len(filled))
        return f"{filled}{empty} {percent:.1f}%"

    water_bar = create_progress_bar(water_percent)
    calories_bar = create_progress_bar(calories_percent)

    message = (
        f"📊 Твой прогресс за сегодня:\n\n"
        f"💧 Вода: {user['logged_water']}/{user['water_goal']} мл\n"
        f"{water_bar}\n\n"
        f"🍏 Калории: {user['logged_calories']:.1f}/{user['calorie_goal']} ккал\n"
        f"{calories_bar}\n"
        f"🔥 Сожжено: {user['burned_calories']} ккал\n\n"
        f"Баланс: {user['logged_calories'] - user['burned_calories']:.1f} ккал"
    )

    await update.message.reply_text(message)


# Отмена действий
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Действие отменено",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# Обработка ошибок
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} caused error {context.error}")
    await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуй еще раз.")


def main() -> None:
    """Запуск бота."""
    # Создаем Application и передаем ему токен бота
    application = Application.builder().token(
        os.getenv('TELEGRAM_TOKEN', '7631239367:AAGHmD8-61R3BPWyo2MU7ZABPxzXgSXuYvQ')
    ).build()

    # Обработчик настройки профиля
    profile_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('set_profile', start)],
        states={
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender)],
            ACTIVITY_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, activity_level)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Обработчик логирования воды
    water_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('log_water', log_water)],
        states={
            LOG_WATER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_water)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Обработчик логирования еды
    food_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('log_food', log_food)],
        states={
            LOG_FOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_food)],
            LOG_FOOD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_food_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Обработчик логирования тренировок
    workout_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('log_workout', log_workout)],
        states={
            LOG_WORKOUT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_workout_time)],
            LOG_WORKOUT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_workout)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Регистрируем обработчики
    application.add_handler(profile_conv_handler)
    application.add_handler(water_conv_handler)
    application.add_handler(food_conv_handler)
    application.add_handler(workout_conv_handler)
    application.add_handler(CommandHandler('check_progress', check_progress))
    application.add_handler(CommandHandler('start', start))

    # Обработчик ошибок
    application.add_error_handler(error)

    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()


if __name__ == '__main__':
    main()