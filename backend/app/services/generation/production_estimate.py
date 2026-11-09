"""Pure helpers for target-runtime to supported-inference planning."""


def production_shot_count(target_duration_seconds: int, shot_duration_seconds: int = 5) -> int:
    """Number of equal-sized inference units required for a target runtime."""
    if target_duration_seconds < 1 or shot_duration_seconds < 1:
        raise ValueError("durations must be positive")
    return (target_duration_seconds + shot_duration_seconds - 1) // shot_duration_seconds


def plan_inference_units(target_duration_seconds: int, duration_options: list[int]) -> list[int]:
    """Plan provider-supported inference durations that cover a finished runtime.

    Prefer an exact duration; otherwise prefer the smallest supported clip
    longer than the remaining timeline (trimmed by the renderer); if none is
    longer, use the largest supported clip and continue. This mirrors the
    production executor's duration-planning policy.
    """
    options = sorted({int(value) for value in duration_options if int(value) > 0})
    if target_duration_seconds < 1 or not options:
        raise ValueError("target duration and supported duration options must be positive")
    remaining = float(target_duration_seconds)
    units: list[int] = []
    while remaining > 0:
        exact = [value for value in options if abs(float(value) - remaining) < 0.001]
        larger = [value for value in options if value > remaining]
        inference_duration = exact[0] if exact else min(larger) if larger else max(options)
        units.append(inference_duration)
        remaining -= min(float(inference_duration), remaining)
    return units
