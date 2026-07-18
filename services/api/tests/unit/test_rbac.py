from __future__ import annotations

import pytest

from app.core.rbac import Permission, has_permission


def test_owner_has_all_permissions() -> None:
    assert all(has_permission("owner", permission) for permission in Permission)


def test_admin_matrix_excludes_user_management() -> None:
    assert has_permission("admin", Permission.CAMPAIGN_WRITE)
    assert has_permission("admin", Permission.PHONE_REVEAL)
    assert not has_permission("admin", Permission.USERS_MANAGE)


def test_sales_agent_allowed_lead_call_subset_only() -> None:
    assert has_permission("sales_agent", Permission.LEADS_READ)
    assert has_permission("sales_agent", Permission.LEADS_WRITE)
    assert has_permission("sales_agent", Permission.CALL_INITIATE)
    assert not has_permission("sales_agent", Permission.USERS_MANAGE)
    assert not has_permission("sales_agent", Permission.SETTINGS_WRITE)
    assert not has_permission("sales_agent", Permission.PHONE_REVEAL)


def test_viewer_is_read_only_and_cannot_reveal_phone() -> None:
    assert has_permission("viewer", Permission.LEADS_READ)
    assert has_permission("viewer", Permission.CAMPAIGN_READ)
    assert not has_permission("viewer", Permission.LEADS_WRITE)
    assert not has_permission("viewer", Permission.PHONE_REVEAL)


def test_unknown_role_or_permission_denied() -> None:
    assert not has_permission("owner ", Permission.USERS_MANAGE)
    assert not has_permission("viewer\nowner", Permission.USERS_MANAGE)
    assert not has_permission("viewer", Permission.USERS_MANAGE)

    with pytest.raises(ValueError):
        Permission("does_not_exist")
