import enum


class AchievementRule(enum.StrEnum):
    """O que é contado para medir o progresso de uma conquista."""

    MOOD_LOGS = "mood_logs"
    """Registros emocionais."""
    MOOD_DAYS = "mood_days"
    """Datas distintas com registro emocional."""
    DISTINCT_MOODS = "distinct_moods"
    """Tipos de emoção distintos registrados."""
    GOOD_PRACTICE_LOGS = "good_practice_logs"
    """Práticas do bem concluídas, repetidas incluídas."""
    DISTINCT_GOOD_PRACTICES = "distinct_good_practices"
    """Práticas do bem diferentes concluídas (good_practice_id distinto)."""
    BREATHING_SESSIONS = "breathing_sessions"
    """Sessões de respiração concluídas."""
    EXERCISE_SESSIONS = "exercise_sessions"
    """Sessões de exercícios concluídas, de qualquer tipo; Práticas do Bem não entram."""
    DIARY_ENTRIES = "diary_entries"
    """Entradas válidas do Diário."""
