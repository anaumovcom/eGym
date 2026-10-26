"""V6 Fish drama-3 expressiveness: per-sentence emotion segments, the allowed palette, mood → voice defaults,
the emotional curve between lines and synthesis parameters.

Words are never changed: markup only adds bracketed directions/sounds/pauses and paired tags around exact
substrings of the validated text. English directions (1 byte per letter) keep the billed markup share low.
"""

import re
from dataclasses import dataclass, field, replace

# ---------- palette (plan V6.2): emotions aimed at the situation or the coach, never at the user ----------
ALWAYS = ("happy", "excited", "calm", "confident", "satisfied", "delighted", "proud", "relaxed", "grateful", "curious",
          "determined", "hopeful", "optimistic", "empathetic", "sympathetic", "compassionate", "moved", "surprised")
HUMOR_ONLY = ("sarcastic", "bored", "indifferent", "doubtful", "confused", "uncertain", "nostalgic", "embarrassed",
              "disappointed", "pessimistic")
ROAST_ONLY = ("disdainful", "envious", "jealous", "hysterical", "frustrated")
FORBIDDEN = ("scared", "worried", "anxious", "nervous", "sad", "depressed", "lonely", "guilty", "ashamed", "regretful",
             "resigned", "unhappy", "upset", "angry", "disgusted", "contemptuous")
EMOTIONS = ("none", *ALWAYS, *HUMOR_ONLY, *ROAST_ONLY)
INTENSITIES = ("none", "slightly", "very", "extremely")
TONES = ("none", "shouting", "whispering", "soft tone", "in a hurry tone", "emphasis")
LOUD_TONES = frozenset({"shouting"})
SOUNDS = ("none", "laughing", "chuckling", "small laugh", "sighing", "gasping", "panting", "breath", "clear throat",
          "yawning")
CROWD = ("crowd laughing", "audience laughing", "background laughter")
SEGMENT_SOUNDS = (*SOUNDS, *CROWD)
PAUSES = ("none", "short pause", "break", "long-break")
TAGS = ("whisper", "emphasis", "soft", "fast", "slow", "stress", "forceful")
LOUD_TAGS = frozenset({"forceful"})
CROWD_ARCHETYPES = frozenset({"stream", "show"})
MAX_SEGMENTS = 4
MAX_TAGS_PER_SEGMENT = 2
DIRECTION_CHARS = 40
MARKUP_SHARE = 0.35
CROWD_EVERY_MS = 300_000
_DIRECTION = re.compile(r"^[A-Za-z ,\-']*$")
_SENTENCES = re.compile(r"(?<=[.!?…])\s+")
_STRIP = re.compile(r"[\[\]<>|]")


@dataclass(frozen=True, slots=True)
class Segment:
    emotion: str = "none"
    intensity: str = "none"
    tone: str = "none"
    direction: str = ""
    sound: str = "none"
    pause: str = "none"
    tags: tuple[tuple[str, str], ...] = ()

    @property
    def loud(self) -> bool:
        return self.tone in LOUD_TONES or any(tag in LOUD_TAGS for _, tag in self.tags)


def segment_from(raw: dict) -> Segment | None:
    """Strict parse of one author segment (already schema-shaped); None if anything is out of the palette."""
    if not isinstance(raw, dict):
        return None
    emotion, intensity, tone = raw.get("emotion"), raw.get("intensity"), raw.get("tone")
    direction, sound, pause, tags = raw.get("direction", ""), raw.get("soundBefore"), raw.get("pauseAfter"), raw.get("tags")
    if (emotion not in EMOTIONS or intensity not in INTENSITIES or tone not in TONES or sound not in SEGMENT_SOUNDS
            or pause not in PAUSES or not isinstance(direction, str) or len(direction) > DIRECTION_CHARS
            or not _DIRECTION.match(direction) or re.search(r"(?i)ignore|system|instruction|prompt", direction)
            or not isinstance(tags, list) or len(tags) > MAX_TAGS_PER_SEGMENT):
        return None
    parsed = []
    for tag in tags:
        if (not isinstance(tag, dict) or tag.get("tag") not in TAGS or not isinstance(tag.get("words"), str)
                or not 1 <= len(tag["words"].strip()) <= 60 or _STRIP.search(tag["words"])):
            return None
        parsed.append((" ".join(tag["words"].split()), tag["tag"]))
    return Segment(emotion, intensity, tone, " ".join(direction.split()), sound, pause, tuple(parsed))


@dataclass(frozen=True, slots=True)
class VoiceContext:
    """What the line is allowed to do with the voice (from settings, intent, mood and scenario)."""
    humor: bool = False
    roast: bool = False
    mood: str = ""
    sounds: bool = True
    crowd: bool = False


def allowed(segment: Segment, ctx: VoiceContext) -> Segment:
    """Sanitize to the palette of this moment instead of failing the whole line over a voice nuance."""
    emotion = segment.emotion
    if (emotion in HUMOR_ONLY and not ctx.humor) or (emotion in ROAST_ONLY and not ctx.roast) or ctx.mood == "recover" and (
            emotion in HUMOR_ONLY or emotion in ROAST_ONLY):
        emotion = "none"
    tone = segment.tone if not (segment.tone == "shouting" and ctx.mood not in {"triumph", "grind", "finale"}) else "emphasis"
    sound = segment.sound
    if not ctx.sounds or (sound in CROWD and not ctx.crowd) or (ctx.mood == "recover" and sound in {"laughing", "chuckling",
                                                                                                   "small laugh"}):
        sound = "none"
    tags = tuple(t for t in segment.tags if not (ctx.mood == "recover" and t[1] == "forceful"))
    return replace(segment, emotion=emotion, tone=tone, sound=sound, tags=tags)


# ---------- mood → voice (plan V6.3) ----------
@dataclass(frozen=True, slots=True)
class MoodVoice:
    emotion: str
    intensity: str
    tone: str
    sound: str
    speed: float
    volume: float
    temperature: float


MOOD_VOICE = {
    "warmup": MoodVoice("confident", "none", "none", "none", 1.0, 0.0, 0.65),
    "focus": MoodVoice("determined", "none", "none", "breath", 1.05, 0.0, 0.6),
    "grind": MoodVoice("determined", "very", "none", "panting", 1.1, 2.0, 0.7),
    "triumph": MoodVoice("excited", "very", "none", "laughing", 1.05, 3.0, 0.8),
    "comeback": MoodVoice("delighted", "none", "none", "gasping", 1.0, 1.0, 0.75),
    "recover": MoodVoice("empathetic", "none", "soft tone", "none", 0.95, -2.0, 0.6),
    "finale": MoodVoice("proud", "very", "none", "none", 0.95, 1.0, 0.75),
}
FIXED = {"count": Segment("confident", tone="none"), "safety": Segment("calm", direction="serious and steady"),
         "partial": Segment("empathetic", tone="soft tone")}


def base_segment(mood: str) -> Segment:
    voice = MOOD_VOICE.get(mood)
    if voice is None:
        return Segment()
    return Segment(voice.emotion, voice.intensity, voice.tone, sound=voice.sound)


# ---------- markup ----------
def _bracket(segment: Segment) -> str:
    parts = []
    if segment.emotion != "none":
        parts.append(f"{segment.intensity} {segment.emotion}" if segment.intensity != "none" else segment.emotion)
    if segment.tone != "none":
        parts.append(segment.tone)
    if segment.direction:
        parts.append(segment.direction)
    return f"[{', '.join(parts)}] " if parts else ""


def _tagged(sentence: str, tags: tuple[tuple[str, str], ...]) -> str:
    out = sentence
    for words, tag in tags:
        index = out.find(words)
        # Exact substring only, and never inside an already inserted tag.
        if index < 0 or "<" in out[:index] and out.rfind("<", 0, index) > out.rfind(">", 0, index):
            continue
        out = f"{out[:index]}<{tag}>{words}</{tag}>{out[index + len(words):]}"
    return out


def render(text: str, segments: tuple[Segment, ...]) -> str:
    sentences = _SENTENCES.split(" ".join(_STRIP.sub(" ", text).split()))
    pieces = []
    for index, sentence in enumerate(sentences):
        segment = segments[index] if index < len(segments) else Segment()
        sound = f"[{segment.sound}] " if segment.sound != "none" else ""
        pause = f" [{segment.pause}]" if segment.pause != "none" else ""
        pieces.append(f"{sound}{_bracket(segment)}{_tagged(sentence, segment.tags)}{pause}")
    return " ".join(pieces)


def strip_markup(markup: str) -> str:
    return " ".join(re.sub(r"\[[^\]]*\]", " ", re.sub(r"</?[a-z]+>", "", markup)).split())


def within_budget(text: str, segments: tuple[Segment, ...], share: float = MARKUP_SHARE) -> tuple[Segment, ...]:
    """Drop secondary markup until it is at most `share` of the billed bytes: intensity → directions → sounds →
    pauses → tags → tones; the sentence emotion goes last."""
    plain = len(" ".join(text.split()).encode())

    def ratio(current: tuple[Segment, ...]) -> float:
        total = len(render(text, current).encode())
        return (total - plain) / total if total else 0.0

    steps = (lambda s: replace(s, intensity="none"), lambda s: replace(s, direction=""), lambda s: replace(s, sound="none"),
             lambda s: replace(s, pause="none"), lambda s: replace(s, tags=()), lambda s: replace(s, tone="none"),
             lambda s: replace(s, emotion="none"))
    current = segments
    for step in steps:
        if ratio(current) <= share:
            break
        # Trim from the last sentence backwards: the opening sentence keeps its colour longest.
        for index in range(len(current) - 1, -1, -1):
            current = (*current[:index], step(current[index]), *current[index + 1:])
            if ratio(current) <= share:
                return current
    return current


# ---------- emotional curve between lines (plan V6.4) ----------
@dataclass
class VoiceHistory:
    recent: list[tuple[str, bool]] = field(default_factory=list)  # (sound, loud) of the last lines
    crowd_at_ms: float = -float("inf")
    extreme_exercises: set[str] = field(default_factory=set)

    def shape(self, segments: tuple[Segment, ...], *, now_ms: float, exercise: str | None) -> tuple[Segment, ...]:
        shaped = []
        last_loud = bool(self.recent) and self.recent[-1][1]
        two_loud = len(self.recent) >= 2 and self.recent[-1][1] and self.recent[-2][1]
        recent_sounds = {sound for sound, _ in self.recent[-3:]}
        for segment in segments:
            if segment.loud and last_loud:
                # Contrast: never two loud lines in a row.
                segment = replace(segment, tone="emphasis" if segment.tone == "shouting" else segment.tone,
                                  tags=tuple((w, "emphasis" if t == "forceful" else t) for w, t in segment.tags))
            if two_loud and segment.tone == "none":
                segment = replace(segment, tone="soft tone")
            if segment.sound != "none" and (segment.sound in recent_sounds or (
                    segment.sound in CROWD and now_ms - self.crowd_at_ms < CROWD_EVERY_MS)):
                segment = replace(segment, sound="none")
            if segment.intensity == "extremely" and exercise is not None and exercise in self.extreme_exercises:
                segment = replace(segment, intensity="very")
            shaped.append(segment)
        return tuple(shaped)

    def note(self, segments: tuple[Segment, ...], *, now_ms: float, exercise: str | None) -> None:
        sound = next((s.sound for s in segments if s.sound != "none"), "none")
        self.recent = [*self.recent[-4:], (sound, any(s.loud for s in segments))]
        if sound in CROWD:
            self.crowd_at_ms = now_ms
        if exercise is not None and any(s.intensity == "extremely" for s in segments):
            self.extreme_exercises.add(exercise)


# ---------- synthesis parameters (plan V6.5) ----------
def synthesis(profile: str, mood: str, phase: str) -> dict:
    """Fish request parameters for the new expressive path; volume is bounded to ±3 dB (the mixer still owns gain)."""
    voice = MOOD_VOICE.get(mood)
    temperature = {"count": 0.4, "safety": 0.4, "partial": 0.6}.get(profile, voice.temperature if voice else 0.65)
    speed = 1.0 if profile in {"count", "safety"} else (voice.speed if voice else 1.0)
    volume = 0.0 if profile in {"count", "safety"} else max(-3.0, min(3.0, voice.volume if voice else 0.0))
    params = {"temperature": temperature, "prosody": {"speed": speed, "volume": volume}, "language": "ru",
              "latency": "low" if phase == "active" else "balanced"}
    return params


# ---------- pre-tagged scripts (operator/pack text with inline drama-3 tags) ----------
# Free-form bracket directions/sounds/pauses ([excited], [very excited], [small laugh], [break], also Cyrillic),
# placed anywhere and back to back, plus the seven documented paired tags. Speaker/phoneme control tokens are not
# accepted here: multi-speaker requests are assembled only by the adapter.
_TAG_TOKEN = re.compile(r"\[[^\[\]]*\]|</?[A-Za-z]+>|[\[\]<>|]")
_BRACKET_BODY = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9 ,.'\-]{0,79}$")


class TaggedTextError(ValueError):
    pass


def parse_tagged(markup: str) -> str:
    """Validate a drama-3 script with inline tags and return its spoken words (tags removed).

    The script itself is never rewritten: a valid one is sent verbatim, an invalid one is refused (no silent edits)."""
    if not isinstance(markup, str) or not markup.strip():
        raise TaggedTextError("empty")
    open_tags: list[str] = []
    spoken = []
    position = 0
    for match in _TAG_TOKEN.finditer(markup):
        spoken.append(markup[position:match.start()])
        position = match.end()
        token = match.group()
        if token.startswith("[") and token.endswith("]") and len(token) > 2:
            if not _BRACKET_BODY.match(token[1:-1].strip()) or re.search(r"(?i)ignore|system|instruction|prompt", token):
                raise TaggedTextError(f"bad_direction:{token[:40]}")
            continue
        if token.startswith("</") and token[2:-1] in TAGS:
            if not open_tags or open_tags.pop() != token[2:-1]:
                raise TaggedTextError(f"unbalanced:{token}")
            continue
        if token.startswith("<") and token.endswith(">") and token[1:-1] in TAGS:
            if open_tags:
                raise TaggedTextError(f"nested:{token}")  # drama-3 paired tags are word-level, never nested
            open_tags.append(token[1:-1])
            continue
        raise TaggedTextError(f"bad_token:{token[:40]}")
    if open_tags:
        raise TaggedTextError(f"unclosed:<{open_tags[-1]}>")
    spoken.append(markup[position:])
    words = " ".join("".join(spoken).split())
    if not re.search(r"[A-Za-zА-Яа-яЁё]", words):
        raise TaggedTextError("no_words")
    return words
