"""Login and sign-up: a full page (strict mode) and a popup (members-only features)."""

from __future__ import annotations

import html

import streamlit as st

from app.core.local_auth import AuthError
from app.ui.appearance import appearance_styles, icon

GENERIC_ERROR = "문제가 생겼어요. 잠시 후 다시 시도해 주세요."

try:  # st.dialog arrived after 1.34; the experimental name exists on the pinned 1.35
    _dialog = st.dialog
except AttributeError:
    _dialog = st.experimental_dialog


def _prepare_look():
    """The workspace sets theme/layout in its toolbar; a full login page needs the same look before that exists."""
    for key, allowed, default in (("layout", ("web", "app"), "web"), ("theme", ("light", "dark"), "light")):
        if key not in st.session_state:
            value = st.query_params.get(key, default)
            st.session_state[key] = value if value in allowed else default
    appearance_styles()


def _message(exc: Exception) -> str:
    return str(exc) if isinstance(exc, AuthError) else GENERIC_ERROR


def _forms(sign_in, sign_up, key_prefix: str):
    """Login / sign-up tabs shared by the page and the popup. Success stores ``app_auth`` and reruns."""
    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
    with login_tab:
        with st.form(f"{key_prefix}_login_form"):
            email = st.text_input("이메일", key=f"{key_prefix}_login_email", placeholder="name@example.com")
            password = st.text_input("비밀번호", type="password", key=f"{key_prefix}_login_password")
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
        if submitted:
            if not email.strip() or not password:
                st.warning("이메일과 비밀번호를 입력해 주세요.")
            else:
                try:
                    st.session_state["app_auth"] = sign_in(email.strip(), password)
                except Exception as exc:  # noqa: BLE001 - shown to the user as a friendly message
                    st.error(_message(exc))
                else:
                    st.rerun()
    with signup_tab:
        with st.form(f"{key_prefix}_signup_form"):
            new_email = st.text_input("이메일", key=f"{key_prefix}_signup_email", placeholder="name@example.com")
            new_password = st.text_input("비밀번호 (8자 이상)", type="password", key=f"{key_prefix}_signup_password")
            confirm = st.text_input("비밀번호 확인", type="password", key=f"{key_prefix}_signup_confirm")
            created = st.form_submit_button("회원가입", type="primary", use_container_width=True)
        if created:
            if not new_email.strip() or not new_password:
                st.warning("이메일과 비밀번호를 입력해 주세요.")
            elif new_password != confirm:
                st.error("비밀번호 확인이 일치하지 않아요.")
            else:
                try:
                    payload = sign_up(new_email.strip(), new_password)
                except Exception as exc:  # noqa: BLE001
                    st.error(_message(exc))
                else:
                    if payload:
                        st.session_state["app_auth"] = payload
                        st.rerun()
                    st.success("가입을 마쳤어요. 이메일로 보낸 확인 링크를 누른 뒤 로그인해 주세요.")


def render_login(sign_in, sign_up):
    """Full login page (REQUIRE_APP_LOGIN). ``sign_in``/``sign_up`` take (email, password) and return a session
    dict, or raise ``AuthError`` with a user-facing message; ``sign_up`` may return {} when e-mail confirmation is pending."""
    _prepare_look()
    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        st.markdown(
            '<div class="ios-login-brand"><span class="ios-app-icon">' + icon("Studio", 27) + '</span>'
            '<h1>Reels-analyzer</h1>'
            '<p>잘 된 릴스를 찾아 내 가게에 맞는 대본과 촬영 계획으로 바꿔 드려요.</p></div>',
            unsafe_allow_html=True,
        )
        _forms(sign_in, sign_up, "page")
        st.caption("내 프로젝트와 분석 결과는 계정별로 분리되어 저장돼요.")


@_dialog("로그인이 필요해요")
def show_login_dialog(sign_in, sign_up, reason: str = ""):
    """Popup asked when a guest reaches something that is stored per member."""
    if reason:
        st.markdown(f'<p class="ios-dialog-reason">{html.escape(reason)}</p>', unsafe_allow_html=True)
    _forms(sign_in, sign_up, "dialog")
    st.caption("로그인하지 않아도 릴스 찾기는 계속 사용할 수 있어요.")
