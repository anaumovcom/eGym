"""Bounded local-first contract. Catalog meanings are not free-form model input."""

import re
from dataclasses import replace
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.coach import CoachModel
from app.services.coach.facts import FactPackage
from app.services.coach.memory import words
from app.services.coach.validation import spoken_numbers

Cue = Literal['set-end', 'set-partial', 'set-skipped', 'last-set-next', 'exercise-done',
              'exercise-partial', 'exercise-skipped', 'workout-done', 'workout-partial']
Idea = Literal['set_closed', 'set_partial', 'set_skipped', 'last_set_remaining', 'exercise_full',
               'exercise_partial', 'exercise_skipped', 'workout_closed', 'workout_partial']
IDEAS = dict(zip(Cue.__args__, Idea.__args__, strict=True))


class LocalCompletion(CoachModel):
    cue_ids: tuple[Cue, ...] = Field(min_length=1, max_length=3)
    acknowledged: tuple[Idea, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode='after')
    def matching(self):
        if len(set(self.cue_ids)) != len(self.cue_ids) or tuple(IDEAS[c] for c in self.cue_ids) != self.acknowledged:
            raise ValueError('Local catalog meanings must match')
        return self

    def applies(self, kind: str) -> bool:
        prefix = {'set_persisted': 'set', 'exercise_finalized': 'exercise', 'workout_finalized': 'workout'}.get(kind)
        return prefix is not None and all(c.startswith(prefix + '-') or (
            prefix == 'set' and c == 'last-set-next') for c in self.cue_ids)


def additional_package(package: FactPackage | None, local: LocalCompletion | None) -> FactPackage | None:
    if package is None or local is None:
        return package
    ideas = set(local.acknowledged)
    # Never drop required partial/limited honesty just because a local full cue ran.
    # set-end merely acknowledges closure; the saved count remains genuinely new.
    covered = (package.outcome == 'full' and bool(ideas & {'set_closed', 'exercise_full'})) or (
        package.outcome == 'partial' and bool(ideas & {'set_partial', 'exercise_partial', 'workout_partial'}))
    return replace(package, facts=tuple(f for f in package.facts if not (
        (covered and f.id == 'outcome') or
        ('last_set_remaining' in ideas and f.id == 'sets-left' and f.value == 1))))


def duplicate_local(text: str, local: LocalCompletion | None) -> bool:
    if local is None:
        return False
    lower = text.lower().replace('ё', 'е')
    patterns = {
        'set_closed': r'(?:подход\w*\s+(?:уже\s+)?(?:заверш|закрыт|закончен|выполн|позади)|'
                  r'(?:завершили|закрыли|закончили|выполнили)\s+подход)',
        'set_partial': r'(?:подход|план подхода)[^.!,;]*(?:частичн|не полностью|не целиком)|'
                   r'(?:частичн|не полностью)[^.!,;]*подход',
        'set_skipped': r'подход\w*\s+пропущ',
        'last_set_remaining': r'остал\w*\s+последн\w*\s+подход',
        'exercise_full': r'(?:упражнение\s+(?:выполн|заверш|закрыт|сделан|позади)|'
                 r'все (?:запланированные )?подходы\s+(?:выполн|заверш|закрыт)|'
                 r'(?:выполнили|завершили|закрыли|сделали)\s+упражнение)',
        'exercise_partial': r'(?:упражнение|план упражнения)[^.!,;]*(?:частичн|не полностью|не целиком)',
        'exercise_skipped': r'упражнение\s+пропущ',
        'workout_closed': r'тренировка\s+(?:заверш|законч|закрыт|позади)|'
                  r'(?:завершили|закончили|закрыли)\s+тренировку',
        'workout_partial': r'(?:тренировка|план тренировки)[^.!,;]*(?:частичн|не полностью|не целиком)',
    }
    for clause in re.split(r'[.!;]', lower):
        for idea in local.acknowledged:
            # A correction of local full → server partial is new mandatory honesty.
            if idea in {'exercise_full', 'set_closed', 'workout_closed'} and re.search(
                    r'частичн|не полностью|не подтвержд|неизвест', clause):
                continue
            if re.search(patterns[idea], clause):
                return True
    return False


def useful_addition(package: FactPackage | None, used: tuple[str, ...], local: LocalCompletion | None,
                    text: str | None = None) -> bool:
    if local is None:
        return True
    if package is None:
        return False
    # Naming the current exercise or generic encouragement is not new result information.
    candidates = [f for f in package.facts if f.id in used and f.id not in {'exercise', 'exercise-names'}]
    if text is None:
        return bool(candidates)
    # A claimed usedFactId alone is not evidence that generic encouragement added
    # information. Require its numbers or a fixed nonnumeric claim/value in speech.
    numbers = set(spoken_numbers(text))
    normalized = ' '.join(words(text))
    return any((bool(f.numbers) and set(f.numbers) <= numbers) or (
        not f.numbers and (' '.join(words(f.claim)) in normalized or (
            f.id != 'outcome' and isinstance(f.value, str) and ' '.join(words(f.value)) in normalized)))
        for f in candidates)