import asyncio
import sys
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select, text

from app.core.security import pwd_context
from app.db.base import Base
from app.db.session import async_session_maker
from app.enums import ActivityType, Gender, Mood, Role
from app.models import (
    Achievement,
    AchievementLog,
    ActivitySession,
    BreathingActivity,
    DailyMessage,
    DiaryEntry,
    EmergencyContact,
    GoodPractice,
    GoodPracticeLog,
    MeditationActivity,
    MoodLog,
    ProfessionalPatient,
    SelfRegulationActivity,
    SelfRegulationSession,
    User,
)


async def clear_db(db) -> None:
    table_names = ", ".join(f'"{name}"' for name in Base.metadata.tables if name != "templates")

    await db.execute(text(f"TRUNCATE TABLE {table_names} CASCADE"))
    await db.commit()


async def ensure_default_activities(db) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    defaults = (
        (
            BreathingActivity,
            "Respiração 4-7-8",
            {
                "max_duration_seconds": 120,
                "inhale_seconds": 4,
                "hold_seconds": 7,
                "exhale_seconds": 8,
                "repeat_count": 4,
            },
        ),
        (
            MeditationActivity,
            "Meditação transcendental",
            {
                "max_duration_seconds": 300,
                "audio_url": "https://www.youtube.com/watch?v=2p8q1vs9K78",
            },
        ),
        (
            SelfRegulationActivity,
            "Estoura Bolhas",
            {"max_duration_seconds": 60, "bubble_spawn_interval_ms": 800},
        ),
    )
    activity_ids = []
    for model, name, configuration in defaults:
        existing_id = await db.scalar(
            select(model.id)
            .where(model.name == name, model.enabled.is_(True), model.deleted_at.is_(None))
            .limit(1)
        )
        if existing_id is not None:
            activity_ids.append(existing_id)
            continue

        activity_id = uuid.uuid4()
        db.add(model(id=activity_id, name=name, **configuration))
        activity_ids.append(activity_id)

    await db.flush()
    return activity_ids[0], activity_ids[1], activity_ids[2]


async def ensure_default_good_practices(db) -> uuid.UUID:
    defaults = (
        (
            "Vá a um estabelecimento pequeno",
            "Visite um comércio em horário de menor movimento.",
        ),
        (
            "Envie uma mensagem gentil",
            "Mande uma mensagem breve para alguém de quem você gosta.",
        ),
        (
            "Anote algo bom do seu dia",
            "Escreva uma coisa, mesmo pequena, que fez bem a você hoje.",
        ),
        (
            "Faça uma pausa consciente",
            "Reserve cinco minutos para descansar e perceber como você está.",
        ),
        (
            "Cuide de um pequeno espaço",
            "Organize um canto da casa que você usa com frequência.",
        ),
        (
            "Observe o que está ao seu redor",
            "Escolha um lugar tranquilo e repare em três detalhes do ambiente.",
        ),
        (
            "Alongue o corpo com calma",
            "Faça um alongamento leve, respeitando os limites do seu corpo.",
        ),
        (
            "Agradeça alguém",
            "Conte a uma pessoa algo que você aprecia nela.",
        ),
    )
    first_practice_id = None
    for title, description in defaults:
        practice_id = await db.scalar(
            select(GoodPractice.id)
            .where(
                GoodPractice.title == title,
                GoodPractice.enabled.is_(True),
                GoodPractice.deleted_at.is_(None),
            )
            .limit(1)
        )
        if practice_id is None:
            practice_id = uuid.uuid4()
            db.add(GoodPractice(id=practice_id, title=title, description=description))
        if first_practice_id is None:
            first_practice_id = practice_id

    await db.flush()
    assert first_practice_id is not None
    return first_practice_id


async def seed() -> None:
    async with async_session_maker() as db:
        if "--reset" in sys.argv:
            print("\n\n🗑️   Deletando os dados prévios do seu banco...")
            await clear_db(db)
            print("\n🌿 Adicionando novos dados do seed")

        if "--clear-db" in sys.argv:
            await clear_db(db)
            print("\n\n✅   Banco limpo, sem semear (todos os dados foram apagados)\n\n")
            return

        existente = await db.execute(select(User))
        if existente.scalars().first() is not None:
            await ensure_default_activities(db)
            await ensure_default_good_practices(db)
            await db.commit()
            print("\n\n✅ Atividades e práticas do bem disponíveis; dados preservados.\n\n")
            return

        now = datetime.now(UTC)

        admin_id = uuid.uuid4()
        professional_id = uuid.uuid4()
        paciente1_id = uuid.uuid4()
        paciente2_id = uuid.uuid4()

        password = "12345678"
        users = [
            User(
                id=admin_id,
                full_name="Administrador Silpo",
                gender=Gender.PREFER_NOT_TO_SAY,
                birth_date=date(1992, 9, 17),
                email="email@email.com",
                password=pwd_context.hash(password),
                phone_number="+5551999825157",
                role=Role.ADMIN,
            ),
            User(
                id=professional_id,
                full_name="Gabriela Teixeira",
                gender=Gender.FEMALE,
                birth_date=date(1985, 7, 22),
                email="teixeira.gabriela@google.com",
                password=pwd_context.hash(password),
                phone_number="+5551990010002",
                role=Role.PROFESSIONAL,
            ),
            User(
                id=paciente1_id,
                full_name="Sol Andrade",
                gender=Gender.NON_BINARY,
                birth_date=date(1999, 1, 30),
                email="sol.andrade@terra.com",
                password=pwd_context.hash(password),
                phone_number="+5551990010003",
                role=Role.USER,
            ),
            User(
                id=paciente2_id,
                full_name="Rafael Tavares",
                gender=Gender.MALE,
                birth_date=date(1995, 11, 5),
                email="rafael.tavares@uol.com",
                password=pwd_context.hash(password),
                phone_number="+5551990010004",
                role=Role.USER,
            ),
        ]

        emergency_contacts = [
            EmergencyContact(
                user_id=paciente1_id,
                full_name="Jaskier Ferreira",
                nickname="Jackal",
                phone_number="+5551990020001",
            ),
            EmergencyContact(
                user_id=paciente2_id,
                full_name="Marina Tavares",
                nickname="Mãe",
                phone_number="+5551990020002",
            ),
        ]

        (
            breathing_activity_id,
            meditation_activity_id,
            self_regulation_activity_id,
        ) = await ensure_default_activities(db)

        breathing_session_id = uuid.uuid4()
        self_regulation_session_id = uuid.uuid4()
        meditation_session_id = uuid.uuid4()

        activity_sessions = [
            ActivitySession(
                id=breathing_session_id,
                user_id=paciente1_id,
                activity_id=breathing_activity_id,
                type=ActivityType.BREATHING,
                time_spent_seconds=76,
                posted_at=now,
            ),
            ActivitySession(
                id=meditation_session_id,
                user_id=paciente2_id,
                activity_id=meditation_activity_id,
                type=ActivityType.MEDITATION,
                time_spent_seconds=290,
                posted_at=now,
            ),
            SelfRegulationSession(
                id=self_regulation_session_id,
                user_id=paciente1_id,
                activity_id=self_regulation_activity_id,
                time_spent_seconds=45,
                posted_at=now,
                bubbles_exploded=23,
            ),
        ]

        achievement_id = uuid.uuid4()
        achievements = [
            Achievement(
                id=achievement_id,
                name="Primeiro Passo",
                image_url="https://thumb.wikimedia.org/wikipedia/commons/thumb/5/54/Bot%C3%B3n_Me_gusta.svg/1280px-Bot%C3%B3n_Me_gusta.svg.png?utm_source=pt.wikipedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
                description="Completou a primeira atividade no Silpo.",
            ),
        ]
        achievement_logs = [
            AchievementLog(user_id=paciente1_id, achievement_id=achievement_id),
        ]

        good_practice_id = await ensure_default_good_practices(db)
        good_practice_logs = [
            GoodPracticeLog(user_id=paciente1_id, good_practice_id=good_practice_id, posted_at=now),
        ]

        mood_log_id = uuid.uuid4()
        mood_logs = [
            MoodLog(
                id=mood_log_id,
                user_id=paciente1_id,
                mood=Mood.BEM,
                log_date=now.date(),
            ),
        ]
        diary_entries = [
            DiaryEntry(
                user_id=paciente1_id,
                mood_log_id=mood_log_id,
                note="Hoje consegui ir no café perto de casa. Fiquei feliz e tomei um capuccino.",
            ),
        ]

        professional_patients = [
            ProfessionalPatient(professional_id=professional_id, patient_id=paciente1_id),
        ]

        daily_messages = [
            DailyMessage(message="Você não está sozinha. Dias melhores estão por vir."),
            DailyMessage(message="Hoje melhor que ontem, amanhã melhor que hoje."),
            DailyMessage(message="Neste momento, estou seguro e protegido."),
        ]

        db.add_all(users + achievements + daily_messages)
        await db.flush()

        db.add_all(
            emergency_contacts
            + activity_sessions
            + achievement_logs
            + good_practice_logs
            + mood_logs
            + professional_patients
        )

        await db.flush()

        db.add_all(diary_entries)

        await db.commit()

        print("\n\n✅ Seed executado com sucesso!\n\n")


if __name__ == "__main__":
    asyncio.run(seed())
