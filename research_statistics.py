"""
================================================================================
AHAD AI - Research Lab
Shared Statistics Utility (Research Layer v1)
================================================================================

Not a standalone Research Lab module - no main(), never registered in
research.py's execution registry, never runs on its own. A pure
function library imported by other Research Layer v1 scripts, so the
Evidence Level classification (STRONG/MODERATE/WEAK/INSUFFICIENT) is
computed identically everywhere it's used, per the approved
specification - reusing the exact same normalized-difference logic
already established in compare_winners_losers.py, not a new formula.

MIN_SAMPLE_SIZE and the "full weight" target match the convention
already used throughout Research Lab.
================================================================================
"""

import statistics

MIN_SAMPLE_SIZE = 30
FULL_WEIGHT_SAMPLE_SIZE = 90


def pooled_std(values_a, values_b):
    """
    Pooled standard deviation across two independent samples - the
    same denominator a standardized effect size (Cohen's d) uses.
    Returns None if it cannot be computed (fewer than 2 points in
    either group, or zero pooled variance).
    """
    n1, n2 = len(values_a), len(values_b)
    if n1 < 2 or n2 < 2:
        return None
    try:
        var1 = statistics.variance(values_a)
        var2 = statistics.variance(values_b)
    except statistics.StatisticsError:
        return None
    pooled_variance = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
    if pooled_variance <= 0:
        return None
    return pooled_variance ** 0.5


def sample_size_factor(n1, n2):
    """
    Scales 0-1 as the smaller group size approaches FULL_WEIGHT_SAMPLE_SIZE,
    capped at 1.0 - identical convention to compare_winners_losers.py.
    """
    smaller = min(n1, n2)
    return min(1.0, smaller / FULL_WEIGHT_SAMPLE_SIZE)


def priority_score(values_a, values_b):
    """
    Normalized difference (effect-size-like) x sample-size factor -
    the same composite already used in compare_winners_losers.py,
    exposed here so every Research Layer v1 module computes it the
    same way rather than reimplementing it.
    """
    n1, n2 = len(values_a), len(values_b)
    if n1 == 0 or n2 == 0:
        return 0.0
    mean_a = statistics.mean(values_a)
    mean_b = statistics.mean(values_b)
    diff = abs(mean_a - mean_b)
    pooled = pooled_std(values_a, values_b)
    consistency = min(diff / pooled, 3.0) if pooled else 0.0
    return round(consistency * sample_size_factor(n1, n2), 4)


def evidence_level(n1, n2, values_a=None, values_b=None, score=None):
    """
    Classifies evidence strength per the approved specification:

        INSUFFICIENT DATA  - n < MIN_SAMPLE_SIZE for either group
        WEAK SIGNAL        - n >= MIN_SAMPLE_SIZE, but priority_score < 0.3
        MODERATE EVIDENCE  - n >= MIN_SAMPLE_SIZE, 0.3 <= score < 0.6
        STRONG EVIDENCE    - n >= FULL_WEIGHT_SAMPLE_SIZE, score >= 0.6

    Either pass values_a/values_b (the score is computed internally),
    or pass a pre-computed `score` directly (e.g. a categorical max-gap
    score computed elsewhere) - one of the two is required.
    """
    if n1 < MIN_SAMPLE_SIZE or n2 < MIN_SAMPLE_SIZE:
        return "INSUFFICIENT DATA"

    if score is None:
        if values_a is None or values_b is None:
            raise ValueError("evidence_level requires either (values_a, values_b) or a precomputed score")
        score = priority_score(values_a, values_b)

    if n1 >= FULL_WEIGHT_SAMPLE_SIZE and n2 >= FULL_WEIGHT_SAMPLE_SIZE and score >= 0.6:
        return "STRONG EVIDENCE"
    if score >= 0.3:
        return "MODERATE EVIDENCE"
    return "WEAK SIGNAL"
