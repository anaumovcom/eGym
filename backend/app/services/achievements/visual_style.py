"""Art direction grounded in the supplied hexagonal achievement references."""

import json

from app.services.achievements.version import MAX_TIERS

STYLE_VERSION = "hexagonal-v2"

REFERENCE_ART_DIRECTION = """
Create ONE premium mobile-game achievement badge, matching the attached reference icons.
Silhouette: a regular point-up hexagon with gently rounded corners, seen straight on,
centered on a square canvas. The badge occupies roughly 80-88 percent of the canvas width
and 88-94 percent of its height. Keep a little dark breathing room on every side.
Border: a clean, moderately narrow, continuous saturated-color hexagonal bevel, approximately
5-7 percent of the badge width. A pale highlight runs along the upper-left outer edge;
the inner edge is darker, giving a shallow inset. It is NOT a circular medallion, thick
metal donut, industrial frame, or mechanical construction. No screws or rivets.
Interior: a dark inset hexagonal panel in a deeper shade of the border hue. Use subtle
angular planes, soft gradients, and local reflected light. A simple scenic background
is appropriate only when the central concept needs it; it must remain subordinate.
Main subject: one large instantly recognizable fitness object, simplified human figure,
or achievement metaphor. Model it as polished stylized 2.5D game art: clean silhouettes,
rounded volumes, broad smooth highlights, small crisp bevels, strong but soft-edged shadows,
and restrained faceting. It is digitally painted/rendered illustration, not a photograph,
not flat outline art, and not a toy made from inflated balloon tubes. Human figures have
simple anonymous faces, clear anatomy, and no tiny realistic facial detail. Equipment can
have metallic shading, but do not turn the entire badge into a metal plaque.
Lighting: warm or cool key light from the upper left, gentle colored rim light, dark
occlusion beneath the subject. Preserve rich color and readable shadows without blown-out
bloom. The main subject fills most of the inner panel and remains legible at thumbnail size.
    Keep the bottom vertex clean and uninterrupted: NO rank marker, diamond, crystal, gem,
    crown, star, pendant, ribbon, or other attached ornament below or across the bottom edge.
    Ignore all bottom markers in the attached references. Use the SAME silhouette and border
    width throughout the set; tier progression changes the subject and lighting, not the outline.
Canvas background: solid very dark blue-black charcoal, approximately #0d141c, with only
a faint local halo. No typography, letters, digits, labels, interface elements, or watermark.
""".strip()

REFERENCE_NEGATIVE = """
No circle, round medal enclosure, shield silhouette, thick silver/gold donut frame, rivets,
screws, bolts, gears, ornate filigree, banners, captions, text, multiple badges, contact sheet,
    busy particle effects, photorealism, flat vector outlines, cropped badge edges, bottom diamonds,
    bottom crowns, bottom crystals, bottom rank markers, or any ornament attached to the lower edge.
""".strip()

RARITY_ART_DIRECTION = {
    "common": "Cool steel-blue border (#7198ad), deep slate interior; satin ceramic and brushed steel subject accents. Never gold or purple.",
    "rare": "Vivid cyan-to-royal-blue border (#21c8ed to #315ddd), deep navy interior; polished enamel and clear blue glass accents.",
    "epic": "Pink-to-violet border (#d347c4 to #793fdb), deep plum interior; rich iridescent enamel and amethyst-toned subject accents.",
    "legendary": "Yellow-gold-to-orange border (#ffd05b to #ed8c25), deep amber interior; luminous gold and amber subject accents. No crown marker.",
}


def image_prompt(tier: dict[str, object]) -> str:
    """Use editorial meaning, not legacy image prompts with contradictory framing."""
    number = int(str(tier["tier"]))
    count = int(str(tier.get("tierCount", 3)))
    if not 1 <= number <= count <= MAX_TIERS:
        raise ValueError("invalid_tier_progression")
    progress = (number - 1) / (count - 1)
    saturation = round(45 + progress * 45)
    if number == count:
        stage = (
            "FINAL TIER: the brightest and most imaginative scene in this line. Deliver a clear, "
            "kind visual punchline using the established subject family, a triumphant silhouette, "
            "rich broad highlights and a restrained radiant backdrop INSIDE the badge. "
            "Keep rarity hue identity, shadow detail and thumbnail readability; no white-out bloom."
        )
    elif number == 1:
        stage = "OPENING TIER: one simple approachable subject, soft highlights, quiet background, no celebratory halo."
    else:
        stage = (
            "INTERMEDIATE TIER: evolve the same subject family into a more accomplished scene; "
            "increase depth, confident pose and local rim light gradually. Reserve the funniest "
            "visual twist and strongest lighting for the final tier."
        )
    concept = {key: tier.get(key) for key in ("title", "description", "threshold", "unit", "tier")}
    # Only the new editorial revision contains scene-only prompts without legacy framing.
    scene = str(tier.get("imagePrompt", "")) if tier.get("editorialStyle") == "v2" else ""
    return (
        "The attached images are authoritative STYLE references, not subjects to duplicate. "
        "Create one new badge for the achievement described below.\n\n"
        + REFERENCE_ART_DIRECTION
        + "\n\nREQUIRED RARITY PALETTE:\n"
        + RARITY_ART_DIRECTION[str(tier["rarity"])]
        + f"\n\nTIER {number} OF {count}: target accent saturation about {saturation}% "
        + "(art-direction target, not a measured pixel guarantee). "
        + stage
        + ("\n\nUNIQUE SUBJECT SCENE (apply the required style above):\n" + scene if scene else "")
        + "\n\nACHIEVEMENT MEANING (choose a clear visual metaphor; do not draw this text):\n"
        + json.dumps(concept, ensure_ascii=False)
        + "\n\nNEGATIVE CONSTRAINTS:\n"
        + REFERENCE_NEGATIVE
    )