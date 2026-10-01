"""An iOS-inspired presentation layer; product state stays in Streamlit."""

from pathlib import Path
from urllib.parse import quote

import streamlit as st

NAV_LABELS = {"Home": "홈", "Radar": "공통점 추출", "Studio": "스튜디오", "Insights": "인사이트", "Playbook": "플레이북", "Settings": "설정"}
NAV_ITEMS = list(NAV_LABELS)[:5]
STAGE_NAMES = {"idea": "아이디어", "script": "대본", "shoot": "촬영", "review": "검토", "posted": "게시 완료"}
ICON_PATHS = {
    "Home": '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
    "Radar": '<circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5Z"/>',
    "Studio": '<rect x="3" y="7" width="18" height="14" rx="3"/><path d="M3 11h18M4 7l-1-3 17-2 1 5M8 3.5l2 3M14 2.8l2 3.2m-6 8 5 2.5-5 2.5Z"/>',
    "Insights": '<path d="M5 20v-6m7 6V9m7 11V4"/>',
    "Playbook": '<path d="M5 3h14v18l-7-4-7 4Z"/>',
    "Settings": '<path d="M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z"/><circle cx="12" cy="12" r="3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
}


def icon(name, size=24):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICON_PATHS[name]}</svg>'


def _choose(key, value):
    st.session_state[key] = value
    st.query_params[key] = value


def _navigate(page):
    st.session_state["active_menu"] = page
    if page in NAV_ITEMS:
        st.session_state["workspace_nav"] = page


def appearance_controls():
    for key, allowed, default in (("layout", ("web", "app"), "web"), ("theme", ("light", "dark"), "light")):
        if key not in st.session_state:
            value = st.query_params.get(key, default)
            st.session_state[key] = value if value in allowed else default
    appearance_styles()
    with st.container():
        st.markdown('<span class="ios-toolbar-marker"></span>', unsafe_allow_html=True)
        brand, web, app, theme, settings = st.columns([3.4, 1, 1, 1.4, .8], gap="small")
        brand.markdown('<div class="ios-wordmark">' + icon("Studio", 23) + '<span>Reel Lab</span></div>', unsafe_allow_html=True)
        for column, label, value in ((web, "웹", "web"), (app, "앱", "app")):
            column.button(label, key=f"layout_{value}", use_container_width=True,
                          type="primary" if st.session_state.layout == value else "secondary",
                          help=f"{label} 화면으로 보기", on_click=_choose, args=("layout", value))
        dark = st.session_state.theme == "dark"
        theme.button("라이트" if dark else "다크", key="theme_switch", use_container_width=True,
                     help="라이트모드로 전환" if dark else "다크모드로 전환",
                     on_click=_choose, args=("theme", "light" if dark else "dark"))
        settings.button("설정", key="open_settings", use_container_width=True, on_click=_navigate, args=("Settings",))
    return st.session_state.layout == "app"


def _nav_changed():
    st.session_state["active_menu"] = st.session_state["workspace_nav"]


def render_navigation(app_layout):
    target = st.session_state.pop("nav_target", None)
    if target:
        _navigate(target)
    current = st.session_state.setdefault("active_menu", "Home")
    if current in NAV_ITEMS:
        st.session_state["workspace_nav"] = current
    else:
        st.session_state["workspace_nav"] = None
    with (st.container() if app_layout else st.sidebar):
        st.markdown('<span class="ios-navigation-marker"></span>', unsafe_allow_html=True)
        if not app_layout:
            st.markdown('<div class="ios-sidebar-brand"><span class="ios-app-icon">' + icon("Studio", 27) + '</span><div>Reel Lab<small>나의 크리에이티브 스튜디오</small></div></div><div class="ios-nav-caption">작업 공간</div>', unsafe_allow_html=True)
        st.radio("주요 메뉴", NAV_ITEMS, key="workspace_nav", format_func=NAV_LABELS.get,
                 horizontal=app_layout, label_visibility="collapsed", on_change=_nav_changed)
        if not app_layout:
            st.markdown('<div class="ios-sidebar-foot">작은 아이디어가<br>다음 성장을 만듭니다.</div>', unsafe_allow_html=True)
    return st.session_state["active_menu"]


def appearance_styles():
    dark = st.session_state.get("theme") == "dark"
    palette = (
        "--bg:#000000;--surface:#1c1c1e;--surface-soft:#2c2c2e;--text:#f5f5f7;"
        "--muted:#a1a1a8;--border:#38383a;--accent:#0a84ff;--accent-strong:#64aaff;"
        "--glass:rgba(30,30,32,.91);--hero:#142135;--hero-end:#192c46;--blue-soft:#182c46;"
        "--green:#6dd58c;--ring-track:#333338;color-scheme:dark;"
        if dark else
        "--bg:#f5f5f7;--surface:#ffffff;--surface-soft:#f0f0f4;--text:#1d1d1f;"
        "--muted:#6e6e73;--border:#e5e5ea;--accent:#007aff;--accent-strong:#0065d4;"
        "--glass:rgba(250,250,252,.9);--hero:#eaf2ff;--hero-end:#f4f7ff;--blue-soft:#eaf2ff;"
        "--green:#248a3d;--ring-track:#ededf2;color-scheme:light;"
    )
    css = Path(__file__).with_name("ios.css").read_text(encoding="utf-8")
    nav_icons = ""
    for index, name in enumerate(NAV_ITEMS, 1):
        svg = icon(name).replace('stroke="currentColor"', 'stroke="black"')
        nav_icons += f'.ios-nav-scope [role="radiogroup"] label:nth-child({index})::before{{mask-image:url("data:image/svg+xml,{quote(svg)}");-webkit-mask-image:url("data:image/svg+xml,{quote(svg)}")}}'
    nav_icons = nav_icons.replace('.ios-nav-scope [role="radiogroup"]', '[role="radiogroup"][aria-label="주요 메뉴"]')
    layout = Path(__file__).with_name("ios_app.css").read_text(encoding="utf-8") if st.session_state.get("layout") == "app" else ""
    st.markdown("<style>:root{" + palette + "}" + css + nav_icons + layout + "</style>", unsafe_allow_html=True)
