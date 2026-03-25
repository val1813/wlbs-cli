"""rbac.py — Role-Based Access Control checker.

This is the DOWNSTREAM module: it imports roles.get_permissions().
Errors raised here originate in roles.py (behavioral distance = 1 hop).
This mirrors the paper's concrete failure-mode example exactly.
"""
from roles import get_permissions


class RBACManager:
    def __init__(self):
        self._cache = {}

    def check_access(self, user_role: str, required_perm: str) -> bool:
        """Return True if user_role has required_perm."""
        if user_role not in self._cache:
            self._cache[user_role] = get_permissions(user_role)  # may raise KeyError
        return required_perm in self._cache[user_role]

    def grant_permissions(self, role: str, perm: str) -> None:
        perms = get_permissions(role)
        if perm not in perms:
            perms.append(perm)

    def revoke_permissions(self, role: str, perm: str) -> None:
        perms = get_permissions(role)
        if perm in perms:
            perms.remove(perm)
