"""Import every model module here so Alembic's autogenerate and
Base.metadata.create_all can discover all tables from a single import.

Import order matters for FK string resolution readability only (not
correctness — SQLAlchemy resolves ForeignKey("table.column") strings
lazily against Base.metadata at mapper-configuration time, not at
import time), but Production is listed early since most of the newer
models reference it."""
from app.models.ai_model import AIModel
from app.models.asset import Asset
from app.models.base import Base
from app.models.brand_kit import BrandKit
from app.models.caption_track import CaptionSegment, CaptionTrack
from app.models.credit import CreditTransaction
from app.models.production import Production
from app.models.export import ContentVariant, Export
from app.models.generation import Generation
from app.models.generation_attempt import GenerationAttempt
from app.models.product import Product
from app.models.production_budget import ProductionBudget, ProductionBudgetLedger
from app.models.production_plan import ProductionPlanRecord
from app.models.production_task import ProductionTask
from app.models.production_task_dependency import ProductionTaskDependency
from app.models.project import Character, Project, Shot
from app.models.provider_health import ProviderHealth
from app.models.provider_cost_record import ProviderCostRecord
from app.models.render_job import RenderJob
from app.models.webhook_event import WebhookEvent
from app.models.user_entitlement import UserEntitlement

__all__ = [
    "Base", "AIModel", "Asset", "BrandKit", "Generation", "CreditTransaction",
    "Project", "Character", "Shot", "WebhookEvent", "RenderJob", "Export",
    "ContentVariant", "ProductionTask", "Production", "ProductionPlanRecord",
    "ProductionBudget", "ProductionBudgetLedger", "GenerationAttempt",
    "ProductionTaskDependency", "Product", "ProviderHealth", "CaptionTrack",
    "CaptionSegment", "UserEntitlement", "ProviderCostRecord",
]
