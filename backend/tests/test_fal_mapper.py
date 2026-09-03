import pytest

from app.core.exceptions import InvalidGenerationParamsError
from app.services.providers.fal.mapper import build_arguments


def test_text_to_image_arguments():
    provider_model_id, args = build_arguments("seedream-v4", "text_to_image", prompt="a cat", aspect_ratio="16:9", num_images=2)
    assert provider_model_id == "fal-ai/bytedance/seedream/v4/text-to-image"
    assert args == {"prompt": "a cat", "num_images": 2, "aspect_ratio": "16:9"}


def test_avatar_arguments_use_both_inputs():
    _, args = build_arguments("omnihuman-1.5", "avatar", input_url="https://x/img.png", secondary_input_url="https://x/audio.mp3")
    assert args == {"image_url": "https://x/img.png", "audio_url": "https://x/audio.mp3"}


def test_mismatched_model_and_type_raises():
    with pytest.raises(InvalidGenerationParamsError):
        build_arguments("seedream-v4", "text_to_video", prompt="a cat")
