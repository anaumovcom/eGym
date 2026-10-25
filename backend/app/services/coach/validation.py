"""Pre-voice validation of author output. Any failure means local/silence, never a free retry loop."""

import re
from dataclasses import dataclass, replace

from app.services.coach import expressive
from app.services.coach.facts import memory_key
from app.services.coach.memory import CoachMemory, words
from app.services.coach.prompts import (
    EMPHASIS,
    ENERGY,
    PACE,
    SILENCE_REASONS,
    VOICE_DIRECTION_CHARS,
    VOICE_SOUNDS,
    VOICE_STRESS,
    AuthorRequest,
)
from app.services.coach.speech_actions import SPEECH_ACTIONS, speech_action

MAX_CHARS = 400

_NUMBER_WORDS: dict[str, int] = {}
for _value, _forms in {
    0: "ноль нуля", 2: "два две двух двум двумя", 3: "три трех трем тремя", 4: "четыре четырех четырем четырьмя",
    5: "пять пяти пятью", 6: "шесть шести шестью", 7: "семь семи семью", 8: "восемь восьми восемью",
    9: "девять девяти девятью", 10: "десять десяти десятью", 11: "одиннадцать одиннадцати",
    12: "двенадцать двенадцати", 13: "тринадцать тринадцати", 14: "четырнадцать четырнадцати",
    15: "пятнадцать пятнадцати", 16: "шестнадцать шестнадцати", 17: "семнадцать семнадцати",
    18: "восемнадцать восемнадцати", 19: "девятнадцать девятнадцати", 20: "двадцать двадцати",
    30: "тридцать тридцати", 40: "сорок сорока", 50: "пятьдесят пятидесяти", 60: "шестьдесят шестидесяти",
    70: "семьдесят семидесяти", 80: "восемьдесят восьмидесяти", 90: "девяносто девяноста", 100: "сто ста",
    200: "двести двухсот", 300: "триста трехсот", 400: "четыреста четырехсот", 500: "пятьсот пятисот",
    600: "шестьсот шестисот", 700: "семьсот семисот", 800: "восемьсот восьмисот", 900: "девятьсот девятисот",
    1000: "тысяча тысячи тысяч тысячу",
}.items():
    for _form in _forms.split():
        _NUMBER_WORDS[_form] = _value
_ONE = {"один", "одна", "одно", "одну", "одного", "одной", "одному"}
_UNIT_NOUN = re.compile(r"^(повтор|подход|секунд|минут|килограмм|кг|раз$|кило)")
_DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
_ALLOWED_CHARS = re.compile(r"^[а-яёА-ЯЁ0-9\s.,!:;—–\-«»\"'()…]*$")
_CAPS = re.compile(r"\b[А-ЯЁ]{3,}\b")

# (category, pattern). Categories with a permit can pass only when a used fact grants it.
_CLAIMS: tuple[tuple[str, re.Pattern], ...] = tuple((c, re.compile(p)) for c, p in (
    ("comparison", r"больше|меньше|лучше|хуже|сильнее|слабее|прогресс|улучш|прибав|раньше|вчера|обычно|по сравнению|прошл\w* раз|выросл|\bрост\b"),
    # Imperative cues ("держи свой темп") are not tempo claims.
    ("tempo", r"быстрее|медленнее|(?<!держи )(?<!держим )(?<!свой )(?<!своем )(?<!сохраняй )темп"),
    ("record", r"рекорд"),
    ("body", r"спин[аеуыо]|колен|осанк|сустав|поясниц|техник\w* (идеальн|безупречн|отличн)|идеальн\w* техник"),
    ("diagnosis", r"отказ|устал|утомл|травм|перетрен|диагноз"),
    ("promise", r"лечени|вылеч|лечит|гарант|обеща|точно потянешь|станешь сильнее|станет сильнее|похуде|результат будет"),
    ("push", r"добав\w* (вес|нагрузк|килограмм|блин)|(еще|ещё) (один|одно|одну|пару|парочку|несколько|раз|повтор|подход)"
             r"|сверх плана|терп|через боль|не останавливайся|не ленись|до упора|любой ценой|через не могу|без права на паузу"),
    ("spotter", r"подстрах|страхую|я (помогаю|держу|давлю)|помогу поднять"),
    # Friendly-roast vocabulary: allowed only when the user enabled roasting (AuthorRequest.roast).
    ("insult", r"пропадал|ленил|лентя|уснул|слабак|слабач|слабеньк|размазн|позор|тряпк"),
    # Never allowed, roast or not: worth as a person and body shaming.
    ("degrade", r"неудачник|никчем|ничтожеств|жиртрест|жирдя|толстя|толстух|пузат|дрищ|урод"),
    ("first", r"впервые|перв\w* (тренировк|раз)"),
    ("partial_success", r"(весь|полностью|целиком) (план|подход)|план выполнен|вс[её] выполнено|идеальн"),
))


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    reason: str | None = None
    speech: str = ""
    used_fact_ids: tuple[str, ...] = ()
    delivery: dict | None = None
    action: str = "silence"


def _fail(reason: str) -> Verdict:
    return Verdict(False, reason)


def spoken_numbers(text: str) -> list[float]:
    tokens = words(text)
    found: list[float] = [float(m.replace(",", ".")) for m in _DIGITS.findall(text)]
    total = current = 0
    active = False
    for index, token in enumerate(tokens):
        value = _NUMBER_WORDS.get(token)
        if value is None and token in _ONE and index + 1 < len(tokens) and _UNIT_NOUN.match(tokens[index + 1]):
            value = 1
        if value is None:
            if active:
                found.append(float(total + current))
            total = current = 0
            active = False
            continue
        active = True
        if value == 1000:
            total += max(current, 1) * 1000
            current = 0
        else:
            current += value
    if active:
        found.append(float(total + current))
    return found


_NUM_TOKEN = r"(?:\d+(?:[.,]\d+)?|" + "|".join(sorted((*_NUMBER_WORDS, *_ONE), key=len, reverse=True)) + r")"
_NUM_SPAN = re.compile(r"\b" + _NUM_TOKEN + r"(?:\s+" + _NUM_TOKEN + r")*\b")
_UNITS = re.compile(r"^\s*(повтор\w*|раз\b|секунд\w*|минут\w*|килограмм\w*|кг\b|кило\b|подход\w*|упражнен\w*)")
_PLAN = r"по плану|планов\w*|план\b|цель\w*|заявлен\w*"
_OBSERVED = r"выполн\w*|сделан\w*|сделал\w*|запис\w*|засчит\w*|поднят\w*|поднял\w*|измер\w*|фактическ\w*"
_ROLE = re.compile(r"(?P<plan>" + _PLAN + r")|(?P<observed>" + _OBSERVED
                   + r")|(?P<remaining>остал\w*|остает\w*|до конца)|(?P<elapsed>прошло|на таймере)")


def _unit(label: str) -> str:
    for prefix, unit in (("повтор", "reps"), ("раз", "reps"), ("секунд", "seconds"), ("минут", "minutes"),
                         ("кил", "kg"), ("кг", "kg"), ("подход", "sets"), ("упражнен", "exercises")):
        if label.startswith(prefix):
            return unit
    return "text"


def _number_value(span: str) -> float:
    if _DIGITS.fullmatch(span):
        return float(span.replace(",", "."))
    total = current = 0
    for token in span.split():
        value = _NUMBER_WORDS.get(token, 1)
        if value == 1000:
            total += max(current, 1) * 1000
            current = 0
        else:
            current += value
    return float(total + current)


def _number_associations(text: str, req: AuthorRequest, used: set[str]) -> bool:
    """Check each quantity against ONE used fact, its unit and declared/observed role.

    Not a general Russian theorem prover: unsupported/ambiguous statistics fail closed.
    App-owned locked clauses bypass this; their framing still cannot add numbers.
    """
    facts = [f for f in req.facts if f.id in used]
    for clause in re.split(r"(?<!\d)[.,;!:](?!\d)|[;!:]", text):
        spans = list(_NUM_SPAN.finditer(clause))
        for index, match in enumerate(spans):
            number = _number_value(match.group())
            suffix = clause[match.end():]
            unit_match = _UNITS.match(suffix)
            unit = _unit(unit_match[1]) if unit_match else None
            values = (number,)
            # A range is one quantity: both endpoints, original order, same fact/unit/role.
            if suffix.lstrip().startswith("до ") and index + 1 < len(spans):
                following = spans[index + 1]
                if clause[match.end():following.start()].strip() == "до":
                    values = (number, _number_value(following.group()))
                    unit_match = _UNITS.match(clause[following.end():])
                    unit = _unit(unit_match[1]) if unit_match else None
            prefix = clause[:match.start()]
            roles = list(_ROLE.finditer(prefix))
            role = roles[-1].lastgroup if roles else None
            if role is None:
                after = _ROLE.search(suffix)
                role = after.lastgroup if after else None
                # A confirmed result followed by its separate outcome is not a
                # plan quantity: «Десять повторений — план подхода выполнен».
                # Keep this deliberately narrow; partial/limited and kg never gain it.
                if (role == "plan" and req.outcome == "full" and unit in {"reps", "seconds"}
                        and any(f.id == "outcome" and f.value == "full" for f in facts)
                        and re.match(r"^\s*(?:повтор\w*|раз|секунд\w*)\s*[—–-]\s*план(?:\s+подхода)?\s+выполнен\b", suffix)):
                    role = "observed"
            # «с половиной» is a real fractional quantity, not a free extra integer.
            if re.match(r"\s+с половиной\b", suffix):
                values = (number + .5,)
                unit_match = _UNITS.match(re.sub(r"^\s+с половиной", "", suffix))
                unit = _unit(unit_match[1]) if unit_match else None
            # «одна мысль» is not a statistic; do not turn conversational one into a number.
            if match.group() in _ONE and not unit and role is None:
                continue
            supported = False
            for fact in facts:
                if not all(n in fact.numbers for n in values):
                    continue
                if len(values) == 2 and tuple(fact.numbers) != values:
                    continue
                if unit and fact.unit != unit:
                    continue
                declared = (fact.quantity_kind == "declared" or fact.id == "target"
                            or fact.id.startswith(("plan-", "planned-")))
                if role == "observed" and declared or role == "plan" and not declared:
                    continue
                # A stored total/plan is not the running clock or a live remainder.
                if role == "remaining" and fact.id not in {"sets-left", "exercises-left"}:
                    continue
                if role == "elapsed":
                    continue  # No current request supplies a verified live elapsed-time fact.
                if declared and fact.unit == "kg" and role != "plan":
                    continue
                supported = True
                break
            if not supported:
                return False
    return True


def _claim_surface(lower: str, req: AuthorRequest) -> str:
    # Narrow grammatical negatives/idioms only. Never erase a whole sentence:
    # «не добавляй вес, но терпи» must still fail on the second clause.
    surface = re.sub(r"\bлучше (?=спокойно\b|без спешки\b)", "", lower)
    surface = re.sub(r"\b(?:сильнее|больше) (?:— )?не значит лучше\b", "", surface)
    surface = re.sub(r"\bбольше не спешим\b", "не спешим", surface)
    surface = re.sub(r"\bне нужно терпеть боль\b", "", surface)
    surface = re.sub(r"\bне добавляй (?:вес|нагрузку)(?: сверх плана)?\b", "", surface)
    if req.outcome in {"partial", "skipped", "limited"}:
        surface = re.sub(r"\bплан выполнен (?:не полностью|частично)\b", "", surface)
        surface = re.sub(r"\b(?:весь )?план (?:пока )?не выполнен(?: полностью)?\b", "", surface)
    return surface


def _check_text(text: str, req: AuthorRequest, used: set[str], *, allowed_numbers: set[float]) -> str | None:
    if len(text) > MAX_CHARS or "\n" in text:
        return "length"
    if re.search(r"[<>{}`\[\]#*_|~]|ignore|system|assistant|developer", text, re.I):
        return "injection"
    if "?" in text:
        return "question"
    if re.search(r"[a-zA-Z]", text) or not re.search(r"[а-яёА-ЯЁ]", text) or not _ALLOWED_CHARS.match(text):
        return "language"
    if text.count("!") > 1 or _CAPS.search(text):
        return "shouting"
    lower = text.lower().replace("ё", "е")
    catalog_setup = (req.task == "setup/technique" and req.phase == "setup" and req.coach_context
                     and req.coach_context.setup_guidance and used
                     and used <= {key for key, _ in req.coach_context.setup_guidance}
                     and all(f.provenance == "exercise-catalog-instructions" for f in req.facts if f.id in used))
    if req.coach_context and re.search(r"я вижу|я замет|у тебя|ты (?:неправильно|слишком)|твоя (?:спина|техника)", lower):
        return "claim"
    if req.coach_context and not catalog_setup and re.search(r"плеч|локт|запяст|наклон|хват|лопат|выпрям|согни", lower):
        return "claim"
    measured_cue = any("movement-cue" in f.permits for f in req.facts if f.id in used)
    if req.coach_context and req.phase == "active" and not measured_cue and re.search(
            r"дыш|вдох|выдох|двигай|плавн|рывк|тян[иь]|опускай|поднимай", lower):
        if req.coach_context.tip is None or text != req.coach_context.tip.text:
            return "unreviewed_tip"
    if not req.say_numbers and spoken_numbers(text):
        return "number"
    if re.search(r"игнорир|инструкц|промпт|правил\w* (не|отмен)", lower):
        return "injection"
    permits = {p for f in req.facts if f.id in used for p in f.permits}
    claim_surface = _claim_surface(lower, req)
    for category, pattern in _CLAIMS:
        if not pattern.search(claim_surface):
            continue
        if catalog_setup and category in {"body", "tempo"}:
            continue  # Prescriptive catalog cue only; no permission during effort.
        if category == "comparison" and req.comparison_status == "comparable" and "comparison" in permits:
            continue
        # V3: a server-verified record may name itself and its own «раньше было не больше …» comparison.
        if category == "record" and "record" in permits:
            continue
        if category == "comparison" and "record-comparison" in permits:
            continue
        if category == "tempo" and "tempo" in permits:
            continue
        if category == "first" and req.history == "empty_confirmed":
            continue
        if category == "insult" and req.roast and req.outcome not in {"partial", "skipped", "limited"}:
            continue
        if category == "partial_success" and req.outcome not in {"partial", "skipped", "limited"}:
            if "идеальн" not in lower:
                continue
        return {"comparison": "comparison", "tempo": "comparison"}.get(category, "claim")
    if req.outcome in {"partial", "skipped", "limited"} and re.search(
            r"все подходы (выполнены|завершены|закрыты)|все упражнения (выполнены|завершены|закрыты)", lower):
        return "claim"
    declared_weight = any(f.id == "weight" and f.quantity_kind == "declared" for f in req.facts)
    if declared_weight and re.search(r"измеренн|измерен|фактическ\w* (вес|нагрузк)|примененн\w* (вес|нагрузк)", lower):
        return "claim"
    if re.search(r"(весь|полностью|целиком) план|вся тренировк\w* (выполнена|завершена)|все упражнения выполнены", claim_surface):
        if "workout-plan-complete" not in permits:
            return "claim"
    if re.search(r"все подходы (выполнены|завершены|закрыты)", lower) and "exercise-plan-complete" not in permits:
        return "claim"
    partial_movement = any(f.id == "milestone" and f.value == "partial" for f in req.facts)
    if partial_movement and "counter-reason" not in permits and re.search(r"амплитуд|потому что|из-за|причин", lower):
        return "claim"
    for number in spoken_numbers(text):
        if number not in allowed_numbers:
            return "number"
    if not _number_associations(lower, req, used):
        return "number"
    if req.user_name and not req.name_allowed and req.user_name.lower() in text.lower():
        return "name"
    return None


_DIRECTION = re.compile(r"^[а-яёА-ЯЁ ,\-]*$")


def voice_block(raw: object) -> dict | None:
    """Stage directions for the voice engine. Never spoken as words, so never part of the fact checks.

    V6 adds optional per-sentence `segments` (expressive.Segment); the legacy three keys stay valid alone."""
    if not isinstance(raw, dict) or set(raw) not in ({"direction", "sound", "stress"}, {"direction", "sound", "stress", "segments"}):
        return None
    segments: tuple = ()
    if "segments" in raw:
        if not isinstance(raw["segments"], list) or len(raw["segments"]) > expressive.MAX_SEGMENTS:
            return None
        parsed = [expressive.segment_from(item) for item in raw["segments"]]
        if any(item is None for item in parsed):
            return None
        segments = tuple(parsed)
    direction, sound, stress = raw["direction"], raw["sound"], raw["stress"]
    if (not isinstance(direction, str) or len(direction) > VOICE_DIRECTION_CHARS or not _DIRECTION.match(direction)
            or re.search(r"игнорир|инструкц|промпт|правил", direction.lower())
            or sound not in VOICE_SOUNDS or stress not in VOICE_STRESS):
        return None
    return {"direction": " ".join(direction.split()), "sound": sound, "stress": stress,
            **({"segments": segments} if segments else {})}


def validate(output: object, req: AuthorRequest, memory: CoachMemory | None = None) -> Verdict:
    speech_key = "framingText" if req.mode == "locked_fact" else "text"
    required = {"action", "intent", "topicKey", "usedFactIds", "delivery", "silenceReason", speech_key}
    if req.voice_markup:
        required.add("voice")
    if not isinstance(output, dict) or set(output) != required:
        return _fail("schema")
    voice = voice_block(output["voice"]) if req.voice_markup else {}
    if voice is None:
        return _fail("voice")
    action, intent, topic = output["action"], output["intent"], output["topicKey"]
    used_raw, delivery, silence, speech = output["usedFactIds"], output["delivery"], output["silenceReason"], output[speech_key]
    if action not in {"speak", "silence"} or intent not in req.intents or topic != req.topic_key:
        return _fail("schema")
    if not isinstance(used_raw, list) or not all(isinstance(x, str) for x in used_raw) or len(set(used_raw)) != len(used_raw):
        return _fail("schema")
    if not isinstance(speech, str) or not isinstance(delivery, dict) or set(delivery) != {"energy", "pace", "emphasis"}:
        return _fail("schema")
    if delivery["energy"] not in ENERGY or delivery["pace"] not in PACE or delivery["emphasis"] not in EMPHASIS:
        return _fail("schema")
    facts = {f.id: f for f in req.facts}
    used = set(used_raw)
    if not used <= set(facts):
        return _fail("facts")
    if action == "silence":
        if speech or used or silence not in SILENCE_REASONS:
            return _fail("schema")
        return Verdict(True, silence, "", (), delivery, "silence")
    if silence is not None:
        return _fail("schema")
    speech = speech.strip()
    if req.task == "setup/technique":
        guidance = req.coach_context.setup_guidance if req.coach_context else ()
        if not guidance or not used or not used <= {key for key, _ in guidance}:
            return _fail("unreviewed_tip")
    if req.coach_context and req.task in {"active/general-tip", "rest/general-tip"}:
        tip = req.coach_context.tip
        if tip is None or speech != tip.text or used != {"reviewed-tip"}:
            return _fail("unreviewed_tip")
    if intent == "humor" and (req.humor == "off" or req.phase == "paused"
                              or req.coach_context and req.coach_context.risk):
        return _fail("claim")
    if req.mode == "ordinary":
        if not speech:
            return _fail("schema")
        allowed = {float(n) for f in req.facts if f.id in used for n in f.numbers}
        policy = SPEECH_ACTIONS[speech_action(req.task)]
        limit = min(req.max_words, policy.max_words, 16 if req.phase == "active" else 60)
        if len(words(speech)) > limit:
            return _fail("length")
        if reason := _check_text(speech, req, used, allowed_numbers=allowed):
            return _fail(reason)
        final = speech
    else:
        if not set(req.locked_fact_ids) <= used:
            return _fail("facts")
        # The app speaks the server-authored clause itself; a verbatim echo of it is dropped, never re-checked as new numbers.
        if req.locked_clause and speech.startswith(req.locked_clause):
            speech = speech[len(req.locked_clause):].strip()
        if speech and (reason := _check_text(speech, req, used, allowed_numbers=set())):
            return _fail(reason)
        if len(words(speech)) > req.max_words:
            return _fail("length")
        final = f"{req.locked_clause} {speech}".strip()
    if len(used) > 2 + len(req.locked_fact_ids):
        return _fail("facts")
    if memory is not None:
        if intent == "humor" and not memory.humor_allowed():
            return _fail("humor_streak")
        if (req.category and intent in {"humor", "motivation"}
            and memory.combination_blocked(req.category, intent, delivery["energy"])):
            return _fail("diversity")
        tip = req.coach_context.tip if req.coach_context else None
        if "reviewed-tip" in used and tip and memory.tip_completed(tip.tip_id, tip.version):
            return _fail("tip_repeat")
        # Different exercises can need the same ordinary opening («Держи корпус»).
        # Preserve exact-text/fact/topic dedup, not a two-word veto on useful setup.
        if "reviewed-tip" not in used and (memory.repeated(final) or (
            req.task != "setup/technique" and memory.opening_blocked(speech or final))):
            return _fail("topic_repeat")
        for fact_id in used:
            if fact_id == "reviewed-tip":
                continue  # Semantic completion, not a partial start, explains a tip.
            if not memory.fact_allowed(memory_key(facts[fact_id]), facts[fact_id].value, summary=req.summary):
                return _fail("fact_repeat")
    if voice and voice.get("segments"):
        # Palette of this moment (humor/roast/mood) and tags only on exact fragments of the spoken text.
        context = expressive.VoiceContext(humor=intent == "humor" and req.humor != "off", roast=req.roast,
                                          mood=(req.mood or {}).get("name", ""))
        voice = {**voice, "segments": tuple(
            expressive.allowed(replace(seg, tags=tuple(t for t in seg.tags if t[0] in final)), context)
            for seg in voice["segments"])}
    return Verdict(True, None, final, tuple(sorted(used)), {**delivery, **voice}, "speak")


def facts_current(req: AuthorRequest, scope_epoch: int, now_ms: float) -> bool:
    return all(f.scope_epoch == scope_epoch and now_ms <= f.valid_until_ms for f in req.facts)
