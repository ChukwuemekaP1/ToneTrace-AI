"""Base service architecture for ToneTrace domain business logic."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """Base class for all application domain services.

    Domain services encapsulate business workflows, transaction boundaries,
    and coordination between repositories and external providers.
    """

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
