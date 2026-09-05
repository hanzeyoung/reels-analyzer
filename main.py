"""
main.py — 소상공인 릴스 분석 대시보드
실행: streamlit run main.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from pathlib import Path
import random
import os
import tempfile

from app.api.gemini import analyze_reel_from_file, format_report

st.set_page_config(page_title="릴스 성과 분석 | 부자", page_icon="🎬", layout="wide")

st.markdown("""
<style>
:root {
  --bg: #ffffff;
  --surface: #f6f8fb;
  --text: #172033;
  --muted: #5b6475;
  --border: #c9d2df;
  --accent: #2457d6;
  --accent-contrast: #ffffff;
  --success: #146c43;
  --warning: #8a5a00;
  --danger: #b42318;
  font-size: 16px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f141c;
    --surface: #171d27;
    --text: #eef3fb;
    --muted: #b8c1d1;
    --border: #3a4658;
    --accent: #8eb0ff;
    --accent-contrast: #08111f;
  }
}

html, body, [data-testid="stAppViewContainer"] {
  color: var(--text);
}

.block-container {
  max-width: 76rem;
  padding-top: 1.5rem;
  padding-bottom: 3rem;
}

h1 { font-size: clamp(1.75rem, 2vw, 2.25rem); line-height: 1.2; }
h2, h3 { line-height: 1.3; }

p, li, label, [data-testid="stMarkdownContainer"] {
  font-size: 1rem;
  line-height: 1.6;
}

button, [role="button"], input, textarea, select {
  min-height: 2.75rem;
  font-size: 1rem !important;
}

button:focus-visible,
[role="button"]:focus-visible,
input:focus-visible,
textarea:focus-visible,
select:focus-visible,
[data-baseweb="radio"] :focus-visible {
  outline: 0.1875rem solid var(--accent) !important;
  outline-offset: 0.1875rem !important;
  box-shadow: none !important;
}

.hook-tag {
  background: var(--surface);
  color: var(--accent);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.375rem 0.625rem;
  font-size: 0.9375rem;
  margin: 0.125rem;
  display: inline-block;
}

@media (max-width: 48rem) {
  .block-container {
    padding-left: 1rem;
    padding-right: 1rem;
  }

  [data-testid="column"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }

  [data-testid="stMetric"] {
    padding-block: 0.5rem;
  }
}
</style>
""", unsafe_allow_html=True)


# ── 목업 데이터 ───────────────────────────────
@st.cache_data
def get_mock_reels(btype: str) -> pd.DataFrame:
    random.seed(42)
    rows = []
    for i in range(20):
        v = random.randint(3000, 150000)
        l = int(v * random.uniform(0.02, 0.08))
        s = int(v * random.uniform(0.01, 0.05))
        sh = int(v * random.uniform(0.005, 0.02))
        norm = min((v * 0.2 + l * 0.3 + (s + sh) * 0.5) / 35000 * 100, 100)
        tier = "S" if norm >= 80 else ("A" if norm >= 60 else ("B" if norm >= 40 else "C"))
        rows.append({
            "릴스": f"reel_{i+1:03d}", "업종": btype, "조회수": v,
            "좋아요": l, "저장": s, "공유": sh, "총점": round(norm, 1), "등급": tier,
            "길이(초)": random.choice([15, 20, 30, 45, 60]),
            "촬영구도": random.choice(["탑뷰", "클로즈업", "팔로잉샷", "정면샷"]),
            "BGM": random.choice(["신나는", "감성적", "조용한"]),
            "업로드": datetime.now() - timedelta(days=random.randint(1, 60)),
        })
    return pd.DataFrame(rows).sort_values("총점", ascending=False).reset_index(drop=True)


# ── 사이드바 ──────────────────────────────────
MENU_OPTIONS = ["📊 대시보드", "🔍 릴스 분석", "📋 트렌드 리포트", "🎯 촬영 가이드"]
MAX_UPLOAD_MB = 200
PLOT_CONFIG = {"displaylogo": False, "responsive": True}
TIER_COLORS = {"S": "#7c5c00", "A": "#146c43", "B": "#2457d6", "C": "#b42318"}

with st.sidebar:
    st.markdown("## 🎬 릴스 분석")
    st.caption("소상공인을 위한 AI 릴스 가이드")
    st.divider()
    menu = st.radio(
        "주요 메뉴",
        MENU_OPTIONS,
        help="대시보드, 릴스 분석, 트렌드 리포트, 촬영 가이드 화면으로 이동합니다.",
    )
    st.divider()
    btype = st.selectbox(
        "내 업종",
        ["카페", "식당", "뷰티", "패션", "운동/헬스", "기타"],
        help="선택한 업종 기준으로 대시보드와 가이드를 조정합니다.",
    )
    st.divider()
    st.caption("🔴 Meta API: 미연동")
    st.caption("🟢 Gemini: 연결됨" if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") else "🔴 Gemini: 미연동")
    st.caption("🔴 Supabase: 미연동")
    st.caption("_API 키 설정 후 실 데이터 전환_")

df = get_mock_reels(btype)


def page_header(title: str, description: str = ""):
    page_name = menu.split(" ", 1)[1] if " " in menu else menu
    st.caption(f"현재 위치: 홈 / {page_name}")
    st.title(title)
    if description:
        st.caption(description)
    st.divider()


# ══════════════════════════════════════
# 📊 대시보드
# ══════════════════════════════════════
if menu == "📊 대시보드":
    page_header(
        f"📊 {btype} 릴스 성과 대시보드",
        "현재 목업 데이터입니다. Meta API 연동 후 실제 데이터로 전환됩니다.",
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("수집된 릴스", f"{len(df)}개", "+3 이번 주")
    c2.metric("평균 점수", f"{df['총점'].mean():.1f}점")
    c3.metric("S등급 릴스", f"{len(df[df['등급']=='S'])}개",
              f"전체의 {len(df[df['등급']=='S'])/len(df)*100:.0f}%")
    c4.metric("평균 조회수", f"{int(df['조회수'].mean()):,}")

    st.divider()
    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("점수 분포")
        st.caption(f"평균 점수는 {df['총점'].mean():.1f}점이며, 최고 점수는 {df['총점'].max():.1f}점입니다.")
        fig = px.histogram(df, x="총점", nbins=10, color_discrete_sequence=["#2457d6"],
                           labels={"총점": "성과 점수", "count": "릴스 수"}, title="릴스 성과 점수 분포")
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=280,
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(size=14))
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)

    with col2:
        st.subheader("등급별 현황")
        tc = df["등급"].value_counts().reindex(["S", "A", "B", "C"], fill_value=0)
        fig2 = px.pie(values=tc.values, names=tc.index, hole=0.5,
                      color=tc.index,
                      color_discrete_map=TIER_COLORS)
        fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=250,
                           paper_bgcolor="rgba(0,0,0,0)")
        st.caption("등급별 개수: " + ", ".join([f"{grade} {count}개" for grade, count in tc.items()]))
        st.plotly_chart(fig2, use_container_width=True, config=PLOT_CONFIG)

    st.divider()
    st.subheader("🏆 상위 10개 릴스")
    st.caption("총점이 높은 순서로 정렬된 릴스 목록입니다. 조회수, 저장, 공유 수를 함께 비교할 수 있습니다.")
    top = df.head(10)[["릴스", "총점", "등급", "조회수", "저장", "공유", "촬영구도", "길이(초)"]].copy()
    top["조회수"] = top["조회수"].apply(lambda x: f"{x:,}")
    st.dataframe(top, use_container_width=True, hide_index=True)


# ══════════════════════════════════════
# 🔍 릴스 분석
# ══════════════════════════════════════
elif menu == "🔍 릴스 분석":
    page_header(
        "🔍 AI 릴스 분석",
        "영상을 업로드하면 초반 후킹, 촬영 구도, 자막 위치, 색감을 분석합니다.",
    )

    tab1, tab2 = st.tabs(["📁 영상 업로드", "📂 내 릴스 목록"])

    with tab1:
        has_gemini_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        if has_gemini_key:
            st.success("Gemini API 연결됨")
        else:
            st.warning("Gemini API 키가 없어 실제 분석을 실행할 수 없습니다.")

        with st.form("reel_analysis_form", clear_on_submit=False):
            uploaded = st.file_uploader(
                "릴스 영상 파일",
                type=["mp4", "mov"],
                help="MP4 또는 MOV 형식의 릴스 영상을 업로드하세요.",
            )
            caption_input = st.text_area(
                "본문 캡션",
                height=120,
                placeholder="예: 성수동 신상 베이커리 카페, 갓 구운 소금빵이 나오는 장면...",
                help="캡션을 입력하면 후킹 문구와 저장 유도 패턴까지 함께 분석합니다.",
            )
            caption_len = len(caption_input.strip())
            uploaded_too_large = bool(uploaded and uploaded.size > MAX_UPLOAD_MB * 1024 * 1024)
            if uploaded:
                file_size_mb = uploaded.size / 1024 / 1024
                st.caption(f"업로드 파일: {uploaded.name} · {file_size_mb:.1f}MB")
                if uploaded_too_large:
                    st.error(f"파일이 너무 큽니다. {MAX_UPLOAD_MB}MB 이하 영상만 분석할 수 있습니다.")

            if caption_input and caption_len < 10:
                st.error("캡션이 너무 짧습니다. 최소 10자 이상 입력하면 분석 품질이 좋아집니다.")
            elif caption_input:
                st.caption(f"캡션 {caption_len}자 입력됨")

            submitted = st.form_submit_button(
                "AI 분석 시작",
                type="primary",
                use_container_width=True,
                disabled=not has_gemini_key or uploaded_too_large,
            )

        if uploaded:
            st.video(uploaded)

        if submitted:
            if not uploaded:
                st.error("영상을 먼저 업로드해주세요.")
            elif uploaded_too_large:
                st.error(f"파일이 너무 큽니다. {MAX_UPLOAD_MB}MB 이하 영상만 분석할 수 있습니다.")
            elif Path(uploaded.name).suffix.lower() not in [".mp4", ".mov"]:
                st.error("지원하지 않는 파일 형식입니다. MP4 또는 MOV 파일을 업로드해주세요.")
            elif caption_input and caption_len < 10:
                st.error("캡션을 입력하려면 최소 10자 이상 작성해주세요.")
            else:
                suffix = Path(uploaded.name).suffix or ".mp4"
                report_path = None
                tmp_path = None

                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uploaded.getbuffer())
                        tmp_path = tmp.name

                    with st.spinner("Gemini가 영상 프레임을 분석 중입니다..."):
                        analysis = analyze_reel_from_file(tmp_path, caption=caption_input)

                    report_text = format_report(analysis)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    reports_dir = Path("reports")
                    reports_dir.mkdir(exist_ok=True)
                    report_path = reports_dir / f"{timestamp}_{Path(uploaded.name).stem}_upload_report.md"
                    report_path.write_text(report_text, encoding="utf-8")

                    st.success("분석 완료")
                    r1, r2, r3 = st.columns(3)
                    r1.metric("사용 프레임", f"{analysis.get('frame_count', 0)}장")
                    r2.metric("자막 위치", analysis.get("subtitle_position", "-"))
                    r3.metric("색감", analysis.get("color_tone", "-"))

                    st.divider()
                    a1, a2 = st.columns(2)
                    with a1:
                        st.markdown("**📷 촬영 분석**")
                        st.markdown(
                            "\n".join([
                                f"- 구도: {', '.join(analysis.get('camera_angles', [])) or '-'}",
                                f"- 컷 속도: {analysis.get('cut_speed', '-')}",
                                f"- 첫 장면: {analysis.get('hook_text', '-')}",
                            ])
                        )
                    with a2:
                        st.markdown("**🎵 오디오/텍스트**")
                        st.markdown(
                            "\n".join([
                                f"- BGM: {analysis.get('bgm_mood', '-')}",
                                f"- 캡션 후킹: {', '.join(analysis.get('caption_hooks', [])) or '-'}",
                            ])
                        )

                    st.info(analysis.get("analysis_summary", "분석 요약을 생성하지 못했습니다."))
                    st.download_button(
                        "보고서 다운로드",
                        data=report_text,
                        file_name=report_path.name,
                        mime="text/markdown",
                        use_container_width=True,
                    )
                    st.caption(f"저장 위치: {report_path}")
                except Exception as exc:
                    st.error(f"분석 실패: {exc}")
                finally:
                    if tmp_path:
                        Path(tmp_path).unlink(missing_ok=True)

    with tab2:
        st.subheader(f"내 {btype} 릴스 목록")
        tier_filter = st.multiselect("등급 필터", ["S", "A", "B", "C"], default=["S", "A", "B", "C"])
        filtered = df[df["등급"].isin(tier_filter)]
        for _, row in filtered.head(8).iterrows():
            with st.expander(f"[{row['등급']}] {row['릴스']} — {row['총점']}점 | 조회수 {int(row['조회수']):,}"):
                cc1, cc2, cc3, cc4 = st.columns(4)
                cc1.metric("좋아요", f"{int(row['좋아요']):,}")
                cc2.metric("저장", f"{int(row['저장']):,}")
                cc3.metric("공유", f"{int(row['공유']):,}")
                cc4.metric("길이", f"{row['길이(초)']}초")
                st.markdown(f"촬영 구도: `{row['촬영구도']}` | BGM: `{row['BGM']}`")


# ══════════════════════════════════════
# 📋 트렌드 리포트
# ══════════════════════════════════════
elif menu == "📋 트렌드 리포트":
    page_header(
        f"📋 이번 주 {btype} 트렌드",
        f"기준: {datetime.now().strftime('%Y년 %m월 %d일')} | 상위 릴스 분석 기반",
    )

    f1, f2, f3 = st.columns(3)
    f1.metric("최적 영상 길이", "30~45초")
    f2.metric("인기 BGM", "신나는")
    f3.metric("평균 상위 점수", "78.4점")

    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("📷 인기 촬영 구도")
        ac = df["촬영구도"].value_counts()
        fig = px.bar(x=ac.index, y=ac.values, color_discrete_sequence=["#2457d6"],
                     labels={"x": "구도", "y": "등장 횟수"})
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=220,
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)

    with c2:
        st.subheader("🔖 인기 해시태그")
        for tag in ["#카페스타그램", "#소상공인", "#릴스", "#일상", "#맛집"]:
            st.markdown(f'<span class="hook-tag">{tag}</span>', unsafe_allow_html=True)
        st.markdown("")
        st.subheader("💬 후킹 패턴")
        for p in ["'주목!'으로 시작", "숫자 포함 문구", "궁금증 유발형"]:
            st.markdown(f"- {p}")

    st.divider()
    st.subheader("📈 점수 vs 조회수")
    fig3 = px.scatter(df, x="총점", y="조회수", color="등급", size="저장",
                      color_discrete_map=TIER_COLORS,
                      hover_data=["촬영구도", "길이(초)"])
    fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=300,
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.caption("점 하나는 릴스 1개입니다. 색상은 등급, 원 크기는 저장 수를 나타냅니다.")
    st.plotly_chart(fig3, use_container_width=True, config=PLOT_CONFIG)


# ══════════════════════════════════════
# 🎯 촬영 가이드
# ══════════════════════════════════════
elif menu == "🎯 촬영 가이드":
    page_header(
        "🎯 맞춤 촬영 가이드",
        f"업종: {btype} | 트렌드 분석 기반 자동 생성",
    )
    st.info("💡 Flux 1.1 Pro API 연동 시 구도 예시 이미지가 자동 생성됩니다.")

    g1, g2 = st.columns(2)

    with g1:
        st.subheader("📐 추천 촬영 구도")
        for name, desc in {
            "탑뷰 (Top View)": "음식·음료를 위에서 내려찍는 구도. 카페·식당에서 특히 효과적.",
            "클로즈업 (Close-Up)": "제품의 질감과 디테일 강조. 저장률을 높이는 구도.",
            "팔로잉샷 (Following Shot)": "움직임을 따라가는 구도. 체류 시간 증가에 효과적.",
        }.items():
            with st.expander(f"📷 {name}"):
                st.write(desc)
                st.caption("_구도 예시 이미지 — Flux API 연동 후 자동 생성됩니다_")

    with g2:
        st.subheader("✂️ 편집 가이드")
        st.markdown(f"""
**영상 길이**: 30~45초 권장

**컷 편집 리듬**
- 첫 3초: 후킹 장면 (멈추게 만들기)
- 3~10초: 핵심 내용 전달
- 10초~끝: 저장/팔로우 유도

**자막**
- 위치: 화면 하단 1/3 권장
- 색상: 밝은 배경엔 어두운 글씨

**BGM** ({btype} 추천)
- 신나는 비트 또는 감성 acoustic
- CapCut 인기 음원 탭 매주 확인
        """)

    st.divider()
    st.subheader("🔗 CapCut 템플릿 바로가기")
    t1, t2, t3 = st.columns(3)
    with t1:
        st.markdown("**탑뷰 스타일**")
        st.link_button("CapCut 열기 →", "https://www.capcut.com")
    with t2:
        st.markdown("**클로즈업 스타일**")
        st.link_button("CapCut 열기 →", "https://www.capcut.com")
    with t3:
        st.markdown("**감성 일상 스타일**")
        st.link_button("CapCut 열기 →", "https://www.capcut.com")
