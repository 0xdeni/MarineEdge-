"""Accounts: owner setup, invites, sign-in, password reset (code and link), profile, team guards.
In-memory store and a fake mailer, so it runs anywhere in a second."""
from __future__ import annotations

import os

from app import accounts as acc
from app.store import MemoryStore


class FakeMailer:
    def __init__(self, on: bool = True):
        self.on = on
        self.sent: list[tuple[str, str, str]] = []

    def configured(self) -> bool:
        return self.on

    def send(self, to, subject, text, html=None):
        self.sent.append((to, subject, text))


def _setup(tokens: str = "admin:owner-setup-code-1:admin", mail: bool = True):
    os.environ["API_TOKENS"] = tokens
    acc.LIMITS.reset()
    st = MemoryStore()
    return st, acc.Accounts(st, FakeMailer(mail))


def _raises(fn, code: str):
    try:
        fn()
    except acc.AccountError as e:
        assert e.code == code, f"expected {code}, got {e.code}: {e}"
        return e
    raise AssertionError(f"expected AccountError {code}")


def test_password_hash_roundtrip_and_rules():
    h = acc.hash_password("correct horse battery")
    assert h.startswith("scrypt$") and acc.verify_password("correct horse battery", h)
    assert not acc.verify_password("correct horse batterY", h) and not acc.verify_password("x", None)
    _raises(lambda: acc.check_password_rules("short"), "weak_password")
    _raises(lambda: acc.check_password_rules("aaaaaaaaaaaa"), "weak_password")
    _raises(lambda: acc.check_password_rules("deni-dudaev-2026", email="deni@example.com", name="Deni Dudaev"), "weak_password")
    _raises(lambda: acc.check_password_rules("password123"), "weak_password")
    acc.check_password_rules("tide-chart-bosporus-41")


def test_first_account_needs_the_setup_code_and_becomes_admin():
    st, a = _setup()
    assert a.state()["setup"] is True
    _raises(lambda: a.signup("Deni", "deni@example.com", "a-long-pass-phrase", setup_code="nope"), "bad_setup_code")
    s = a.signup("Deni Dudaev", " Deni@Example.com ", "a-long-pass-phrase", setup_code="owner-setup-code-1", ua="iPhone Safari")
    assert s.user["email"] == "deni@example.com" and s.user["role"] == "admin" and s.token
    assert a.state()["setup"] is False
    who = a.session_user(s.token)
    assert who and who[0]["id"] == s.user["id"]
    assert st.get_session(acc.sha256(s.token))["token_hash"] != s.token          # only the hash is stored


def test_owner_adopts_the_old_token_users_state():
    st, a = _setup("deni:owner-setup-code-1:admin")
    st.set_watchlist("deni", [9000013, 9000019])                                  # written by the old token sign-in
    s = a.login("deni@example.com", "owner-setup-code-1")                         # the old way to sign in still works once
    assert s.user["role"] == "admin" and st.get_watchlist("deni@example.com") == [9000013, 9000019]
    _raises(lambda: a.login("someone@example.com", "owner-setup-code-1"), "bad_credentials")   # only while the server has no accounts


def test_invites_are_single_use_and_bound_to_their_email():
    st, a = _setup()
    owner = a.signup("Deni", "deni@example.com", "a-long-pass-phrase", setup_code="owner-setup-code-1").user
    _raises(lambda: a.signup("Ana", "ana@example.com", "another-long-pass"), "bad_invite")
    inv = a.create_invite(owner, email="ana@example.com", role="analyst", base_url="https://me.example")
    assert inv["link"].startswith("https://me.example/#/invite/") and inv["emailed"] is True
    assert a.invite_info(inv["code"])["valid"] and a.invite_info("nope")["valid"] is False
    _raises(lambda: a.signup("Bob", "bob@example.com", "another-long-pass", invite=inv["code"]), "invite_email")
    s = a.signup("Ana Silva", "ana@example.com", "another-long-pass", invite=inv["code"])
    assert s.user["role"] == "analyst"
    _raises(lambda: a.signup("Ana 2", "ana@example.com", "another-long-pass", invite=inv["code"]), "bad_invite")
    open_inv = a.create_invite(owner, role="admin")
    s2 = a.signup("Bea", "bea@example.com", "yet-another-pass-9", invite=open_inv["code"])
    assert s2.user["role"] == "admin"
    assert len(a.team()["users"]) == 3 and a.team()["invites"] == []


def test_login_errors_do_not_reveal_accounts_and_are_rate_limited():
    st, a = _setup()
    a.signup("Deni", "deni@example.com", "a-long-pass-phrase", setup_code="owner-setup-code-1")
    e1 = _raises(lambda: a.login("deni@example.com", "wrong-pass-123"), "bad_credentials")
    e2 = _raises(lambda: a.login("nobody@example.com", "wrong-pass-123"), "bad_credentials")
    assert str(e1) == str(e2)
    for _ in range(9):                                   # 10 wrong passwords in 15 minutes…
        _raises(lambda: a.login("deni@example.com", "wrong-pass-123"), "bad_credentials")
    _raises(lambda: a.login("deni@example.com", "a-long-pass-phrase"), "rate_limited")


def test_forgot_and_reset_with_an_emailed_code():
    st, a = _setup()
    a.signup("Deni", "deni@example.com", "a-long-pass-phrase", setup_code="owner-setup-code-1")
    assert a.forgot("nobody@example.com", "https://x") == {"ok": True, "email": True} and a.mailer.sent == []
    a.forgot("deni@example.com", "https://x")
    to, subject, text = a.mailer.sent[-1]
    code = next(w for w in text.replace(".", " ").split() if w.isdigit() and len(w) == 6)
    _raises(lambda: a.reset("brand-new-pass-77", email="deni@example.com", code="000000" if code != "000000" else "111111"), "bad_code")
    s = a.reset("brand-new-pass-77", email="deni@example.com", code=code)
    assert s.user["email"] == "deni@example.com"
    _raises(lambda: a.login("deni@example.com", "a-long-pass-phrase"), "bad_credentials")
    assert a.login("deni@example.com", "brand-new-pass-77").token
    _raises(lambda: a.reset("another-new-pass-1", email="deni@example.com", code=code), "bad_reset")      # used once


def test_reset_link_made_by_an_admin_signs_out_everywhere():
    st, a = _setup(mail=False)
    owner = a.signup("Deni", "deni@example.com", "a-long-pass-phrase", setup_code="owner-setup-code-1").user
    inv = a.create_invite(owner, role="analyst")
    ana = a.signup("Ana", "ana@example.com", "another-long-pass", invite=inv["code"])
    assert a.forgot("ana@example.com", "https://x") == {"ok": True, "email": False}
    link = a.admin_reset_link(owner, ana.user["id"], "https://me.example")["link"]
    token = link.split("/reset/")[1]
    assert a.reset_info(token)["email"] == "ana@example.com"
    s = a.reset("fresh-password-2026", token=token)
    assert a.session_user(ana.token) is None and a.session_user(s.token)
    assert a.reset_info(token)["valid"] is False


def test_profile_changes_and_last_admin_guards():
    st, a = _setup()
    owner_s = a.signup("Deni", "deni@example.com", "a-long-pass-phrase", setup_code="owner-setup-code-1")
    owner = owner_s.user
    u = a.update_profile(owner, name="Deni Dudaev", prefs={"theme": "dark", "evil": 1})
    assert u["name"] == "Deni Dudaev" and u["prefs"] == {"theme": "dark"}
    _raises(lambda: a.update_profile(u, email="d@example.com", current_password="wrong"), "bad_password")
    u = a.update_profile(u, email="d@example.com", current_password="a-long-pass-phrase")
    assert u["email"] == "d@example.com"
    _raises(lambda: a.set_member(u, u["id"], role="analyst"), "last_admin")
    _raises(lambda: a.set_member(u, u["id"], status="disabled"), "last_admin")
    _raises(lambda: a.remove_member(u, u["id"]), "last_admin")
    inv = a.create_invite(u, role="admin")
    bea = a.signup("Bea", "bea@example.com", "yet-another-pass-9", invite=inv["code"]).user
    a.set_member(u, bea["id"], status="disabled")
    _raises(lambda: a.login("bea@example.com", "yet-another-pass-9"), "disabled")
    a.change_password(u, "a-long-pass-phrase", "changed-pass-phrase-3", owner_s.session_id)
    assert a.session_user(owner_s.token)                                         # this device stays signed in


def test_sessions_list_and_revoke():
    st, a = _setup()
    s1 = a.signup("Deni", "deni@example.com", "a-long-pass-phrase", setup_code="owner-setup-code-1", ua="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1")
    s2 = a.login("deni@example.com", "a-long-pass-phrase", ua="Mozilla/5.0 (Macintosh) Chrome/130")
    lst = a.sessions(s1.user, s1.session_id)
    assert [x["current"] for x in lst] == [True, False] and lst[0]["device"] == "iPhone · Safari" and lst[1]["device"] == "Mac · Chrome"
    assert a.revoke_other_sessions(s1.user, s1.session_id) == 1
    assert a.session_user(s2.token) is None and a.session_user(s1.token)
    st.sess[s1.session_id]["expires_at"] = 1
    assert a.session_user(s1.token) is None
