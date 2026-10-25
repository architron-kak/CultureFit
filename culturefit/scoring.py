"""Heuristic ranking from top venues; scores are relative, not match probabilities."""
import math
import re

BAD = re.compile(
    r"\b(hotels?|hostels?|motels?|ibis|hilton|hampton|moxy|resorts?|apartments?|residences?|inn|"
    r"airport|bank|pharmacy|kfc|subway|mcdonald'?s|гостиниц\w*)\b", re.I,
)
LOW_SPREAD = 0.03  # Heuristic for raw API affinity (0..1), not a statistical confidence interval.


def _text(e):
    tags = ' '.join(str(t.get('name') or '') for t in (e.get('tags') or []) if isinstance(t, dict))
    return f"{e.get('name', '')} {tags}"


def is_venue(e, exclude=()):
    text = _text(e)
    if BAD.search(text):
        return False
    for word in exclude:
        word = word.strip().lower()
        if not word:
            continue
        if word.isascii():
            # Gemini and users may supply plural categories ("bars", "clubs").
            stem = word[:-1] if word.endswith('s') and not word.endswith('ss') else word
            pattern = rf'\b{re.escape(stem)}(?:s|es)?\b'
        else:
            pattern = rf'\b{re.escape(word)}\w*'
        if re.search(pattern, text, re.I):
            return False
    return True


def _affinity(e):
    value = (e.get('query') or {}).get('affinity')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _eligible(entities, exclude):
    return [e for e in entities if is_venue(e, exclude) and _affinity(e) is not None]


def area_score(entities, exclude=(), k=5):
    values = sorted((_affinity(e) for e in _eligible(entities, exclude)), reverse=True)[:k]
    return sum(values) / len(values) if values else None


def evidence(entities, exclude=(), n=3):
    ents = sorted(_eligible(entities, exclude), key=_affinity, reverse=True)
    return [{
        'name': e.get('name', 'Unnamed venue'),
        'affinity': round(_affinity(e), 3),
        'tags': [t['name'] for t in (e.get('tags') or []) if isinstance(t, dict) and t.get('name')][:5],
        'why': (e.get('query') or {}).get('explainability'),
    } for e in ents[:n]]


def rank_areas(data, exclude=()):
    if not data or not next(iter(data.values())):
        raise ValueError('At least one person and one area are required')
    people = list(data)
    areas = list(next(iter(data.values())))
    if any(set(rows) != set(areas) for rows in data.values()):
        raise ValueError('All people must have the same areas')
    raw = {p: {a: area_score(data[p][a], exclude) for a in areas} for p in people}
    rel, spread = {}, {}
    for p in people:
        values = [v for v in raw[p].values() if v is not None]
        lo, hi = (min(values), max(values)) if values else (0, 0)
        spread[p] = round(hi - lo, 4)
        rel[p] = {
            a: (None if raw[p][a] is None else (100 * (raw[p][a] - lo) / (hi - lo) if hi > lo else 50))
            for a in areas
        }
    out = []
    for a in areas:
        unrounded = {p: rel[p][a] for p in people}
        scores = {p: round(v) if v is not None else None for p, v in unrounded.items()}
        complete = all(v is not None for v in unrounded.values())
        weakest = min(unrounded, key=unrounded.get) if complete else None
        out.append({
            'area': a,
            'group_fit': round(unrounded[weakest]) if complete else None,
            'weakest_person': weakest,
            'scores': scores,
            'gives_up': {p: 100 - s if s is not None else None for p, s in scores.items()},
            'evidence': {p: evidence(data[p][a], exclude) for p in people},
            'venue_counts': {p: len(_eligible(data[p][a], exclude)) for p in people},
            'status': 'ok' if complete else 'insufficient_data',
        })
    out.sort(key=lambda x: (x['group_fit'] is not None, x['group_fit'] or 0), reverse=True)
    return {'areas': out, 'spread': spread,
            'low_confidence_for': [p for p in people if spread[p] < LOW_SPREAD],
            'insufficient_data_for': [p for p in people if any(v is None for v in raw[p].values())]}
