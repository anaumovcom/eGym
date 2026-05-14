"""
Переводит значения полей упражнений в exercises/**/*.json на русский язык
через Ollama translategemma. Каждый файл переводится целиком и последовательно,
без кэша. Поля male_videos, female_videos, youtube_url пропускаются.
Оригинальное название упражнения сохраняется в поле name (английский),
русский перевод названия добавляется в поле name_ru.
"""

import json
import pathlib
import re
import sys
import urllib.request
import csv

ROOT = pathlib.Path(__file__).parent / "exercises"
NAME_TRANSLATIONS_CSV = pathlib.Path(__file__).parent / "exercise_name_translations.csv"
MODEL = "translategemma"
EXCLUDED_KEYS = {"male_videos", "female_videos", "youtube_url", "muscles"}
TRANSLATABLE_KEYS = {"steps", "guide"}

# ── вспомогательные функции ────────────────────────────────────────────────────

def iter_strings(obj, parent_key=None, should_translate: bool = False):
    """Обходит структуру упражнения и возвращает строки из steps/guide, требующие перевода."""
    if parent_key in EXCLUDED_KEYS:
        return
    if parent_key in TRANSLATABLE_KEYS:
        should_translate = True
    if isinstance(obj, str):
        if should_translate and obj and obj.lower() not in SKIP_VALUES:
            yield obj
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_strings(item, parent_key, should_translate)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from iter_strings(value, key, should_translate)


SKIP_VALUES = {"none", "n/a", ""}


def apply_translations(obj, translations: dict, parent_key=None, should_translate: bool = False):
    """Подставляет переводы только в steps/guide."""
    if parent_key in EXCLUDED_KEYS:
        return obj
    if parent_key in TRANSLATABLE_KEYS:
        should_translate = True
    if isinstance(obj, str):
        if should_translate and obj and obj.lower() not in SKIP_VALUES:
            return translations.get(obj, obj)
        return obj
    if isinstance(obj, list):
        return [apply_translations(item, translations, parent_key, should_translate) for item in obj]
    if isinstance(obj, dict):
        return {key: apply_translations(value, translations, key, should_translate) for key, value in obj.items()}
    return obj

# ── Ollama ─────────────────────────────────────────────────────────────────────

def ollama_generate(prompt: str, json_format: bool = False, timeout: int = 900) -> str:
    payload: dict = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 12000},
    }
    if json_format:
        payload["format"] = "json"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))["response"]


def parse_json_object(text: str) -> dict:
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        result = json.loads(match.group(0))
    if not isinstance(result, dict):
        raise ValueError("Ожидался JSON-объект от модели")
    return result


# Словарь точных переводов коротких категориальных значений
FIXED_TRANSLATIONS = {
    "Beginner": "Начинающий",
    "Novice": "Для начинающих",
    "Intermediate": "Средний уровень",
    "Advanced": "Продвинутый",
    "Expert": "Эксперт",
    "Push": "Толкающее",
    "Pull": "Тянущее",
    "Static": "Статическое",
    "Compound": "Базовое",
    "Isolation": "Изолированное",
    "Overhand": "Прямой хват",
    "Underhand": "Обратный хват",
    "Neutral": "Нейтральный хват",
    "Hammer": "Молотковый хват",
    "Pronated": "Пронированный хват",
    "Supinated": "Супинированный хват",
    "Stretches": "Растяжка",
    "Cardio": "Кардио",
    "Band": "Резиновая лента",
    "Barbell": "Штанга",
    "Dumbbell": "Гантели",
    "Kettlebell": "Гиря",
    "Cable": "Блочный тренажёр",
    "Machine": "Тренажёр",
    "Bodyweight": "Вес тела",
    "EZ Bar": "EZ-штанга",
    "Foam Roll": "Массажный ролик",
}


def translate_single(text: str) -> str:
    if text in FIXED_TRANSLATIONS:
        return FIXED_TRANSLATIONS[text]
    prompt = (
        "You are translating a fitness exercise database field value from English to Russian.\n"
        "The value may be a short category label (e.g. difficulty, equipment, muscle name) "
        "or a full instruction sentence.\n"
        "Rules:\n"
        "- Return ONLY the Russian translation of the given text.\n"
        "- Do NOT add explanations, comments, or extra text.\n"
        "- Do NOT translate proper names (Bosu, Smith, Pilates, EZ).\n"
        "- For muscle names use anatomical Russian terms (бицепс, трицепс, квадрицепс, etc.).\n"
        "- Keep numbers, units and file names unchanged.\n"
        f"Text to translate: {text}"
    )
    response = ollama_generate(prompt, json_format=False).strip()
    response = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", response).strip()
    if len(response) >= 2 and response[0] == response[-1] and response[0] in {'"', "'"}:
        response = response[1:-1].strip()
    return response or text


def translate_name_with_context(name: str, translated_data: dict) -> str:
    """Переводит название упражнения, передавая модели переведённый контекст из файла."""
    muscles = translated_data.get("muscles", [])
    muscles_str = ", ".join(muscles) if muscles else "—"
    equipment = translated_data.get("equipment", "")
    steps = translated_data.get("steps", [])
    steps_str = " ".join(steps[:3]) if steps else ""

    prompt = (
        "You are a professional fitness translator. Translate the English exercise name to Russian.\n"
        "\n"
        "TERMINOLOGY GLOSSARY (always use these exact translations):\n"
        "\n"
        "BASIC MOVEMENTS:\n"
        "  curl=сгибание, press=жим, raise=подъём, row=тяга, fly=разведение,\n"
        "  extension=разгибание (EXCEPTION: back extension=гиперэкстензия),\n"
        "  squat=приседание, lunge=выпад, deadlift=становая тяга,\n"
        "  crunch=скручивание, hip thrust=ягодичный мост, kickback=отведение назад,\n"
        "  pulldown=тяга верхнего блока, pullover=пуловер, shrug=шраги,\n"
        "  plank=планка, stretch=растяжка, hold=удержание,\n"
        "  circle=круговые вращения, rotation=вращение, swing=мах, bridge=ягодичный мост,\n"
        "  dip=отжимание в упоре, push-up=отжимание, sit-up=подъём туловища,\n"
        "  pull-up=подтягивание, chin-up=подтягивание обратным хватом,\n"
        "  hip abduction=отведение бедра, hip adduction=приведение бедра,\n"
        "  calf raise=подъём на носки, tibialis raise=подъём носков\n"
        "\n"
        "NAMED/SPECIALTY MOVEMENTS:\n"
        "  skullcrusher=французский жим, tate press=жим Тейта,\n"
        "  guillotine press=жим «гильотина», larsen press=жим Ларсена,\n"
        "  spider curl=сгибание рук на наклонной скамье лицом вниз,\n"
        "  preacher curl=сгибание рук на скамье Скотта,\n"
        "  concentration curl=концентрированное сгибание рук,\n"
        "  drag curl=сгибание рук вдоль тела, zottman curl=сгибание Зоттмана,\n"
        "  jefferson curl=сгибание позвоночника в висе (Джефферсон), zercher squat=приседание Зерхера,\n"
        "  hack squat=гакк-приседание, sumo squat=приседание сумо, sumo deadlift=становая тяга сумо,\n"
        "  pendlay row=тяга Пендлея, renegade row=тяга гантелей в планке,\n"
        "  upright row=тяга к подбородку, gorilla row=тяга «горилла»,\n"
        "  good morning=наклон с отягощением «доброе утро»,\n"
        "  face pull=тяга к лицу, pallof press=жим Паллофа,\n"
        "  wood chopper=упражнение «дровосек», hip hinge=наклон с прямой спиной,\n"
        "  windmill=«мельница», waiter's bow=поклон официанта,\n"
        "  arnold press=жим Арнольда, y-press=жим Y, z-press=жим Z (сидя на полу),\n"
        "  push press=толчковый жим, thruster=трастер (приседание с жимом),\n"
        "  clean and press=взятие на грудь и жим,\n"
        "  clean and jerk=толчок (взятие на грудь и швунг),\n"
        "  hang clean=взятие на грудь с виса, snatch=рывок,\n"
        "  farmers carry/walk/march=прогулка фермера, suitcase=«чемодан»,\n"
        "  hollow hold=удержание «банан», superman=«супермен»,\n"
        "  russian twist=скручивание с поворотом, side bend=наклон в сторону,\n"
        "  inchworm=упражнение «гусеница», bulgarian split squat=болгарские выпады,\n"
        "  curtsy lunge=выпад-реверанс, step up=подъём на платформу,\n"
        "  knee drive=подъём колена, kickstand=с опорой одной ногой,\n"
        "  quad stomp=топание квадрицепсом\n"
        "\n"
        "GRIP / POSITION descriptors:\n"
        "  rear delt=задняя дельта, silverback=«серебристая спина» (вариант шраг),\n"
        "  bayesian=по Байесу, internal rotation=внутренняя ротация,\n"
        "  external rotation=внешняя ротация, neutral grip=нейтральный хват,\n"
        "  supinated=хват снизу, pronated=хват сверху, close grip=узкий хват,\n"
        "  wide grip=широкий хват, overhand=прямой хват, underhand=обратный хват\n"
        "\n"
        "EQUIPMENT:\n"
        "  band/resistance band=с резиновой лентой, dumbbell=с гантелью,\n"
        "  barbell=со штангой, cable=на блоке, machine=на тренажёре,\n"
        "  bodyweight=(без снаряда), kettlebell=с гирей, ez-bar=с EZ-штангой,\n"
        "  landmine=с грифом в упоре (ландмайн), foam roller=с роликом\n"
        "\n"
        "MODIFIERS:\n"
        "  bilateral=двустороннее, unilateral=одностороннее,\n"
        "  single-arm=одной рукой, single-leg=на одной ноге,\n"
        "  alternating=поочерёдное, kneeling=на коленях,\n"
        "  half-kneeling=на одном колене, seated=сидя, standing=стоя,\n"
        "  lying/laying=лёжа, prone=лицом вниз, supine=лицом вверх,\n"
        "  incline=на наклонной скамье, decline=на скамье с наклоном вниз,\n"
        "  overhead=над головой, reverse=обратное, hammer=молотковое,\n"
        "  isometric=изометрическое, eccentric=эксцентрическое,\n"
        "  high=верхний блок, low=нижний блок, mid=средний блок,\n"
        "  lateral=в сторону, front=вперёд, rear=назад, backward=назад, forward=вперёд,\n"
        "  long lever=с прямой рукой, short lever=с согнутой рукой,\n"
        "  staggered=со смещённой стойкой, offset=асимметричный,\n"
        "  elevated=с возвышением, deficit=с дефицитом (углублением),\n"
        "  loaded=с отягощением, weighted=с отягощением\n"
        "\n"
        "MUSCLES → BODY PART for naming (add body part to the name when it helps clarity):\n"
        "  biceps/brachialis=рук, triceps=рук, shoulders/deltoid=плеч, chest/pectorals=груди,\n"
        "  back/lats/rhomboids=спины, glutes=ягодиц, hamstrings=бедра (задней поверхности),\n"
        "  quadriceps=ног, calves/gastrocnemius=голени, abdominals/core=пресса,\n"
        "  forearms=предплечий, hip flexors=сгибателей бедра, adductors=приводящих мышц,\n"
        "  abductors=отводящих мышц\n"
        "\n"
        "WORD ORDER in Russian fitness names: [movement] [body part] [equipment modifier]\n"
        "Examples: Band Curl → Сгибание рук с резиновой лентой\n"
        "          Dumbbell Lateral Raise → Подъём гантелей в стороны\n"
        "          Cable Face Pull → Тяга к лицу на блоке\n"
        "          Barbell Squat → Приседание со штангой\n"
        "          Band Glute Kickback → Отведение ноги назад с резиновой лентой\n"
        "          Seated Dumbbell Overhead Press → Жим гантелей над головой сидя\n"
        "          Alternating Dumbbell Curl → Поочерёдное сгибание рук с гантелями\n"
        "          Band Hip Thrust → Ягодичный мост с резиновой лентой\n"
        "          Incline Dumbbell Fly → Разведение гантелей на наклонной скамье\n"
        "          Plank → Планка\n"
        "          Backward Arm Circle → Круговые вращения руками назад\n"
        "          Forward Arm Circle → Круговые вращения руками вперёд\n"
        "          Ankle Circle → Круговые вращения стопой\n"
        "\n"
        "RULES:\n"
        "- Translate word-by-word using ONLY the glossary above, do NOT invent synonyms.\n"
        "- Do NOT use 'подтягивание' for 'curl'. Curl always means сгибание.\n"
        "- Use the muscles field to add the correct body part when relevant.\n"
        "- Return ONLY the Russian name, no quotes, no explanations, no punctuation at the end.\n"
        "\n"
        f"Exercise name to translate: {name}\n"
        f"Muscles involved: {muscles_str}\n"
        f"Equipment: {equipment}\n"
        f"Description: {steps_str}"
    )
    response = ollama_generate(prompt, json_format=False).strip()
    response = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", response).strip()
    if len(response) >= 2 and response[0] == response[-1] and response[0] in {'"', "'"}:
        response = response[1:-1].strip()
    return response or name

# ── основной процесс ───────────────────────────────────────────────────────────

def load_name_translations() -> dict[str, str]:
    """Загружает переводы названий упражнений из CSV."""
    if not NAME_TRANSLATIONS_CSV.exists():
        raise FileNotFoundError(f"CSV с переводами названий не найден: {NAME_TRANSLATIONS_CSV}")

    translations: dict[str, str] = {}
    with NAME_TRANSLATIONS_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")
        for row in reader:
            slug = (row.get("slug") or "").strip()
            name_en = (row.get("name_en") or "").strip()
            name_ru = (row.get("name_ru") or "").strip()
            if not name_ru:
                continue
            if slug:
                translations[slug] = name_ru
            if name_en:
                translations[name_en] = name_ru

    return translations

def translate_file(path: pathlib.Path, name_translations: dict[str, str]) -> dict:
    """Переводит один файл целиком и возвращает переведённые данные."""
    data = json.loads(path.read_text(encoding="utf-8"))
    original_name = data.get("name", "")

    seen: set[str] = set()
    pending: list[str] = []
    for text in iter_strings(data):
        if text not in seen:
            seen.add(text)
            pending.append(text)

    translations: dict[str, str] = {}
    for i, text in enumerate(pending, 1):
        try:
            translations[text] = translate_single(text)
        except Exception as exc:
            print(f"  Перевод не удался, оставляем оригинал ({i}/{len(pending)}): {text!r}: {exc}", flush=True)
            translations[text] = text

    new_data = apply_translations(data, translations)

    # Восстанавливаем оригинальное английское название
    new_data["name"] = original_name
    # Берём русский перевод названия из CSV
    if original_name:
        slug = path.parent.name
        new_data["name_ru"] = name_translations.get(slug) or name_translations.get(original_name) or original_name

    return new_data


def main() -> None:
    files = sorted(ROOT.glob("*/*.json"))
    if not files:
        print(f"JSON-файлы не найдены в {ROOT}")
        sys.exit(1)

    changed = 0
    name_translations = load_name_translations()

    for file_idx, path in enumerate(files, 1):
        print(f"[{file_idx}/{len(files)}] {path.name}...", end=" ", flush=True)

        new_data = translate_file(path, name_translations)
        new_text = json.dumps(new_data, ensure_ascii=False, indent=2) + "\n"
        path.write_text(new_text, encoding="utf-8")
        changed += 1
        print("готово", flush=True)

    # Финальная проверка — все файлы должны быть валидным JSON
    for path in files:
        json.loads(path.read_text(encoding="utf-8"))

    print(f"\nГотово. Изменено файлов: {changed}.")


if __name__ == "__main__":
    main()
