"""Settings screen: account, what the app can do right now, Instagram connection, own data.

Everything here is written for end users. Environment variable names and server hints are shown
only in operator mode (ADMIN_MODE), never to regular members.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from app.core.oauth_state import consume_state, issue_state
from app.ui.gate import ask_login, is_guest
from app.ui.workspace import _header, _safe

OAUTH_REISSUE_SECONDS = 12 * 60


def _service_rows(ctx):
    """name, what it does for the member, ready, operator hint (env var NAMES only, never values)."""
    meta_hint = "아래 'Instagram 계정'에서 연결하세요." if ctx.get("meta_oauth_ready") else "META_APP_ID, META_APP_SECRET, META_REDIRECT_URI"
    return [
        ("인기 릴스 찾기", "내 업종의 인기 릴스를 찾고, 링크로 직접 추가할 수 있어요.", bool(ctx.get("can_collect")), "APIFY_TOKEN"),
        ("AI 릴스 분석", "릴스의 구도·자막·컷을 AI가 살펴보고 공통 패턴을 알려줘요.", bool(ctx.get("can_analyze_visual")), "GEMINI_API_KEY"),
        ("촬영 구도 이미지", "촬영 구도를 보여주는 참고 이미지를 만들어 줘요. (선택)", bool(ctx.get("can_generate_image")), "BFL_API_KEY"),
        ("내레이션 음성", "대본을 읽어 주는 음성 샘플을 만들어 줘요. (선택)", bool(ctx.get("can_generate_voice")), "ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID"),
        ("Instagram 성과 분석", "내 계정의 실제 조회수·저장률로 어떤 릴스가 잘 됐는지 알려줘요.", bool(ctx.get("meta_token_present")), meta_hint),
    ]


def _account_card(ctx):
    email = str(ctx.get("auth_email") or "")
    initial = _safe((email[:1] or "?").upper())
    st.markdown(
        f'<div class="ios-account"><span class="ios-avatar">{initial}</span>'
        f'<div><b>{_safe(email or "내 계정")}</b><small>이 계정의 프로젝트와 분석 결과는 다른 회원과 분리되어 저장돼요.</small></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("로그아웃", key="settings_logout"):
        ctx["logout"]()


def _services_panel(ctx):
    admin = bool(ctx.get("is_admin"))
    rows = _service_rows(ctx)
    items = "".join(
        f'<div class="ios-service {"is-ready" if ok else ""}"><div class="ios-service-main"><b>{_safe(name)}</b><span>{_safe(role)}</span>'
        + (f'<small class="ios-service-hint">운영자용 · 필요: <code>{_safe(hint)}</code></small>' if admin and not ok else "")
        + f'</div><em class="ios-pill">{"사용 가능" if ok else "준비 중"}</em></div>'
        for name, role, ok, hint in rows
    )
    st.markdown(f'<div class="ios-services">{items}</div>', unsafe_allow_html=True)
    if admin and any(not row[2] for row in rows):
        st.caption("운영자 안내: 환경변수는 서버의 .env 파일에 넣은 뒤 앱을 다시 시작하면 반영돼요. 키 값은 화면에 표시되지 않아요.")


def _guest_card(ctx):
    st.markdown(
        '<div class="ios-account"><span class="ios-avatar">?</span>'
        '<div><b>로그인하지 않았어요</b><small>로그인하면 프로젝트와 분석 결과가 내 계정에 저장되고, 다시 와서 이어서 작업할 수 있어요.</small></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("로그인 / 회원가입", key="settings_login", type="primary", use_container_width=True):
        ask_login(ctx, "내 프로젝트와 분석 결과를 계정에 저장해요.")


def _instagram_section(ctx):
    st.subheader("Instagram 계정")
    if is_guest(ctx):
        st.info("Instagram 연결은 내 계정에 저장되는 정보라서 로그인한 뒤에 할 수 있어요.")
        if st.button("로그인하고 연결하기", key="settings_ig_login", use_container_width=True):
            ask_login(ctx, "Instagram 연결 정보는 내 계정에 저장돼요.")
        return
    if not ctx.get("meta_oauth_ready"):
        if ctx.get("is_admin"):
            st.info("운영자 안내: META_APP_ID, META_APP_SECRET, META_REDIRECT_URI를 .env에 넣으면 Instagram 연결을 시작할 수 있습니다.")
        else:
            st.info("Instagram 연결은 곧 열릴 예정이에요. 그때까지는 릴스 찾기와 대본·촬영 계획 만들기를 먼저 사용해 보세요.")
        return
    callback_code = st.query_params.get("code", "")
    callback_state = st.query_params.get("state", "")
    state_path, owner = ctx["oauth_state_path"], ctx["oauth_owner"]
    if callback_code and not st.session_state.get("meta_access_token"):
        # Instagram에서 돌아오면 새 세션이라 state는 서버에 일회용으로 저장해 둔다. 비어 있거나 만료·재사용·타인 것이면 거부.
        if not consume_state(state_path, callback_state, owner):
            st.error("Instagram 연결 상태를 확인할 수 없습니다. 아래 'Instagram 연결하기'로 다시 진행해 주세요.")
        else:
            try:
                payload = ctx["exchange_oauth"](callback_code)
                token = payload.get("access_token", "")
                if not token:
                    raise RuntimeError("Meta에서 access token을 받지 못했습니다.")
                st.session_state["meta_access_token"] = token
                ctx["save_meta_token"](token, payload)
                st.query_params.clear()
                st.success("Instagram 연결이 완료됐습니다.")
            except Exception as exc:
                st.error(f"Instagram 연결 실패: {exc}")
    if st.session_state.get("meta_access_token") or ctx.get("meta_token_present"):
        st.success("Instagram이 연결돼 있어요. 인사이트 동기화를 실행할 수 있어요.")
        return
    # 링크는 화면을 열 때 만들고, 서버 저장 state가 만료되기 전에 새로 발급한다.
    if not st.session_state.get("meta_oauth_url") or time.time() - st.session_state.get("meta_oauth_issued_at", 0) > OAUTH_REISSUE_SECONDS:
        try:
            url, _state = ctx["build_oauth_url"](state=issue_state(state_path, owner))
            st.session_state["meta_oauth_url"] = url
            st.session_state["meta_oauth_issued_at"] = time.time()
        except Exception as exc:
            st.session_state.pop("meta_oauth_url", None)
            st.error(f"연결 링크를 만들지 못했습니다: {exc}")
    oauth_url = st.session_state.get("meta_oauth_url")
    if oauth_url:
        st.link_button("Instagram 연결하기", oauth_url, type="primary", use_container_width=True)
        st.caption("열린 Instagram 화면에서 로그인하고 승인해 주세요. 링크는 15분 동안 유효해요.")


def _data_section(ctx):
    """Export and delete the signed-in member's own data."""
    st.subheader("내 데이터")
    st.caption("내가 만든 프로젝트와 분석 결과를 내려받거나 삭제할 수 있어요.")
    if st.button("내 데이터 내보내기 준비", key="privacy_export_prepare", use_container_width=True):
        try:
            st.session_state["privacy_export_path"] = str(ctx["export_user_data"](ctx["auth_user_id"]))
        except FileNotFoundError:
            st.info("아직 내보낼 데이터가 없어요. 프로젝트를 만든 뒤 다시 시도해 주세요.")
    export_path = Path(st.session_state.get("privacy_export_path", ""))
    if export_path.is_file():
        st.download_button("ZIP 다운로드", data=export_path.read_bytes(), file_name=export_path.name, mime="application/zip", use_container_width=True)
    with st.expander("계정 삭제"):
        st.warning("계정과 모든 프로젝트·분석 결과가 삭제되고 되돌릴 수 없어요.")
        if not ctx.get("can_delete_account"):
            st.caption("지금은 계정 삭제를 직접 처리할 수 없어요. 운영자에게 요청해 주세요.")
            return
        typed = st.text_input("삭제하려면 '삭제'를 입력하세요", key="delete_account_confirm")
        if st.button("계정 영구 삭제", key="delete_account_apply", disabled=typed.strip() != "삭제", use_container_width=True):
            try:
                ctx["delete_my_account"]()
            except Exception as exc:
                st.error(f"계정을 삭제하지 못했어요: {exc}")


def render_settings(ctx):
    _header("Settings", "내 계정과 사용할 수 있는 기능을 확인하세요.")
    if ctx.get("auth_user_id"):
        st.subheader("내 계정")
        _account_card(ctx)
    elif is_guest(ctx):
        st.subheader("내 계정")
        _guest_card(ctx)
    st.subheader("사용할 수 있는 기능")
    _services_panel(ctx)
    _instagram_section(ctx)
    if ctx.get("auth_user_id"):
        _data_section(ctx)
    if ctx.get("is_admin"):
        st.subheader("시스템 현황")
        jobs = ctx["list_jobs"]()
        if jobs:
            st.dataframe(pd.DataFrame(jobs), use_container_width=True, hide_index=True)
