from app.services.providers.stock.base import StockProvider
from app.services.providers.stock.pexels import PexelsStockProvider

_STOCK_PROVIDERS: dict[str, type] = {"pexels": PexelsStockProvider}


def get_stock_provider(name: str = "pexels") -> StockProvider:
    cls = _STOCK_PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown stock provider: {name}")
    return cls()


def list_stock_providers() -> list[StockProvider]:
    return [cls() for cls in _STOCK_PROVIDERS.values()]
