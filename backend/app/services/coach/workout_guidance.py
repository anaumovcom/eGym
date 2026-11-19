"""Editorial offline recordings for the saved plans, 2026-11-19. Never read user data at run time.

Source of each variant: exercises/<slug>/<slug>.json, checked against the actual builder load type.
These are form reminders, not observations, clinical advice, machine settings or instructions to add load.
The older live-author pilot in tips.py intentionally has a different, narrower permission boundary.
"""

from dataclasses import dataclass
from typing import Literal

Phase = Literal["setup", "active", "rest"]
PHASES: tuple[Phase, ...] = ("setup", "active", "rest")
VERSION = "workout-1"


@dataclass(frozen=True, slots=True)
class Movement:
    slug: str
    key: str  # Short stable audio ID, independent of the translated label and the 40-char URL limit.
    label: str
    profile: str
    setup: str
    active: str
    rest: str

    def clip_id(self, phase: Phase) -> str:
        return f"tip-{self.key}-{phase}"

    def metadata(self, phase: Phase) -> dict:
        return {"kind": "workout", "version": VERSION, "exerciseSlugs": [self.slug], "phases": [phase],
                "profile": self.profile}


# An exact profile encodes an equipment + (runtime kind, load mode) pair, not independent fuzzy matches.
# In particular a bodyweight incline press is NOT a push-up, and an inverted row needs a stationary bar.
PROFILES = {
    "cardio": {"equipment": ["Cardio", "Кардио"], "variants": {"timed": "timer"}, "activeControl": None},
    "smith": {"equipment": ["Smith-Machine", "Smith Machine", "Машина Смита"],
              "variants": {"machine": "constant"}, "activeControl": "training"},
    "incline": {"equipment": ["Smith-Machine", "Smith Machine", "Машина Смита"],
               "variants": {"bodyweight": "unloaded", "machine": "constant"}, "activeControl": "training"},
    "inverted": {"equipment": ["Smith-Machine", "Smith Machine", "Машина Смита"],
                 "variants": {"machine": "constant"}, "activeControl": "fixed_hold"},
    "pulldown": {"equipment": ["Machine", "Тренажёр"], "variants": {"machine": "constant"}, "activeControl": "training"},
}

MOVEMENTS = (
    Movement("butt-kick", "heel-flick", "Захлёст голени", "cardio",
             "Встань прямо и оставь за собой место для пяток.",
             "Поочерёдно сгибай ноги, не гоняясь за высотой.",
             "В следующем подходе дай рукам двигаться в такт шагам."),
    Movement("cardio-knee-taps", "knee-taps", "Касания коленей", "cardio",
             "Встань устойчиво. Колени поднимай по очереди.",
             "Подводи колено к ладони, а не плечо к колену.",
             "Для касаний выбери высоту, при которой корпус остаётся ровным."),
    Movement("cardio-quick-feet", "quick-feet", "Быстрые шаги", "cardio",
             "Освободи место под ногами для коротких шагов на месте.",
             "Касайся пола лёгкими короткими шагами.",
             "В следующей серии сначала найди ритм, а не скорость."),
    Movement("smith-machine-seated-overhead-press", "seated-press", "Жим над головой сидя", "smith",
             "Обопрись спиной о скамью и устойчиво поставь стопы.",
             "Во время жима сохраняй опору спиной.",
             "В следующем подходе возвращай руки вниз так же плавно, как поднимаешь."),
    Movement("underhand-pulldown", "underhand-pull", "Тяга верхнего блока обратным хватом", "pulldown",
             "Перед тягой обратным хватом найди устойчивое положение сидя.",
             "Веди локти вниз без раскачки корпуса.",
             "В следующем подходе плавно отпускай рукоять вверх."),
    Movement("smith-machine-narrow-stance-squat", "narrow-squat", "Присед с узкой постановкой ног", "smith",
             "В узкой стойке найди устойчивую опору на обе стопы.",
             "Направляй колени в ту же сторону, что и носки.",
             "Для следующего приседа выбери глубину, на которой пятки остаются на полу."),
    Movement("smith-machine-close-grip-bench-press", "close-press", "Жим лёжа узким хватом", "smith",
             "Перед узким жимом поставь стопы на пол и проверь удобство хвата.",
             "Держи кисти на одной линии с предплечьями.",
             "При следующем опускании не отбивай гриф от груди."),
    Movement("smith-machine-romanian-deadlift", "romanian", "Румынская тяга", "smith",
             "Встань устойчиво и слегка согни колени.",
             "Начинай наклон с движения таза назад.",
             "В следующем подходе держи гриф близко к ногам, не тянись им к полу."),
    Movement("smith-machine-incline-bench-press", "incline-press", "Жим на наклонной скамье", "incline",
             "Устройся на наклонной скамье так, чтобы обе стопы имели опору.",
             "Сохраняй контакт спины со скамьёй.",
             "В следующем подходе обрати внимание на плавное опускание рук."),
    Movement("smith-machine-inverted-row", "inverted-row", "Австралийские подтягивания", "inverted",
             "Для австралийских подтягиваний нужна неподвижная перекладина.",
             "Поднимай грудь и таз вместе.",
             "На следующем подъёме тянись грудью, не вытягивая шею."),
    Movement("smith-machine-drag-curl", "drag-curl", "Сгибание рук вдоль тела", "smith",
             "Встань устойчиво: гриф будет двигаться близко к телу.",
             "Сгибая руки, веди локти назад.",
             "В следующем подходе оставь корпус неподвижным, работай руками."),
    Movement("smith-machine-skullcrusher", "lying-extension", "Французский жим лёжа", "smith",
             "Перед французским жимом устойчиво расположись на скамье.",
             "Сгибай руки в локтях без рывка.",
             "Следующий подход начни плавно, сохраняя положение плеч."),
    Movement("smith-machine-bench-press", "bench-press", "Жим лёжа", "smith",
             "Ляг на скамью так, чтобы обе стопы уверенно стояли на полу.",
             "Опускай гриф плавно, без отскока.",
             "Для следующего жима проверь, что кисти не заламываются назад."),
    Movement("smith-machine-overhand-row", "overhand-row", "Тяга в наклоне прямым хватом", "smith",
             "Прими устойчивый наклон и сохрани естественное положение спины.",
             "Веди локти назад, не раскачивая корпус.",
             "В следующем подходе удерживай тот же наклон и при опускании грифа."),
    Movement("smith-machine-squat", "squat", "Присед в тренажёре Смита", "smith",
             "Перед приседом найди удобную стойку с опорой на всю стопу.",
             "Сгибай колени и тазобедренные суставы вместе.",
             "В следующем подходе поднимайся с опорой на обе стопы."),
    Movement("smith-machine-upright-row", "upright-row", "Тяга к подбородку", "smith",
             "Возьми гриф удобно и встань устойчиво перед тягой.",
             "Веди локти вверх в комфортной амплитуде.",
             "В следующем подходе не гонись за высотой, опускай гриф плавно."),
    Movement("smith-machine-calf-raise", "calf-raise", "Подъём на носки", "smith",
             "Распредели опору между обеими стопами перед подъёмом на носки.",
             "Поднимай пятки плавно, без пружинящих движений.",
             "В следующем подходе не бросай пятки вниз."),
)

# Run-local rotation, used only after a reported, completed non-zero set. No comparisons or extra reps.
MOTIVATION = {
    "support-breather": "Есть подход! Теперь можно перевести дух.",
    "support-one-step": "Ещё один шаг сделан. Хорошая работа.",
    "support-rest": "Подход позади. Эта пауза тоже часть тренировки.",
    "support-your-pace": "Хорошая работа. На отдыхе некуда спешить.",
    "support-small-wins": "Из таких подходов и складывается тренировка.",
    "support-credit": "Есть! Эту часть работы можно отметить.",
    "support-reset": "Подход за плечами. Дай себе передохнуть.",
    "support-focus": "Хорошая работа. Теперь можно немного отвлечься от счёта.",
}


def browser_index() -> dict:
    """Build-time allowlist: no workout-specific text or DB lookup in the playback loop."""
    return {"version": VERSION, "profiles": PROFILES, "motivation": list(MOTIVATION),
            "movements": [{"slug": m.slug, "key": m.key, "label": m.label, "profile": m.profile} for m in MOVEMENTS]}