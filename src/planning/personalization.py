"""Soft visit estimates and time suitability from served evidence and trip preferences."""

from corpus.serving import feature


def _supports(votes, value):
    return votes.get(value, 0) > max([0] + [n for v, n in votes.items() if v != value])


def _matches(evidence, weight):
    contexts = evidence.get('by_context') or {}
    votes = [contexts[f'{k}={v}'] for k, v in (weight.get('context') or {}).items()
             if contexts.get(f'{k}={v}')]
    if votes:
        return all(_supports(row, weight['value']) for row in votes)
    return evidence.get('value') == weight['value']


def duration(place, cfg, pace, soft_weights=(), *, minimum=False):
    """Explicit wall-clock overrides win; automatic targets stay inside the served estimate range."""
    if place.requested_duration is not None:
        return place.requested_duration
    short, typical, long = (place.visit[k] for k in ('short', 'typical', 'long'))
    if minimum:
        return min(short, duration(place, cfg, pace, soft_weights))
    policy = cfg.personalization.get('activities', {})
    activity = place.rec.get('identity', {}).get('category_group')
    if activity not in policy:
        return place.visit[cfg.visit_key[pace]]
    interest = 0.0
    for w in soft_weights or ():
        if w['feature'] not in cfg.personalization.get('interest_features', ()):
            continue
        evidence = feature(place.rec, w['feature'])
        if (evidence and evidence.get('status') == 'VERIFIED'
                and _matches(evidence, w) and w.get('weight', 0) > 0):
            interest += w['weight']
    baseline = place.visit[policy[activity].get('baseline', 'typical')]
    gain = min(1.0, interest / cfg.personalization.get('interest_full', 1.0))
    return max(short, min(long, round(baseline + gain * (long - baseline))))


def time_band(start, cfg):
    for name, (a, b) in cfg.personalization.get('time_bands', {}).items():
        if a <= start < b:
            return name
    return None


def suitability(place, start, cfg, soft_weights=()):
    """Bounded support, not a probability: counts establish evidence, never scale its strength."""
    band = time_band(start, cfg)
    if not band:
        return 0.0
    value = 0.0
    for w in soft_weights or ():
        if w.get('weight', 0) <= 0:
            continue
        evidence = feature(place.rec, w['feature'])
        if not evidence or evidence.get('status') != 'VERIFIED':
            continue
        contexts = evidence.get('by_context') or {}
        wanted = w.get('context') or {}
        if any(contexts.get(f'{k}={v}') and not _supports(contexts[f'{k}={v}'], w['value'])
               for k, v in wanted.items()):
            continue
        desired_time = wanted.get('time_of_day') if isinstance(wanted, dict) else None
        if desired_time and desired_time != band:
            continue
        votes = contexts.get(f'time_of_day={band}', {})
        supported = _supports(votes, w['value'])
        explicit = desired_time == band and _matches(evidence, w)
        if supported or explicit:
            value += min(1.0, w['weight'])
    rhythm = cfg.personalization.get('daily_rhythm', {})
    activity = place.rec.get('identity', {}).get('category_group')
    return value + rhythm.get(activity, {}).get(band, 0.0)


def preferred_start(place, earliest, latest, cfg, soft_weights=()):
    """A soft preference may wait within a feasible block, bounded by its supported benefit."""
    choices = [earliest] + [a for a, _ in cfg.personalization.get('time_bands', {}).values()
                            if earliest <= a <= latest]
    cost = cfg.personalization.get('wait_cost_per_min', 0.02)
    return max(choices, key=lambda s: (suitability(place, s, cfg, soft_weights) - cost * (s - earliest), -s))
