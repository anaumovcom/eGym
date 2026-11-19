from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MuscleDefinition:
    id: str
    name: str
    group: str
    area: str
    recommended: tuple[str, ...]
    avoided: tuple[str, ...]


CANONICAL_MUSCLE_DEFINITIONS: dict[str, MuscleDefinition] = {
    "abdominals": MuscleDefinition("abdominals", "Пресс", "front", "middle", ("Планка", "Dead Bug"), ("Тяжёлые скручивания",)),
    "biceps": MuscleDefinition("biceps", "Бицепс", "front", "upper", ("Сгибание рук с лёгким весом", "Hammer Curl"), ("Тяжёлые подъёмы на бицепс",)),
    "calves": MuscleDefinition("calves", "Икры", "back", "lower", ("Подъём на носки", "Лёгкая ходьба"), ("Взрывные прыжки",)),
    "chest": MuscleDefinition("chest", "Грудь", "front", "upper", ("Планка", "Лёгкая тяга"), ("Жим лёжа", "Жим с пола")),
    "forearms": MuscleDefinition("forearms", "Предплечья", "front", "upper", ("Фермерская прогулка", "Лёгкий вис"), ("Тяжёлая изоляция хвата",)),
    "front-shoulders": MuscleDefinition("front-shoulders", "Передние дельты", "front", "upper", ("Лёгкий жим гантелей", "Подъём рук перед собой"), ("Тяжёлый армейский жим",)),
    "glutes": MuscleDefinition("glutes", "Ягодицы", "back", "middle", ("Глют-мост", "Шаги с резинкой"), ("Тяжёлые выпады",)),
    "hamstrings": MuscleDefinition("hamstrings", "Бицепс бедра", "back", "lower", ("Лёгкая румынская тяга", "Сгибание ног"), ("Тяжёлая румынская тяга",)),
    "lats": MuscleDefinition("lats", "Широчайшие", "back", "upper", ("Тяга сверху", "Тяга прямыми руками"), ("Тяжёлая тяга сверху",)),
    "obliques": MuscleDefinition("obliques", "Косые мышцы живота", "front", "middle", ("Боковая планка", "Pallof Press"), ("Тяжёлые вращения корпуса",)),
    "quads": MuscleDefinition("quads", "Квадрицепсы", "front", "lower", ("Лёгкие выпады", "Разгибание ног"), ("Тяжёлый присед",)),
    "rear-shoulders": MuscleDefinition("rear-shoulders", "Задние дельты", "back", "upper", ("Face Pull", "Обратная разводка"), ("Тяжёлая тяга к лицу",)),
    "traps": MuscleDefinition("traps", "Трапеции", "back", "upper", ("Шраги с лёгким весом", "Face Pull"), ("Тяжёлые шраги",)),
    "traps-middle": MuscleDefinition("traps-middle", "Средняя трапеция", "back", "upper", ("Тяга к поясу", "Face Pull"), ("Тяжёлая тяга к поясу",)),
    "triceps": MuscleDefinition("triceps", "Трицепс", "back", "upper", ("Тяга к поясу",), ("Французский жим",)),
}


# Manifest targets with display metadata only; not achievement or training groups.
_SUPPLEMENTAL_DISPLAY_DEFINITIONS = {
    "adductors": MuscleDefinition("adductors", "Приводящие мышцы бедра", "front", "lower", (), ()),
    "hip-flexors": MuscleDefinition("hip-flexors", "Сгибатели бедра", "front", "lower", (), ()),
    "side-delts": MuscleDefinition("side-delts", "Средние дельты", "front", "upper", (), ()),
    "neck": MuscleDefinition("neck", "Мышцы шеи", "back", "upper", (), ()),
    "anterior-shin": MuscleDefinition("anterior-shin", "Передняя группа голени", "front", "lower", (), ()),
    "foot": MuscleDefinition("foot", "Мышцы стопы", "front", "lower", (), ()),
    "rotator-cuff": MuscleDefinition("rotator-cuff", "Ротаторная манжета", "back", "upper", (), ()),
    "serratus": MuscleDefinition("serratus", "Передняя зубчатая мышца", "front", "middle", (), ()),
    "hips": MuscleDefinition("hips", "Тазобедренные мышцы", "front", "lower", (), ()),
    "lowerback": MuscleDefinition("lowerback", "Низ спины", "back", "middle", (), ()),
}


LEGACY_MUSCLE_SPLITS: dict[str, tuple[tuple[str, float], ...]] = {
    # Older runtime clients persisted translated display names as database IDs.
    **{item.name: ((item.id, 1.0),) for item in
       (*CANONICAL_MUSCLE_DEFINITIONS.values(), *_SUPPLEMENTAL_DISPLAY_DEFINITIONS.values())},
    "Шея": (("neck", 1.0),),
    "abs": (("abdominals", 1.0),),
    "front-delta": (("front-shoulders", 1.0),),
    "rear-delta": (("rear-shoulders", 1.0),),
    "back": (("lats", 0.7), ("traps-middle", 0.3)),
    "shoulders": (("front-shoulders", 0.5), ("rear-shoulders", 0.5)),
    "core": (("abdominals", 0.7), ("obliques", 0.3)),
    "legs": (("quads", 0.45), ("hamstrings", 0.25), ("glutes", 0.2), ("calves", 0.1)),
}


def split_muscle_targets(muscle_id: str) -> tuple[tuple[str, float], ...]:
    return LEGACY_MUSCLE_SPLITS.get(muscle_id, ((muscle_id, 1.0),))


def is_legacy_muscle_id(muscle_id: str) -> bool:
    return muscle_id in LEGACY_MUSCLE_SPLITS


def get_muscle_definition(muscle_id: str) -> MuscleDefinition:
    definition = CANONICAL_MUSCLE_DEFINITIONS.get(muscle_id) or _SUPPLEMENTAL_DISPLAY_DEFINITIONS.get(muscle_id)

    if definition is not None:
        return definition

    fallback_name = muscle_id.replace("-", " ").replace("_", " ").title()
    return MuscleDefinition(muscle_id, fallback_name, "front", "upper", ("Лёгкое кардио",), ("Тяжёлая изоляция",))