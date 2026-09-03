"""Import every model module here so Alembic's autogenerate and
Base.metadata.create_all can discover all tables from a single import."""
from app.models.ai_model import AIModel
from app.models.base import Base
from app.models.credit import CreditTransaction
from app.models.generation import Generation
from app.models.project import Character, Project, Shot
from app.models.webhook_event import WebhookEvent

__all__ = ["Base", "AIModel", "Generation", "CreditTransaction", "Project", "Character", "Shot", "WebhookEvent"]
