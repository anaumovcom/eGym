"""Find recurring movement combinations in finalized workouts, keeping sessions and training days distinct."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from itertools import combinations, groupby
from typing import TYPE_CHECKING

from app.services.achievements.collection import DUETS, FORMATS, SEASONS

if TYPE_CHECKING:
    from app.services.achievements.facts import WorkoutFacts


WORKOUT_STORIES = frozenset({"discovery.crossroads", "discovery.encore", "calendar.weekend_guest", "signature.bookends"})


def workout_stories(workouts: list[WorkoutFacts], witness_id: int | None = None) -> tuple[dict[str, int], dict[str, tuple[str, ...]]]:
    """Count dated events and optionally name the movements that actually triggered one finish."""
    counts: Counter[str] = Counter()
    witnesses: dict[str, tuple[str, ...]] = {}
    seen: set[str] = set()
    previous_debuts: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    middles: dict[tuple[str, str], set[frozenset[str]]] = defaultdict(set)
    weekly_movements: dict[tuple[int, int, bool], set[str]] = defaultdict(set)
    weekend_weeks: set[tuple[int, int]] = set()

    def record(key: str, workout: WorkoutFacts, *example: str) -> None:
        counts[key] += 1
        if workout.row.id == witness_id:
            witnesses.setdefault(key, example)

    for day, sessions in groupby(sorted(workouts, key=lambda w: (w.day, w.finish_key)), key=lambda w: w.day):
        daily_slugs: set[str] = set()
        daily_middles: dict[tuple[str, str], set[frozenset[str]]] = defaultdict(set)
        counted_bookends = False
        year, week, weekday = day.isocalendar()
        weekend = weekday >= 6
        for workout in sessions:
            # Sets are in the saved exercise order. Multiple sets in one exercise occupy one slot.
            exercises = list({item.exercise_id: item.slug for item in workout.sets}.values())
            slugs = set(exercises)
            for pair in combinations(sorted(slugs), 2):
                if pair not in seen_pairs and seen.issuperset(pair):
                    record("discovery.crossroads", workout, *pair)
                seen_pairs.add(pair)
            for slug in sorted((slugs & previous_debuts) - daily_slugs):
                record("discovery.encore", workout, slug)
            common = slugs & weekly_movements[year, week, not weekend]
            if common and (year, week) not in weekend_weeks:
                record("calendar.weekend_guest", workout, min(common))
                weekend_weeks.add((year, week))
            weekly_movements[year, week, weekend].update(slugs)
            if len(slugs) >= 3 and exercises[0] != exercises[-1]:
                ends = (exercises[0], exercises[-1])
                middle = frozenset(exercises[1:-1])
                if not counted_bookends and middles[ends] - {middle}:
                    record("signature.bookends", workout, ends[0], ends[1])
                    counted_bookends = True
                daily_middles[ends].add(middle)
            daily_slugs.update(slugs)
        for ends, variants in daily_middles.items():
            middles[ends].update(variants)
        previous_debuts = daily_slugs - seen
        seen.update(daily_slugs)
    return dict(counts), witnesses


def movement_patterns(workouts: list[WorkoutFacts]) -> dict[str, float]:
    counts: Counter[str] = Counter()
    last_seen: dict[str, date] = {}
    last_training_day: date | None = None
    setlists: set[frozenset[str]] = set()
    prior_lineups_missing_one: set[frozenset[str]] = set()
    pair_days: Counter[tuple[str, str]] = Counter()
    partners: dict[str, set[str]] = defaultdict(set)
    days_with_partners: Counter[str] = Counter()
    weekly_formats: dict[tuple[int, int], set[str]] = defaultdict(set)
    relay_weeks: set[tuple[int, int]] = set()
    rediscovered: set[str] = set()
    slug_seasons: dict[str, set[int]] = defaultdict(set)
    seasons: set[tuple[int, int]] = set()
    month_slugs: dict[int, set[str]] = defaultdict(set)
    month_halves: dict[int, set[bool]] = defaultdict(set)
    kind_weeks: dict[str, set[tuple[int, int]]] = defaultdict(set)
    kind_slug_days: dict[tuple[str, str], set[date]] = defaultdict(set)

    for day, sessions in groupby(sorted(workouts, key=lambda w: w.day), key=lambda w: w.day):
        season = day.month % 12 // 3
        seasons.add((day.year + (day.month == 12), season))
        counts[f"calendar.season_{season}"] += 1
        month = day.year * 12 + day.month
        month_halves[month].add(day.day <= 15)
        week = tuple(day.isocalendar()[:2])
        daily_events: set[str] = set()
        daily_setlists: set[frozenset[str]] = set()
        daily_pairs: set[tuple[str, str]] = set()
        daily_slugs: set[str] = set()
        daily_formats: set[str] = set()
        for workout in sessions:
            slugs = frozenset(item.slug for item in workout.sets)
            kinds = {item.kind for item in workout.sets}
            daily_formats.update(kinds)
            for item in workout.sets:
                kind_weeks[item.kind].add(week)
                kind_slug_days[item.kind, item.slug].add(day)
            for pair in combinations(sorted(kinds), 2):
                if pair in DUETS:
                    daily_events.add(f"duet.{'_'.join(pair)}")
            if len(kinds) >= 3:
                daily_events.add("signature.trio")
            familiar = slugs.intersection(last_seen)
            if familiar and slugs - familiar:
                daily_events.add("discovery.old_and_new")
            if len(slugs) >= 2:
                if familiar == slugs:
                    daily_events.add("signature.familiar_only")
                if slugs in setlists:
                    daily_events.add("signature.same_setlist")
                daily_setlists.add(slugs)
                daily_pairs.update(combinations(sorted(slugs), 2))
            if len(slugs) >= 3 and slugs not in setlists and any(slugs - {slug} in prior_lineups_missing_one for slug in slugs):
                daily_events.add("signature.remix")
            if familiar and last_training_day and (day - last_training_day).days >= 15:
                daily_events.add("return.homecoming")
            daily_slugs.update(slugs)
        counts.update(daily_events)
        pair_days.update(daily_pairs)
        for a, b in daily_pairs:
            partners[a].add(b)
            partners[b].add(a)
        days_with_partners.update({slug for pair in daily_pairs for slug in pair})
        for lineup in daily_setlists - setlists:
            if len(lineup) >= 3:
                prior_lineups_missing_one.update(lineup - {slug} for slug in lineup)
        setlists.update(daily_setlists)
        if weekly_formats[week] and len(weekly_formats[week] | daily_formats) >= 2:
            relay_weeks.add(week)
        weekly_formats[week].update(daily_formats)
        month_slugs[month].update(daily_slugs)
        for slug in daily_slugs:
            if slug in last_seen and (day - last_seen[slug]).days >= 29:
                rediscovered.add(slug)
            last_seen[slug] = day
            slug_seasons[slug].add(season)
        last_training_day = day

    counts["return.rediscovered"] = len(rediscovered)
    counts["signature.reunited_pairs"] = sum(days >= 3 for days in pair_days.values())
    counts["discovery.club_host"] = sum(len(guests) >= 3 and days_with_partners[slug] >= 3 for slug, guests in partners.items())
    counts["calendar.format_relay"] = len(relay_weeks)
    counts["discovery.seasoned"] = sum(len(seen) == 4 for seen in slug_seasons.values())
    counts["calendar.season_turns"] = len(seasons)
    season_counts = Counter(season for _, season in seasons)
    counts["calendar.four_colours"] = min(season_counts[i] for i in range(len(SEASONS)))
    counts["calendar.both_halves"] = sum(len(halves) == 2 for halves in month_halves.values())
    counts["calendar.month_bridge"] = sum(bool(slugs & month_slugs.get(month - 1, set())) for month, slugs in month_slugs.items())
    for kind in FORMATS:
        counts[f"calendar.{kind}_weeks"] = len(kind_weeks[kind])
        counts[f"discovery.{kind}_regulars"] = sum(len(days) >= 3 for (k, _), days in kind_slug_days.items() if k == kind)
    return dict(counts)
