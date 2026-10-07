"""Pre-voice validation of author output. Any failure means local/silence, never a free retry loop."""

import re
from dataclasses import dataclass

from app.services.coach.memory import CoachMemory, words
from app.services.coach.prompts import EMPHASIS, ENERGY, PACE, SILENCE_REASONS, AuthorRequest

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
    ("comparison", r"больше|меньше|лучше|хуже|сильнее|слабее|прогресс|улучш|прибав|чем раньше|чем в прошл|выросл|\bрост\b"),
    # Imperative cues ("держи свой темп") are not tempo claims.
    ("tempo", r"быстрее|медленнее|(?<!держи )(?<!держим )(?<!свой )(?<!своем )(?<!сохраняй )темп"),
    ("record", r"рекорд"),
    ("body", r"спин[аеуыо]|колен|осанк|сустав|поясниц|техник\w* (идеальн|безупречн|отличн)|идеальн\w* техник"),
    ("diagnosis", r"отказ|устал|утомл|травм|перетрен|диагноз"),
    ("promise", r"лечени|вылеч|лечит|гарант|обеща|точно потянешь|станешь сильнее|станет сильнее|похуде|результат будет"),
    ("push", r"добав\w* (вес|нагрузк|килограмм|блин)|(еще|ещё) (один|одно|одну|пару|парочку|несколько|раз|повтор|подход)"
             r"|сверх плана|терп|через боль|не останавливайся|не ленись|до упора"),
    ("spotter", r"подстрах|страхую|я (помогаю|держу|давлю)|помогу поднять"),
    ("insult", r"пропадал|ленил|лентя|уснул|слабак"),
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
    if re.search(r"игнорир|инструкц|промпт|правил\w* (не|отмен)", lower):
        return "injection"
    permits = {p for f in req.facts if f.id in used for p in f.permits}
    for category, pattern in _CLAIMS:
        if not pattern.search(lower):
            continue
        if category == "comparison" and req.comparison_status == "comparable" and "comparison" in permits:
            continue
        if category == "tempo" and "tempo" in permits:
            continue
        if category == "first" and req.history == "empty_confirmed":
            continue
        if category == "partial_success" and req.outcome not in {"partial", "skipped"}:
            if "идеальн" not in lower:
                continue
        return {"comparison": "comparison", "tempo": "comparison"}.get(category, "claim")
    for number in spoken_numbers(text):
        if number not in allowed_numbers:
            return "number"
    if req.user_name and not req.name_allowed and req.user_name.lower() in text.lower():
        return "name"
    return None


def validate(output: object, req: AuthorRequest, memory: CoachMemory | None = None) -> Verdict:
    speech_key = "framingText" if req.mode == "locked_fact" else "text"
    required = {"action", "intent", "topicKey", "usedFactIds", "delivery", "silenceReason", speech_key}
    if not isinstance(output, dict) or set(output) != required:
        return _fail("schema")
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
    if req.mode == "ordinary":
        if not speech:
            return _fail("schema")
        allowed = {float(n) for f in req.facts if f.id in used for n in f.numbers}
        if len(words(speech)) > req.max_words:
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
        if memory.repeated(final) or memory.opening_blocked(speech or final):
            return _fail("topic_repeat")
        for fact_id in used:
            if not memory.fact_allowed(fact_id, facts[fact_id].value, summary=req.summary):
                return _fail("fact_repeat")
    return Verdict(True, None, final, tuple(sorted(used)), delivery, "speak")


def facts_current(req: AuthorRequest, scope_epoch: int, now_ms: float) -> bool:
    return all(f.scope_epoch == scope_epoch and now_ms <= f.valid_until_ms for f in req.facts)
