"""Conservative pilot, engineering review only; NOT medical/human technique certification.

Imported machine-pulldown has empty guide and ambiguous cable/bar steps. No grip,
torso angle, range, timing or anatomy instruction is approved for this machine.
Simulator/runtime moves a bar; that does not verify a cable-pulldown variant.
"""

from dataclasses import asdict, dataclass

from app.services.exercise_library import get_imported_exercise


@dataclass(frozen=True, slots=True)
class ReviewedTip:
    tip_id: str
    version: str
    source: str
    review: str
    applicable_variants: tuple[str, ...]
    load_modes: tuple[str, ...]
    phases: tuple[str, ...]
    prerequisites: tuple[str, ...]
    exclusions: tuple[str, ...]
    text: str

    def data(self) -> dict:
        return asdict(self)


_COMMON = dict(version="1", source="engineering-policy:neutral-machine-cues-1",
               review="engineering-reviewed-not-clinically-certified",
               applicable_variants=("machine-pulldown",), load_modes=("constant",),
               prerequisites=("loaded-catalog-machine", "known-mode", "no-discomfort"),
               exclusions=("body-observation", "cable-variant-inference", "pain", "load-change"))
TIPS = (
    ReviewedTip(tip_id="machine-prepare", phases=("setup", "rest"),
                text="Перед началом движения спокойно подготовься к подходу.", **_COMMON),
    ReviewedTip(tip_id="machine-no-jerks", phases=("active",),
                text="Во время движения избегай резких рывков.", **_COMMON),
)


def select_tip(slug: str | None, kind: str | None, variant: str | None, mode: str | None,
               phase: str, *, discomfort: int | None = None) -> ReviewedTip | None:
    # Exact identifiers, never fuzzy matching or raw imported prose in prompts.
    if slug != "machine-pulldown" or variant != slug or kind != "machine" or discomfort not in (None, 0):
        return None
    try:
        loaded = get_imported_exercise(slug)
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if loaded is None or loaded.equipment != "Machine":
        return None
    return next((tip for tip in TIPS if variant in tip.applicable_variants
                 and mode in tip.load_modes and phase in tip.phases), None)