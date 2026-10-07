"""Server fact builder: spoken numbers, history comparison policy and validated aggregates only."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

Gender = Literal["m", "f", "n"]
ComparisonStatus = Literal["comparable", "limited", "unavailable"]
HistoryStatus = Literal["available", "limited", "unavailable", "empty_confirmed"]

METRIC_POLICY_VERSION = "metric-policy-0.1"
WEIGHT_RESOLUTION_KG = 0.5
# Raw telemetry labels are never speech facts: units/update timing are not validated.
FORBIDDEN_METRICS = frozenset({"amplitudePercent", "tempoLabel", "repQuality", "concentricS", "eccentricS"})
TEMPO_METRIC_POLICY_VERIFIED = False

_ONES = {"m": ("ноль", "один", "два"), "f": ("ноль", "одна", "две"), "n": ("ноль", "одно", "два")}
_UNITS = ("", "", "", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_TEENS = ("десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
          "семнадцать", "восемнадцать", "девятнадцать")
_TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто")
_HUNDREDS = ("", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот")


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _below_thousand(n: int, gender: Gender) -> list[str]:
    words = []
    if n >= 100:
        words.append(_HUNDREDS[n // 100])
        n %= 100
    if 10 <= n <= 19:
        return [*words, _TEENS[n - 10]]
    if n >= 20:
        words.append(_TENS[n // 10])
        n %= 10
    if n:
        words.append(_ONES[gender][n] if n <= 2 else _UNITS[n])
    return words


def number_words(n: int, gender: Gender = "m") -> str:
    if type(n) is not int or not 0 <= n < 1_000_000:
        raise ValueError("Spoken number out of bounds")
    if n == 0:
        return "ноль"
    thousands, rest = divmod(n, 1000)
    words = []
    if thousands:
        words += _below_thousand(thousands, "f")
        words.append(plural_ru(thousands, "тысяча", "тысячи", "тысяч"))
    if rest:
        words += _below_thousand(rest, gender)
    return " ".join(words)


UNIT_FORMS = {
    "reps": ("n", "повторение", "повторения", "повторений"),
    "seconds": ("f", "секунда", "секунды", "секунд"),
    "kg": ("m", "килограмм", "килограмма", "килограммов"),
    "sets": ("m", "подход", "подхода", "подходов"),
}


def spoken_quantity(n: int, unit: str) -> str:
    gender, one, few, many = UNIT_FORMS[unit]
    return f"{number_words(n, gender)} {plural_ru(n, one, few, many)}"


@dataclass(frozen=True, slots=True)
class AllowedFact:
    id: str
    claim: str
    status: Literal["confirmed", "derived-validated"]
    value: int | float | str | bool | None = None
    unit: str = "text"
    permits: tuple[str, ...] = ()
    numbers: tuple[float, ...] = ()
    scope_epoch: int = 0
    valid_until_ms: float = float("inf")

    def __post_init__(self):
        if self.id in FORBIDDEN_METRICS:
            raise ValueError("Unvalidated metric cannot become a speech fact")
        if not self.claim or len(self.claim) > 200:
            raise ValueError("Invalid fact claim")


@dataclass(frozen=True, slots=True)
class SetResult:
    set_id: str
    user_id: str
    exercise_slug: str
    progress_unit: Literal["reps", "seconds"]
    set_type: Literal["warmup", "working"]
    ordinal: int
    value: int | None
    outcome: Literal["completed", "partial", "skipped", "aborted"]
    confirmed: bool = True
    target: int | None = None
    target_exact: bool = True
    weight_kg: float | None = None
    load_mode: str | None = None
    range_id: str | None = None
    calibration_id: str | None = None
    count_method: str | None = None


@dataclass(frozen=True, slots=True)
class Comparison:
    status: ComparisonStatus
    delta: int | None = None
    previous_set_id: str | None = None
    differences: tuple[str, ...] = ()
    policy: str = METRIC_POLICY_VERSION


def _weight_step(value: float | None) -> int | None:
    return None if value is None else round(value / WEIGHT_RESOLUTION_KG)


def compare(current: SetResult, previous: SetResult | None, history: HistoryStatus) -> Comparison:
    if history in {"unavailable", "empty_confirmed"} or previous is None or previous.set_id == current.set_id:
        return Comparison("unavailable")
    if (previous.user_id, previous.exercise_slug, previous.progress_unit) != (
            current.user_id, current.exercise_slug, current.progress_unit):
        return Comparison("unavailable")
    checks = {
        "set_type": previous.set_type == current.set_type,
        "ordinal": previous.ordinal == current.ordinal,
        "load_mode": previous.load_mode == current.load_mode,
        "weight": _weight_step(previous.weight_kg) == _weight_step(current.weight_kg) and current.weight_kg is not None,
        "range": previous.range_id == current.range_id and previous.calibration_id == current.calibration_id,
        "count_method": previous.count_method == current.count_method,
        "confirmed": previous.confirmed and current.confirmed and previous.value is not None and current.value is not None,
        "outcome": previous.outcome == "completed" and current.outcome in {"completed", "partial"},
    }
    differences = tuple(name for name, ok in checks.items() if not ok)
    if differences or history == "limited":
        return Comparison("limited", previous_set_id=previous.set_id, differences=differences or ("limited_sample",))
    return Comparison("comparable", delta=current.value - previous.value, previous_set_id=previous.set_id)


@dataclass(frozen=True, slots=True)
class FactPackage:
    trigger_id: str
    facts: tuple[AllowedFact, ...]
    comparison: Comparison
    outcome: str
    locked_clause: str | None = None
    locked_fact_ids: tuple[str, ...] = ()
    history: HistoryStatus = "unavailable"
    notes: tuple[str, ...] = field(default=())


def saved_set_facts(current: SetResult, comparison: Comparison, *, scope_epoch: int, valid_until_ms: float,
                    history: HistoryStatus = "unavailable", analysis_opt_in: bool = False) -> FactPackage:
    if not current.confirmed:
        raise ValueError("Only saved acknowledged results build facts")
    common = {"scope_epoch": scope_epoch, "valid_until_ms": valid_until_ms}
    if current.outcome == "skipped" or not current.value:
        return FactPackage("T38", (AllowedFact("outcome", "Подход пропущен", "confirmed", "skipped", **common),),
                           Comparison("unavailable"), "skipped", history=history)
    unit = current.progress_unit
    spoken = spoken_quantity(current.value, unit)
    facts = [AllowedFact("saved-set", f"Выполнено {spoken}", "confirmed", current.value, unit,
                         numbers=(current.value,), **common)]
    partial = current.outcome != "completed"
    outcome = "partial" if partial else "full"
    facts.append(AllowedFact("outcome", "План подхода выполнен частично" if partial else "План подхода выполнен",
                             "confirmed", outcome, **common))
    if current.target is not None and current.target_exact:
        facts.append(AllowedFact("target", f"План подхода — {spoken_quantity(current.target, unit)}", "confirmed",
                                 current.target, unit, numbers=(current.target,), **common))
    if current.weight_kg is not None and float(current.weight_kg).is_integer() and current.weight_kg > 0:
        kg = int(current.weight_kg)
        facts.append(AllowedFact("weight", f"Вес {spoken_quantity(kg, 'kg')}", "confirmed", kg, "kg",
                                 numbers=(kg,), **common))
    trigger, clause, locked = ("T37" if partial else "T36"), None, ()
    if comparison.status == "comparable" and comparison.delta is not None:
        previous = current.value - comparison.delta
        if comparison.delta > 0:
            trigger = "T39"
            clause = (f"С тем же весом раньше было {spoken_quantity(previous, unit)}, "
                      f"сегодня {number_words(current.value, UNIT_FORMS[unit][0])}.")
        elif comparison.delta == 0 and not partial:
            trigger = "T40"
            clause = f"Повторили прошлый результат: {spoken}."
        elif comparison.delta < 0 and analysis_opt_in:
            trigger = "T41"
        if clause or trigger == "T41":
            facts.append(AllowedFact("comparison", clause or f"Раньше было {spoken_quantity(previous, unit)}",
                                     "derived-validated", comparison.delta, unit, ("comparison",),
                                     (previous, current.value), **common))
            locked = ("comparison", "saved-set") if clause else ()
    return FactPackage(trigger, tuple(facts), comparison, outcome, clause, locked, history)


@dataclass(frozen=True, slots=True)
class RepSample:
    full: bool
    concentric_s: float | None
    continuous: bool = True


def tempo_aggregate(samples: Sequence[RepSample], *, conditions_unchanged: bool,
                    policy_verified: bool = TEMPO_METRIC_POLICY_VERIFIED) -> AllowedFact | None:
    """Within-set median baseline of first 3 full reps vs last 2–3; None unless every guard holds."""
    if not policy_verified or not conditions_unchanged or any(not s.continuous for s in samples):
        return None
    full = [s.concentric_s for s in samples if s.full and s.concentric_s is not None and 0 < s.concentric_s < 30]
    if len(full) < 5:
        return None
    baseline, recent = statistics.median(full[:3]), statistics.median(full[-3:])
    change = (recent - baseline) / baseline
    if abs(change) < 0.2:
        return None
    claim = "Последние движения были медленнее" if change > 0 else "Последние движения были быстрее"
    return AllowedFact("tempo-aggregate", claim, "derived-validated", "slower" if change > 0 else "faster",
                       permits=("tempo",))
