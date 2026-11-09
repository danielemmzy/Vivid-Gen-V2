"""Persist model capability contracts and explicit cost provenance.

This migration is additive. Existing generations and credit-ledger rows remain
unchanged; catalog capabilities are backfilled for known providers, and new
cost-source fields make runtime estimates distinguishable from invoice data.
"""
from alembic import op
import sqlalchemy as sa
import json

revision = "0010_model_caps_cost_source"
down_revision = "0009_model_catalog_pricing"
branch_labels = None
depends_on = None
SCHEMA = "core"

CAPABILITIES = {
    "seedream-v4": {"input_type": "text_to_image", "resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16"], "resolution_mode": "preset_based", "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": False},
    "wan-2.5": {"input_type": "text_to_video", "resolutions": ["1080p"], "duration_options": [5], "aspect_ratios": ["16:9", "9:16"], "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": True},
    "flux-2-turbo": {"input_type": "text_to_image", "resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "resolution_mode": "preset_based", "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": False},
    "flux-2": {"input_type": "text_to_image", "resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "resolution_mode": "preset_based", "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": False},
    "flux-2-turbo-edit": {"input_type": "image_to_image", "resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": False, "resolution_mode": "preset_based"},
    "flux-kontext-pro": {"input_type": "image_to_image", "resolutions": [], "duration_options": [], "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": False, "resolution_mode": "preset_based"},
    "wan-2.2-ti2v-5b": {"input_type": "text_to_video", "resolutions": ["720p"], "duration_options": [5], "aspect_ratios": ["16:9", "9:16"], "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": True},
    "wan-2.2-ti2v-5b-i2v": {"input_type": "image_to_video", "resolutions": ["720p"], "duration_options": [5], "aspect_ratios": ["16:9", "9:16"], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": True},
    "kling-2.5-turbo-pro": {"input_type": "text_to_video", "resolutions": [], "duration_options": [5, 10], "aspect_ratios": ["16:9", "9:16", "1:1"], "audio_input": False, "audio_output": False, "image_input": False, "movie_shots": True, "resolution_mode": "provider_native"},
    "kling-2.5-turbo-pro-i2v": {"input_type": "image_to_video", "resolutions": [], "duration_options": [5, 10], "aspect_ratios": [], "audio_input": False, "audio_output": False, "image_input": True, "movie_shots": True, "resolution_mode": "provider_native"},
    "omnihuman-1.5": {"input_type": "avatar", "resolutions": [], "duration_options": [], "aspect_ratios": ["16:9", "9:16"], "audio_input": True, "audio_output": True, "image_input": True, "movie_shots": False, "resolution_mode": "provider_native"},
    "video-translate-dub": {"input_type": "video_translation", "resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": True, "audio_output": True, "image_input": False, "movie_shots": False, "resolution_mode": "preserve_input"},
    "video-dub-audio-only": {"input_type": "video_translation", "resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": True, "audio_output": True, "image_input": False, "movie_shots": False, "resolution_mode": "preserve_input"},
    "audio-replace": {"input_type": "audio_replace", "resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": True, "audio_output": True, "image_input": False, "movie_shots": False, "resolution_mode": "preserve_input"},
    "tts-voice-clone": {"input_type": "text_to_speech", "resolutions": [], "duration_options": [], "aspect_ratios": [], "audio_input": False, "audio_output": True, "image_input": False, "movie_shots": False},
}


def upgrade() -> None:
    op.add_column("ai_model", sa.Column("capabilities", sa.JSON(), nullable=False, server_default="{}"), schema=SCHEMA)
    op.add_column("ai_model", sa.Column("cost_strategy", sa.String(40), nullable=False, server_default="catalog_unit_price"), schema=SCHEMA)
    op.add_column("ai_model", sa.Column("cost_estimate_basis", sa.String(255), nullable=True), schema=SCHEMA)
    op.add_column("generation", sa.Column("actual_cost_source", sa.String(40), nullable=True), schema=SCHEMA)
    op.add_column("generation_attempt", sa.Column("actual_cost_source", sa.String(40), nullable=True), schema=SCHEMA)

    for model_id, caps in CAPABILITIES.items():
        op.execute(sa.text(
            f'UPDATE "{SCHEMA}"."ai_model" SET capabilities = CAST(:caps AS JSON) WHERE id = :model_id'
        ).bindparams(caps=json.dumps(caps), model_id=model_id))

    op.execute(sa.text(f'''UPDATE "{SCHEMA}"."ai_model"
        SET provider_price_usd = 0.06,
            cost_strategy = 'modal_runtime_estimate',
            cost_estimate_basis = 'estimated Modal runtime using published resource rates; not invoice-reconciled'
        WHERE id IN ('wan-2.2-ti2v-5b', 'wan-2.2-ti2v-5b-i2v')'''))
    op.execute(sa.text(f'''UPDATE "{SCHEMA}"."ai_model"
        SET cost_estimate_basis = 'catalog provider-price snapshot; not provider-invoice-reconciled'
        WHERE cost_estimate_basis IS NULL'''))


def downgrade() -> None:
    op.drop_column("generation_attempt", "actual_cost_source", schema=SCHEMA)
    op.drop_column("generation", "actual_cost_source", schema=SCHEMA)
    op.drop_column("ai_model", "cost_estimate_basis", schema=SCHEMA)
    op.drop_column("ai_model", "cost_strategy", schema=SCHEMA)
    op.drop_column("ai_model", "capabilities", schema=SCHEMA)
