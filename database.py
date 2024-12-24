from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime, timedelta
import pytz
from scheduler import send_reminder, start_event

# Создаем базу данных
Base = declarative_base()
engine = create_engine('sqlite:///events.db')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Определяем модели
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    time = Column(DateTime, nullable=False)
    creator_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    creator = relationship("User", back_populates="created_events")

class Participant(Base):
    __tablename__ = "participants"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event = relationship("Event", back_populates="participants")
    user = relationship("User")

class BlockedParticipant(Base):
    __tablename__ = "blocked_participants"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event = relationship("Event")
    user = relationship("User")

class UserDate(Base):
    __tablename__ = "user_dates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, nullable=False, unique=True)
    user = relationship("User")

# Связи
User.created_events = relationship("Event", back_populates="creator")
Event.participants = relationship("Participant", back_populates="event")

def create_db():
    Base.metadata.create_all(bind=engine)


# Функция для добавления пользователя в таблицу users, если его еще нет
def add_user_to_db(user_id, username):
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(id=user_id, username=username)
            session.add(user)
            session.commit()

# Сохранение события в базу данных
def save_event(event_name, event_time, creator_id, application):
    """Сохранить событие в базу данных и настроить напоминания."""
    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    event_time = event_time.astimezone(moscow_tz)  # Приводим время события к московскому времени
    reminder_time = event_time - timedelta(hours=1)

    with SessionLocal() as session:
        # Сохраняем событие
        event = Event(name=event_name, time=event_time, creator_id=creator_id)
        session.add(event)
        session.commit()
        event_id = event.id

        # Логируем и добавляем напоминание
        if reminder_time > now:
            print(f"Регистрация напоминания на {reminder_time}")
            application.job_queue.run_once(
                send_reminder,
                when=(reminder_time - now).total_seconds(),
                data={"event_id": event_id, "event_name": event_name}
            )
        else:
            print(f"Пропущено напоминание для '{event_name}', так как время прошло.")

        # Логируем и добавляем задачу для начала события
        if event_time > now:
            print(f"Регистрация начала события на {event_time}")
            application.job_queue.run_once(
                start_event,
                when=(event_time - now).total_seconds(),
                data={"event_id": event_id, "event_name": event_name}
            )
        else:
            print(f"Пропущено событие '{event_name}', так как время прошло.")

        return event_id





# Сохранение участника события
def save_participant(event_id, user_id):
    with SessionLocal() as session:
        participant = Participant(event_id=event_id, user_id=user_id)
        session.add(participant)
        session.commit()



def is_user_participant(event_id, user_id):
    """Проверить, является ли пользователь участником события."""
    with SessionLocal() as session:
        participant = session.query(Participant).filter_by(event_id=event_id, user_id=user_id).first()
        return participant is not None

def remove_participant(event_id, user_id):
    """Удалить участника из события."""
    with SessionLocal() as session:
        participant = session.query(Participant).filter_by(event_id=event_id, user_id=user_id).first()
        if participant:
            session.delete(participant)
            session.commit()

def get_events():
    """Получить список всех событий."""
    with SessionLocal() as session:
        events = session.query(Event).all()
        return [(event.id, event.name, event.time) for event in events]

def get_user_events(user_id):
    """Получить события, созданные пользователем."""
    with SessionLocal() as session:
        events = session.query(Event).filter(Event.creator_id == user_id).all()
        return [(event.id, event.name, event.time) for event in events]

def get_participants(event_id):
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

def block_participant(event_id, user_id):
    """Добавить пользователя в список заблокированных для события."""
    with SessionLocal() as session:
        blocked = BlockedParticipant(event_id=event_id, user_id=user_id)
        session.add(blocked)
        session.commit()

def add_date(user_id, date):
    """Добавить дату для пользователя, если её ещё нет."""
    with SessionLocal() as session:
        exists = session.query(UserDate).filter(UserDate.user_id == user_id, UserDate.date == date).first()
        if exists:
            return False  # Дата уже существует
        new_date = UserDate(user_id=user_id, date=date)
        session.add(new_date)
        session.commit()
        return True

def get_user_dates(user_id):
    """Получить список всех дат пользователя."""
    with SessionLocal() as session:
        dates = session.query(UserDate).filter(UserDate.user_id == user_id).all()
        return [date.date for date in dates]

def delete_user_date(user_id, date):
    """Удалить дату пользователя."""
    with SessionLocal() as session:
        # Преобразуем дату в формат datetime, если она передана как строка
        if isinstance(date, str):
            from datetime import datetime
            date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")

        user_date = session.query(UserDate).filter(UserDate.user_id == user_id, UserDate.date == date).first()
        if user_date:
            session.delete(user_date)
            session.commit()
            print(f"Дата {date} для пользователя {user_id} успешно удалена.")
            return True
        print(f"Дата {date} для пользователя {user_id} не найдена.")
        return False



