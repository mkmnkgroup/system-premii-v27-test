import pytest
from secure_draft_access import DraftAccessDenied, authorized_identity, isolated_test_connection
from workflow_drafts import draft_key


class User:
    def __init__(self, email='', logged_in=False):
        self.email = email
        self.is_logged_in = logged_in


def test_rejects_unauthenticated_user():
    with pytest.raises(DraftAccessDenied):
        authorized_identity(User('staff@example.com'), ['staff@example.com'])


def test_rejects_unlisted_user():
    with pytest.raises(DraftAccessDenied):
        authorized_identity(User('other@example.com', True), ['staff@example.com'])


def test_accepts_only_allowed_logged_in_user():
    assert authorized_identity(User('STAFF@example.com', True), ['staff@example.com']) == 'staff@example.com'


def test_rejects_missing_allowlist():
    with pytest.raises(DraftAccessDenied):
        authorized_identity(User('staff@example.com', True), [])


def test_test_database_must_be_isolated():
    with pytest.raises(DraftAccessDenied):
        isolated_test_connection('postgresql://postgres:password@db.epggtvgjfraflzibqrvr.supabase.co/postgres')
    with pytest.raises(DraftAccessDenied):
        isolated_test_connection('postgresql://postgres:password@db.bzpfukyugfuybqivjyoz.supabase.co/postgres')
    assert isolated_test_connection('postgresql://v27_test_app:password@db.bzpfukyugfuybqivjyoz.supabase.co/postgres')


def test_period_keys_are_scoped_and_validated():
    assert draft_key('2026-11', 'schedule') == 'draft_v27:2026-11:schedule'
    with pytest.raises(ValueError):
        draft_key('2026-13', 'schedule')
    with pytest.raises(ValueError):
        draft_key('2026-11', 'unknown')
