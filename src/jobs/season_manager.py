import logging
from typing import List

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import Domain, Season
from src.core.yggdrasil.store import YggdrasilStore

logger = logging.getLogger(__name__)


class SeasonManager:
    """季节管理器 - 管理各领域的季节转换"""

    def __init__(self, store: YggdrasilStore, config: YggdrasilConfig):
        self.store = store
        self.config = config

    async def get_domain_season(self, domain_id: int) -> Season:
        """获取领域当前季节"""
        domain = await self.store.get_domain(domain_id)
        if not domain:
            return Season.SPRING
        return domain.season

    async def set_season(self, domain_id: int, season: Season) -> None:
        """设置领域季节"""
        await self.store.update_domain_season(domain_id, season)
        logger.info(f"Domain {domain_id} changed season to {season.value}")

    async def list_all_domains(self) -> List[Domain]:
        """列出所有领域"""
        return await self._collect_domains(None)

    async def _collect_domains(self, parent_id: int | None) -> List[Domain]:
        """递归收集所有领域"""
        children = await self.store.list_child_domains(parent_id)
        result = list(children)
        for child in children:
            result.extend(await self._collect_domains(child.id))
        return result

    async def next_season(self, domain_id: int) -> Season:
        """轮转季节：春 → 夏 → 秋 → 冬 → 春"""
        current = await self.get_domain_season(domain_id)
        order = [Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER]
        idx = order.index(current) if current in order else 0
        next_idx = (idx + 1) % len(order)
        next_season = order[next_idx]
        await self.set_season(domain_id, next_season)
        return next_season


__all__ = ["SeasonManager"]
