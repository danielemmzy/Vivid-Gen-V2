"""V2 Phase 10: caption segment -> .srt conversion. Separate from the
transcription provider itself (openai_whisper.py) so any future
transcription provider that returns the same `[{start, end, text}]` shape
works here unchanged."""


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(seg['start'])} --> {_srt_timestamp(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def write_srt(segments: list[dict], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(segments_to_srt(segments))
