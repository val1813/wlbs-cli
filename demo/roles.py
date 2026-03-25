"""roles.py — defines Role and permission registry.

This is the ROOT CAUSE module in the paper's example:
  roles.py exports get_permissions(); rbac.py imports and calls it.
  A bug here manifests as an error in rbac.py (downstream),
  but the cause lives here (upstream).
"""

# Intentional bug for validation: 'admin' key is missing
PERMISSIONS = {
    "editor": ["read", "write"],
    "viewer": ["read"],
    # 'admin' deliberately omitted — causes KeyError in rbac.py
}


def get_permissions(role: str) -> list:
    """Return permissions for a role. Raises KeyError if role unknown."""
    return PERMISSIONS[role]  # Bug: no .get() fallback


def list_roles() -> list:
    return list(PERMISSIONS.keys())


def add_role(role: str, perms: list) -> None:
    PERMISSIONS[role] = perms
