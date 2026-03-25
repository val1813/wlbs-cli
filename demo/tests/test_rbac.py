"""Test suite for rbac.py — errors here trace back to roles.py (d=1 hop)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rbac import RBACManager


def test_editor_read_access():
    mgr = RBACManager()
    assert mgr.check_access("editor", "read") is True


def test_editor_write_access():
    mgr = RBACManager()
    assert mgr.check_access("editor", "write") is True


def test_viewer_read_access():
    mgr = RBACManager()
    assert mgr.check_access("viewer", "read") is True


def test_viewer_no_write():
    mgr = RBACManager()
    assert mgr.check_access("viewer", "write") is False


def test_admin_access():
    """This test FAILS because 'admin' is missing from roles.PERMISSIONS.
    The error manifests in rbac.py but the root cause is in roles.py.
    This is the exact cross-file failure scenario from the paper.
    """
    mgr = RBACManager()
    assert mgr.check_access("admin", "read") is True  # KeyError from roles.py


def test_grant_permissions():
    """Also fails for the same root cause."""
    mgr = RBACManager()
    mgr.grant_permissions("admin", "delete")  # KeyError from roles.py
