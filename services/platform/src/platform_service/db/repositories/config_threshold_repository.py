from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.config_threshold import ConfigThreshold
from platform_service.db.models.config_threshold_change import ConfigThresholdChange


def _coerce_json_to_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


@dataclass(frozen=True)
class ConfigThresholdState:
    id: int
    key: str
    value_json: Any
    version: int
    title: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    updated_by: str | None


@dataclass(frozen=True)
class ConfigThresholdChangeRecord:
    previous_value_json: Any | None
    current_value_json: Any
    updated_by: str
    updated_at: datetime


def _latest_change_id_subquery(*, tenant_id: int | None = None):
    stmt = select(
        ConfigThresholdChange.config_threshold_id,
        func.max(ConfigThresholdChange.id).label("change_id"),
    )
    if tenant_id is not None:
        stmt = stmt.where(ConfigThresholdChange.tenant_id == tenant_id)
    return stmt.group_by(ConfigThresholdChange.config_threshold_id).subquery()


def _state_from_row(config: ConfigThreshold, change: ConfigThresholdChange) -> ConfigThresholdState:
    return ConfigThresholdState(
        id=config.id,
        key=config.key,
        value_json=change.current_value_json,
        version=change.version,
        title=config.title,
        description=config.description,
        created_at=config.created_at,
        updated_at=change.updated_at,
        updated_by=change.updated_by,
    )


class ConfigThresholdRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_value(self, key: str, *, tenant_id: int = DEFAULT_TENANT_ID) -> Any | None:
        stmt = (
            select(ConfigThresholdChange.current_value_json)
            .join(ConfigThreshold, ConfigThreshold.id == ConfigThresholdChange.config_threshold_id)
            .where(
                ConfigThreshold.key == key,
                ConfigThreshold.tenant_id == tenant_id,
            )
            .order_by(ConfigThresholdChange.updated_at.desc(), ConfigThresholdChange.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_int(self, key: str, default: int, *, tenant_id: int = DEFAULT_TENANT_ID) -> int:
        value = await self.get_value(key, tenant_id=tenant_id)
        return _coerce_json_to_int(value, default)

    async def get_int_for_keys(
        self, defaults: dict[str, int], *, tenant_id: int = DEFAULT_TENANT_ID
    ) -> dict[str, int]:
        """Return a copy of `defaults` with any matching config keys overriding values."""
        if not defaults:
            return {}
        keys = tuple(defaults.keys())
        latest = _latest_change_id_subquery(tenant_id=tenant_id)
        stmt = (
            select(ConfigThreshold.key, ConfigThresholdChange.current_value_json)
            .join(latest, ConfigThreshold.id == latest.c.config_threshold_id)
            .join(ConfigThresholdChange, ConfigThresholdChange.id == latest.c.change_id)
            .where(
                ConfigThreshold.key.in_(keys),
                ConfigThreshold.tenant_id == tenant_id,
            )
        )
        rows = (await self.session.execute(stmt)).all()
        out = dict(defaults)
        for row_key, value_json in rows:
            if row_key in out:
                out[row_key] = _coerce_json_to_int(value_json, out[row_key])
        return out

    async def list_all(self, *, tenant_id: int | None = None) -> list[ConfigThresholdState]:
        latest = _latest_change_id_subquery(tenant_id=tenant_id)
        stmt = (
            select(ConfigThreshold, ConfigThresholdChange)
            .join(latest, ConfigThreshold.id == latest.c.config_threshold_id)
            .join(ConfigThresholdChange, ConfigThresholdChange.id == latest.c.change_id)
        )
        if tenant_id is not None:
            stmt = stmt.where(ConfigThreshold.tenant_id == tenant_id)
        rows = (await self.session.execute(stmt)).all()
        return [_state_from_row(config, change) for config, change in rows]

    async def get_by_key(
        self, key: str, *, tenant_id: int = DEFAULT_TENANT_ID
    ) -> ConfigThresholdState | None:
        latest = _latest_change_id_subquery(tenant_id=tenant_id)
        stmt = (
            select(ConfigThreshold, ConfigThresholdChange)
            .join(latest, ConfigThreshold.id == latest.c.config_threshold_id)
            .join(ConfigThresholdChange, ConfigThresholdChange.id == latest.c.change_id)
            .where(
                ConfigThreshold.key == key,
                ConfigThreshold.tenant_id == tenant_id,
            )
        )
        row = (await self.session.execute(stmt)).one_or_none()
        if row is None:
            config = await self._get_metadata_by_key(key, tenant_id=tenant_id)
            if config is None:
                return None
            return None
        config, change = row
        return _state_from_row(config, change)

    async def get_metadata_by_key(
        self, key: str, *, tenant_id: int = DEFAULT_TENANT_ID
    ) -> ConfigThreshold | None:
        return await self._get_metadata_by_key(key, tenant_id=tenant_id)

    async def _get_metadata_by_key(
        self, key: str, *, tenant_id: int = DEFAULT_TENANT_ID
    ) -> ConfigThreshold | None:
        stmt = select(ConfigThreshold).where(
            ConfigThreshold.key == key,
            ConfigThreshold.tenant_id == tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_latest_change(self, config_threshold_id: int) -> ConfigThresholdChange | None:
        stmt = (
            select(ConfigThresholdChange)
            .where(ConfigThresholdChange.config_threshold_id == config_threshold_id)
            .order_by(ConfigThresholdChange.updated_at.desc(), ConfigThresholdChange.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_changes(
        self,
        key: str,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ConfigThresholdChangeRecord], int]:
        config = await self._get_metadata_by_key(key, tenant_id=tenant_id)
        if config is None:
            return [], 0

        count_stmt = (
            select(func.count())
            .select_from(ConfigThresholdChange)
            .where(
                ConfigThresholdChange.config_threshold_id == config.id,
                ConfigThresholdChange.tenant_id == tenant_id,
            )
        )
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(ConfigThresholdChange)
            .where(
                ConfigThresholdChange.config_threshold_id == config.id,
                ConfigThresholdChange.tenant_id == tenant_id,
            )
            .order_by(ConfigThresholdChange.updated_at.desc(), ConfigThresholdChange.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        records = [
            ConfigThresholdChangeRecord(
                previous_value_json=row.previous_value_json,
                current_value_json=row.current_value_json,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
        return records, total

    async def update_config(
        self,
        key: str,
        value_json: Any,
        *,
        tenant_id: int = DEFAULT_TENANT_ID,
        updated_by: str,
        title: str | None = None,
        description: str | None = None,
    ) -> ConfigThresholdState | None:
        config = await self._get_metadata_by_key(key, tenant_id=tenant_id)
        if config is None:
            return None

        if title is not None:
            config.title = title
        if description is not None:
            config.description = description

        latest = await self._get_latest_change(config.id)
        value_changed = latest is None or latest.current_value_json != value_json
        if value_changed:
            next_version = 1 if latest is None else latest.version + 1
            previous_value = None if latest is None else latest.current_value_json
            change = ConfigThresholdChange(
                tenant_id=tenant_id,
                config_threshold_id=config.id,
                key=config.key,
                previous_value_json=previous_value,
                current_value_json=value_json,
                version=next_version,
                updated_by=updated_by,
            )
            self.session.add(change)
            await self.session.flush()
            latest = change

        await self.session.flush()
        if latest is None:
            return None
        return _state_from_row(config, latest)
