"""Focused lifecycle manual edit regression tests; no database connection."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.permission_policy_v2 import permission_for_request
from app.modules.data_pages.lifecycle_manual import set_manual_lifecycle
from app.modules.data_pages.schemas import ListingLifecycleBatchSetRequest
from app.modules.integration_sync.data_pages_real_sync import (
    LISTING_MART_REFRESH_UPDATE_EXPRESSIONS,
)


@pytest.mark.parametrize(
    "stage",
    [
        "测品期",
        "打品期",
        "启动期",
        "上升期",
        "稳定期",
        "下滑期",
        "断货期",
        "修复期",
    ],
)
def test_manual_operational_stages_accepted(stage):
    value = ListingLifecycleBatchSetRequest(listing_ids=[uuid4()], stage=stage)
    assert value.stage == stage


@pytest.mark.parametrize("stage", ["清货期", "已归档", "其他", ""])
def test_workflow_stages_not_manually_selectable(stage):
    with pytest.raises(ValidationError):
        ListingLifecycleBatchSetRequest(listing_ids=[uuid4()], stage=stage)


def test_new_action_permission_precedes_generic_archive_rule():
    result = permission_for_request(
        "POST",
        "/api/listings/walmart/lifecycle/batch-set",
        "page:products:listing-management:view",
    )
    assert result == "action:products:listing-management:edit-lifecycle"


def test_normal_listing_refresh_preserves_operator_status():
    assert "lifecycle_status" not in LISTING_MART_REFRESH_UPDATE_EXPRESSIONS


def test_scoped_atomic_single_manual_change():
    listing_id = uuid4()
    row = SimpleNamespace(
        id=listing_id,
        source_account_ref="account-a",
        store_id="store-x",
        item_id="item-1",
        msku="sku-1",
        lifecycle_status=None,
    )
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = [row]
    session.execute.return_value.scalars.return_value.all.return_value = []
    changed, unchanged = set_manual_lifecycle(
        session=session,
        listing_ids=[listing_id],
        stage="启动期",
        reason="运营首次设置",
        actor_ref="operator",
        account_refs=frozenset({"account-a"}),
    )
    assert (changed, unchanged) == (1, 0)
    assert row.lifecycle_status == "启动期"
    assert session.execute.call_count == 3  # archive check, state upsert, immutable audit
    session.commit.assert_called_once()


def test_out_of_scope_batch_fails_without_commit():
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = []
    with pytest.raises(PermissionError):
        set_manual_lifecycle(
            session=session,
            listing_ids=[uuid4()],
            stage="启动期",
            reason="人工初始化",
            actor_ref="operator",
            account_refs=frozenset({"account-a"}),
        )
    session.commit.assert_not_called()
