"""V2 machine telemetry facts: relative, rounded observations of the bar, never of the body.

Source: the browser's rep tracker over the machine's own position/velocity stream (metric-policy-0.3).
Claims are fixed server text; the browser only sends bounded numbers. No percentages or seconds are offered
as speakable numbers: the model says «заметно медленнее», not a figure it cannot verify by ear.
"""

import json

from app.services.coach.facts import AllowedFact

METRIC_POLICY_VERSION = "metric-policy-0.3"
VELOCITY_DROP, VELOCITY_DROP_HARD = 15, 30
FAST_DESCENT, SLOW_DESCENT = 0.7, 1.3
LONG_PAUSE_S = 5.0
PERMITS = ("tempo",)


def parse(raw: object) -> dict | None:
    """Accept the wire dict (or its JSON string, as kept for revalidation) with bounded numeric fields only."""
    if isinstance(raw, str) and len(raw) <= 400:
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, dict):
        return None
    bounds = {"reps": (1, 200), "velocityDropPct": (0, 100), "concentricS": (0.1, 20), "eccentricS": (0.1, 20),
              "longestPauseS": (0, 600)}
    clean: dict = {}
    for key, (low, high) in bounds.items():
        value = raw.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool) and low <= value <= high:
            clean[key] = float(value)
    if isinstance(raw.get("steady"), bool):
        clean["steady"] = raw["steady"]
    return clean or None


def wire(raw: object) -> str | None:
    clean = parse(raw)
    return json.dumps(clean, sort_keys=True) if clean else None


def _fact(fact_id: str, claim: str, value: object, common: dict, *, cue: bool = False) -> AllowedFact:
    return AllowedFact(fact_id, claim, "derived-validated", value, permits=PERMITS + (("movement-cue",) if cue else ()),
                       **{**common, "provenance": "machine-telemetry", "quantity_kind": "measured",
                          "sufficiency": "limited"})


def tempo_claim(metrics: dict) -> tuple[str, str] | None:
    eccentric, concentric = metrics.get("eccentricS"), metrics.get("concentricS")
    if not eccentric or not concentric:
        return None
    ratio = eccentric / concentric
    if ratio < FAST_DESCENT:
        return "fast-descent", "По датчикам тренажёра опускание идёт заметно быстрее подъёма"
    if ratio > SLOW_DESCENT:
        return "slow-descent", "По датчикам тренажёра опускание медленнее подъёма, подконтрольное"
    return "even", "По датчикам тренажёра подъём и опускание идут в одном темпе"


def moment_facts(moment: str, metrics: dict | None, common: dict) -> list[AllowedFact]:
    """In-set moments of the rep tracker (#9–#11, #14)."""
    metrics = metrics or {}
    if moment == "velocity_drop_hard":
        return [_fact("velocity-drop", "По датчикам тренажёра скорость повторений сильно упала: идут самые тяжёлые",
                      "hard", common)]
    if moment == "velocity_drop":
        return [_fact("velocity-drop", "По датчикам тренажёра скорость повторений заметно снизилась", "noticeable", common)]
    if moment == "tempo" and (tempo := tempo_claim(metrics)):
        return [_fact("tempo-ratio", tempo[1], tempo[0], common, cue=tempo[0] == "fast-descent")]
    return []


def set_facts(metrics: dict | None, common: dict) -> list[AllowedFact]:
    """Summary of a finished set for its result line and the review (#28)."""
    if not metrics or metrics.get("reps", 0) < 3:
        return []
    found = []
    drop = metrics.get("velocityDropPct")
    if drop is not None:
        found.append(_fact("set-velocity", "К концу подхода скорость повторений заметно снизилась"
                           if drop >= VELOCITY_DROP else "Скорость повторений держалась до конца подхода",
                           "dropped" if drop >= VELOCITY_DROP else "held", common))
    if (tempo := tempo_claim(metrics)) is not None:
        found.append(_fact("set-tempo", tempo[1].replace("идёт", "шло").replace("идут", "шли"), tempo[0], common,
                           cue=tempo[0] == "fast-descent"))
    if metrics.get("steady") is True:
        found.append(_fact("set-steady", "Повторения шли ровно, в одном ритме от первого до последнего", True, common))
    if metrics.get("longestPauseS", 0) >= LONG_PAUSE_S:
        found.append(_fact("set-pause", "В подходе была длинная пауза между повторениями", True, common))
    return found
