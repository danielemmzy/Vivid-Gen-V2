"""Prompt/input moderation. This did not exist in the original codebase at
all — for a public-facing generation product that accepts arbitrary text
prompts and uploaded photos (especially the avatar/lip-sync and photo-to-
video flows, which take a real person's photo as input), shipping without
any moderation layer is a real legal and trust-and-safety exposure, not a
nice-to-have. This is a minimal, fast, synchronous pre-check — it is NOT a
substitute for the provider's own safety filtering, which still applies.
Its job is to reject the cheap, obvious cases before we spend a credit
reservation and a provider call on them, and to flag ambiguous cases for
human review rather than silently allow or silently block.

Swap `_blocklist_check` for a real classifier (e.g. an LLM-based prompt
classifier, or a provider's moderation endpoint) when volume justifies it
— the interface (`ModerationResult`) doesn't need to change."""
import re
from dataclasses import dataclass, field

from app.core.constants import ModerationVerdict

# Deliberately minimal and illustrative — a real deployment should load this
# from a maintained, reviewed list (settings.moderation_blocklist_path),
# not hardcode it here. Categories: CSAM-adjacent terms are handled by a
# hard block with no bypass; everything else is a soft flag for review.
_HARD_BLOCK_PATTERNS = [
    r"\bchild\b.{0,20}\b(nude|naked|sexual)\b",
    r"\b(minor|underage)\b.{0,20}\b(nude|naked|sexual)\b",
]
_FLAG_PATTERNS = [
    r"\bdeepfake\b.{0,20}\b(politician|celebrity|president)\b",
    r"\bnon[- ]?consensual\b",
]


@dataclass
class ModerationResult:
    verdict: str
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.verdict == ModerationVerdict.ALLOW


class ModerationService:
    def __init__(self) -> None:
        self._hard_block = [re.compile(p, re.IGNORECASE) for p in _HARD_BLOCK_PATTERNS]
        self._flag = [re.compile(p, re.IGNORECASE) for p in _FLAG_PATTERNS]

    def check_prompt(self, prompt: str | None) -> ModerationResult:
        if not prompt:
            return ModerationResult(ModerationVerdict.ALLOW)
        for pattern in self._hard_block:
            if pattern.search(prompt):
                return ModerationResult(ModerationVerdict.BLOCK, ["prohibited_content"])
        reasons = [p.pattern for p in self._flag if p.search(prompt)]
        if reasons:
            return ModerationResult(ModerationVerdict.FLAG_FOR_REVIEW, reasons)
        return ModerationResult(ModerationVerdict.ALLOW)


moderation_service = ModerationService()
