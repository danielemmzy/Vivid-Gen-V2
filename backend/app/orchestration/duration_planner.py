"""Pure helpers for mapping finished timeline duration to model-supported clips."""
from app.core.exceptions import InvalidGenerationParamsError


def choose_supported_clip_duration(remaining_seconds: float, duration_options: list[int]) -> tuple[int, float]:
    """Return provider-supported inference duration and usable timeline slice.

    If less than the model's minimum duration remains, generate the minimum
    supported clip and trim its render copy to the exact remaining timeline.
    """
    options = sorted({int(value) for value in duration_options if int(value) > 0})
    if not options:
        raise InvalidGenerationParamsError("The selected model has no verified shot-duration options.")
    if remaining_seconds <= 0:
        raise InvalidGenerationParamsError("Remaining movie duration must be positive.")
    exact = [option for option in options if abs(float(option) - float(remaining_seconds)) < 0.001]
    if exact:
        inference_duration = exact[0]
    else:
        larger = [option for option in options if option > remaining_seconds]
        # Prefer one slightly-longer supported clip that can be trimmed over
        # stitching two clips for a small remainder (e.g. 8s -> 10s, trimmed).
        inference_duration = min(larger) if larger else max(options)
    return inference_duration, min(float(inference_duration), float(remaining_seconds))
