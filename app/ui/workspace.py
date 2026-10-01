"""Project-first Streamlit workspace; persistent work always goes through user-scoped files."""

from __future__ import annotations

import calendar
import html
import json
import re
from urllib.parse import quote
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from app.ui.appearance import NAV_LABELS, STAGE_NAMES, icon

from app.core.audio_rights import recommend_audio_options
from app.core.content_projects import PROJECT_STAGES, create_project, list_projects, pipeline_counts, update_project
from app.core.performance_insights import build_account_baseline, compare_snapshot_windows, load_performance_history, normalize_insights
from app.core.signal_studies import add_signal, build_signal_synthesis, build_visual_synthesis, load_study, replace_signals, save_visual_analysis
from app.api.guide_media import download_flux_guide, generate_elevenlabs_voiceover, generate_flux_guide


def _safe(value):
    return html.escape(str(value or ""))


def _go(page):
    st.session_state["nav_target"] = page
    st.rerun()


def _project(projects, project_id):
    return next((item for item in projects if item.get("id") == project_id), None)


def _load_settings(path):
    try:
        values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return values if isinstance(values, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_settings(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _header(title, subtitle):
    label = "오늘의 스튜디오" if title == "Home" else NAV_LABELS.get(title, title)
    kicker = "" if title == "Home" else '<div class="rl-kicker">Reel Lab · 나의 작업 공간</div>'
    st.markdown(
        f'<header class="rl-head">{kicker}<h1>{_safe(label)}</h1><p>{_safe(subtitle)}</p></header>',
        unsafe_allow_html=True,
    )


def _metric(label, value, detail=""):
    st.markdown(f'<div class="rl-metric"><span>{_safe(label)}</span><b>{_safe(value)}</b><small>{_safe(detail)}</small></div>', unsafe_allow_html=True)


def _section(title, detail=""):
    detail_html = f'<span>{_safe(detail)}</span>' if detail else ""
    st.markdown(f'<div class="ios-section-title"><h2>{_safe(title)}</h2>{detail_html}</div>', unsafe_allow_html=True)


def _empty(title, description, symbol="Studio"):
    st.markdown(f'<div class="ios-empty"><div class="ios-empty-icon">{icon(symbol)}</div><div><h3>{_safe(title)}</h3><p>{_safe(description)}</p></div></div>', unsafe_allow_html=True)


def _new_project_form(ctx):
    with st.form("new_project", clear_on_submit=True):
        st.markdown("### 어떤 이야기를 담아볼까요?")
        title = st.text_input("프로젝트 이름", placeholder="예: 비 오는 날, 따뜻한 크림라떼")
        idea = st.text_area("아이디어", placeholder="보여주고 싶은 장면이나 매장 이야기를 자유롭게 적어주세요.", height=100)
        create = st.form_submit_button("프로젝트 만들기", type="primary", use_container_width=True)
    if create:
        if not title.strip() and not idea.strip():
            st.warning("프로젝트 이름이나 아이디어를 먼저 적어주세요.")
            return
        item = create_project(title or idea, ctx["projects_path"], business_type=ctx["business_type"], concept=idea)
        st.session_state["active_project_id"] = item["id"]
        st.session_state["show_new_project"] = False
        _go("Studio")


def _calendar_date(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _goal_calendar(projects, goal, preferences, ctx):
    if st.button("← 홈으로", key="close_goal_calendar"):
        st.session_state["show_goal_calendar"] = False
        st.rerun()
    today = datetime.now().date()
    month_value = st.session_state.get("goal_calendar_month", today.strftime("%Y-%m"))
    try:
        month_date = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
    except ValueError:
        month_date = today.replace(day=1)
    previous_month = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    left, title, right = st.columns([1, 4, 1])
    if left.button("‹", key="calendar_previous", use_container_width=True):
        st.session_state["goal_calendar_month"] = previous_month.strftime("%Y-%m")
        st.rerun()
    title.markdown(f'<div class="calendar-heading">{month_date.year}년 {month_date.month}월</div>', unsafe_allow_html=True)
    if right.button("›", key="calendar_next", use_container_width=True):
        st.session_state["goal_calendar_month"] = next_month.strftime("%Y-%m")
        st.rerun()

    reel_days = set()
    for project in projects:
        for field in ("created_at", "published_at"):
            project_date = _calendar_date(project.get(field))
            if project_date and project_date.year == month_date.year and project_date.month == month_date.month:
                reel_days.add(project_date.day)
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(month_date.year, month_date.month)
    headers = "".join(f"<th>{day}</th>" for day in ["월", "화", "수", "목", "금", "토", "일"])
    rows = []
    for week in weeks:
        cells = []
        for day in week:
            if not day:
                cells.append("<td></td>")
            else:
                classes = " has-reel" if day in reel_days else ""
                today_class = " is-today" if month_date.year == today.year and month_date.month == today.month and day == today.day else ""
                cells.append(f'<td class="{classes}{today_class}"><span>{day}</span></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<div class="goal-calendar"><table><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True)

    st.markdown("### 이번 주 목표 바꾸기")
    new_goal = st.number_input("이번 주 게시 목표", 1, 20, goal, label_visibility="collapsed")
    if new_goal != goal:
        _save_settings(ctx["workspace_settings_path"], {**preferences, "weekly_publish_goal": int(new_goal)})
        st.rerun()


def home(ctx):
    projects = list_projects(ctx["projects_path"])
    counts = pipeline_counts(projects)
    active = next((item for item in projects if item.get("stage") != "posted"), None)
    preferences = _load_settings(ctx["workspace_settings_path"])
    goal = min(20, max(1, int(preferences.get("weekly_publish_goal", 3))))
    week_start = datetime.now() - timedelta(days=datetime.now().weekday())
    done = sum(
        1 for item in projects
        if item.get("stage") == "posted" and str(item.get("published_at", "")) >= week_start.isoformat()[:10]
    )
    _header("Home", "아이디어를 담고, 나만의 릴스를 완성해 보세요.")
    if st.session_state.get("show_goal_calendar"):
        _goal_calendar(projects, goal, preferences, ctx)
        return

    focus, progress = st.columns([1.65, 1], gap="medium")
    with focus:
        with st.container(border=True):
            title = active.get("title") if active else "작은 아이디어,\n새로운 가능성."
            description = "새로운 아이디어를 프로젝트로 만들고 대본과 촬영 계획을 완성해 보세요."
            st.markdown(
                f'<span class="ios-focus-marker"></span><div class="ios-focus">'
                f'<div class="ios-eyebrow">{icon("Studio", 18)}프로젝트 만들기</div>'
                f'<h2>{_safe(title).replace(chr(10), "<br>")}</h2>'
                f'<p>{_safe(description)}</p><div class="ios-focus-art">{icon("Studio", 64)}</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown('<span class="ios-hero-create-marker"></span>', unsafe_allow_html=True)
            if st.button("+", key="hero_create_project", help="새 프로젝트 만들기"):
                st.session_state["show_new_project"] = True
                st.rerun()
    with progress:
        percent = min(100, done / goal * 100)
        with st.container(border=True):
            st.markdown('<span class="ios-goal-card-marker"></span>', unsafe_allow_html=True)
            goal_title, goal_arrow = st.columns([5, 1])
            goal_title.markdown('<div class="ios-goal-title">이번 주 목표</div>', unsafe_allow_html=True)
            if goal_arrow.button("→", key="open_goal_calendar", help="캘린더 보기"):
                st.session_state["show_goal_calendar"] = True
                st.rerun()
            st.markdown(
                f'<style>.ios-ring{{background:conic-gradient(var(--accent) {percent:.1f}%,var(--ring-track) 0)}}</style>'
                f'<div class="ios-goal-ring-wrap"><div class="ios-ring"><div class="ios-ring-inner">'
                f'<strong>{done}<span> / {goal}</span></strong><small>게시한 릴스</small>'
                f'</div></div></div>',
                unsafe_allow_html=True,
            )
    if st.session_state.get("show_new_project"):
        _new_project_form(ctx)

    _section("제작 현황")
    with st.container():
        st.markdown('<span class="ios-pipeline-marker"></span>', unsafe_allow_html=True)
        stage_columns = st.columns(5, gap="small")
        for column, stage in zip(stage_columns, PROJECT_STAGES):
            with column:
                if st.button(f"{STAGE_NAMES[stage]}\n{counts[stage]}", key=f"stage_{stage}", use_container_width=True):
                    target = next((item for item in projects if item.get("stage") == stage), None)
                    if target:
                        st.session_state["active_project_id"] = target["id"]
                        _go("Studio")
                    else:
                        st.session_state["home_notice"] = f"{STAGE_NAMES[stage]} 단계의 프로젝트가 없습니다."
                        st.rerun()
    notice = st.session_state.pop("home_notice", "")
    if notice:
        st.info(notice)

    _section("최근 프로젝트")
    visible_count = len(projects) if st.session_state.get("show_all_projects") else 3
    if not projects:
        _empty("첫 이야기를 기다리고 있어요", "새 프로젝트를 만들면 이곳에 모아드릴게요.")
    for item in projects[:visible_count]:
        with st.container(border=True):
            updated = str(item.get("updated_at", ""))[:10].replace("-", ".")
            st.markdown('<span class="ios-project-click-marker"></span>', unsafe_allow_html=True)
            if st.button(f"{item.get('title') or '제목 없는 프로젝트'}\n{updated}", key=f"recent_{item['id']}", use_container_width=True):
                st.session_state["active_project_id"] = item["id"]
                _go("Studio")
    if len(projects) > 3 and not st.session_state.get("show_all_projects"):
        if st.button("전체보기", key="show_all_projects_button", use_container_width=True):
            st.session_state["show_all_projects"] = True
            st.rerun()
    elif len(projects) > 3 and st.session_state.get("show_all_projects"):
        if st.button("접기", key="hide_all_projects_button", use_container_width=True):
            st.session_state["show_all_projects"] = False
            st.rerun()


def _radar_reels(snapshot, changes):
    accounts = {item.get("username"): item for item in changes}
    signals = []
    for item in snapshot.get("media", []):
        account = accounts.get(item.get("username"), {})
        signals.append({
            "media_id": item.get("media_id", ""), "username": item.get("username", ""),
            "url": item.get("url", ""), "caption": item.get("caption", ""), "track": item.get("track", ""),
            "thumbnail_url": item.get("thumbnail_url", ""), "video_url": item.get("video_url", ""),
            "views": int(item.get("views") or 0), "published_at": item.get("published_at", ""),
            "view_delta": int(account.get("same_media_view_delta") or account.get("view_delta") or 0),
            "comparison_confidence": account.get("comparison_confidence", "low"),
            "is_new_account": bool(account.get("is_new")),
            "discovered_at": snapshot.get("captured_at", ""),
        })
    return sorted(signals, key=lambda item: (item["view_delta"], item["views"]), reverse=True)


def _study_identity(item):
    return str(item.get("media_id") or item.get("url") or "")


def _build_full_variants(project: dict, synthesis: dict | None = None) -> dict[str, str]:
    """Create shootable drafts without presenting a generic hook as a full script."""
    source = project.get("source") or {}
    synthesis = synthesis or source.get("synthesis") or {}
    plan = synthesis.get("storyboard_plan") or []
    if plan:
        base_lines = [
            f"{row.get('time', '')} | {row.get('shot', '')} | 자막: {row.get('subtitle', '')} | {row.get('camera', '')}"
            for row in plan
        ]
        evidence = " / ".join(dict.fromkeys(str(row.get("evidence_pattern") or "") for row in plan if row.get("evidence_pattern")))
        base = "\n".join(base_lines)
        note = f"\n공통 패턴 근거: {evidence}" if evidence else ""
        return {
            "sales": base + note + "\nCTA 방향: 저장 후 방문할 이유를 한 문장으로 확정하세요.",
            "story": base + note + "\nCTA 방향: 이 장면이 매장의 실제 이야기와 어떻게 이어지는지 물어보세요.",
            "curiosity": base + note + "\nCTA 방향: 첫 장면의 답을 방문해서 확인하도록 유도하세요.",
        }
    focus = ", ".join(synthesis.get("repeated_terms") or synthesis.get("repeated_hashtags") or [])
    query = str(source.get("query") or "").strip()
    title = re.sub(r"\s*pattern study\s*$", "", str(project.get("title") or ""), flags=re.IGNORECASE).strip()
    subject = (query or title or focus or "대표 메뉴").strip()
    hook = (project.get("hook") or f"{subject}의 완성 장면을 먼저 보여주세요.").strip()
    hook = re.sub(r"^\d+(?:\.\d+)?\s*[-~–]\s*\d+(?:\.\d+)?초\s*[:|·]?\s*", "", hook)
    hook = f"0-2초 | {hook}"
    camera = ((source.get("visual_synthesis") or {}).get("top_camera") or "클로즈업").strip()
    proof = f"5-10초 | {camera}으로 만드는 손과 핵심 재료를 2~3개 컷으로 보여주세요."
    pattern_note = f" Radar 근거: {focus}." if focus else ""
    return {
        "sales": "\n".join([
            hook,
            f"2-5초 | 손님이 {subject}에서 얻는 가장 큰 이점을 한 문장으로 말해주세요.",
            proof,
            f"10-14초 | 완성된 {subject}을(를) 한입·한 모금·사용 장면으로 증명하세요.",
            "14-18초 | CTA: 오늘 매장에서 직접 확인해보세요.",
        ]) + pattern_note,
        "story": "\n".join([
            hook,
            f"2-5초 | 오늘 {subject}을(를) 준비하게 된 매장 이야기부터 짧게 시작하세요.",
            proof,
            "10-14초 | 손님에게 내놓는 마지막 손길과 매장 분위기를 보여주세요.",
            "14-18초 | CTA: 다음에 어떤 장면을 보고 싶은지 댓글로 남겨주세요.",
        ]) + pattern_note,
        "curiosity": "\n".join([
            hook,
            f"2-5초 | 질문: 왜 손님들이 {subject} 앞에서 멈출까요?",
            f"5-10초 | {camera}으로 답이 되는 한 가지 디테일을 숨기듯 보여주세요.",
            f"10-14초 | 답: {subject}의 핵심 포인트를 완성 장면과 함께 공개하세요.",
            "14-18초 | CTA: 다음 방문에서 이 장면을 찾아보세요.",
        ]) + pattern_note,
    }


def _create_study_project(items, query, synthesis, visual, visual_analyses, ctx):
    """Turn the current Radar study into the active Studio project."""
    patterns = synthesis.get("common_patterns") or []
    focus = (
        " · ".join(item["label"] for item in patterns[:2])
        or ", ".join(synthesis["repeated_terms"][:3])
        or query
        or "대표 장면"
    )
    project = create_project(
        f"{query} pattern study",
        ctx["projects_path"],
        business_type=ctx["business_type"],
        concept=f"{query}에서 반복된 장면: {focus}",
        source={
            "type": "signal_study",
            "query": query,
            "signals": items,
            "synthesis": synthesis,
            "visual_synthesis": visual,
            "visual_analyses": visual_analyses,
        },
    )
    variants = _build_full_variants({**project, "hook": synthesis["recommended_hook"]}, synthesis)
    project = update_project(
        project["id"],
        {
            "hook": synthesis["recommended_hook"],
            "script": variants["sales"],
            "script_variants": variants,
            "shot_list": synthesis["recommended_structure"],
            "stage": "script",
        },
        ctx["projects_path"],
    )
    st.session_state["active_project_id"] = project["id"]
    st.session_state["studio_notice"] = f"릴스 {len(visual_analyses)}개의 공통 시각 패턴을 반영한 프로젝트를 만들었습니다."
    _go("Studio")


def _render_study_basket(study, query, ctx):
    items = study.get("items") or []
    analyzable_items = [item for item in items if item.get("thumbnail_url") or item.get("video_url")]
    slot = st.empty()
    with slot.container(border=True):
        st.markdown(f"### 전체 분석 대상 · {len(items)}개")
        st.caption("검색 결과와 직접 추가한 링크를 모두 공통 시각 패턴 분석에 사용합니다.")
        ready = len(items) >= 2 and len(analyzable_items) >= 2
        analyze = st.button(
            "전체 릴스 공통 시각 패턴 분석",
            type="primary",
            use_container_width=True,
            disabled=not ctx["can_analyze_visual"] or not ready,
        )
        if len(items) < 2:
            st.info("공통 패턴을 만들려면 분석 가능한 릴스가 두 개 이상 필요합니다.")
        elif len(analyzable_items) < 2:
            st.warning("영상 또는 썸네일을 가져온 릴스가 두 개 이상 필요합니다.")
    if not analyze:
        return

    slot.empty()
    synthesis = build_signal_synthesis(items, query=query)
    completed, failures = {}, []
    with st.spinner(f"릴스 {len(analyzable_items)}개의 구도·자막·컷 신호를 분석하는 중입니다..."):
        for selected in analyzable_items:
            identity = _study_identity(selected)
            try:
                if selected.get("thumbnail_url"):
                    completed[identity] = ctx["analyze_thumbnail"](
                        selected["thumbnail_url"], caption=selected.get("caption", "")
                    )
                elif ctx.get("analyze_sequence_url"):
                    completed[identity] = ctx["analyze_sequence_url"](
                        selected["video_url"], caption=selected.get("caption", "")
                    )
            except Exception as exc:
                failures.append(f"@{selected.get('username', 'unknown')}: {exc}")
    save_visual_analysis(completed, ctx["study_path"])
    if not completed:
        st.error("릴스 시각 분석을 완료하지 못했습니다. 잠시 후 다시 시도해주세요.")
        if failures:
            st.caption(" / ".join(failures[:2]))
        return
    visual = build_visual_synthesis(completed, items)
    _create_study_project(items, query, synthesis, visual, completed, ctx)


def radar(ctx):
    _header("Radar", "여러 공개 릴스에서 반복되는 구조를 모아 하나의 제작 방향으로 만듭니다")
    query = st.text_input("어떤 릴스를 찾고 있나요?", value=st.session_state.get("radar_query", ctx["business_type"]), placeholder="예: 성수동 카페")
    st.session_state["radar_query"] = query
    notice = st.session_state.pop("radar_notice", "")
    if notice:
        st.success(notice)
    if st.button("릴스 검색하기", type="primary", use_container_width=True, disabled=not ctx["can_collect"] or not query.strip()):
        try:
            clean_query = query.strip()
            with st.spinner(f"‘{clean_query}’ 관련 공개 릴스를 찾고 있습니다..."):
                reels = ctx["collect"](clean_query, max_items=45, top_n=12)
                if not reels:
                    raise RuntimeError("관련 릴스를 찾지 못했습니다. 지역명과 업종을 함께 입력해보세요. 예: 광주 맛집")
                before = ctx["load_previous"](clean_query)
                snapshot = ctx["build_snapshot"](reels, clean_query)
                changes = ctx["compare_snapshots"](before, snapshot)
                st.session_state["market_changes"] = changes
                st.session_state["market_changes_query"] = clean_query
                ctx["save_snapshot"](snapshot)
                st.session_state["market_snapshot"] = snapshot
                signals = _radar_reels(snapshot, changes)
                replace_signals(signals, ctx["study_path"], query=clean_query)
                st.session_state["radar_notice"] = f"관련 릴스 {len(signals)}개 전체를 분석 대상으로 추가했습니다."
            st.rerun()
        except Exception as exc:
            st.error(f"릴스 검색에 실패했습니다: {exc}")
    if not ctx["can_collect"]:
        st.caption("설정에서 수집 서비스를 연결하면 검색을 시작할 수 있어요.")
        if st.button("서비스 연결하기", key="radar_connect"):
            _go("Settings")
    snapshot = st.session_state.get("market_snapshot")
    if snapshot and snapshot.get("query") != query.strip():
        snapshot = ctx["load_previous"](query.strip()) if query.strip() else None
    if not snapshot:
        _empty("어떤 릴스가 눈에 들어오나요?", "지역이나 업종을 검색해 새로운 아이디어를 발견해 보세요.", "Radar")
        return
    changes = (
        st.session_state.get("market_changes")
        if st.session_state.get("market_changes_query") == snapshot.get("query")
        else snapshot.get("accounts", [])
    ) or snapshot.get("accounts", [])
    signals = _radar_reels(snapshot, changes)
    if not signals:
        st.warning("저장된 검색 결과가 없습니다. 지역명과 업종을 함께 입력해 다시 검색해주세요.")
        return
    study = load_study(ctx["study_path"])
    if study.get("query") != snapshot.get("query"):
        study = replace_signals(signals, ctx["study_path"], query=snapshot.get("query", query))

    _render_study_basket(study, query, ctx)

    with st.form("radar_add_reel_url"):
        st.markdown("### 추가로 분석할 릴스")
        reel_url = st.text_input(
            "Instagram 릴스 링크",
            placeholder="https://www.instagram.com/reel/ABC123/",
        )
        add_url = st.form_submit_button(
            "링크 추가",
            use_container_width=True,
            disabled=not ctx["can_collect"],
        )
    if add_url:
        if not reel_url.strip():
            st.warning("추가할 Instagram 릴스 링크를 입력해주세요.")
        else:
            try:
                with st.spinner("링크에서 영상 정보를 가져오는 중입니다..."):
                    signal = ctx["collect_url"](reel_url.strip())
                    updated = add_signal(signal, ctx["study_path"])
                st.session_state["radar_notice"] = f"추가 링크를 포함해 릴스 {len(updated.get('items') or [])}개를 분석합니다."
                st.rerun()
            except Exception as exc:
                st.error(f"릴스 링크를 추가하지 못했습니다: {exc}")


def _stats(text, project):
    seconds = max(8, round(len(text.replace(" ", "")) / 6))
    cuts = max(3, min(12, round(seconds / 3)))
    difficulty = "Easy" if cuts <= 4 else "Moderate" if cuts <= 7 else "Detailed"
    fit = "High" if project.get("business_type") and project.get("concept") else "Review"
    return f"{seconds}s · {cuts} cuts · {difficulty} · store fit {fit}"


def _clean_shot_instruction(value: str) -> str:
    text = re.sub(r"^\s*\d+(?:\.\d+)?\s*[-~–]\s*\d+(?:\.\d+)?초\s*[:|·]?\s*", "", str(value or ""))
    text = re.split(r"\s*[·|]\s*자막\s*[:‘]", text, maxsplit=1)[0]
    return re.sub(r"\s+", " ", text).strip(" ·|-")


def _script_segments(text: str) -> list[dict]:
    segments = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("공통 패턴 근거:", "CTA 방향:")):
            continue
        match = re.match(
            r"^((?:\d+(?:\.\d+)?\s*[-~–]\s*\d+(?:\.\d+)?초)|(?:마지막\s*\d*(?:\.\d+)?초))\s*[|·:]?\s*(.*)$",
            line,
        )
        time_label = match.group(1) if match else f"장면 {len(segments) + 1}"
        content = match.group(2) if match else line
        parts = [part.strip() for part in content.split("|") if part.strip()]
        description = parts[0] if parts else content
        subtitle = ""
        shot = ""
        for part in parts[1:]:
            if part.startswith("자막:"):
                subtitle = part.split(":", 1)[1].strip()
            elif not shot:
                shot = part
        if not subtitle and "CTA:" in description:
            subtitle = description.split("CTA:", 1)[1].strip()
            description = "마지막 행동 유도"
        segments.append({
            "time": time_label.replace("-", "–").replace("~", "–"),
            "description": description,
            "subtitle": subtitle or "자막 없음",
            "shot": shot or _clean_shot_instruction(description),
        })
        if len(segments) == 5:
            break
    return segments


def _segment_cards(segments: list[dict], empty_message: str) -> str:
    if not segments:
        return f'<div class="timeline-empty">{_safe(empty_message)}</div>'
    cards = "".join(
        f'<article class="timeline-card"><span>{_safe(segment["time"])}</span>'
        f'<div class="script-line"><b>내용</b><p>{_safe(segment["description"])}</p></div>'
        f'<div class="script-line"><b>자막</b><p>{_safe(segment["subtitle"])}</p></div>'
        f'<div class="script-line"><b>샷</b><p>{_safe(segment["shot"])}</p></div></article>'
        for segment in segments
    )
    return f'<div class="timeline-card-grid">{cards}</div>'


def _shot_cards(shots: list[str], empty_message: str) -> str:
    if not shots:
        return f'<div class="timeline-empty">{_safe(empty_message)}</div>'
    ranges = ["0–2초", "2–5초", "5–9초", "9–13초", "13–15초"]
    cards = "".join(
        f'<article class="timeline-card shot-only-card"><span>{ranges[index]}</span><p>{_safe(shot)}</p></article>'
        for index, shot in enumerate(shots[:5])
    )
    return f'<div class="timeline-card-grid">{cards}</div>'


def _storyboard_card(ctx, step, hide_shooting=False):
    card = ctx["render_storyboard_card"](step)
    card = re.sub(r'<p class="story-note"><strong>분석 반영:</strong>.*?</p>', "", card, flags=re.DOTALL)
    if hide_shooting:
        card = re.sub(r'<p class="story-note"><strong>촬영:</strong>.*?</p>', "", card, flags=re.DOTALL)
    return card


def _project_tab(item, ctx):
    with st.form(f"brief_{item['id']}"):
        title = st.text_input("프로젝트 이름", item.get("title", ""))
        concept = st.text_area("아이디어", item.get("concept", ""), height=80)
        save = st.form_submit_button("기획 저장", type="primary", use_container_width=True)
    if save:
        update_project(item["id"], {"title": title, "concept": concept}, ctx["projects_path"])
        st.rerun()

    st.subheader("첫 문장 추천")
    with st.form(f"hook_{item['id']}"):
        hook = st.text_area("첫 문장", item.get("hook", ""), height=70, placeholder="첫 2초에 손님이 멈출 이유")
        hook_save = st.form_submit_button("첫 문장 저장", use_container_width=True)
    if hook_save:
        update_project(item["id"], {"hook": hook, "stage": "script"}, ctx["projects_path"])
        st.rerun()

    st.subheader("추천 대본")
    variants = item.get("script_variants") or {}
    variants_are_short = not variants or any(len(str(variants.get(key) or "")) < 180 for key in ("sales", "story", "curiosity"))
    if variants_are_short:
        if st.button("전체 대본 만들기", use_container_width=True):
            full_variants = _build_full_variants(item)
            update_project(item["id"], {"script_variants": full_variants, "script": full_variants["sales"], "stage": "script"}, ctx["projects_path"])
            st.rerun()
    variant_names = {"sales": "상품 소개", "story": "스토리", "curiosity": "호기심"}
    variant_key = st.radio(
        "대본 유형", list(variant_names), format_func=variant_names.get, horizontal=True,
        key=f"script_choice_{item['id']}", label_visibility="collapsed",
    )
    current_text = variants.get(variant_key) or (item.get("script", "") if variant_key == "sales" else "")
    segments = _script_segments(current_text)
    st.markdown(_segment_cards(segments, "대본을 만들면 초 구간별 카드가 여기에 표시됩니다."), unsafe_allow_html=True)
    with st.expander(f"{variant_names[variant_key]} 대본 문구 수정"):
        edited_text = st.text_area("초 구간마다 한 줄씩 입력", current_text, key=f"variant_{item['id']}_{variant_key}", height=220, label_visibility="collapsed")
        if st.button("수정한 대본 저장", key=f"variant_save_{item['id']}_{variant_key}", use_container_width=True):
            values = {**variants, variant_key: edited_text}
            update_project(item["id"], {"script_variants": values, "script": values.get("sales", ""), "stage": "script"}, ctx["projects_path"])
            st.rerun()

    st.subheader("촬영 목록")
    cleaned_shots = [_clean_shot_instruction(shot) for shot in (item.get("shot_list") or [])]
    cleaned_shots = [shot for shot in cleaned_shots if shot][:5]
    st.markdown(
        _shot_cards(cleaned_shots, "대본을 선택하면 촬영 장면이 여기에 표시됩니다."),
        unsafe_allow_html=True,
    )
    with st.expander("촬영 목록 수정"):
        with st.form(f"shots_{item['id']}"):
            shots = st.text_area("한 줄에 한 장면씩 적어주세요", "\n".join(cleaned_shots), height=150)
            shot_save = st.form_submit_button("촬영 목록 저장", use_container_width=True)
        if shot_save:
            values = [_clean_shot_instruction(line) for line in shots.splitlines()]
            update_project(item["id"], {"shot_list": [value for value in values if value][:5], "stage": "shoot"}, ctx["projects_path"])
            st.rerun()

    source = item.get("source") or {}
    visual = source.get("visual_synthesis") or {}
    primary_camera = visual.get("top_camera") or "클로즈업"
    variant_shots = [segment["description"] for segment in segments][:5] or cleaned_shots
    preview_item = {**item, "script": current_text, "shot_list": variant_shots}
    steps = ctx["build_storyboard_steps"](ctx["business_type"], primary_camera, None, item.get("analysis") or {}, project=preview_item)[:5]

    st.subheader("촬영 스토리보드")
    for step in steps:
        st.markdown(_storyboard_card(ctx, step, hide_shooting=True), unsafe_allow_html=True)
    if st.button("이 대본으로 선택하기", type="primary", use_container_width=True, key=f"choose_script_{item['id']}_{variant_key}"):
        selected_shots = [_clean_shot_instruction(step.get("shoot", "")) for step in steps]
        values = {**variants, variant_key: current_text}
        update_project(
            item["id"],
            {"script": current_text, "script_variants": values, "shot_list": [shot for shot in selected_shots if shot][:5], "stage": "shoot"},
            ctx["projects_path"],
        )
        st.session_state["studio_view"] = "촬영"
        st.rerun()

    st.subheader("제작 가이드")
    guide_assets = item.get("guide_assets") or {}
    guide_prompt = (
        f"Vertical 9:16 storyboard reference for a {ctx['business_type']} Instagram reel. "
        f"Concept: {item.get('concept') or item.get('title')}. Opening hook: {item.get('hook') or 'Show the result first'}. "
        f"Camera: {primary_camera}. Show a practical small-business filming setup, clear subject, natural light, no text overlay."
    )
    image = guide_assets.get("image") or {}
    image_path = image.get("path", "")
    if image_path and Path(image_path).exists():
        st.image(image_path, caption="구도 참고 이미지")
    if ctx.get("can_generate_image") and st.button("이미지 가이드 만들기", use_container_width=True):
        try:
            with st.spinner("프로젝트에 맞는 구도 이미지를 만드는 중입니다..."):
                image = generate_flux_guide(guide_prompt)
                target = ctx["guides_dir"] / f"{item['id']}_visual.jpeg"
                image = {**image, "path": download_flux_guide(image["sample_url"], target)}
            update_project(item["id"], {"guide_assets": {**guide_assets, "image": image}}, ctx["projects_path"])
            st.rerun()
        except Exception as exc:
            st.error(f"이미지 가이드를 만들지 못했습니다: {exc}")

    voice = guide_assets.get("voiceover") or {}
    voice_path = voice.get("path", "")
    if voice_path and Path(voice_path).exists():
        st.audio(voice_path, format="audio/mpeg")
    if ctx.get("can_generate_voice"):
        voice_text = st.text_area("내레이션 대본", voice.get("text") or current_text, key=f"voice_{item['id']}", height=90)
        if st.button("음성 가이드 만들기", use_container_width=True):
            try:
                with st.spinner("음성 가이드를 만드는 중입니다..."):
                    audio = generate_elevenlabs_voiceover(voice_text)
                target = ctx["guides_dir"] / f"{item['id']}_voiceover.mp3"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(audio)
                update_project(item["id"], {"guide_assets": {**guide_assets, "voiceover": {"path": str(target), "text": voice_text, "provider": "elevenlabs"}}}, ctx["projects_path"])
                st.rerun()
            except Exception as exc:
                st.error(f"음성 가이드를 만들지 못했습니다: {exc}")


def _shoot_tab(item, ctx):
    visual = ((item.get("source") or {}).get("visual_synthesis") or {})
    primary_camera = visual.get("top_camera") or "클로즈업"
    steps = ctx["build_storyboard_steps"](ctx["business_type"], primary_camera, None, item.get("analysis") or {}, project=item)[:5]
    selected_key = f"shoot_step_{item['id']}"
    selected_index = st.session_state.get(selected_key)
    st.subheader("촬영 스토리보드")
    if selected_index is not None and 0 <= int(selected_index) < len(steps):
        if st.button("←", key=f"shoot_back_{item['id']}", help="전체 시간대로 돌아가기"):
            st.session_state[selected_key] = None
            st.rerun()
        st.markdown(_storyboard_card(ctx, steps[int(selected_index)]), unsafe_allow_html=True)
    else:
        ranges = ["0–2초", "2–5초", "5–9초", "9–13초", "13–15초"]
        columns = st.columns(len(steps), gap="small")
        for index, (column, step) in enumerate(zip(columns, steps)):
            if column.button(ranges[index], key=f"shoot_time_{item['id']}_{index}", use_container_width=True):
                st.session_state[selected_key] = index
                st.rerun()

    st.subheader("음원 추천")
    recommendations = recommend_audio_options(item)
    selected_id = str((item.get("audio") or {}).get("recommendation_id") or "")
    for option in recommendations:
        search_url = f"https://www.facebook.com/sound/collection/?q={quote(option['keywords'])}"
        with st.container(border=True):
            st.markdown(
                f'<div class="audio-option"><h3>{_safe(option["name"])}</h3>'
                f'<p><b>BPM</b><span>{_safe(option["bpm"])}</span></p>'
                f'<p><b>추천 이유</b><span>{_safe(option["reason"])}</span></p>'
                f'<p><b>검색어</b><span>{_safe(option["keywords"])}</span></p></div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "선택됨" if selected_id == option["id"] else "이 음원 추천 선택",
                key=f"audio_pick_{item['id']}_{option['id']}", use_container_width=True,
                disabled=selected_id == option["id"],
            ):
                update_project(
                    item["id"],
                    {"audio": {
                        "name": option["name"], "recommendation_id": option["id"],
                        "recommendation_name": option["name"], "recommendation_reason": option["reason"],
                        "search_keywords": option["keywords"], "bpm": option["bpm"], "url": search_url,
                        "rights_source": option.get("rights_source", "meta_sound_collection"),
                    }},
                    ctx["projects_path"],
                )
                st.rerun()

    selected = next((option for option in recommendations if option["id"] == selected_id), None)
    if selected:
        selected_url = str((item.get("audio") or {}).get("url") or f"https://www.facebook.com/sound/collection/?q={quote(selected['keywords'])}")
        st.markdown(f'### 선택한 음원 추천 · {_safe(selected["name"])}')
        st.link_button("음원 링크 열기", selected_url, type="primary", use_container_width=True)
        url_json = json.dumps(selected_url)
        components.html(
            f"""<button id="copy-audio" onclick='navigator.clipboard.writeText({url_json}).then(() => this.textContent="복사됨")'>링크 복사</button>
            <style>body{{margin:0}}#copy-audio{{width:100%;height:46px;border:0;border-radius:12px;background:#eef2f7;color:#0065d4;font:600 15px system-ui;cursor:pointer}}</style>""",
            height=52,
        )


def _analyze_tab(item, ctx):
    left, right = st.columns([1, 1])
    with left:
        upload = st.file_uploader("분석할 영상", ["mp4", "mov", "m4v"], key=f"video_{item['id']}")
        if upload and st.button("영상 분석하기", type="primary", use_container_width=True):
            target = ctx["uploads_dir"] / f"{item['id']}_{re.sub(r'[^A-Za-z0-9._-]', '_', upload.name)}"
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(upload.getvalue())
            try:
                with st.spinner("Analyzing the cut..."): result = ctx["analyze_file"](target, caption=item.get("script", ""))
                notes = [{"text":text, "done":False} for text in (result.get("priority_actions") or [])]
                update_project(item["id"], {"analysis":result, "edit_notes":notes, "stage":"review"}, ctx["projects_path"]); st.rerun()
            except Exception as exc: st.error(f"Analysis could not finish: {exc}")
        analysis = item.get("analysis") or {}
        if analysis: st.metric("AI 예상 점수", f"{float(analysis.get('overall_score') or 0):.0f}")
        st.caption("AI의 예상 결과입니다. 게시 후 실제 성과와 비교해 보세요.")
    with right:
        notes = [note if isinstance(note, dict) else {"text":str(note), "done":False} for note in (item.get("edit_notes") or [])]
        if not notes: st.caption("수정 항목이 아직 없습니다.")
        for index, note in enumerate(notes):
            st.markdown(f'<div class="rl-signal"><b>{"Done" if note.get("done") else "Edit"}</b><p>{_safe(note.get("text"))}</p></div>', unsafe_allow_html=True)
            a,b,c = st.columns(3)
            if a.button("대본에 반영", key=f"script_note_{item['id']}_{index}"):
                update_project(item["id"], {"script":(item.get("script", "") + "\n" + note["text"]).strip()}, ctx["projects_path"]); st.rerun()
            if b.button("촬영 목록에 반영", key=f"shots_note_{item['id']}_{index}"):
                update_project(item["id"], {"shot_list":[*(item.get("shot_list") or []), note["text"]]}, ctx["projects_path"]); st.rerun()
            if c.button("수정 완료", key=f"done_note_{item['id']}_{index}"):
                notes[index]["done"] = True; update_project(item["id"], {"edit_notes":notes}, ctx["projects_path"]); st.rerun()
    diagnostics = (item.get("analysis") or {}).get("timeline_diagnostics") or []
    if diagnostics:
        st.markdown('<div class="rl-timeline"><i class="tl-hook"></i><i class="tl-good"></i><i class="tl-risk"></i><i class="tl-cta"></i></div>', unsafe_allow_html=True)
        st.caption("파랑: 훅 · 초록: 강점 · 주황: 이탈 위험 · 보라: 행동 유도")
        frame = pd.DataFrame(diagnostics)
        if {"timestamp_seconds", "predicted_retention"}.issubset(frame.columns):
            fig = px.line(frame, x="timestamp_seconds", y="predicted_retention", markers=True, color_discrete_sequence=["#007aff"])
            fig.update_layout(height=220, margin=dict(l=0,r=0,t=10,b=0), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#f5f5f7" if st.session_state.get("theme") == "dark" else "#1d1d1f")
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo":False, "responsive":True})


def _publish_tab(item, ctx):
    st.subheader("게시 정보")
    st.caption("게시 후 media ID와 게시 시각을 확인하면 Insights의 Meta 실측과 연결됩니다.")
    with st.form(f"publish_{item['id']}"):
        media_id = st.text_input("Instagram 게시물 ID", item.get("instagram_media_id", ""))
        published_at = st.text_input("게시 시각", item.get("published_at", ""), placeholder="YYYY-MM-DD HH:MM")
        stage = st.selectbox("제작 단계", PROJECT_STAGES, PROJECT_STAGES.index(item.get("stage", "idea")), format_func=lambda value:STAGE_NAMES[value])
        save = st.form_submit_button("게시 정보 저장", type="primary", use_container_width=True)
    if save:
        if stage == "posted" and (not media_id.strip() or not published_at.strip()): st.error("게시 완료로 저장하려면 게시물 ID와 게시 시각을 입력해 주세요.")
        else: update_project(item["id"], {"instagram_media_id":media_id.strip(), "published_at":published_at.strip(), "stage":stage}, ctx["projects_path"]); st.rerun()


def studio(ctx):
    projects = list_projects(ctx["projects_path"])
    _header("Studio", "한 프로젝트를 기획부터 게시 전 검토까지 완성")
    notice = st.session_state.pop("studio_notice", "")
    if notice:
        st.success(notice)
    if not projects:
        _empty("첫 프로젝트를 시작해 보세요", "홈에서 아이디어를 적거나, 발견에서 마음에 드는 릴스를 가져오세요.")
        if st.button("홈으로 이동", type="primary", use_container_width=True): _go("Home")
        return
    ids = [item["id"] for item in projects]
    current = st.session_state.get("active_project_id") if st.session_state.get("active_project_id") in ids else ids[0]
    selected = st.selectbox("프로젝트", ids, ids.index(current), format_func=lambda value:next(item["title"] for item in projects if item["id"] == value))
    st.session_state["active_project_id"] = selected
    item = _project(projects, selected)
    view = st.radio(
        "스튜디오 단계",
        ["대본", "촬영", "게시"],
        horizontal=True,
        key="studio_view",
        label_visibility="collapsed",
    )
    if view == "대본":
        _project_tab(item, ctx)
    elif view == "촬영":
        _shoot_tab(item, ctx)
    else:
        _publish_tab(item, ctx)


def _measured(ctx):
    return [item for item in ctx["load_user_reels"](ctx["business_type"]) if item.get("출처") == "Meta 실측"]


def insights(ctx):
    _header("Insights", "게시한 릴스에서 다음 제작 결정을 찾습니다")
    measured = _measured(ctx)
    posted = [item for item in list_projects(ctx["projects_path"]) if item.get("stage") == "posted"]
    st.selectbox("조회 기간", ["최근 7일", "최근 30일", "전체 기간"])
    if not measured:
        _empty("성장의 기록이 시작될 곳", "Instagram을 연결하면 게시한 릴스의 실제 성과를 확인할 수 있어요.", "Insights")
        if st.button("Instagram 연결하기", key="insights_connect"):
            _go("Settings")
        for item in posted: st.markdown(f'<div class="rl-row"><b>{_safe(item.get("title"))}</b><span>Posted</span><span>Waiting for Meta sync</span><span>{_safe(item.get("published_at"))}</span></div>', unsafe_allow_html=True)
        return
    rows = [{**item, **normalize_insights(item.get("insights", {}))} for item in measured]
    frame = pd.DataFrame(rows)
    baseline = build_account_baseline([{"insights":item.get("insights", {})} for item in measured])
    best = frame.sort_values("save_rate", ascending=False).iloc[0]
    lift = (float(best["save_rate"]) / max(float(baseline.get("median_save_rate") or 0), .01) - 1) * 100
    st.markdown(f'<div class="rl-action"><div class="rl-kicker">What changed</div><h3>{_safe(best.get("릴스명", "This reel"))}의 저장률이 내 중앙값보다 {lift:+.0f}%</h3><div>클로즈업 훅, 길이, CTA를 한 가지씩 다음 프로젝트에서 재검증하세요.</div></div>', unsafe_allow_html=True)
    for col,label,value,detail in zip(st.columns(3), ["계정 중앙 조회수", "최고 저장률", "중앙 참여율"], [f"{int(baseline['median_views']):,}", f"{float(best['save_rate']):.1f}%", f"{float(baseline['median_engagement_rate']):.1f}%"], [f"{baseline['count']} measured reels", "Meta measured", "Meta measured"]):
        with col: _metric(label,value,detail)
    st.subheader("내 계정의 평균과 비교")
    columns = [key for key in ["릴스명", "views", "save_rate", "engagement_rate", "길이(초)", "촬영구도", "업로드"] if key in frame]
    st.dataframe(frame[columns].sort_values("save_rate", ascending=False), use_container_width=True, hide_index=True)
    for item in posted:
        history = load_performance_history(str(item.get("instagram_media_id") or ""), path=ctx["performance_history_path"])
        changes = compare_snapshot_windows(history)
        text = " · ".join(f"{hours}h: +{value['views_delta']:,} views" for hours,value in changes.items() if value)
        st.caption(f"{item.get('title')}: {text or 'Waiting for Meta sync'}")
    if st.button("좋은 패턴을 플레이북에 저장", type="primary", use_container_width=True):
        _save_playbook({"key":f"best-{best.get('릴스명', 'reel')}", "group":"worked", "label":"High-save project pattern", "sample_count":1, "lift":round(lift,1), "confidence":"provisional", "evidence":best.get("릴스명", "Meta reel")}, ctx["playbook_path"])
        st.success("패턴을 저장했어요. 성과가 쌓이면 다시 확인해 보세요.")


def _save_playbook(pattern, path):
    try: rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (OSError,json.JSONDecodeError): rows = []
    rows = [row for row in rows if row.get("key") != pattern.get("key")]
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp"); temp.write_text(json.dumps([pattern,*rows],ensure_ascii=False,indent=2),encoding="utf-8"); temp.replace(path)


def _playbook(ctx):
    try: saved = json.loads(ctx["playbook_path"].read_text(encoding="utf-8")) if ctx["playbook_path"].exists() else []
    except (OSError,json.JSONDecodeError): saved=[]
    reels = _measured(ctx); derived=[]
    if reels:
        frame = pd.DataFrame(reels); median=float(frame.get("조회수",pd.Series([0])).median() or 0)
        if "촬영구도" in frame and "조회수" in frame:
            for value, group in frame.groupby("촬영구도"):
                count=len(group); lift=(float(group["조회수"].mean())/median-1)*100 if median else 0
                group_name="worked" if count>=3 and lift>=10 else "avoid" if count>=3 and lift<=-10 else "uncertain"
                confidence="high" if count>=10 else "medium" if count>=5 else "provisional" if count>=3 else "insufficient data"
                derived.append({"key":f"composition:{value}","group":group_name,"label":f"Composition: {value}","sample_count":count,"lift":round(lift,1),"confidence":confidence,"evidence":", ".join(group.get("릴스명",pd.Series(dtype=str)).head(3))})
    return saved+derived


def playbook(ctx):
    _header("Playbook", "근거가 쌓인 패턴만 다음 프로젝트에 적용")
    patterns=_playbook(ctx)
    if not patterns:
        _empty("나만의 성공 패턴을 모아보세요", "실제 성과가 3개 이상 쌓이면 효과가 있었던 구도와 이야기를 정리해 드려요.", "Playbook")
        if st.button("성과 확인하기 →", key="playbook_insights"):
            _go("Insights")
        return
    for group,title in [("worked","효과가 있었던 패턴"),("uncertain","조금 더 확인할 패턴"),("avoid","피하면 좋을 패턴")]:
        st.subheader(title); items=[item for item in patterns if item.get("group")==group]
        if not items: st.caption("아직 충분한 근거가 쌓이지 않았어요.")
        for index,pattern in enumerate(items):
            st.markdown(f'<div class="rl-signal"><h3>{_safe(pattern.get("label"))}</h3><p>Sample {int(pattern.get("sample_count") or 0)} · {float(pattern.get("lift") or 0):+.0f}% vs median · {_safe(pattern.get("confidence"))}</p><small>Evidence: {_safe(pattern.get("evidence") or "No linked reel")}</small></div>', unsafe_allow_html=True)
            if st.button("프로젝트에 적용", key=f"playbook_{group}_{index}", use_container_width=True):
                projects=list_projects(ctx["projects_path"]); item=_project(projects,st.session_state.get("active_project_id")) or next((row for row in projects if row.get("stage")!="posted"),None)
                if not item: st.info("먼저 프로젝트를 만들어 주세요.")
                else:
                    update_project(item["id"], {"concept":(item.get("concept","")+"\nApply: "+pattern["label"]).strip(),"stage":"script"},ctx["projects_path"]); st.session_state["active_project_id"]=item["id"]; _go("Studio")


def settings(ctx):
    _header("Settings", "내 작업 공간을 편안하게, 필요한 연결을 한곳에서.")
    st.subheader("서비스 연결")
    services = "".join(f'<div class="ios-service {"is-ready" if ready else ""}"><span>{_safe(name)}</span><small><i></i>{"연결됨" if ready else "연결 전"}</small></div>' for name, ready in ctx["service_status"])
    st.markdown(f'<div class="ios-services">{services}</div>', unsafe_allow_html=True)
    st.subheader("Instagram 계정")
    if not ctx.get("meta_oauth_ready"):
        st.info("META_APP_ID, META_APP_SECRET, META_REDIRECT_URI를 .env에 넣으면 안전한 Instagram 연결을 시작할 수 있습니다.")
    else:
        callback_code = st.query_params.get("code", "")
        callback_state = st.query_params.get("state", "")
        expected_state = st.session_state.get("meta_oauth_state", "")
        if callback_code and not st.session_state.get("meta_access_token"):
            if callback_state != expected_state:
                st.error("Instagram 연결 상태를 확인할 수 없습니다. Connect Instagram을 다시 선택하세요.")
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
            st.success("Instagram access token is available. Insights 동기화를 실행할 수 있습니다.")
        else:
            if st.button("Instagram 연결 준비", type="primary", use_container_width=True):
                try:
                    url, state = ctx["build_oauth_url"]()
                    st.session_state["meta_oauth_url"] = url
                    st.session_state["meta_oauth_state"] = state
                    st.rerun()
                except Exception as exc:
                    st.error(f"연결 준비 실패: {exc}")
            oauth_url = st.session_state.get("meta_oauth_url")
            if oauth_url:
                st.link_button("Instagram 연결하기", oauth_url, type="primary", use_container_width=True)
                st.caption("열린 Instagram 화면에서 테스트 계정으로 직접 로그인하고 승인하세요.")
    st.subheader("트렌드 추적"); st.caption("Radar 검색 조건과 알림은 사용자별 파일에 저장됩니다.")
    st.subheader("데이터 및 개인정보"); st.caption("데이터 내보내기와 삭제는 계정 관리 흐름에서만 처리합니다.")
    if ctx.get("is_admin"):
        st.subheader("시스템 현황"); jobs=ctx["list_jobs"]()
        if jobs: st.dataframe(pd.DataFrame(jobs),use_container_width=True,hide_index=True)


def render_workspace(menu, ctx):
    {"Home":home,"Radar":radar,"Studio":studio,"Insights":insights,"Playbook":playbook,"Settings":settings}[menu](ctx)
