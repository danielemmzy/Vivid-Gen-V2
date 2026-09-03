from app.services.generation.pricing import calculate_credits


def test_markup_image():
    assert calculate_credits(0.03) == 8


def test_markup_wan_5_seconds():
    assert calculate_credits(0.25) == 63


def test_markup_kling_5_seconds():
    assert calculate_credits(0.35) == 88


def test_markup_veo_like_cost():
    assert calculate_credits(2.0) == 500


def test_zero_or_negative_cost_floors_to_minimum():
    assert calculate_credits(0) == 1
    assert calculate_credits(-1) == 1
