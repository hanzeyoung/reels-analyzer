from app.ui.gate import MEMBER_ONLY_MENUS, is_guest, require_member


def _ctx(user_id="", enabled=True):
    opened = []
    return {"login_enabled": enabled, "auth_user_id": user_id, "open_login": opened.append}, opened


def test_guest_is_only_when_login_is_enabled_and_nobody_is_signed_in():
    assert is_guest(_ctx()[0]) is True
    assert is_guest(_ctx(user_id="u1")[0]) is False
    assert is_guest(_ctx(enabled=False)[0]) is False  # login switched off: nobody is asked to sign in


def test_require_member_opens_the_popup_for_guests_and_lets_members_through():
    guest_ctx, opened = _ctx()
    assert require_member(guest_ctx, "프로젝트는 내 계정에 저장돼요.") is False
    assert opened == ["프로젝트는 내 계정에 저장돼요."]
    member_ctx, member_opened = _ctx(user_id="u1")
    assert require_member(member_ctx, "x") is True and member_opened == []


def test_members_only_menus_are_the_ones_stored_per_member():
    assert set(MEMBER_ONLY_MENUS) == {"Studio", "Insights", "Playbook"}
    assert all(title and description for title, description in MEMBER_ONLY_MENUS.values())
