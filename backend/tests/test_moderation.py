from app.core.constants import ModerationVerdict
from app.services.moderation.service import moderation_service


def test_clean_prompt_allowed():
    result = moderation_service.check_prompt("a golden retriever running on a beach at sunset")
    assert result.verdict == ModerationVerdict.ALLOW


def test_empty_prompt_allowed():
    assert moderation_service.check_prompt(None).allowed
    assert moderation_service.check_prompt("").allowed


def test_hard_blocked_content_is_blocked():
    result = moderation_service.check_prompt("a naked child in a sexual pose")
    assert result.verdict == ModerationVerdict.BLOCK
