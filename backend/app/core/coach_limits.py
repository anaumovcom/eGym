"""Shared generation headroom; not permission for longer speech or a larger spend cap."""

# Responses output includes reasoning, structured JSON and the spoken text.
COACH_TEXT_OUTPUT_TOKENS = 2048
COACH_MAX_TEXT_OUTPUT_TOKENS = 8192
# V0 routes: rest/setup/summary lines may reason longer; scenario/bible/episode JSON is the largest output.
COACH_NARRATIVE_OUTPUT_TOKENS = 4096
COACH_PLAN_OUTPUT_TOKENS = 6144
COACH_JUDGE_OUTPUT_TOKENS = 1024
# Realtime output also needs reasoning alongside the transcript/audio budget.
COACH_VOICE_REASONING_TOKENS = 1536
