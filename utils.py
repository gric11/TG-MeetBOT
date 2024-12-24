from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("Создать событие", callback_data='create_event')],
        [InlineKeyboardButton("Список событий", callback_data='list_events')],
        [InlineKeyboardButton("Мои события", callback_data='my_events')],
        [InlineKeyboardButton("Мой календарь", callback_data='my_calendar')],
    ]
    return InlineKeyboardMarkup(keyboard)
