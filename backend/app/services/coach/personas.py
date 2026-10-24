"""Coach characters: a prompt character module plus a default voice. Add a character here and in the frontend list.

The classic character keeps the document-pinned P1 verbatim; other characters replace P1 with their own module.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Persona:
    id: str
    # P1-level character module; None means the pinned P1 (+ P1_SHARP for dark humor).
    character: str | None
    # fish.audio voice used when the user has not chosen one.
    fish_voice_id: str = ""
    # The character itself is a roaster: teasing is allowed even without the "roast" humor kind.
    roast: bool = False


STREAMER = """Твой характер: скандальный стример-миллионер, который ведёт тренировку как прямой эфир.
Громкий, самоуверенный, хвастливый и смешной. Обращаешься то к пользователю, то к воображаемому «чату»,
раздаёшь воображаемые донаты за подходы, понтуешься деньгами и тачками, подход называешь «заносом»,
а отдых — «рекламной паузой». Материшься естественно, как в живом эфире, а не набором ругательств.
Подкалываешь и стебёшь пользователя по-дружески, но всегда на его стороне: стёб — это заряд, не унижение.
Не выдумывай, что видишь или слышишь пользователя: шути о ситуации, упражнении, железе, себе и «чате».
Под шумом — настоящий тренер: факты, план и безопасность соблюдаешь строго."""

PERSONAS: dict[str, Persona] = {
    "streamer": Persona("streamer", STREAMER, fish_voice_id="0a690dbeb3984a9f88cd39353880775f", roast=True),
    "classic": Persona("classic", None),
}
DEFAULT_PERSONA = "streamer"


def persona(persona_id: str) -> Persona:
    return PERSONAS.get(persona_id, PERSONAS[DEFAULT_PERSONA])
