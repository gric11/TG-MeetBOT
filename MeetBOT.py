import os
from dotenv import load_dotenv
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, \
    filters, CallbackContext
from datetime import datetime, timedelta
import pytz

# Загрузка переменных окружения из .env файла
load_dotenv()

# Получение токена из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Создаем или подключаемся к базе данных
def create_db():
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        time TEXT,
                        creator_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS participants (
                        event_id INTEGER,
                        user_id INTEGER,
                        FOREIGN KEY (event_id) REFERENCES events (id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        username TEXT)''')  # Для хранения пользователей и их имен

    conn.commit()
    conn.close()


# Функция для добавления пользователя в таблицу users, если его еще нет
def add_user_to_db(user_id, username):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    # Проверка, существует ли уже пользователь
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    if cursor.fetchone() is None:
        # Если пользователя нет, добавляем его в таблицу users
        cursor.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()

    conn.close()


# Сохранение события в базу данных
def save_event(event_name, event_time, creator_id, application):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    # Сохранение события в базе данных
    cursor.execute("INSERT INTO events (name, time, creator_id) VALUES (?, ?, ?)",
                   (event_name, event_time, creator_id))
    conn.commit()
    event_id = cursor.lastrowid  # Получаем ID нового события
    conn.close()

    # Преобразуем строку времени события в datetime и устанавливаем московское время
    moscow_tz = pytz.timezone('Europe/Moscow')
    event_datetime = datetime.strptime(event_time, "%d-%m-%Y %H:%M")
    event_datetime = moscow_tz.localize(event_datetime)

    # Запланируем напоминание за 1 час до события
    reminder_time = event_datetime - timedelta(hours=1)
    if reminder_time > datetime.now(moscow_tz):
        application.job_queue.run_once(
            send_reminder,
            when=reminder_time,
            data={"event_name": event_name, "chat_id": creator_id}
        )

    # Запланируем удаление и уведомление всех участников о начале события
    application.job_queue.run_once(
        start_event,
        when=event_datetime,
        data={"event_id": event_id, "event_name": event_name}
    )

    return event_id



# Сохранение участника события
def save_participant(event_id, user_id):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("INSERT INTO participants (event_id, user_id) VALUES (?, ?)",
                   (event_id, user_id))
    conn.commit()
    conn.close()


# Проверка, является ли пользователь участником события
def is_user_participant(event_id, user_id):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM participants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
    is_participant = cursor.fetchone() is not None
    conn.close()
    return is_participant


# Удаление участника из события
def remove_participant(event_id, user_id):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM participants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
    conn.commit()
    conn.close()


# Получение списка всех событий
def get_events():
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events")
    events = cursor.fetchall()
    conn.close()
    return events


# Получение событий, созданных пользователем
def get_user_events(user_id):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("SELECT e.id, e.name, e.time FROM events e WHERE e.creator_id = ?", (user_id,))
    user_events = cursor.fetchall()
    conn.close()
    return user_events


# Получение пользователей, участвующих в событии
def get_participants(event_id):
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("SELECT u.username FROM participants p JOIN users u ON p.user_id = u.id WHERE p.event_id = ?", (event_id,))
    participants = cursor.fetchall()
    conn.close()
    return participants


# Создание клавиатуры для меню
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("Создать событие", callback_data='create_event')],
        [InlineKeyboardButton("Список событий", callback_data='list_events')],
        [InlineKeyboardButton("Мои события", callback_data='my_events')],
    ]
    return InlineKeyboardMarkup(keyboard)


# Обработчик для кнопки "Главное меню"
async def main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Создать событие", callback_data='create_event')],
        [InlineKeyboardButton("Список событий", callback_data='list_events')],
        [InlineKeyboardButton("Мои события", callback_data='my_events')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.edit_text('Выберите действие:', reply_markup=reply_markup)


# Стартовый обработчик
async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    # Добавляем пользователя в таблицу users, если его там нет
    add_user_to_db(user_id, username)

    keyboard = [
        [InlineKeyboardButton("Создать событие", callback_data='create_event')],
        [InlineKeyboardButton("Список событий", callback_data='list_events')],
        [InlineKeyboardButton("Мои события", callback_data='my_events')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Добро пожаловать! Выберите действие:', reply_markup=reply_markup)


# Обработчик создания события
async def handle_create_event_button(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.message.edit_text("Введите название события:")
    return 1


# Обработчик ввода названия события
async def event_name(update: Update, context: CallbackContext):
    event_name = update.message.text
    context.user_data['event_name'] = event_name
    await update.message.reply_text('Введите дату события (например, 21-12-2024 14:30):')
    return 2


# Обработчик ввода даты события
async def event_date(update: Update, context: CallbackContext):
    event_date = update.message.text
    try:
        # Attempt to parse the date in the new DD-MM-YYYY HH:MM format
        event_time = datetime.strptime(event_date, "%d-%m-%Y %H:%M")
        moscow_tz = pytz.timezone('Europe/Moscow')
        event_time = moscow_tz.localize(event_time)

        event_name = context.user_data['event_name']
        creator_id = update.message.from_user.id

        # Save the event with the correct date format
        event_id = save_event(event_name, event_time.strftime('%d-%m-%Y %H:%M'), creator_id, context.application)

        # Add the creator to the participant list
        save_participant(event_id, creator_id)

        await update.message.reply_text(
            f"Событие '{event_name}' создано на {event_time.strftime('%d-%m-%Y %H:%M')} по московскому времени! "
            f"Вы добавлены в список участников.",
            reply_markup=main_menu_keyboard()
        )

        # Clear the context data
        context.user_data.clear()
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            'Неверный формат даты. Пожалуйста, введите дату в формате DD-MM-YYYY HH:MM.',
            reply_markup=main_menu_keyboard()
        )
        return 2



# Отображение списка событий
async def list_events(update: Update, context: CallbackContext):
    query = update.callback_query
    events = get_events()

    if not events:
        await query.answer('События не созданы.')
        return

    keyboard = []
    for event in events:
        keyboard.append([InlineKeyboardButton(event[1], callback_data=f'event_{event[0]}')])

    keyboard.append([InlineKeyboardButton("Главное меню", callback_data='main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text('Выберите событие для участия:', reply_markup=reply_markup)


# Детали события и участники
async def event_details(update: Update, context: CallbackContext):
    query = update.callback_query
    event_id = int(query.data.split('_')[1])
    user_id = query.from_user.id

    # Получаем данные о событии
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event = cursor.fetchone()

    cursor.execute("SELECT u.username FROM participants p JOIN users u ON p.user_id = u.id WHERE p.event_id = ?", (event_id,))
    participants = cursor.fetchall()

    cursor.execute("SELECT username FROM users WHERE id = ?", (event[3],))
    creator = cursor.fetchone()[0]

    conn.close()

    # Формируем сообщение
    message = f"Событие: {event[1]}\nДата: {event[2]}\nОрганизатор: {creator}\n\nУчастники:\n"
    for participant in participants:
        message += f"- {participant[0]}\n"

    # Кнопки для присоединения/покидания
    keyboard = []

    if is_user_participant(event_id, user_id):
        keyboard.append([InlineKeyboardButton("Покинуть событие", callback_data=f'leave_{event_id}')])
    else:
        keyboard.append([InlineKeyboardButton("Присоединиться к событию", callback_data=f'join_{event_id}')])

    keyboard.append([InlineKeyboardButton("Главное меню", callback_data='main_menu')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(message, reply_markup=reply_markup)


# Присоединение к событию
async def join_event(update: Update, context: CallbackContext):
    event_id = int(update.callback_query.data.split('_')[1])
    user_id = update.callback_query.from_user.id

    if is_user_participant(event_id, user_id):
        await update.callback_query.answer('Вы уже участвуете в этом событии!')
    else:
        save_participant(event_id, user_id)
        await update.callback_query.answer('Вы присоединились к событию!')

    await event_details(update, context)


# Покидание события
async def leave_event(update: Update, context: CallbackContext):
    event_id = int(update.callback_query.data.split('_')[1])
    user_id = update.callback_query.from_user.id

    if not is_user_participant(event_id, user_id):
        await update.callback_query.answer('Вы не участвуете в этом событии!')
    else:
        remove_participant(event_id, user_id)
        await update.callback_query.answer('Вы покинули событие!')

    await event_details(update, context)


async def my_events(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    user_events = get_user_events(user_id)

    if not user_events:
        await query.answer("У вас нет созданных событий.")
        return

    # Клавиатура с событиями, созданными пользователем
    keyboard = []
    for event in user_events:
        keyboard.append([InlineKeyboardButton(event[1], callback_data=f'my_event_{event[0]}')])

    keyboard.append([InlineKeyboardButton("Главное меню", callback_data='main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("Ваши события:", reply_markup=reply_markup)


# Обработчик для показа деталей события, созданного пользователем, с кнопкой "Удалить событие"
async def my_event_details(update: Update, context: CallbackContext):
    query = update.callback_query
    event_id = int(query.data.split('_')[2])

    # Получаем информацию о событии и участниках
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event = cursor.fetchone()

    cursor.execute("SELECT u.username FROM participants p JOIN users u ON p.user_id = u.id WHERE p.event_id = ?", (event_id,))
    participants = cursor.fetchall()

    cursor.execute("SELECT username FROM users WHERE id = ?", (event[3],))
    creator = cursor.fetchone()[0]

    conn.close()

    # Формируем сообщение
    message = f"Событие: {event[1]}\nДата: {event[2]}\nОрганизатор: {creator}\n\nУчастники:\n"
    for participant in participants:
        message += f"- {participant[0]}\n"

    # Кнопки для удаления события и возврата в главное меню
    keyboard = [
        [InlineKeyboardButton("Удалить событие", callback_data=f'delete_event_{event_id}')],
        [InlineKeyboardButton("Главное меню", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(message, reply_markup=reply_markup)


# Удаление события с уведомлением участников, включая название события
async def delete_event(update: Update, context: CallbackContext):
    query = update.callback_query
    event_id = int(query.data.split('_')[2])

    # Получаем название события и участников перед удалением
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    # Получаем название события
    cursor.execute("SELECT name FROM events WHERE id = ?", (event_id,))
    event_name = cursor.fetchone()[0]

    # Получаем участников события
    cursor.execute("SELECT user_id FROM participants WHERE event_id = ?", (event_id,))
    participants = cursor.fetchall()

    # Удаляем событие и его участников
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    cursor.execute("DELETE FROM participants WHERE event_id = ?", (event_id,))
    conn.commit()
    conn.close()

    # Уведомляем участников об отмене события с указанием его названия
    for participant in participants:
        user_id = participant[0]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Организатор отменил событие '{event_name}'."
        )

    # Уведомляем организатора об успешном удалении события
    await query.message.edit_text("Событие успешно удалено.", reply_markup=main_menu_keyboard())

# Функция для отправки напоминания
async def send_reminder(context: CallbackContext):
    job_data = context.job.data
    event_name = job_data["event_name"]
    chat_id = job_data["chat_id"]

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Напоминание: Событие '{event_name}' начнётся через час!"
    )

async def start_event(context: CallbackContext):
    job_data = context.job.data
    event_id = job_data["event_id"]
    event_name = job_data["event_name"]

    # Подключаемся к базе данных
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()

    # Получаем список участников события
    cursor.execute("SELECT user_id FROM participants WHERE event_id = ?", (event_id,))
    participants = cursor.fetchall()

    # Отправляем уведомления участникам
    for participant in participants:
        user_id = participant[0]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Событие '{event_name}' началось!"
        )

    # Удаляем событие и его участников из базы данных
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    cursor.execute("DELETE FROM participants WHERE event_id = ?", (event_id,))
    conn.commit()
    conn.close()

# Добавляем новый обработчик для кнопки "Мои события" и функции для обработки событий

def main():
    create_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))

    conversation_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_create_event_button, pattern='create_event')],
        states={
            1: [MessageHandler(filters.TEXT, event_name)],
            2: [MessageHandler(filters.TEXT, event_date)],
        },
        fallbacks=[],
    )
    application.add_handler(conversation_handler)

    application.add_handler(CallbackQueryHandler(main_menu, pattern='main_menu'))
    application.add_handler(CallbackQueryHandler(list_events, pattern='list_events'))
    application.add_handler(CallbackQueryHandler(my_events, pattern='my_events'))
    application.add_handler(CallbackQueryHandler(event_details, pattern='event_'))
    application.add_handler(CallbackQueryHandler(my_event_details, pattern='my_event_'))
    application.add_handler(CallbackQueryHandler(join_event, pattern='join_'))
    application.add_handler(CallbackQueryHandler(leave_event, pattern='leave_'))
    application.add_handler(CallbackQueryHandler(delete_event, pattern='delete_event_'))

    application.run_polling()


if __name__ == '__main__':
    main()
























