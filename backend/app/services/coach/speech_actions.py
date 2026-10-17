"""Deterministic speech direction, separate from provider speak/silence and delivery."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpeechAction:
    phases: tuple[str, ...]
    fact_policy: str
    max_words: int
    priority: int


SPEECH_ACTIONS = {
    "orient": SpeechAction(("setup",), "declared-plan-or-reviewed-guide", 25, 60),
    "instruct": SpeechAction(("setup",), "catalog-guidance-no-observed-form", 30, 60),
    "support": SpeechAction(("active", "paused"), "current-moment-no-inferred-body-state", 16, 30),
    "result": SpeechAction(("rest",), "persisted-result-preserve-partial-and-locked-clause", 40, 90),
    "explain": SpeechAction(("setup", "active", "rest"), "reviewed-tip-only", 30, 50),
    "playful": SpeechAction(("rest",), "no-new-statistic-optional-safe-situation", 30, 10),
    "summary": SpeechAction(("summary",), "persisted-highlights-with-plan-sufficiency", 45, 100),
}


def speech_action(task: str) -> str:
    if task == "setup/technique":
        return "instruct"
    if task.endswith("general-tip") or task == "setup/orientation":
        return "explain"
    if task.startswith("setup/"):
        return "orient"
    if task.startswith("summary/"):
        return "summary"
    if task in {"rest/playful", "callback"}:
        return "playful"
    if task.startswith("rest/"):
        return "result"
    return "support"


# Manner, not canned sentences: real pilots copied literal example jokes almost verbatim.
SCENARIO_EXAMPLES = {
    "orient": "Манера: коротко помоги сосредоточиться перед текущим упражнением. Не добавляй несуществующий план.",
    "instruct": "Манера: конкретная памятка перед движением, без приветствия, похвалы и общих лозунгов. Не оценивай выполнение пользователя.",
    "support": "Манера: одна короткая самостоятельная поддержка, не цепочка команд. Не повторяй недавнюю формулировку или её начало.",
    "result": "Манера при partial: уважительно признай записанное без жалости и объявления полного успеха.",
    "explain": "Манера: один утверждённый tip.text без добавлений, иначе silence.",
    "playful": "Манера: необязательная свежая короткая шутка о паузе, обстановке зала или самоирония тренера. "
               "Без насмешки над человеком, без выдуманных наблюдений; не возвращайся к недавней шутке в новой формулировке.",
    "summary": "Манера: один подтверждённый итог и короткая самостоятельная концовка, без новых обещаний.",
}