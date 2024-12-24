from telegram.ext import CallbackContext
import telegram


def get_participants(event_id):
    from database import SessionLocal, Participant, User, BlockedParticipant
    """Получить список участников события, исключая заблокированных."""
    with SessionLocal() as session:
        participants = (
            session.query(User.id, User.username)
            .join(Participant, User.id == Participant.user_id)
            .filter(Participant.event_id == event_id)
            .filter(~session.query(BlockedParticipant).filter(
                BlockedParticipant.event_id == event_id,
                BlockedParticipant.user_id == User.id
            ).exists())
            .all()
        )
    return [{"id": participant[0], "username": participant[1]} for participant in participants]




async def send_reminder(context: CallbackContext):
    print("send_reminder вызвана")
    job_data = context.job.data
    event_id = job_data.get("event_id")
    event_name = job_data.get("event_name")

    # Получаем участников события
    participants = get_participants(event_id)

    if not participants:
        print(f"Участников для события {event_id} нет.")
        return None

    # Отправляем напоминания участникам
    for user in participants:
        try:
            await context.bot.send_message(
                chat_id=user["id"],  # Используем ID для отправки
                text=f"Напоминание: Событие '{event_name}' начнётся через час!"
            )
        except telegram.error.BadRequest as e:
            print(f"Ошибка при отправке сообщения для {user['username']} ({user['id']}): {e}")




async def start_event(context: CallbackContext):
    from database import SessionLocal, Participant, Event, BlockedParticipant
    print("start_event вызвана")
    job_data = context.job.data
    event_id = job_data.get("event_id")
    event_name = job_data.get("event_name")

    # Получаем участников события
    participants = get_participants(event_id)

    # Отправляем уведомления участникам
    for user in participants:
        try:
            await context.bot.send_message(
                chat_id=user["id"],
                text=f"Событие '{event_name}' началось!"
            )
        except telegram.error.BadRequest as e:
            print(f"Ошибка при отправке сообщения для {user['username']} ({user['id']}): {e}")

    # Удаляем событие и связанные данные из базы данных
    with SessionLocal() as session:
        session.query(Participant).filter(Participant.event_id == event_id).delete()
        session.query(BlockedParticipant).filter(BlockedParticipant.event_id == event_id).delete()
        session.query(Event).filter(Event.id == event_id).delete()
        session.commit()
        print(f"Событие {event_id} и связанные данные успешно удалены.")





