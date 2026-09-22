"""Project-first Streamlit workspace; persistent work always goes through user-scoped files."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui.appearance import NAV_LABELS, STAGE_NAMES, icon

from app.core.audio_rights import annotate_tracks, recommend_audio_options
from app.core.content_projects import PROJECT_STAGES, create_project, list_projects, next_action, pipeline_counts, update_project
from app.core.performance_insights import build_account_baseline, compare_snapshot_windows, load_performance_history, normalize_insights
from app.core.signal_studies import add_signal, build_signal_synthesis, build_visual_synthesis, load_study, remove_signal, save_visual_analysis
from app.core.storyboard import build_mobile_coach_url
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
    label = NAV_LABELS.get(title, title)
    date = datetime.now()
    day = "월화수목금토일"[date.weekday()]
    kicker = f"{date.month}월 {date.day}일 {day}요일" if title == "Home" else "Reel Lab · 나의 작업 공간"
    label = "오늘의 스튜디오" if title == "Home" else label
    st.markdown(f'<header class="rl-head"><div class="rl-kicker">{_safe(kicker)}</div><h1>{_safe(label)}</h1><p>{_safe(subtitle)}</p></header>', unsafe_allow_html=True)


def _metric(label, value, detail=""):
    st.markdown(f'<div class="rl-metric"><span>{_safe(label)}</span><b>{_safe(value)}</b><small>{_safe(detail)}</small></div>', unsafe_allow_html=True)


def _section(title, detail=""):
    st.markdown(f'<div class="ios-section-title"><h2>{_safe(title)}</h2><span>{_safe(detail)}</span></div>', unsafe_allow_html=True)


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


def home(ctx):
    projects = list_projects(ctx["projects_path"])
    counts = pipeline_counts(projects)
    active = next((item for item in projects if item.get("stage") != "posted"), None)
    preferences = _load_settings(ctx["workspace_settings_path"])
    goal = min(20, max(1, int(preferences.get("weekly_publish_goal", 3))))
    week_start = datetime.now() - timedelta(days=datetime.now().weekday())
    done = sum(1 for item in projects if item.get("stage") == "posted" and str(item.get("published_at", "")) >= week_start.isoformat()[:10])
    _header("Home", "아이디어를 담고, 나만의 릴스를 완성해 보세요.")
    focus, progress = st.columns([1.65, 1], gap="medium")
    with focus:
        with st.container(border=True):
            eyebrow = "이어서 만들기" if active else "당신의 다음 릴스"
            title = active.get("title") if active else "작은 아이디어,\n새로운 가능성."
            description = next_action(active) if active else "매장의 일상에서 시작해 보세요.\n기획부터 촬영, 분석까지 함께할게요."
            title_html = _safe(title).replace("\n", "<br>")
            description_html = _safe(description).replace("\n", "<br>")
            st.markdown(f'<span class="ios-focus-marker"></span><div class="ios-focus"><div class="ios-eyebrow">{icon("Studio", 16)}{eyebrow}</div><h2>{title_html}</h2><p>{description_html}</p><div class="ios-focus-art">{icon("Studio", 44)}</div></div>', unsafe_allow_html=True)
            if active:
                if st.button("프로젝트 이어서 만들기  →", type="primary", key="continue_project"):
                    st.session_state["active_project_id"] = active["id"]
                    _go("Studio")
            elif st.button("새 프로젝트 시작하기  +", type="primary", key="start_project"):
                st.session_state["show_new_project"] = not st.session_state.get("show_new_project", False)
    with progress:
        percent = min(100, done / goal * 100)
        remaining = max(0, goal - done)
        message = f"이번 주 목표까지 {remaining}개 남았어요." if remaining else "이번 주 목표를 달성했어요."
        st.markdown(f'<style>.ios-ring{{background:conic-gradient(var(--accent) {percent:.1f}%,var(--ring-track) 0)}}</style><div class="ios-goal"><div class="ios-goal-top">이번 주 목표<small>꾸준함이 만드는 성장</small></div><div class="ios-ring"><div class="ios-ring-inner"><strong>{done}<span style="font-size:.9rem;color:var(--muted);letter-spacing:0"> / {goal}</span></strong><small>게시한 릴스</small></div></div><p>{message}</p></div>', unsafe_allow_html=True)
    if st.session_state.get("show_new_project"):
        _new_project_form(ctx)
    _section("제작 현황", f"전체 {len(projects)}개 프로젝트")
    stages = "".join(f'<div class="ios-pipeline-item"><span>{STAGE_NAMES[stage]}</span><b>{counts[stage]}</b></div>' for stage in PROJECT_STAGES)
    st.markdown(f'<div class="ios-pipeline">{stages}</div>', unsafe_allow_html=True)
    recent, discover = st.columns([1.65, 1], gap="medium")
    with recent:
        _section("최근 프로젝트", "최근 수정 순")
        if not projects:
            _empty("첫 이야기를 기다리고 있어요", "새 프로젝트를 만들면 이곳에 모아드릴게요.")
        for item in projects[:4]:
            with st.container(border=True):
                updated = str(item.get("updated_at", ""))[:10].replace("-", ".")
                st.markdown(f'<div class="ios-project"><div class="ios-project-icon">{icon("Studio", 22)}</div><div class="ios-project-text"><b>{_safe(item.get("title"))}</b><small>{updated}</small></div><span class="ios-stage">{_safe(STAGE_NAMES.get(item.get("stage"), "아이디어"))}</span></div>', unsafe_allow_html=True)
                if st.button("프로젝트 열기 →", key=f"recent_{item['id']}", use_container_width=True):
                    st.session_state["active_project_id"] = item["id"]
                    _go("Studio")
        if active and st.button("새 프로젝트 만들기 +", key="new_project_secondary", use_container_width=True):
            st.session_state["show_new_project"] = True
            st.rerun()
    with discover:
        _section("영감이 필요할 때")
        with st.container(border=True):
            st.markdown(f'<div class="ios-project"><div class="ios-project-icon">{icon("Radar", 24)}</div><div class="ios-project-text"><b>다음 아이디어 발견하기</b><small>다른 릴스에서 우리 매장의 힌트를 찾아요.</small></div></div>', unsafe_allow_html=True)
            if st.button("릴스 탐색하기 →", key="discover_reels", use_container_width=True):
                _go("Radar")
    with st.expander("주간 게시 목표 조정"):
        new_goal = st.number_input("이번 주에 몇 개를 게시할까요?", 1, 20, goal)
        if new_goal != goal:
            _save_settings(ctx["workspace_settings_path"], {**preferences, "weekly_publish_goal": new_goal})
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


def _render_study_basket(study, query, ctx):
    items = study.get("items") or []
    with st.expander(f"분석에 담은 릴스 · {len(items)}개", expanded=bool(items)):
        if not items:
            st.caption("릴스 2~5개를 담으면 공통 패턴을 근거와 함께 합성합니다.")
            return
        for index, item in enumerate(items):
            row, remove = st.columns([5, 1])
            row.caption(f"@{item.get('username', 'unknown')} · {int(item.get('views') or 0):,} views · {str(item.get('caption') or 'No caption')[:56]}")
            if remove.button("삭제", key=f"study_remove_{index}"):
                remove_signal(_study_identity(item), ctx["study_path"])
                st.rerun()
        if len(items) < 2:
            st.info("최소 두 릴스를 선택하면 하나의 프로젝트용 공통 패턴을 만들 수 있습니다.")
            return
        synthesis = build_signal_synthesis(items, query=query)
        visual_analyses = study.get("visual_analyses") or {}
        visual = build_visual_synthesis(visual_analyses, items)
        thumbnail_items = [item for item in items if item.get("thumbnail_url")]
        if len(thumbnail_items) >= 2:
            if st.button("공통 시각 패턴 분석", use_container_width=True, disabled=not ctx["can_analyze_visual"]):
                completed, failures = dict(visual_analyses), []
                with st.spinner("선택한 릴스의 구도·자막·컷 신호를 분석하는 중입니다..."):
                    for selected in thumbnail_items[:5]:
                        try:
                            completed[_study_identity(selected)] = ctx["analyze_thumbnail"](selected["thumbnail_url"], caption=selected.get("caption", ""))
                        except Exception as exc:
                            failures.append(f"@{selected.get('username', 'unknown')}: {exc}")
                save_visual_analysis(completed, ctx["study_path"])
                if failures:
                    st.warning("일부 릴스의 시각 분석을 완료하지 못했습니다. " + " / ".join(failures[:2]))
                st.rerun()
        elif not thumbnail_items:
            st.caption("현재 수집 결과에 썸네일 URL이 없어 시각 공통 분석을 실행할 수 없습니다. 새로 수집한 신호에서 제공됩니다.")
        if visual["analyzed_count"]:
            st.caption(f"시각 근거 {visual['analyzed_count']}개 · 구도 {visual['top_camera'] or '-'} · 자막 {visual['top_subtitle_position'] or '-'} · 컷 {visual['top_cut_speed'] or '-'} · BGM {visual['top_bgm_mood'] or '-'} · 신뢰도 {visual['confidence']}")
        pattern_labels = [f"{item['label']} ({item['reel_count']}/{synthesis['sample_count']})" for item in synthesis.get("common_patterns") or []]
        st.markdown(
            f'<div class="rl-action"><div class="rl-kicker">Pattern brief · {synthesis["sample_count"]} reels</div>'
            f'<h3>{_safe(" · ".join(pattern_labels[:3]) or "공통 패턴을 확정할 근거가 부족합니다.")}</h3>'
            f'<div>중앙 조회 {int(synthesis["median_views"]):,} · 신뢰도 {_safe(synthesis["confidence"])} · '
            f'서로 다른 릴스에서 반복된 단어 {_safe(", ".join(synthesis["repeated_terms"][:3]) or "없음")}</div></div>',
            unsafe_allow_html=True,
        )
        for pattern in (synthesis.get("common_patterns") or [])[:3]:
            with st.expander(f"근거 보기 · {pattern['label']} · {pattern['reel_count']}/{synthesis['sample_count']}개 릴스"):
                st.caption(pattern["why_it_matters"])
                for evidence in pattern.get("evidence") or []:
                    matched = ", ".join(evidence.get("matches") or [])
                    st.markdown(f"**@{_safe(evidence.get('username') or 'unknown')}** · {_safe(matched)}")
                    st.caption(evidence.get("excerpt") or "본문 근거 없음")
        st.caption(" · ".join(synthesis["recommended_structure"]))
        if st.button("모은 릴스로 프로젝트 만들기", type="primary", use_container_width=True):
            # A project must contain visual evidence when thumbnails and an AI
            # connection are available; users should not have to discover and
            # press a separate prerequisite button first.
            completed = dict(visual_analyses)
            missing = [row for row in thumbnail_items[:5] if _study_identity(row) not in completed]
            if missing and ctx["can_analyze_visual"]:
                with st.spinner("프로젝트에 사용할 실제 구도·자막 위치를 분석하는 중입니다..."):
                    for selected in missing:
                        try:
                            completed[_study_identity(selected)] = ctx["analyze_thumbnail"](selected["thumbnail_url"], caption=selected.get("caption", ""))
                        except Exception:
                            # Caption evidence remains usable. The project marks
                            # visual confidence separately instead of inventing it.
                            pass
                save_visual_analysis(completed, ctx["study_path"])
                visual = build_visual_synthesis(completed, items)
            video_items = [row for row in items[:5] if row.get("video_url")]
            if video_items and ctx["can_analyze_visual"] and ctx.get("analyze_sequence_url"):
                with st.spinner("영상 길이를 정규화해 5개 시간 구간의 공통 구도를 분석하는 중입니다..."):
                    for selected in video_items:
                        identity = _study_identity(selected)
                        try:
                            sequence = ctx["analyze_sequence_url"](selected["video_url"], caption=selected.get("caption", ""))
                            completed[identity] = {**completed.get(identity, {}), **sequence}
                        except Exception:
                            pass
                visual = build_visual_synthesis(completed, items)
            patterns = synthesis.get("common_patterns") or []
            focus = " · ".join(item["label"] for item in patterns[:2]) or ", ".join(synthesis["repeated_terms"][:3]) or query or "대표 장면"
            project = create_project(
                f"{query} pattern study",
                ctx["projects_path"],
                business_type=ctx["business_type"],
                concept=f"{query}에서 반복된 장면: {focus}",
                source={"type": "signal_study", "query": query, "signals": items, "synthesis": synthesis, "visual_synthesis": visual},
            )
            project["hook"] = synthesis["recommended_hook"]
            variants = _build_full_variants(project, synthesis)
            project = update_project(project["id"], {"hook": synthesis["recommended_hook"], "script": variants["sales"], "script_variants": variants, "shot_list": synthesis["recommended_structure"], "stage": "script"}, ctx["projects_path"])
            st.session_state["active_project_id"] = project["id"]
            _go("Studio")


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
                st.session_state["market_changes"] = ctx["compare_snapshots"](before, snapshot)
                st.session_state["market_changes_query"] = clean_query
                ctx["save_snapshot"](snapshot)
                st.session_state["market_snapshot"] = snapshot
                st.session_state["radar_notice"] = f"관련 릴스 {len(reels)}개를 찾았습니다."
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
    _render_study_basket(study, query, ctx)
    rising = sum(bool(item["view_delta"]) for item in signals)
    for col, label, value, detail in zip(st.columns(4), ["상승 중인 릴스", "새로운 계정", "반복되는 훅", "콘텐츠 형식"], [rising, sum(bool(item.get("is_new_account")) for item in signals), sum(bool(item.get("caption")) for item in signals), len(snapshot.get("top_hashtags", []))], ["vs prior capture", "this capture", "caption evidence", "repeat signals"]):
        with col: _metric(label, value, detail)
    for index, signal in enumerate(signals[:20]):
        delta = signal["view_delta"]
        views = signal["views"]
        baseline = max(views - delta, 1)
        multiple = f"{views / baseline:.1f}x" if delta else "new"
        kind = "New account" if signal.get("is_new_account") else ("Rising reel" if delta else "Reference reel")
        url = signal.get("url") or ""
        caption = str(signal.get("caption") or "")
        st.markdown(f'<div class="rl-signal"><div class="rl-kicker">{_safe(kind)}</div><h3>@{_safe(signal.get("username"))}</h3><p>{_safe(caption[:150] or "캡션 근거 없음")}</p><small>Views {views:,} · +{delta:,} · {multiple} · confidence {_safe(signal.get("comparison_confidence") or "low")} · {_safe(signal.get("published_at") or snapshot.get("captured_at"))}</small></div>', unsafe_allow_html=True)
        a, b, c = st.columns(3)
        if url: a.link_button("원본 보기", url, use_container_width=True)
        selected = _study_identity(signal) in {_study_identity(item) for item in study.get("items", [])}
        if b.button("추가됨" if selected else "분석에 담기", key=f"study_add_{index}", use_container_width=True, disabled=selected):
            add_signal(signal, ctx["study_path"])
            st.rerun()
        if c.button("프로젝트로 만들기", key=f"signal_{index}", use_container_width=True):
            item = create_project(f"@{signal.get('username', 'signal')} structure study", ctx["projects_path"], business_type=ctx["business_type"], concept="한 개의 경쟁 릴스 구조를 내 매장 장면으로 각색", source={"type":"competitor_signal", "url":url, "username":signal.get("username", ""), "query":query, "views":views, "view_delta":delta, "discovered_at":signal.get("discovered_at"), "comparison_confidence":signal.get("comparison_confidence", "low")})
            st.session_state["active_project_id"] = item["id"]
            _go("Studio")


def _stats(text, project):
    seconds = max(8, round(len(text.replace(" ", "")) / 6))
    cuts = max(3, min(12, round(seconds / 3)))
    difficulty = "Easy" if cuts <= 4 else "Moderate" if cuts <= 7 else "Detailed"
    fit = "High" if project.get("business_type") and project.get("concept") else "Review"
    return f"{seconds}s · {cuts} cuts · {difficulty} · store fit {fit}"


def _script_segments(text: str) -> list[dict]:
    segments = []
    for index, raw_line in enumerate(str(text or "").splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^((?:\d+(?:\.\d+)?\s*[-~–]\s*\d+(?:\.\d+)?초)|(?:마지막\s*\d*(?:\.\d+)?초))\s*[|·:]?\s*(.*)$", line)
        if match:
            time_label, content = match.group(1), match.group(2)
        else:
            time_label, content = f"장면 {index + 1}", line
        segments.append({"time": time_label.replace("-", "–").replace("~", "–"), "content": content})
    return segments


def _segment_cards(segments: list[dict], empty_message: str) -> str:
    if not segments:
        return f'<div class="timeline-empty">{_safe(empty_message)}</div>'
    cards = "".join(
        f'<article class="timeline-card"><span>{_safe(segment["time"])}</span><p>{_safe(segment["content"])}</p></article>'
        for segment in segments
    )
    return f'<div class="timeline-card-grid">{cards}</div>'


def _project_tab(item, ctx):
    with st.form(f"brief_{item['id']}"):
        title = st.text_input("프로젝트 이름", item.get("title", ""))
        concept = st.text_area("아이디어", item.get("concept", ""), height=80)
        save = st.form_submit_button("기획 저장", type="primary", use_container_width=True)
    if save:
        update_project(item["id"], {"title":title, "concept":concept}, ctx["projects_path"]); st.rerun()
    st.subheader("첫 장면의 훅")
    with st.form(f"hook_{item['id']}"):
        hook = st.text_area("첫 문장", item.get("hook", ""), height=70, placeholder="첫 2초에 손님이 멈출 이유")
        hook_save = st.form_submit_button("훅 저장", use_container_width=True)
    if hook_save:
        update_project(item["id"], {"hook":hook, "stage":"script"}, ctx["projects_path"]); st.rerun()
    st.subheader("대본 버전")
    variants = item.get("script_variants") or {}
    variants_are_short = not variants or any(len(str(variants.get(key) or "")) < 180 for key in ("sales", "story", "curiosity"))
    if variants_are_short:
        st.caption("현재 초안은 방향만 있습니다. 촬영 순서와 CTA까지 포함한 대본으로 확장할 수 있습니다.")
        if st.button("전체 대본 만들기", use_container_width=True):
            full_variants = _build_full_variants(item)
            update_project(item["id"], {"script_variants": full_variants, "script": full_variants["sales"], "stage": "script"}, ctx["projects_path"])
            st.rerun()
    for tab, key, name in zip(st.tabs(["상품 소개", "스토리", "호기심"]), ["sales", "story", "curiosity"], ["상품 소개", "스토리", "호기심"]):
        with tab:
            current_text = variants.get(key) or (item.get("script", "") if key == "sales" else "")
            st.markdown(_segment_cards(_script_segments(current_text), "대본을 만들면 초 구간별 카드가 여기에 표시됩니다."), unsafe_allow_html=True)
            st.caption(_stats(current_text, item))
            with st.expander(f"{name} 대본 문구 수정"):
                text = st.text_area("초 구간마다 한 줄씩 입력", current_text, key=f"variant_{item['id']}_{key}", height=220, label_visibility="collapsed")
                if st.button("수정한 대본 저장", key=f"variant_save_{item['id']}_{key}", use_container_width=True):
                    values = {**variants, key:text}
                    update_project(item["id"], {"script_variants":values, "script":values.get("sales", ""), "stage":"script"}, ctx["projects_path"]); st.rerun()
    st.subheader("촬영 목록")
    shot_ranges = ["0–2초", "2–5초", "5–9초", "9–13초", "13–15초"]
    shot_segments = [
        {"time": shot_ranges[min(index, len(shot_ranges) - 1)], "content": shot}
        for index, shot in enumerate(item.get("shot_list") or [])
    ]
    st.markdown(_segment_cards(shot_segments, "촬영 목록을 만들면 장면별 카드가 여기에 표시됩니다."), unsafe_allow_html=True)
    with st.expander("촬영 목록 수정"):
        with st.form(f"shots_{item['id']}"):
            shots = st.text_area("한 줄에 한 장면씩 적어주세요", "\n".join(item.get("shot_list") or []), height=150)
            shot_save = st.form_submit_button("촬영 목록 저장", use_container_width=True)
        if shot_save:
            update_project(item["id"], {"shot_list":[line.strip() for line in shots.splitlines() if line.strip()], "stage":"shoot"}, ctx["projects_path"]); st.rerun()
    source = item.get("source") or {}
    visual = source.get("visual_synthesis") or {}
    signals_with_thumbnails = [
        row for row in (source.get("signals") or [])[:5]
        if row.get("thumbnail_url")
    ]
    needs_geometry = (
        source.get("type") == "signal_study"
        and len(signals_with_thumbnails) >= 2
        and not visual.get("subject_bbox")
    )
    needs_sequence = (
        source.get("type") == "signal_study"
        and sum(bool(row.get("video_url")) for row in (source.get("signals") or [])) >= 2
        and int(visual.get("sequence_analyzed_count") or 0) < 2
    )
    if (needs_geometry or needs_sequence) and ctx.get("can_analyze_visual") and not source.get("sequence_geometry_attempted_at"):
        analyses, failures = dict(source.get("visual_analyses") or {}), []
        with st.spinner("릴스 길이를 정규화해 구간별 물품·자막 좌표를 계산하는 중입니다..."):
            for signal in signals_with_thumbnails:
                try:
                    identity = _study_identity(signal)
                    if needs_geometry and not analyses.get(identity, {}).get("subject_bbox"):
                        analyses[identity] = {**analyses.get(identity, {}), **ctx["analyze_thumbnail"](
                            signal["thumbnail_url"], caption=signal.get("caption", "")
                        )}
                    if signal.get("video_url") and ctx.get("analyze_sequence_url"):
                        analyses[identity] = {**analyses.get(identity, {}), **ctx["analyze_sequence_url"](
                            signal["video_url"], caption=signal.get("caption", "")
                        )}
                except Exception as exc:
                    failures.append(str(exc))
        visual = build_visual_synthesis(analyses, source.get("signals") or [])
        updated_source = {
            **source,
            "visual_synthesis": visual,
            "visual_analyses": analyses,
            "visual_geometry_attempted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sequence_geometry_attempted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "visual_geometry_error": failures[0][:240] if failures else "",
        }
        update_project(item["id"], {"source": updated_source}, ctx["projects_path"])
        st.rerun()
    primary_camera = visual.get("top_camera") or "클로즈업"
    st.subheader("촬영 스토리보드")
    if source.get("type") == "signal_study":
        st.caption(
            f"Radar 시각 근거 {visual.get('analyzed_count', 0)}개 · 추천 구도 {primary_camera} · "
            f"자막 {visual.get('top_subtitle_position') or '검토 필요'} · "
            f"컷 {visual.get('top_cut_speed') or '검토 필요'}"
        )
        if (needs_geometry or needs_sequence) and source.get("sequence_geometry_attempted_at"):
            st.warning("공통 물품·자막 좌표를 충분히 추출하지 못했습니다. 아래 5컷에는 장면별 안전 영역을 표시합니다.")
    else:
        st.caption("프로젝트의 훅과 촬영 목록을 바꾸면 피사체 위치, 자막 위치와 문구도 함께 바뀝니다.")
    steps = ctx["build_storyboard_steps"](
        ctx["business_type"], primary_camera, None, item.get("analysis") or {}, project=item
    )
    for step in steps:
        st.markdown(ctx["render_storyboard_card"](step), unsafe_allow_html=True)
    st.subheader("제작 가이드")
    guide_assets = item.get("guide_assets") or {}
    visual = (source.get("visual_synthesis") or {}) if source.get("type") == "signal_study" else {}
    guide_prompt = (
        f"Vertical 9:16 storyboard reference for a {ctx['business_type']} Instagram reel. "
        f"Concept: {item.get('concept') or item.get('title')}. "
        f"Opening hook: {item.get('hook') or 'Show the result first'}. "
        f"Camera: {visual.get('top_camera') or 'close-up'}. "
        "Show a practical small-business filming setup, clear subject, natural light, no text overlay."
    )
    image = guide_assets.get("image") or {}
    image_path = image.get("path", "")
    if image_path and Path(image_path).exists():
        st.image(image_path, caption="Generated reference image. Use the composition, not another creator's exact content.")
    if ctx.get("can_generate_image"):
        if st.button("이미지 가이드 만들기", use_container_width=True):
            try:
                with st.spinner("Generating a project-specific visual reference..."):
                    image = generate_flux_guide(guide_prompt)
                    target = ctx["guides_dir"] / f"{item['id']}_visual.jpeg"
                    image = {**image, "path": download_flux_guide(image["sample_url"], target)}
                update_project(item["id"], {"guide_assets": {**guide_assets, "image": image}}, ctx["projects_path"])
                st.rerun()
            except Exception as exc:
                st.error(f"Visual guide could not be generated: {exc}")
    else:
        st.caption("이미지 생성 서비스를 연결하면 장면별 가이드를 만들 수 있어요.")

    voice = guide_assets.get("voiceover") or {}
    voice_path = voice.get("path", "")
    if voice_path and Path(voice_path).exists():
        st.audio(voice_path, format="audio/mpeg")
    if ctx.get("can_generate_voice"):
        voice_text = st.text_area("내레이션 대본", voice.get("text") or item.get("script") or item.get("hook", ""), key=f"voice_{item['id']}", height=90)
        if st.button("음성 가이드 만들기", use_container_width=True):
            try:
                with st.spinner("Generating voice guide..."):
                    audio = generate_elevenlabs_voiceover(voice_text)
                target = ctx["guides_dir"] / f"{item['id']}_voiceover.mp3"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(audio)
                update_project(item["id"], {"guide_assets": {**guide_assets, "voiceover": {"path": str(target), "text": voice_text, "provider": "elevenlabs"}}}, ctx["projects_path"])
                st.rerun()
            except Exception as exc:
                st.error(f"Voice guide could not be generated: {exc}")
    else:
        st.caption("음성 생성 서비스를 연결하면 내레이션을 미리 들을 수 있어요.")


def _shoot_tab(item, ctx):
    st.subheader("촬영")
    for index, shot in enumerate(item.get("shot_list") or []): st.checkbox(str(shot), key=f"shot_{item['id']}_{index}")
    st.subheader("음원 선택")
    old = item.get("audio") or {}
    recommendations = recommend_audio_options(item)
    st.caption("프로젝트 훅, 반복 키워드, 영상 분위기와 컷 속도를 기준으로 고른 방향입니다. Meta Sound Collection에서 검색할 키워드도 함께 제공합니다.")
    recommendation_cards = "".join(
        f'<article class="timeline-card"><span>{index + 1}순위 · {option["bpm"]} BPM</span>'
        f'<p><strong>{_safe(option["name"])}</strong><br>{_safe(option["reason"])}<br>'
        f'<small>검색어: {_safe(option["keywords"])}</small></p></article>'
        for index, option in enumerate(recommendations)
    )
    st.markdown(f'<div class="timeline-card-grid">{recommendation_cards}</div>', unsafe_allow_html=True)
    selection_mode = st.radio("선택 방법", ["추천에서 고르기", "내가 원하는 음악 입력"], horizontal=True, key=f"audio_mode_{item['id']}")
    selected_option = None
    if selection_mode == "추천에서 고르기":
        selected_id = st.radio(
            "추천 후보",
            [option["id"] for option in recommendations],
            format_func=lambda value: next(f"{option['name']} · {option['bpm']} BPM" for option in recommendations if option["id"] == value),
            key=f"audio_recommendation_{item['id']}",
        )
        selected_option = next(option for option in recommendations if option["id"] == selected_id)
    with st.form(f"audio_{item['id']}"):
        if selected_option:
            st.info(f"선택: {selected_option['name']} · {selected_option['use']}\n\nMeta Sound Collection 검색어: {selected_option['keywords']}")
            name = st.text_input("실제로 찾은 곡명", old.get("name", ""), placeholder="추천 검색어로 찾은 실제 곡명을 입력하세요")
        else:
            name = st.text_input("사용할 음원", old.get("name", ""), placeholder="곡명 또는 Instagram 오디오 이름")
        sources = ["", "meta_sound_collection", "owned", "commissioned", "licensed_by_business"]
        default_source = selected_option.get("rights_source", "") if selected_option else old.get("rights_source", "")
        source = st.selectbox("음원 이용 권한", sources, index=sources.index(default_source) if default_source in sources else 0)
        license_name = st.text_input("라이선스 또는 이용 근거", old.get("license", ""))
        evidence_url = st.text_input("증빙 링크", old.get("evidence_url", ""))
        expiry = st.text_input("이용 만료일", old.get("expires_at", ""), placeholder="YYYY-MM-DD")
        audio_save = st.form_submit_button("이 음원으로 선택", type="primary", use_container_width=True)
    if audio_save:
        saved_name = name.strip() or (f"추천 방향: {selected_option['name']}" if selected_option else "")
        recommendation_data = ({
            "recommendation_id": selected_option["id"],
            "recommendation_name": selected_option["name"],
            "recommendation_reason": selected_option["reason"],
            "search_keywords": selected_option["keywords"],
            "bpm": selected_option["bpm"],
        } if selected_option else {})
        update_project(item["id"], {"audio":{"name":saved_name, "rights_source":source, "license":license_name, "evidence_url":evidence_url, "expires_at":expiry, "verified_at":datetime.now().isoformat(timespec="seconds"), **recommendation_data}}, ctx["projects_path"]); st.rerun()
    if old.get("name"):
        rights = annotate_tracks([{"곡명":old.get("name"), **old}], registry_path=ctx["audio_registry"])[0]["rights"]
        st.info(f"{rights.get('level', 'review').upper()} · {rights.get('status', '')} · {rights.get('detail', '')} · checked {old.get('verified_at', '-') or '-'} · expires {rights.get('expires_at', '-') or '-'}")
    if ctx.get("mobile_coach_url"):
        coach_server = ctx.get("mobile_coach_server") or {}
        if not coach_server.get("running"):
            st.error(f"촬영 코치 서버를 시작하지 못했습니다: {coach_server.get('error') or '알 수 없는 오류'}")
            return
        visual = ((item.get("source") or {}).get("visual_synthesis") or {})
        primary_camera = visual.get("top_camera") or "클로즈업"
        steps = ctx["build_storyboard_steps"](
            ctx["business_type"], primary_camera, None, item.get("analysis") or {}, project=item
        )
        coach_url = build_mobile_coach_url(
            ctx["mobile_coach_url"], item, steps, ctx.get("app_return_url", "")
        )
        st.subheader("프로젝트 촬영 코치")
        st.caption("앱 실행과 함께 촬영 코치 서버도 자동으로 시작됩니다. 같은 와이파이의 휴대폰으로 QR을 열면 컷 순서, 피사체 위치와 실제 자막 문구가 표시됩니다.")
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={quote(coach_url, safe='')}"
        qr_col, action_col = st.columns([1, 2])
        with qr_col:
            st.image(qr_url, caption="휴대폰으로 스캔")
        with action_col:
            st.link_button("이 프로젝트로 촬영 시작", coach_url, type="primary", use_container_width=True)
            st.code(coach_url, language=None)
            if not coach_url.startswith("https://"):
                st.warning("휴대폰 카메라는 대부분 HTTPS 주소에서만 열립니다. 배포 주소를 MOBILE_COACH_BASE_URL에 설정하세요.")


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
    if not projects:
        _empty("첫 프로젝트를 시작해 보세요", "홈에서 아이디어를 적거나, 발견에서 마음에 드는 릴스를 가져오세요.")
        if st.button("홈으로 이동", type="primary", use_container_width=True): _go("Home")
        return
    ids = [item["id"] for item in projects]
    current = st.session_state.get("active_project_id") if st.session_state.get("active_project_id") in ids else ids[0]
    selected = st.selectbox("프로젝트", ids, ids.index(current), format_func=lambda value:next(item["title"] for item in projects if item["id"] == value))
    st.session_state["active_project_id"] = selected
    item = _project(projects, selected)
    source = item.get("source") or {}
    source_label = {"signal_study": "릴스에서 발견한 아이디어", "competitor_signal": "참고 릴스", "original idea": "직접 만든 아이디어"}.get(source.get("type"), "직접 만든 아이디어")
    st.caption(f"{STAGE_NAMES.get(item.get('stage'), '아이디어')} · {source_label}" + (f" · @{source['username']}" if source.get("username") else ""))
    tabs = st.tabs(["프로젝트", "촬영", "분석", "게시", "라이브러리", "작업 현황"])
    with tabs[0]: _project_tab(item, ctx)
    with tabs[1]: _shoot_tab(item, ctx)
    with tabs[2]: _analyze_tab(item, ctx)
    with tabs[3]: _publish_tab(item, ctx)
    with tabs[4]:
        reels = ctx["load_user_reels"](ctx["business_type"])
        if reels: st.dataframe(pd.DataFrame(reels), use_container_width=True, hide_index=True)
        else: st.caption("저장한 영상이 아직 없어요.")
    with tabs[5]:
        jobs = ctx["list_jobs"]()
        if jobs: st.dataframe(pd.DataFrame(jobs), use_container_width=True, hide_index=True)
        else: st.caption("진행 중인 작업이 없어요.")


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
