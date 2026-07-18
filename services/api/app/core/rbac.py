"""Rol tabanlı yetkilendirme matrisi."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SALES_AGENT = "sales_agent"
    VIEWER = "viewer"


class Permission(StrEnum):
    LEADS_READ = "leads:read"
    LEADS_WRITE = "leads:write"
    LEADS_IMPORT = "leads:import"
    LEADS_EXPORT = "leads:export"
    PHONE_REVEAL = "phone:reveal"
    CALL_INITIATE = "call:initiate"
    CALL_TERMINATE = "call:terminate"
    CAMPAIGN_READ = "campaign:read"
    CAMPAIGN_WRITE = "campaign:write"
    CAMPAIGN_CONTROL = "campaign:control"
    PREMIUM_MODEL = "model:premium"
    KB_WRITE = "kb:write"
    PROMPT_WRITE = "prompt:write"
    PRICING_WRITE = "pricing:write"
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"
    USERS_MANAGE = "users:manage"
    SUPPRESSION_WRITE = "suppression:write"
    SUPPRESSION_REMOVE = "suppression:remove"
    AUDIT_READ = "audit:read"
    COSTS_READ = "costs:read"


_MATRIX: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(Permission) - frozenset({Permission.USERS_MANAGE}),
    Role.SALES_AGENT: frozenset(
        {
            Permission.LEADS_READ,
            Permission.LEADS_WRITE,
            Permission.CALL_INITIATE,
            Permission.CALL_TERMINATE,
            Permission.CAMPAIGN_READ,
            Permission.COSTS_READ,
            Permission.SUPPRESSION_WRITE,
        }
    ),
    Role.VIEWER: frozenset(
        {Permission.LEADS_READ, Permission.CAMPAIGN_READ, Permission.COSTS_READ}
    ),
}


def has_permission(role: str, permission: Permission) -> bool:
    try:
        return permission in _MATRIX[Role(role)]
    except ValueError:
        return False


def permissions_for(role: str) -> list[str]:
    try:
        return sorted(p.value for p in _MATRIX[Role(role)])
    except ValueError:
        return []
