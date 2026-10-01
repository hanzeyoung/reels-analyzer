"""Soft login gate: guests can look around, but features stored per member ask them to sign in."""

from __future__ import annotations

import html

import streamlit as st

from app.ui.appearance import icon

MEMBER_ONLY_MENUS = {
    "Studio": ("스튜디오는 로그인이 필요해요", "프로젝트와 대본, 촬영 계획이 내 계정에 저장돼요. 로그인하면 언제든 이어서 작업할 수 있어요."),
    "Insights": ("인사이트는 로그인이 필요해요", "내 Instagram 성과를 계정에 연결해 저장하고 비교해요. 로그인하면 이어서 볼 수 있어요."),
    "Playbook": ("플레이북은 로그인이 필요해요", "성과가 쌓인 패턴을 내 계정에 모아 둬요. 로그인하면 다음 프로젝트에 적용할 수 있어요."),
}


def is_guest(ctx) -> bool:
    return bool(ctx.get("login_enabled")) and not ctx.get("auth_user_id")


def ask_login(ctx, reason: str) -> None:
    """Open the sign-in popup on this run."""
    ctx["open_login"](reason)


def require_member(ctx, reason: str) -> bool:
    """True when the member may continue; for a guest the popup opens and False is returned."""
    if not is_guest(ctx):
        return True
    ask_login(ctx, reason)
    return False


def member_gate_page(ctx, menu: str) -> bool:
    """Draw the gate card for a members-only menu. Returns True when the page was replaced (guest)."""
    if menu not in MEMBER_ONLY_MENUS or not is_guest(ctx):
        return False
    title, description = MEMBER_ONLY_MENUS[menu]
    st.markdown(
        f'<div class="ios-empty"><div class="ios-empty-icon">{icon("Home" if menu == "Home" else menu)}</div>'
        f'<div><h3>{html.escape(title)}</h3><p>{html.escape(description)}</p></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("로그인 / 회원가입", key=f"gate_login_{menu}", type="primary", use_container_width=True):
        ask_login(ctx, description)
    # 메뉴에 들어올 때 한 번만 자동으로 띄운다. 닫은 뒤 같은 화면에서 다시 그려져도 반복해서 뜨지 않는다.
    if st.session_state.get("gate_popup_menu") != menu:
        st.session_state["gate_popup_menu"] = menu
        ask_login(ctx, description)
    return True
