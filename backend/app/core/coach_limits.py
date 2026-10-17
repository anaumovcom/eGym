"""Shared generation headroom; not permission for longer speech or a larger spend cap."""

# Responses output includes reasoning, structured JSON and the spoken text.
COACH_TEXT_OUTPUT_TOKENS = 2048
COACH_MAX_TEXT_OUTPUT_TOKENS = 8192
# Realtime output also needs reasoning alongside the transcript/audio budget.
COACH_VOICE_REASONING_TOKENS = 1536