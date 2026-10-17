"""Server fact builder: spoken numbers, history comparison policy and validated aggregates only."""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

Gender = Literal["m", "f", "n"]
ComparisonStatus = Literal["comparable", "limited", "unavailable"]
HistoryStatus = Literal["available", "limited", "unavailable", "empty_confirmed"]

METRIC_POLICY_VERSION = "metric-policy-0.2"
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
    "exercises": ("n", "упражнение", "упражнения", "упражнений"),
    "minutes": ("f", "минута", "минуты", "минут"),
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
    # Source record ("set:12", "exercise:3"): equal values of different sets are different facts for memory.
    ref: str = ""
    provenance: str = "unspecified"
    quantity_kind: Literal["declared", "applied", "measured", "derived", "unspecified"] = "unspecified"
    observed_at_ms: float | None = None
    sufficiency: Literal["sufficient", "limited", "unknown"] = "unknown"

    def __post_init__(self):
        if self.id in FORBIDDEN_METRICS:
            raise ValueError("Unvalidated metric cannot become a speech fact")
        if not self.claim or len(self.claim) > 200:
            raise ValueError("Invalid fact claim")
        if len(self.provenance) > 120 or len(self.unit) > 32 or len(self.ref) > 200:
            raise ValueError("Unbounded fact provenance")
        if self.observed_at_ms is not None and (not math.isfinite(self.observed_at_ms)
                                               or not 0 <= self.observed_at_ms <= 10**15):
            raise ValueError("Invalid fact timestamp")


def memory_key(fact: AllowedFact) -> str:
    return f"{fact.id}@{fact.ref}" if fact.ref else fact.id


def weight_fact(kg: float | None, *, fact_id: str = "weight", prefix: str = "Вес", **common) -> AllowedFact | None:
    """Whole or half kilograms only (machine resolution); anything else is not a speakable fact."""
    if kg is None or isinstance(kg, bool) or not 0 < kg <= 1000:
        return None
    steps = round(kg / WEIGHT_RESOLUTION_KG)
    if abs(steps * WEIGHT_RESOLUTION_KG - kg) > 1e-6:
        return None
    whole, half = divmod(steps, 2)
    if not whole:
        return None
    if half:
        return AllowedFact(fact_id, f"{prefix} {number_words(whole)} с половиной килограмма", "confirmed", whole + 0.5,
                           "kg", numbers=(whole + 0.5, whole), **common)
    return AllowedFact(fact_id, f"{prefix} {spoken_quantity(whole, 'kg')}", "confirmed", whole, "kg",
                       numbers=(whole,), **common)


def target_fact(low: int | None, high: int | None, unit: str, *, prefix: str = "План подхода —",
                **common) -> AllowedFact | None:
    if type(high) is not int or not 0 < high <= 1000:
        return None
    if low is None or low == high:
        return AllowedFact("target", f"{prefix} {spoken_quantity(high, unit)}", "confirmed", high, unit,
                           numbers=(high,), **common)
    if type(low) is not int or not 0 < low < high:
        return None
    return AllowedFact("target", f"{prefix} от {low} до {high} {UNIT_FORMS[unit][3]}", "confirmed", f"{low}-{high}",
                       unit, numbers=(low, high), **common)


@dataclass(frozen=True, slots=True)
class SetResult:
    set_id: str
    user_id: str
    exercise_slug: str
    progress_unit: Literal["reps", "seconds"]
    set_type: Literal["warmup", "working"] | None
    ordinal: int
    value: int | None
    outcome: Literal["completed", "partial", "skipped", "aborted", "unknown"]
    confirmed: bool = True
    target: int | None = None
    target_exact: bool = True
    weight_kg: float | None = None
    load_mode: str | None = None
    range_id: str | None = None
    calibration_id: str | None = None
    count_method: str | None = None
    target_min: int | None = None
    exercise_kind: str | None = None
    # Analytics weight_kg is a declared plan, NOT measured force or applied setting.
    applied_weight_kg: float | None = None
    measured_weight_kg: float | None = None
    observed_at_ms: float | None = None
    load_profile_id: str | None = None
    target_open: bool = False


@dataclass(frozen=True, slots=True)
class Comparison:
    status: ComparisonStatus
    delta: int | None = None
    previous_set_id: str | None = None
    differences: tuple[str, ...] = ()
    policy: str = METRIC_POLICY_VERSION


def _weight_step(value: float | None) -> int | None:
    return (round(value / WEIGHT_RESOLUTION_KG)
            if type(value) in {int, float} and math.isfinite(value) and 0 < value <= 1000 else None)


def _known(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.lower() not in {
        "unknown", "unavailable", "none", "null", "n/a", "not_applicable"}


def target_met(result: SetResult) -> bool:
    """A completion label alone cannot override a missed or unknown target."""
    if result.target_open:
        return (result.confirmed and result.outcome == "completed" and type(result.value) is int and result.value > 0
                and result.target is None and result.target_min is None)
    minimum = result.target if result.target_exact else result.target_min
    return (result.confirmed and result.outcome == "completed" and type(result.value) is int
            and type(minimum) is int and minimum > 0 and result.value >= minimum
            and (result.target_exact or (type(result.target) is int and result.target >= minimum)))


def compare(current: SetResult, previous: SetResult | None, history: HistoryStatus) -> Comparison:
    if history in {"unavailable", "empty_confirmed"} or previous is None or previous.set_id == current.set_id:
        return Comparison("unavailable")
    if (previous.user_id, previous.exercise_slug, previous.progress_unit) != (
            current.user_id, current.exercise_slug, current.progress_unit):
        return Comparison("unavailable")
    checks = {
        "exercise_kind": current.exercise_kind in {"machine", "bodyweight", "timed", "stretch"}
                         and previous.exercise_kind == current.exercise_kind,
        "set_type": current.set_type in {"warmup", "working"} and previous.set_type == current.set_type,
        "ordinal": current.ordinal > 0 and previous.ordinal == current.ordinal,
        "load_mode": _known(current.load_mode) and previous.load_mode == current.load_mode,
        "weight": _weight_step(current.weight_kg) is not None
                  and _weight_step(previous.weight_kg) == _weight_step(current.weight_kg),
        "range": _known(current.range_id) and previous.range_id == current.range_id,
        "calibration": _known(current.calibration_id) and previous.calibration_id == current.calibration_id,
        "count_method": _known(current.count_method) and previous.count_method == current.count_method,
        "confirmed": previous.confirmed and current.confirmed
                 and type(previous.value) is int and 0 <= previous.value < 1_000_000
                 and type(current.value) is int and 0 <= current.value < 1_000_000,
        "outcome": previous.outcome == "completed" and current.outcome in {"completed", "partial"}
               and (previous.target is None or target_met(previous)),
    }
    if (current.exercise_kind == "machine" and _known(current.load_mode)
            and current.load_mode == previous.load_mode != "constant"):
        # Dynamic modes need the same complete settings profile (eccentric ratio,
        # assistance/speed etc.), not merely the same mode name and base weight.
        checks["load_profile"] = _known(current.load_profile_id) and previous.load_profile_id == current.load_profile_id
    if current.exercise_kind in {"bodyweight", "timed", "stretch"}:
        allowed_modes = {"bodyweight", "unloaded", "external"}
        if current.exercise_kind == "stretch":
            allowed_modes.add("stretch")
        checks["kind_mode"] = current.load_mode in allowed_modes
        # Non-machine calibration is explicitly inapplicable by policy, not null equality.
        checks["calibration"] = previous.exercise_kind == current.exercise_kind
        # Only explicitly unloaded protocols make load inapplicable. Weighted timed
        # or bodyweight variants still require a known declared weight.
        if current.load_mode in {"bodyweight", "unloaded", "stretch"}:
            checks["weight"] = previous.load_mode == current.load_mode and all(
                weight is None or (type(weight) in {int, float} and weight == 0)
                for weight in (current.weight_kg, previous.weight_kg))
    # Optional measured/applied quantities never silently substitute for the plan.
    for name in ("applied_weight_kg", "measured_weight_kg"):
        a, b = getattr(current, name), getattr(previous, name)
        if a is not None or b is not None:
            checks[name] = _weight_step(a) is not None and _weight_step(a) == _weight_step(b)
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
    source_signature: str = ""


def saved_set_facts(current: SetResult, comparison: Comparison, *, scope_epoch: int, valid_until_ms: float,
                    history: HistoryStatus = "unavailable", analysis_opt_in: bool = False, ref: str = "") -> FactPackage:
    if not current.confirmed:
        raise ValueError("Only saved acknowledged results build facts")
    common = {"scope_epoch": scope_epoch, "valid_until_ms": valid_until_ms, "ref": ref,
              "provenance": "persisted-result", "observed_at_ms": current.observed_at_ms,
              "sufficiency": "sufficient"}
    if current.outcome == "skipped":
        return FactPackage("T38", (AllowedFact("outcome", "Подход пропущен", "confirmed", "skipped", **common),),
                           Comparison("unavailable"), "skipped", history=history)
    if type(current.value) is not int or not 0 <= current.value < 1_000_000:
        raise ValueError("Confirmed result value required")
    unit = current.progress_unit
    spoken = spoken_quantity(current.value, unit)
    facts = [AllowedFact("saved-set", f"Выполнено {spoken}", "confirmed", current.value, unit,
                         numbers=(current.value,), **common)]
    partial = (current.value == 0 or current.outcome in {"partial", "aborted"}
               or (current.outcome == "completed" and current.target is not None and not target_met(current)))
    outcome = "partial" if partial else "full" if target_met(current) else "limited"
    claim = ("План подхода выполнен частично" if partial else "Подход завершён без фиксированной цели"
             if current.target_open and target_met(current) else "План подхода выполнен"
             if target_met(current) else "Подход сохранён; фиксированная цель не подтверждена")
    facts.append(AllowedFact("outcome", claim, "derived-validated", outcome,
                             **{**common, "quantity_kind": "derived",
                                "sufficiency": "limited" if outcome == "limited" else "sufficient"}))
    if current.target is not None and (current.target_exact or current.target_min is not None):
        low = current.target if current.target_exact else current.target_min
        if (target := target_fact(low, current.target, unit,
                      **{**common, "provenance": "persisted-plan", "quantity_kind": "declared"})) is not None:
            facts.append(target)
    if (weight := weight_fact(current.weight_kg, prefix="Плановый вес", quantity_kind="declared",
                             **{**common, "provenance": "persisted-plan"})) is not None:
        facts.append(weight)
    trigger, clause, locked = ("T37" if partial else "T36"), None, ()
    if comparison.status == "comparable" and comparison.delta is not None:
        previous = current.value - comparison.delta
        if comparison.delta > 0:
            trigger = "T39"
            conditions = "При том же плановом весе" if current.weight_kg is not None else "При тех же условиях"
            clause = (f"{conditions} раньше было {spoken_quantity(previous, unit)}, "
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
