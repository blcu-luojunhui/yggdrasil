import logging
from typing import List

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import Domain, Season
from src.core.yggdrasil.store import YggdrasilStore

logger = logging.getLogger(__name__)


class SeasonManager:
    """季节管理器 - 管理子树级别的季节周期"""

    SEASON_ORDER = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]

    def __init__(self, store: YggdrasilStore, config: YggdrasilConfig):
        self.store = store
        self.config = config

    async def get_season(self, domain_path: str = "/") -> Season:
        cycle = await self.store.get_season_cycle(domain_path)
        if cycle:
            return Season(cycle["current_season"])
        return Season.SPRING

    async def set_season(self, domain_path: str, season: Season) -> None:
        await self.store.upsert_season_cycle(domain_path, season)

    async def next_season(self, domain_path: str = "/") -> Season:
        current = await self.get_season(domain_path)
        idx = self.SEASON_ORDER.index(current)
        next_idx = (idx + 1) % len(self.SEASON_ORDER)
        next_season = self.SEASON_ORDER[next_idx]
        await self.set_season(domain_path, next_season)
        logger.info(f"Domain {domain_path} season: {current.value} → {next_season.value}")
        return next_season

    async def list_all_domains(self) -> List[Domain]:
        return await self._collect_domains(None)

    async def _collect_domains(self, parent_id: int | None) -> List[Domain]:
        children = await self.store.list_child_domains(parent_id)
        result = list(children)
        for child in children:
            result.extend(await self._collect_domains(child.id))
        return result


__all__ = ["SeasonManager"]