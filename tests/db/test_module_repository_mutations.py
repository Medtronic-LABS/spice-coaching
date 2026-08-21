"""ModuleRepository — edit, review, retire, count, merge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from platform_service.db.models.behavioural_gap import BehaviouralGap
from platform_service.db.models.module import Module
from platform_service.db.module_availability import LIFECYCLE_REVIEW_PENDING
from platform_service.db.repositories.module_gap_repository import ModuleGapRepository
from platform_service.db.repositories.module_lifecycle_repository import (
    ModuleLifecycleError,
    ModuleLifecycleRepository,
)
from platform_service.db.repositories.module_repository import (
    ModuleNotFoundError,
    ModuleRepository,
    ModuleVersionConflictError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.db.conftest import (
    _make_family,
    _make_module,
)
from tests.helpers.hierarchy_fixtures import AM_ID, PO_ID, seed_basic_hierarchy

pytestmark = [requires_db, pytest.mark.asyncio]


class TestEditModule:
    async def test_creates_new_version_with_supersedes_pointer(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1 title"}, version=1)

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "v2 title"})

        assert v2.id != v1.id
        assert v2.module_family_id == fam.id
        assert v2.version == 2
        assert v2.supersedes_module_id == v1.id
        assert v2.title_localized["bn"] == "v2 title"

    async def test_resets_clinically_reviewed_to_false(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session,
            family=fam,
            clinically_reviewed=True,
        )
        v1.clinically_reviewed_at = datetime.now(UTC)
        v1.clinically_reviewed_by = uuid4()

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "new title"})
        # New version starts unreviewed regardless of v1's flag.
        assert v2.clinically_reviewed is False

    async def test_copies_unchanged_fields_forward(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "v1"},
            description_localized={"bn": "original desc"},
            domain="rmnch",
        )
        v1.estimated_minutes = 15
        v1.difficulty_level = "hard"
        v1.module_type = "content_update"

        repo = ModuleRepository(db_session)
        # Edit ONLY the title.
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "v2"})

        assert v2.title_localized["bn"] == "v2"
        # Untouched fields copy forward.
        assert v2.description_localized["bn"] == "original desc"
        assert v2.domain == "rmnch"
        assert v2.estimated_minutes == 15
        assert v2.difficulty_level == "hard"
        assert v2.module_type == "content_update"

    async def test_edit_updates_domain_and_estimated_minutes(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1"}, domain="rmnch")
        v1.estimated_minutes = 15

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(
            v1.id,
            expected_version=v1.version,
            domain="ncd",
            estimated_minutes=25,
        )

        assert v2.domain == "ncd"
        assert v2.estimated_minutes == 25
        assert v2.title_localized["bn"] == "v1"

    async def test_updates_family_current_pointer(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1"})
        # Verify pointer starts at v1.
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v1.id

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "v2"})
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

    async def test_edit_unknown_module_raises(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.edit_module(uuid4(), expected_version=1, title={"bn": "x"})

    async def test_rejects_version_mismatch(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1"})

        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleVersionConflictError) as exc_info:
            await repo.edit_module(v1.id, expected_version=99, title={"bn": "nope"})
        assert exc_info.value.expected_version == 99
        assert exc_info.value.current_version == v1.version
        assert exc_info.value.latest_module_id == v1.id

    async def test_rejects_edit_when_not_family_tip(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1"}, version=1)
        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "v2"})

        with pytest.raises(ModuleVersionConflictError) as exc_info:
            await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "fork"})
        assert exc_info.value.current_version == v2.version
        assert exc_info.value.latest_module_id == v2.id

    async def test_edit_creates_draft_successor_without_retiring_prior(
        self, db_session: AsyncSession
    ) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1"})
        assert v1.lifecycle_status == "published"

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "v2"})
        await db_session.refresh(v1)

        assert v1.lifecycle_status == "published"
        assert v2.lifecycle_status == "draft"
        assert v2.supersedes_module_id == v1.id
        assert v2.version == v1.version + 1

    async def test_edit_retired_module_raises(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam, lifecycle_status="retired", set_family_pointer=False)

        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.edit_module(m.id, expected_version=m.version, title={"bn": "post-retire"})

    async def test_edit_replaces_module_json_when_provided(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, module_json={"cards": [{"title": {"bn": "old"}}]})

        repo = ModuleRepository(db_session)
        new_cards = {"cards": [{"title": {"bn": "new1"}}, {"title": {"bn": "new2"}}]}
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, module_json=new_cards)
        assert v2.module_json == new_cards

    async def test_edit_copies_behavioural_gap_links(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1"})
        gap_a = BehaviouralGap(
            gap_code=f"gap_a_{uuid4().hex[:8]}",
            description="a",
            domain="rmnch",
            detection_rule_jsonb={},
            tenant_id=1,
        )
        gap_b = BehaviouralGap(
            gap_code=f"gap_b_{uuid4().hex[:8]}",
            description="b",
            domain="rmnch",
            detection_rule_jsonb={},
            tenant_id=1,
        )
        db_session.add_all([gap_a, gap_b])
        await db_session.flush()
        gap_repo = ModuleGapRepository(db_session)
        await gap_repo.replace_links(v1.id, gap_ids=[gap_a.id, gap_b.id], primary_gap_id=gap_a.id)

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "v2"})

        v2_gap_ids = await gap_repo.get_gap_ids(v2.id)
        assert set(v2_gap_ids) == {gap_a.id, gap_b.id}
        await db_session.refresh(v2)
        assert v2.primary_gap_id == gap_a.id

    async def test_edit_copies_thumbnail_when_omitted(self, db_session: AsyncSession) -> None:
        thumb = f"medtronics-storage/ingest/thumbnails/{uuid4()}.png"
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, thumbnail_storage_path=thumb)

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "v2"})

        assert v2.thumbnail_storage_path == thumb

    async def test_edit_clears_thumbnail_when_set_null(self, db_session: AsyncSession) -> None:
        thumb = f"medtronics-storage/ingest/thumbnails/{uuid4()}.png"
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, thumbnail_storage_path=thumb)

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(
            v1.id,
            expected_version=v1.version,
            title={"bn": "v2"},
            thumbnail_storage_path=None,
        )

        assert v2.thumbnail_storage_path is None

    async def test_edit_replaces_thumbnail(self, db_session: AsyncSession) -> None:
        old_thumb = f"medtronics-storage/ingest/thumbnails/{uuid4()}.png"
        new_thumb = f"medtronics-storage/module-thumbnails/{uuid4()}.png"
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, thumbnail_storage_path=old_thumb)

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(
            v1.id,
            expected_version=v1.version,
            title={"bn": "v2"},
            thumbnail_storage_path=new_thumb,
        )

        assert v2.thumbnail_storage_path == new_thumb

    async def test_edit_retargets_review_pending_merge_source_both_sides(
        self, db_session: AsyncSession
    ) -> None:
        source_fam = await _make_family(db_session)
        source = await _make_module(
            db_session,
            family=source_fam,
            title_localized={"bn": "source"},
            version=1,
        )
        pair_fam = await _make_family(db_session)
        secondary = await _make_module(
            db_session,
            family=pair_fam,
            title_localized={"bn": "secondary"},
            version=1,
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            set_family_pointer=False,
        )
        primary = await _make_module(
            db_session,
            family=pair_fam,
            title_localized={"bn": "primary"},
            version=2,
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            set_family_pointer=False,
        )
        primary.merge_secondary_module_id = secondary.id
        primary.merge_source_module_id = source.id
        secondary.merge_primary_module_id = primary.id
        secondary.merge_source_module_id = source.id
        await db_session.flush()

        repo = ModuleRepository(db_session)
        new_tip = await repo.edit_module(
            source.id,
            expected_version=source.version,
            title={"bn": "source v2"},
        )

        await db_session.refresh(primary)
        await db_session.refresh(secondary)
        assert primary.merge_source_module_id == new_tip.id
        assert secondary.merge_source_module_id == new_tip.id
        assert primary.merge_source_module_id != source.id

    async def test_edit_retargets_all_review_pending_pairs_sharing_source(
        self, db_session: AsyncSession
    ) -> None:
        source_fam = await _make_family(db_session)
        source = await _make_module(
            db_session,
            family=source_fam,
            title_localized={"bn": "shared source"},
            version=1,
        )
        pair_a_fam = await _make_family(db_session)
        secondary_a = await _make_module(
            db_session,
            family=pair_a_fam,
            title_localized={"bn": "secondary a"},
            version=1,
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            set_family_pointer=False,
        )
        primary_a = await _make_module(
            db_session,
            family=pair_a_fam,
            title_localized={"bn": "primary a"},
            version=2,
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            set_family_pointer=False,
        )
        primary_a.merge_secondary_module_id = secondary_a.id
        primary_a.merge_source_module_id = source.id
        secondary_a.merge_primary_module_id = primary_a.id
        secondary_a.merge_source_module_id = source.id

        pair_b_fam = await _make_family(db_session)
        secondary_b = await _make_module(
            db_session,
            family=pair_b_fam,
            title_localized={"bn": "secondary b"},
            version=1,
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            set_family_pointer=False,
        )
        primary_b = await _make_module(
            db_session,
            family=pair_b_fam,
            title_localized={"bn": "primary b"},
            version=2,
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            set_family_pointer=False,
        )
        primary_b.merge_secondary_module_id = secondary_b.id
        primary_b.merge_source_module_id = source.id
        secondary_b.merge_primary_module_id = primary_b.id
        secondary_b.merge_source_module_id = source.id
        await db_session.flush()

        other_source = await _make_module(
            db_session,
            title_localized={"bn": "other source"},
            version=1,
        )
        unrelated = await _make_module(
            db_session,
            title_localized={"bn": "unrelated pending"},
            version=1,
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            set_family_pointer=False,
        )
        unrelated.merge_source_module_id = other_source.id
        await db_session.flush()

        repo = ModuleRepository(db_session)
        new_tip = await repo.edit_module(
            source.id,
            expected_version=source.version,
            title={"bn": "shared source v2"},
        )

        for row in (primary_a, secondary_a, primary_b, secondary_b):
            await db_session.refresh(row)
            assert row.merge_source_module_id == new_tip.id

        await db_session.refresh(unrelated)
        assert unrelated.merge_source_module_id == other_source.id

    async def test_edit_without_review_pending_merge_source_unchanged(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "solo"})

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, expected_version=v1.version, title={"bn": "solo v2"})

        assert v2.id != v1.id
        assert v2.merge_source_module_id is None


# ─── retire_module: family pointer cascade ─────────────────────────────────


class TestRetireModule:
    async def test_retire_sets_status_and_retired_at(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam)

        repo = ModuleRepository(db_session)
        out = await repo.retire_module(m.id)

        assert out.lifecycle_status == "retired"
        assert out.retired_at is not None

    async def test_retire_sets_retired_by_user_id(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam)

        repo = ModuleRepository(db_session)
        out = await repo.retire_module(m.id, retired_by_user_id=PO_ID)

        assert out.retired_by == PO_ID

    async def test_retire_idempotent_does_not_overwrite_retired_by(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam)

        repo = ModuleRepository(db_session)
        await repo.retire_module(m.id, retired_by_user_id=AM_ID)
        await repo.retire_module(m.id, retired_by_user_id=PO_ID)

        await db_session.refresh(m)
        assert m.retired_by == AM_ID

    async def test_retire_falls_back_to_prior_published_version(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "v1"}, version=1)
        v2 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "v2"},
            version=2,
            published_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

        repo = ModuleRepository(db_session)
        await repo.retire_module(v2.id)

        await db_session.refresh(fam)
        # Pointer falls back to v1.
        assert fam.current_published_module_id == v1.id

    async def test_retire_clears_family_pointer_when_no_other_published(
        self, db_session: AsyncSession
    ) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_localized={"bn": "only"})
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v1.id

        repo = ModuleRepository(db_session)
        await repo.retire_module(v1.id)

        await db_session.refresh(fam)
        assert fam.current_published_module_id is None

    async def test_retiring_non_pointer_version_does_not_clear_pointer(
        self, db_session: AsyncSession
    ) -> None:
        """Retiring v1 when v2 is the family's current pointer must leave
        the pointer at v2."""
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session, family=fam, title_localized={"bn": "v1"}, version=1, set_family_pointer=False
        )
        v2 = await _make_module(db_session, family=fam, title_localized={"bn": "v2"}, version=2)
        # Pointer is on v2.
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

        repo = ModuleRepository(db_session)
        await repo.retire_module(v1.id)

        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

    async def test_retire_unknown_raises(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.retire_module(uuid4())


# ─── count_modules: mirror of list-default ─────────────────────────────────


class TestCountModules:
    async def test_default_excludes_retired(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        await _make_module(db_session, family=fam, title_localized={"bn": "live"})
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_localized={"bn": "retired"},
            lifecycle_status="retired",
            set_family_pointer=False,
        )

        repo = ModuleRepository(db_session)
        # Count all (excludes retired by default). We can't pin an exact
        # number because other tests in the same session might have left
        # rows; instead assert that count(default) == count(status=published)
        # for the modules we just inserted (no other state should be retired).
        published = await repo.count_modules(status="published")
        default = await repo.count_modules()
        retired = await repo.count_modules(status="retired")
        assert default == published
        assert retired >= 1  # at least our retired one

    async def test_default_includes_review_pending_and_deactivated(self, db_session: AsyncSession) -> None:
        marker = f"count-rp-{uuid4().hex[:6]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_localized={"bn": marker},
            lifecycle_status="review_pending",
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_localized={"bn": f"{marker}-deactivated"},
            lifecycle_status="deactivated",
            set_family_pointer=False,
        )

        repo = ModuleRepository(db_session)
        default_rows = await repo.list_modules(full_text_query=marker)
        review_pending = await repo.count_modules(status="review_pending", full_text_query=marker)
        deactivated = await repo.count_modules(status="deactivated", full_text_query=marker)
        default = await repo.count_modules(full_text_query=marker)
        titles = {m.title_localized["bn"] for m in default_rows}
        assert marker in titles
        assert f"{marker}-deactivated" in titles
        assert review_pending == 1
        assert deactivated == 1
        assert default == 2

    async def test_clinically_reviewed_filter_count(self, db_session: AsyncSession) -> None:
        # Use a unique tag in description so we can isolate.
        marker = f"count-test-{uuid4().hex[:6]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            description_localized={"bn": marker},
            clinically_reviewed=True,
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            description_localized={"bn": marker},
            clinically_reviewed=False,
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            description_localized={"bn": marker},
            clinically_reviewed=False,
        )

        # Count flips with the filter.
        repo = ModuleRepository(db_session)
        # Direct query for our marker since count_modules lacks a description filter.
        reviewed = (
            (
                await db_session.execute(
                    select(
                        ModuleRepository.__init__.__globals__["Module"]
                    ).where(  # use Module from the repo's namespace
                        Module.description_localized["bn"] == marker, Module.clinically_reviewed.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        unreviewed = (
            (
                await db_session.execute(
                    select(Module).where(
                        Module.description_localized["bn"] == marker, Module.clinically_reviewed.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(reviewed) == 1
        assert len(unreviewed) == 2
        # And the repo's count_modules with the flag filter is at least these.
        assert await repo.count_modules(clinically_reviewed=True) >= 1
        assert await repo.count_modules(clinically_reviewed=False) >= 2


def _merge_tip_cards(title: str) -> dict:
    return {
        "cards": [
            {
                "title": {"bn": title},
                "body": {"bn": "b"},
                "next_action": {"bn": "n"},
                "source_block_ids": [],
            }
        ]
    }


class TestListActiveModulesForMerge:
    async def test_prefers_published_over_later_draft(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "v1 published"},
            lifecycle_status="published",
            version=1,
            module_json=_merge_tip_cards("c1"),
        )
        v2 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "v2 draft"},
            lifecycle_status="draft",
            version=2,
            module_json=_merge_tip_cards("c2"),
            set_family_pointer=False,
        )
        await _make_module(
            db_session,
            title_localized={"bn": "retired row"},
            lifecycle_status="retired",
            version=1,
            module_json=_merge_tip_cards("c"),
        )
        await db_session.commit()

        active = await repo.list_active_modules_for_merge(tenant_id=1)
        ids = {m.id for m in active}
        assert v1.id in ids
        assert v2.id not in ids

    async def test_draft_only_family_returns_latest_draft(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "draft v1"},
            lifecycle_status="draft",
            version=1,
            module_json=_merge_tip_cards("c1"),
            set_family_pointer=False,
        )
        v2 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "draft v2"},
            lifecycle_status="draft",
            version=2,
            module_json=_merge_tip_cards("c2"),
            set_family_pointer=False,
        )
        await db_session.commit()

        ids = {m.id for m in await repo.list_active_modules_for_merge(tenant_id=1)}
        assert v2.id in ids
        assert v1.id not in ids

    async def test_two_published_versions_returns_latest_published(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "published v1"},
            lifecycle_status="published",
            version=1,
            module_json=_merge_tip_cards("c1"),
        )
        v2 = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "published v2"},
            lifecycle_status="published",
            version=2,
            module_json=_merge_tip_cards("c2"),
        )
        await db_session.commit()

        ids = {m.id for m in await repo.list_active_modules_for_merge(tenant_id=1)}
        assert v2.id in ids
        assert v1.id not in ids

    async def test_ignores_later_review_pending_and_keeps_published(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        fam = await _make_family(db_session)
        published = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "published tip"},
            lifecycle_status="published",
            version=1,
            module_json=_merge_tip_cards("c1"),
        )
        pending = await _make_module(
            db_session,
            family=fam,
            title_localized={"bn": "review pending"},
            lifecycle_status=LIFECYCLE_REVIEW_PENDING,
            version=2,
            module_json=_merge_tip_cards("c2"),
            set_family_pointer=False,
        )
        await db_session.commit()

        ids = {m.id for m in await repo.list_active_modules_for_merge(tenant_id=1)}
        assert published.id in ids
        assert pending.id not in ids

    async def test_excludes_modules_with_empty_cards(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        empty = await _make_module(
            db_session,
            title_localized={"bn": "no cards"},
            module_json={"cards": []},
            lifecycle_status="published",
        )
        await db_session.commit()
        ids = {m.id for m in await repo.list_active_modules_for_merge(tenant_id=1)}
        assert empty.id not in ids

    async def test_excludes_other_tenant_modules(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        ours = await _make_module(
            db_session,
            title_localized={"bn": "tenant 1"},
            lifecycle_status="published",
            module_json=_merge_tip_cards("c1"),
            tenant_id=1,
        )
        theirs = await _make_module(
            db_session,
            title_localized={"bn": "tenant 99"},
            lifecycle_status="published",
            module_json=_merge_tip_cards("c99"),
            tenant_id=99,
        )
        await db_session.commit()

        ids = {m.id for m in await repo.list_active_modules_for_merge(tenant_id=1)}
        assert ours.id in ids
        assert theirs.id not in ids


class TestLifecycleRepositoryPublish:
    async def test_publish_changes_status_and_timestamps(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="draft")

        repo = ModuleLifecycleRepository(db_session)
        state = await repo.publish(mod.id, reason="Admin manual publish")

        assert state.lifecycle_status == "published"
        assert state.activated_at is not None

        await db_session.refresh(mod)
        assert mod.lifecycle_status == "published"
        assert mod.published_at is not None

        await db_session.refresh(fam)
        assert fam.current_published_module_id == mod.id

    async def test_publish_sets_published_by_user_id(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="draft")

        repo = ModuleLifecycleRepository(db_session)
        await repo.publish(mod.id, published_by_user_id=PO_ID, reason="Admin manual publish")

        await db_session.refresh(mod)
        assert mod.published_by == PO_ID

    async def test_publish_idempotent_does_not_overwrite_published_by(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="draft")

        repo = ModuleLifecycleRepository(db_session)
        await repo.publish(mod.id, published_by_user_id=AM_ID)
        await repo.publish(mod.id, published_by_user_id=PO_ID)

        await db_session.refresh(mod)
        assert mod.published_by == AM_ID

    async def test_publish_retired_module_raises_error(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="retired")

        repo = ModuleLifecycleRepository(db_session)
        with pytest.raises(ModuleLifecycleError):
            await repo.publish(mod.id)

    async def test_deactivate_sets_deactivated_by_user_id(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="published")

        repo = ModuleLifecycleRepository(db_session)
        await repo.deactivate(mod.id, deactivated_by_user_id=PO_ID, reason="Seasonal pause")

        await db_session.refresh(mod)
        assert mod.deactivated_by == PO_ID
        assert mod.lifecycle_status == "deactivated"

    async def test_reactivate_sets_activated_by_user_id(self, db_session: AsyncSession) -> None:
        await seed_basic_hierarchy(db_session)
        fam = await _make_family(db_session)
        mod = await _make_module(db_session, family=fam, lifecycle_status="published")

        repo = ModuleLifecycleRepository(db_session)
        await repo.deactivate(mod.id, deactivated_by_user_id=PO_ID)
        await repo.reactivate(mod.id, activated_by_user_id=AM_ID, reason="Resume program")

        await db_session.refresh(mod)
        assert mod.activated_by == AM_ID
        assert mod.lifecycle_status == "published"


# Suppress unused-import lint when only referenced via select(...)
_ = UUID
