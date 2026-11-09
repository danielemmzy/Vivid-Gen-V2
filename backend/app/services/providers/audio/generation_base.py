"""Provider-neutral contract for prompt-to-audio music and ambience generation."""
from typing import Literal, Protocol

AudioRole = Literal["music", "ambience"]


class AudioGenerationProvider(Protocol):
    name: str

    async def generate(
        self, *, prompt: str, duration_seconds: int, role: AudioRole, output_path: str,
    ) -> float:
        """Write a decodable audio file and return its measured duration."""
        ...
