import telegram
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ConversationHandler, CallbackContext
from database import (
    SessionLocal,
    Event,
    User,
    Participant,
    add_user_to_db,
    save_event,
    save_participant,
    is_user_participant,
    remove_participant,
    get_participants,
    block_participant,
    BlockedParticipant,
    add_date,
    get_user_dates,
    delete_user_date
)

from utils import main_menu_keyboard
from datetime import datetime, time
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP
import pytz
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Обработчик для кнопки "Главное меню"
async def main_menu(update: Update, context: CallbackContext):
    reply_markup = main_menu_keyboard()  # Используем клавиатуру из utils.py
    await update.callback_query.message.edit_text('Выберите действие:', reply_markup=reply_markup)


ASK_NAME = 1  # Состояние для запроса имени

# Стартовый обработчик
async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    if username:
        # Сохраняем и показываем главное меню
        add_user_to_db(user_id, username)
        reply_markup = main_menu_keyboard()
        await update.message.reply_text(
            "Добро пожаловать! Выберите действие из меню:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    else:
        # Запрашиваем имя
        await update.message.reply_text("У вас нет имени пользователя в Telegram. Пожалуйста, укажите своё имя:")
        context.user_data["user_id"] = user_id
        return ASK_NAME





# Обработчик создания события
async def handle_create_event_button(update: Update, context: CallbackContext):
    """Начало процесса создания события."""
    await update.callback_query.answer()
    await update.callback_query.message.edit_text("Введите название события:")
    return 1  # Переход к состоянию ввода названия события




# Обработчик ввода названия события
async def event_name(update: Update, context: CallbackContext):
    """Обработчик ввода названия события."""
    event_name = update.message.text.strip()
    context.user_data["event_name"] = event_name

    # Генерация календаря для выбора даты
    calendar, step = DetailedTelegramCalendar().build()
    await update.message.reply_text(
        f"Выберите {step}:",
        reply_markup=calendar
    )
    return 2  # Переход к выбору даты




# Обработчик ввода даты события
async def event_date(update: Update, context: CallbackContext):
    calendar, step = DetailedTelegramCalendar().build()
    await update.message.reply_text(
        f"Выберите {step}:",
        reply_markup=calendar
    )
    return 3



async def handle_calendar(update: Update, context: CallbackContext):
    query = update.callback_query

    try:
        # Проверяем корректность данных
        if not query.data:
            raise ValueError("Пустые данные для календаря.")

        # Обработка выбора даты
        result, key, step = DetailedTelegramCalendar().process(query.data)

        # Устанавливаем текущую дату в Московском часовом поясе
        moscow_tz = pytz.timezone("Europe/Moscow")
        now = datetime.now(moscow_tz).date()

        if not result and key:
            # Показываем следующий шаг календаря
            await query.message.edit_text(
                f"Выберите {LSTEP[step]}:",
                reply_markup=key
            )
            return 2  # Остаёмся в процессе выбора даты

        if result:
            selected_date = result

            # Проверяем, что дата не в прошлом
            if selected_date < now:
                # Генерируем календарь заново
                calendar, step = DetailedTelegramCalendar().build()
                await query.message.edit_text(
                    f"Нельзя выбрать дату в прошлом. Выберите {LSTEP[step]} ещё раз:",
                    reply_markup=calendar
                )
                return 2  # Повтор выбора даты

            # Сохраняем выбранную дату и переходим к следующему шагу
            context.user_data['event_date'] = selected_date
            await query.message.edit_text(
                f"Вы выбрали дату: {selected_date}. Теперь введите время события (например, 14:30):"
            )
            return 3  # Переход к следующему шагу (ввод времени)
    except (KeyError, ValueError) as e:
        print(f"Ошибка: {e}")
        # Генерируем календарь заново при ошибке
        calendar, step = DetailedTelegramCalendar().build()
        await query.message.reply_text(
            "Произошла ошибка при обработке календаря. Попробуйте снова.",
            reply_markup=calendar
        )
        return 2  # Возврат к выбору даты




async def event_time(update: Update, context: CallbackContext):
    event_time_text = update.message.text
    try:
        # Получаем дату события из контекста
        event_date = context.user_data['event_date']

        # Обрабатываем введённое время
        event_time = datetime.strptime(event_time_text, "%H:%M").time()

        # Комбинируем дату и время, добавляем московский часовой пояс
        moscow_tz = pytz.timezone("Europe/Moscow")
        event_datetime = datetime.combine(event_date, event_time)
        event_datetime = moscow_tz.localize(event_datetime)  # Сохраняем время как московское

        # Проверяем, что выбранное время позже текущего
        now = datetime.now(moscow_tz)
        if event_datetime <= now:
            await update.message.reply_text(
                "Нельзя выбрать время раньше текущего момента. Попробуйте снова."
            )
            return 3  # Остаёмся в состоянии ввода времени

        # Сохраняем событие в базу данных
        event_name = context.user_data['event_name']
        creator_id = update.message.from_user.id
        event_id = save_event(
            event_name=event_name,
            event_time=event_datetime,
            creator_id=creator_id,
            application=context.application  # Передача application
        )

        # Добавляем создателя как участника события
        save_participant(event_id, creator_id)

        # Подтверждение пользователю
        await update.message.reply_text(
            f"Событие '{event_name}' создано на {event_datetime.strftime('%d-%m-%Y %H:%M %Z')}!",
            reply_markup=main_menu_keyboard()
        )

        # Очищаем данные
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ.")
        return 3




# Отображение списка событий
async def list_events(update: Update, context: CallbackContext):
    """Обработчик для отображения общего списка событий."""
    query = update.callback_query

    # Получаем список событий
    with SessionLocal() as session:
        events = session.query(Event).all()

    if not events:
        # Отправляем уведомление, если событий нет
        await query.answer("На данный момент нет доступных событий!", show_alert=True)
        return

    # Создаём кнопки для каждого события
    buttons = [
        [InlineKeyboardButton(event.name, callback_data=f"event_details_{event.id}")]
        for event in events
    ]

    buttons.append([InlineKeyboardButton("Главное меню", callback_data="main_menu")])

    # Отправляем список событий
    reply_markup = InlineKeyboardMarkup(buttons)
    await query.message.edit_text("Доступные события:", reply_markup=reply_markup)


# Детали события и участники
async def event_details(update: Update, context: CallbackContext):
    query = update.callback_query

    try:
        # Ожидаем формат callback_data: event_details_<event_id>
        data = query.data.split('_')
        if len(data) != 3 or data[0] != "event" or data[1] != "details":
            raise ValueError("Некорректный формат callback_data.")

        event_id = int(data[2])

        # Получаем информацию о событии и участниках
        with SessionLocal() as session:
            event = session.query(Event).filter(Event.id == event_id).first()
            if not event:
                await query.answer("Событие не найдено.", show_alert=True)
                return

            participants = get_participants(event_id)
            creator = session.query(User).filter(User.id == event.creator_id).first().username

        # Формируем список участников
        participant_list = "\n".join(
            f"- @{user['username']}" if user["username"] else f"- Пользователь {user['id']}"
            for user in participants
        ) or "Нет участников"

        # Формируем сообщение
        message = (
            f"Событие: {event.name}\n"
            f"Дата: {event.time.strftime('%d-%m-%Y %H:%M')}\n"
            f"Организатор: {creator}\n\n"
            f"Участники:\n{participant_list}"
        )

        # Кнопки для управления
        keyboard = [
            [InlineKeyboardButton("Присоединиться", callback_data=f"join_{event_id}")],
            [InlineKeyboardButton("Покинуть", callback_data=f"leave_{event_id}")],
            [InlineKeyboardButton("Главное меню", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(message, reply_markup=reply_markup)

    except ValueError as e:
        print(f"Ошибка: {e}")
        await query.answer("Произошла ошибка при обработке данных события.")
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        await query.message.edit_text("Произошла ошибка. Попробуйте снова.")







# Присоединение к событию
async def join_event(update: Update, context: CallbackContext):
    """Обработчик для присоединения пользователя к событию."""
    query = update.callback_query
    event_id = int(query.data.split('_')[1])
    user_id = query.from_user.id

    with SessionLocal() as session:
        # Проверяем, заблокирован ли пользователь
        is_blocked = session.query(BlockedParticipant).filter_by(event_id=event_id, user_id=user_id).first()
        if is_blocked:
            await query.answer("Вы заблокированы и не можете присоединиться к этому событию.", show_alert=True)
            return

    # Проверяем, не является ли пользователь уже участником
    if is_user_participant(event_id, user_id):
        await query.answer("Вы уже участвуете в этом событии!")
        return

    # Добавляем пользователя как участника
    save_participant(event_id, user_id)
    await query.answer("Вы успешно присоединились к событию!")
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
    """Обработчик для отображения списка событий пользователя."""
    query = update.callback_query
    user_id = query.from_user.id

    # Получаем список событий пользователя
    with SessionLocal() as session:
        events = session.query(Event).filter(Event.creator_id == user_id).all()

    if not events:
        # Отправляем уведомление, если событий нет
        await query.answer("У вас нет созданных событий!", show_alert=True)
        return

    # Создаём кнопки для каждого события
    buttons = [
        [InlineKeyboardButton(event.name, callback_data=f"my_event_{event.id}")]
        for event in events
    ]

    buttons.append([InlineKeyboardButton("Главное меню", callback_data="main_menu")])

    # Отправляем список событий
    reply_markup = InlineKeyboardMarkup(buttons)
    await query.message.edit_text("Ваши события:", reply_markup=reply_markup)





# Обработчик для показа деталей события, созданного пользователем, с кнопкой "Удалить событие"
async def my_event_details(update: Update, context: CallbackContext):
    """Обработчик для отображения деталей события."""
    query = update.callback_query

    try:
        # Парсим ID события из query.data
        data = query.data.split('_')
        if len(data) != 3 or data[0] != "my" or data[1] != "event":
            raise ValueError("Некорректный формат данных кнопки.")

        event_id = int(data[2])

        # Получаем информацию о событии
        with SessionLocal() as session:
            event = session.query(Event).filter(Event.id == event_id).first()
            if not event:
                await query.message.edit_text("Событие не найдено.")
                return

            participants = get_participants(event_id)

        # Формируем список участников с кнопками удаления
        participant_buttons = [
            [
                InlineKeyboardButton(
                    f"Удалить @{participant['username']}" if participant["username"] else f"Удалить ID {participant['id']}",
                    callback_data=f"remove_participant_{event_id}_{participant['id']}"
                )
            ]
            for participant in participants
        ]

        # Добавляем кнопки для удаления события и возврата
        participant_buttons.append([InlineKeyboardButton("Удалить событие", callback_data=f"delete_event_{event_id}")])
        participant_buttons.append([InlineKeyboardButton("Назад", callback_data="my_events")])

        # Формируем текст сообщения
        message = (
            f"Название: {event.name}\n"
            f"Дата: {event.time.strftime('%d-%m-%Y %H:%M')}\n\n"
            f"Участники:\n" +
            "\n".join(f"- @{p['username']}" if p['username'] else f"- Пользователь {p['id']}" for p in participants)
        )

        # Отправляем сообщение с кнопками
        reply_markup = InlineKeyboardMarkup(participant_buttons)
        await query.message.edit_text(message, reply_markup=reply_markup)

    except ValueError as e:
        print(f"Ошибка: {e}")
        await query.answer("Произошла ошибка при обработке данных события.")
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        await query.message.edit_text("Произошла ошибка. Попробуйте снова.")









# Удаление события с уведомлением участников, включая название события
async def delete_event(update: Update, context: CallbackContext):
    query = update.callback_query
    event_id = int(query.data.split('_')[2])

    with SessionLocal() as session:
        # Получаем событие для имени
        event = session.query(Event).filter(Event.id == event_id).first()
        if not event:
            await query.message.edit_text("Событие не найдено.")
            return

        event_name = event.name

        # Удаляем участников
        session.query(Participant).filter(Participant.event_id == event_id).delete()

        # Удаляем записи о блокировке
        session.query(BlockedParticipant).filter(BlockedParticipant.event_id == event_id).delete()

        # Удаляем само событие
        session.delete(event)
        session.commit()

    # Уведомляем участников об удалении события
    participants = get_participants(event_id)
    for user in participants:
        try:
            await context.bot.send_message(
                chat_id=user["id"],
                text=f"Событие '{event_name}' было отменено организатором."
            )
        except telegram.error.BadRequest as e:
            print(f"Ошибка отправки сообщения пользователю {user['id']}: {e}")

    # Уведомляем создателя об успешном удалении
    await query.message.edit_text("Событие успешно удалено.", reply_markup=main_menu_keyboard())


async def remove_participant_handler(update: Update, context: CallbackContext):
    """Обработчик для удаления участника события."""
    query = update.callback_query
    data = query.data.split('_')
    event_id = int(data[2])
    user_id = int(data[3])

    # Удаляем участника из события и блокируем его
    remove_participant(event_id, user_id)
    block_participant(event_id, user_id)

    # Уведомляем участника о том, что он удалён
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Вы были удалены из события. У вас больше нет возможности присоединиться."
        )
    except telegram.error.BadRequest as e:
        print(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

    # Обновляем список участников
    with SessionLocal() as session:
        event = session.query(Event).filter(Event.id == event_id).first()
        if not event:
            await query.message.edit_text("Событие не найдено.")
            return

        participants = get_participants(event_id)

    # Формируем обновлённые кнопки участников
    participant_buttons = [
        [
            InlineKeyboardButton(
                f"Удалить @{participant['username']}" if participant["username"] else f"Удалить ID {participant['id']}",
                callback_data=f"remove_participant_{event_id}_{participant['id']}"
            )
        ]
        for participant in participants
    ]

    # Добавляем кнопки для удаления события и возврата
    participant_buttons.append([InlineKeyboardButton("Удалить событие", callback_data=f"delete_event_{event_id}")])
    participant_buttons.append([InlineKeyboardButton("Назад", callback_data="my_events")])

    # Формируем текст сообщения
    message = (
        f"Название: {event.name}\n"
        f"Дата: {event.time.strftime('%d-%m-%Y %H:%M')}\n\n"
        f"Участники:\n" +
        "\n".join(f"- @{p['username']}" if p['username'] else f"- Пользователь {p['id']}" for p in participants)
    )

    # Обновляем сообщение с обновлёнными кнопками
    reply_markup = InlineKeyboardMarkup(participant_buttons)
    await query.message.edit_text(message, reply_markup=reply_markup)

async def ask_name(update: Update, context: CallbackContext):
    """Обработчик для сохранения имени пользователя."""
    user_id = context.user_data.get("user_id")
    name = update.message.text.strip()

    # Сохраняем имя в базу данных
    add_user_to_db(user_id, name)

    # Показ главного меню
    reply_markup = main_menu_keyboard()  # Используем клавиатуру из utils.py
    await update.message.reply_text(
        "Спасибо! Вы успешно зарегистрированы. Выберите действие из меню:",
        reply_markup=reply_markup
    )

    return ConversationHandler.END  # Завершаем обработку состояния


async def my_calendar(update: Update, context: CallbackContext):
    """Главное меню календаря."""
    user_id = update.callback_query.from_user.id
    dates = get_user_dates(user_id)

    # Формируем кнопки для дат
    buttons = [[InlineKeyboardButton(date.strftime("%d-%m-%Y"), callback_data=f"manage_date_{date}")] for date in dates]
    buttons.append([InlineKeyboardButton("Добавить дату", callback_data="add_date")])
    buttons.append([InlineKeyboardButton("Назад", callback_data="main_menu")])

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.callback_query.message.edit_text("Ваш календарь:", reply_markup=reply_markup)

async def add_date_handler(update: Update, context: CallbackContext):
    """Обработчик добавления даты."""
    logger.info("Generating calendar for adding a date...")
    calendar, step = DetailedTelegramCalendar().build()
    logger.info(f"Calendar generated for step: {step}")
    await update.callback_query.message.edit_text(
        f"Выберите {LSTEP[step]}:",
        reply_markup=calendar
    )


async def handle_calendar_date(update: Update, context: CallbackContext):
    """Обработка выбора даты."""
    query = update.callback_query
    logger.info(f"Callback data received: {query.data}")

    try:
        # Проверяем, является ли callback данными для удаления даты
        if query.data.startswith("delete_date_"):
            logger.info("Data is for deleting a date.")
            date = query.data.split("_", 2)[2]  # Получаем дату из delete_date_<date>
            await delete_date(update, context, date)
            return

        # Проверяем, является ли callback данными для управления датой
        if query.data.startswith("manage_date_"):
            logger.info("Data is for managing a date.")
            date = query.data.split("_", 2)[2]
            await manage_date(update, context, date)
            return

        # Обработка данных от календаря
        logger.info("Processing calendar data...")
        result, key, step = DetailedTelegramCalendar().process(query.data)
        logger.info(f"Process result: {result}, Next step: {step}")

        if not result and key:
            # Показываем следующий шаг выбора
            logger.info(f"Generated keyboard for step '{step}': {key}")
            await query.message.edit_text(
                f"Выберите {LSTEP[step]}:",
                reply_markup=key
            )
            return  # Остаемся в процессе выбора

        if result:
            # Если дата выбрана, сохраняем её
            user_id = query.from_user.id
            if add_date(user_id, result):
                logger.info(f"Дата {result.strftime('%d-%m-%Y')} успешно добавлена!")
                await query.message.edit_text(f"Дата {result.strftime('%d-%m-%Y')} успешно добавлена!")
            else:
                logger.info(f"Дата {result.strftime('%d-%m-%Y')} уже существует!")
                await query.message.edit_text(f"Дата {result.strftime('%d-%m-%Y')} уже существует.")
            await my_calendar(update, context)
    except Exception as e:
        # Логируем ошибки
        logger.error(f"Ошибка обработки календаря: {e}")
        await query.message.edit_text("Произошла ошибка при выборе даты. Попробуйте снова.")







async def manage_date(update: Update, context: CallbackContext, date):
    """Меню управления выбранной датой."""
    buttons = [
        [InlineKeyboardButton("Удалить дату", callback_data=f"delete_date_{date}")],
        [InlineKeyboardButton("Назад", callback_data="my_calendar")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.callback_query.message.edit_text(f"Управление датой {date}:", reply_markup=reply_markup)



async def delete_date(update: Update, context: CallbackContext, date):
    """Удаление выбранной даты."""
    query = update.callback_query
    user_id = query.from_user.id

    try:
        # Удаление даты из базы данных
        logger.info(f"Attempting to delete date: {date}")
        success = delete_user_date(user_id, date)
        if success:
            await query.message.edit_text(f"Дата {date} удалена.")
        else:
            await query.message.edit_text(f"Дата {date} не найдена или уже удалена.")
        await my_calendar(update, context)
    except Exception as e:
        logger.error(f"Ошибка удаления даты: {e}")
        await query.message.edit_text("Произошла ошибка при удалении даты. Попробуйте снова.")













