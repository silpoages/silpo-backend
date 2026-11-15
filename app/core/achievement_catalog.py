"""Catálogo das conquistas do Silpo.

O modelo `Achievement` guarda só nome, descrição, imagem e habilitação. A categoria, a regra
de desbloqueio e a meta de cada conquista ficam aqui, ligadas a ela pelo `id` fixo, que é o
identificador estável usado pelo seed, pelo tracking e pela API.
"""

import uuid
from dataclasses import dataclass

from app.enums import AchievementCategory, AchievementRule


@dataclass(frozen=True, slots=True)
class AchievementDefinition:
    id: uuid.UUID
    """Identificador estável: nunca muda entre ambientes nem entre execuções do seed."""
    code: str
    name: str
    description: str
    icon: str
    """Nome do ícone Ionicons usado pelo app; gravado em `Achievement.image_url`."""
    category: AchievementCategory
    rule: AchievementRule
    target: int


ACHIEVEMENT_CATALOG: tuple[AchievementDefinition, ...] = (
    AchievementDefinition(
        id=uuid.UUID("f19be169-97bb-57be-ae34-8cbfa6760a41"),
        code="first_step",
        name="Primeiro passo",
        description="Registre como você está se sentindo pela primeira vez",
        icon="leaf-outline",
        category=AchievementCategory.MOOD,
        rule=AchievementRule.MOOD_LOGS,
        target=1,
    ),
    AchievementDefinition(
        id=uuid.UUID("81ac122a-ea35-51c5-b31d-f20e89bd713a"),
        code="knowing_myself",
        name="Me conhecendo melhor",
        description="Registre emoções em 7 dias diferentes",
        icon="calendar-outline",
        category=AchievementCategory.MOOD,
        rule=AchievementRule.MOOD_DAYS,
        target=7,
    ),
    AchievementDefinition(
        id=uuid.UUID("70510413-026a-50d3-b8f5-fdf885ea710d"),
        code="all_emotions_matter",
        name="Todas as emoções importam",
        description="Registre 3 emoções diferentes",
        icon="color-palette-outline",
        category=AchievementCategory.MOOD,
        rule=AchievementRule.DISTINCT_MOODS,
        target=3,
    ),
    AchievementDefinition(
        id=uuid.UUID("07f93791-7e4b-5ad1-b494-a254b2924614"),
        code="small_victories",
        name="Pequenas vitórias",
        description="Conclua sua primeira prática do bem",
        icon="sparkles-outline",
        category=AchievementCategory.GOOD_PRACTICE,
        rule=AchievementRule.GOOD_PRACTICE_LOGS,
        target=1,
    ),
    AchievementDefinition(
        id=uuid.UUID("f9297ae3-e9bd-577c-838e-b274fc60096f"),
        code="cultivating_good",
        name="Cultivando o bem",
        description="Conclua 5 práticas do bem",
        icon="flower-outline",
        category=AchievementCategory.GOOD_PRACTICE,
        rule=AchievementRule.GOOD_PRACTICE_LOGS,
        target=5,
    ),
    AchievementDefinition(
        id=uuid.UUID("462dfc64-14ac-5915-a15e-0e5198d97457"),
        code="exploring_possibilities",
        name="Explorando possibilidades",
        description="Conclua 3 práticas do bem diferentes",
        icon="compass-outline",
        category=AchievementCategory.GOOD_PRACTICE,
        rule=AchievementRule.DISTINCT_GOOD_PRACTICES,
        target=3,
    ),
    AchievementDefinition(
        id=uuid.UUID("bb0bfde9-9337-5943-ab52-2eab7334d928"),
        code="moment_to_breathe",
        name="Um momento para respirar",
        description="Conclua sua primeira sessão de respiração",
        icon="water-outline",
        category=AchievementCategory.EXERCISE,
        rule=AchievementRule.BREATHING_SESSIONS,
        target=1,
    ),
    AchievementDefinition(
        id=uuid.UUID("047a074e-ac2e-5ee8-b4bc-c947178df19b"),
        code="taking_care_of_me",
        name="Cuidando de mim",
        description="Conclua 10 sessões de exercícios",
        icon="heart-outline",
        category=AchievementCategory.EXERCISE,
        rule=AchievementRule.EXERCISE_SESSIONS,
        target=10,
    ),
    AchievementDefinition(
        id=uuid.UUID("6f2895f0-ce8a-57f0-b548-ad1ef07c5124"),
        code="my_story_matters",
        name="Minha história importa",
        description="Faça seu primeiro registro no diário",
        icon="book-outline",
        category=AchievementCategory.DIARY,
        rule=AchievementRule.DIARY_ENTRIES,
        target=1,
    ),
    AchievementDefinition(
        id=uuid.UUID("6b518329-ac38-5820-84c9-334ddacc622c"),
        code="putting_into_words",
        name="Colocando em palavras",
        description="Faça 5 registros no diário",
        icon="create-outline",
        category=AchievementCategory.DIARY,
        rule=AchievementRule.DIARY_ENTRIES,
        target=5,
    ),
)

CATALOG_ACHIEVEMENT_IDS: tuple[uuid.UUID, ...] = tuple(
    definition.id for definition in ACHIEVEMENT_CATALOG
)
ACHIEVEMENTS_BY_ID: dict[uuid.UUID, AchievementDefinition] = {
    definition.id: definition for definition in ACHIEVEMENT_CATALOG
}
ACHIEVEMENTS_BY_CODE: dict[str, AchievementDefinition] = {
    definition.code: definition for definition in ACHIEVEMENT_CATALOG
}
