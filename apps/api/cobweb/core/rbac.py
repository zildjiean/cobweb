"""RBAC enforcement.

Permission matrix (role × action):

                       view    create  modify  delete  trigger_scan  audit_export
    admin                ✓       ✓       ✓       ✓        ✓             ✓
    project_admin        ✓       ✓       ✓       ✓ (own)  ✓             ✗
    user                 ✓       ✓       ✓ (own) ✗        ✓             ✗
    auditor              ✓       ✗       ✗       ✗        ✗             ✓
"""

from __future__ import annotations

from cobweb.models.org import OrgRole

PERMISSIONS: dict[OrgRole, set[str]] = {
    OrgRole.ADMIN: {
        "org:manage", "org:view",
        "project:create", "project:view", "project:update", "project:delete",
        "target:create", "target:view", "target:update", "target:delete",
        "scan:create", "scan:view", "scan:cancel", "scan:delete",
        "vuln:view", "vuln:update",
        "finding:delete", "finding:translate", "finding:remediate",
        "user:invite", "user:remove",
        "apitoken:manage",
        "audit:view", "audit:export",
        "integration:manage",
        "llm:configure",
    },
    OrgRole.PROJECT_ADMIN: {
        "org:view",
        "project:create", "project:view", "project:update", "project:delete",
        "target:create", "target:view", "target:update", "target:delete",
        "scan:create", "scan:view", "scan:cancel", "scan:delete",
        "vuln:view", "vuln:update",
        "finding:delete", "finding:translate", "finding:remediate",
        "user:invite",
        "apitoken:manage",
    },
    OrgRole.USER: {
        "org:view",
        "project:view",
        "target:view",
        "scan:create", "scan:view",
        "vuln:view", "vuln:update",
        "finding:translate", "finding:remediate",
    },
    OrgRole.AUDITOR: {
        "org:view",
        "project:view", "target:view",
        "scan:view", "vuln:view",
        "audit:view", "audit:export",
    },
}


def has_permission(role: OrgRole, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())


def require(role: OrgRole, permission: str) -> None:
    from fastapi import HTTPException, status

    if not has_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role.value}' lacks permission '{permission}'",
        )
