import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from database import create_db
from handlers import (
    start, handle_create_event_button, event_name, main_menu, list_events,
    my_events, event_details, my_event_details, join_event, leave_event,
    delete_event, handle_calendar, event_time, remove_participant_handler, ask_name,
    my_calendar, add_date_handler, handle_calendar_date, manage_date, delete_date
)

# Константы для состояний
ASK_NAME = 1

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

def main():
    # Создание базы данных, если её ещё нет
    create_db()

    # Инициализация приложения Telegram
    application = Application.builder().token(BOT_TOKEN).build()

    user_registration_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        },
        fallbacks=[]
    )

    create_event_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_create_event_button, pattern="create_event")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_name)],
            2: [CallbackQueryHandler(handle_calendar)],
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_time)],
        },
        fallbacks=[]
    )

    # Регистрация обработчиков
    application.add_handler(user_registration_handler)
    application.add_handler(create_event_handler)
    application.add_handler(CallbackQueryHandler(main_menu, pattern='main_menu'))
    application.add_handler(CallbackQueryHandler(handle_create_event_button, pattern="create_event"))
    application.add_handler(CallbackQueryHandler(list_events, pattern='list_events'))
    application.add_handler(CallbackQueryHandler(my_events, pattern='my_events'))
    application.add_handler(CallbackQueryHandler(event_details, pattern='event_details_'))
    application.add_handler(CallbackQueryHandler(my_event_details, pattern="my_event_"))
    application.add_handler(CallbackQueryHandler(join_event, pattern='join_'))
    application.add_handler(CallbackQueryHandler(leave_event, pattern='leave_'))
    application.add_handler(CallbackQueryHandler(delete_event, pattern='delete_event_'))
    application.add_handler(CallbackQueryHandler(handle_calendar, pattern='^\\d{4}-\\d{2}-\\d{2}$'))
    application.add_handler(CallbackQueryHandler(remove_participant_handler, pattern="remove_participant_"))
    application.add_handler(CallbackQueryHandler(my_calendar, pattern='my_calendar'))
    application.add_handler(CallbackQueryHandler(add_date_handler, pattern='add_date'))
    application.add_handler(CallbackQueryHandler(handle_calendar_date, pattern=".*"))
    application.add_handler(CallbackQueryHandler(manage_date, pattern='manage_date_'))
    application.add_handler(CallbackQueryHandler(delete_date, pattern='delete_date_'))

    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()