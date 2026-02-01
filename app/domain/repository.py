"""Asynchronous repository utilities for domain models.

This module provides a small generic async repository abstraction that
wraps common ORM operations with explicit async methods to enforce the
project's async-first policy.
"""
from __future__ import annotations

from typing import Any, Generic, List, Optional, Type, TypeVar

from django.db import models

ModelType = TypeVar("ModelType", bound=models.Model)


class AsyncRepository(Generic[ModelType]):
    """Generic asynchronous repository for a Django model.

    Example:
        repo = AsyncRepository(Book)
        books = await repo.get_all()
    """

    def __init__(self, model: Type[ModelType]) -> None:
        """Initialize the repository with a Django model class.

        Args:
            model: The Django model class to operate on.
        """

        self.model = model

    async def get_all(self) -> List[ModelType]:
        """Return all model instances as a list using async iteration.

        This method collects results into memory; consider streaming in
        production for large datasets.
        """

        result: List[ModelType] = [item async for item in self.model.objects.all()]
        return result

    async def get_by_id(self, pk: Any) -> Optional[ModelType]:
        """Return a single model instance by primary key or ``None``.

        Uses :meth:`QuerySet.aget` to perform the lookup asynchronously.
        """

        try:
            obj = await self.model.objects.aget(pk=pk)
        except self.model.DoesNotExist:
            return None
        return obj

    async def create(self, **data: Any) -> ModelType:
        """Create and return a new model instance using :meth:`acreate`.

        All fields should be passed as keyword arguments.
        """

        obj = await self.model.objects.acreate(**data)  # type: ignore[attr-defined]
        return obj

    async def update(self, pk: Any, **data: Any) -> Optional[ModelType]:
        """Update fields on an instance and persist changes asynchronously.

        Returns the updated instance or ``None`` if not found.
        """

        obj = await self.get_by_id(pk)
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        await obj.asave()  # type: ignore[attr-defined]
        return obj

    async def delete(self, pk: Any) -> bool:
        """Delete an instance by primary key.

        Returns True if the object existed and was deleted, False otherwise.
        """

        obj = await self.get_by_id(pk)
        if obj is None:
            return False
        await obj.adelete()  # type: ignore[attr-defined]
        return True
