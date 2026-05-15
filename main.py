"""
main.py — 소상공인 릴스 분석 대시보드
실행: streamlit run main.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import random, time

st.set_page_config(page_title="릴스 성과 분석 | 부자", page_icon="🎬", layout="wide")

st.markdown("""
<style>
.hook-tag { background:#e7f3ff; color:#1a56db; border-radius:20px;
            padding:3px 12px; font-size:13px; margin:2px; display:inline-block; }
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
with st.sidebar:
    st.markdown("## 🎬 릴스 분석")
    st.caption("소상공인을 위한 AI 릴스 가이드")
    st.divider()
    menu = st.radio("메뉴", ["📊 대시보드", "🔍 릴스 분석", "📋 트렌드 리포트", "🎯 촬영 가이드"],
                    label_visibility="collapsed")
    st.divider()
    btype = st.selectbox("내 업종", ["카페", "식당", "뷰티", "패션", "운동/헬스", "기타"])
    st.divider()
    st.caption("🔴 Meta API: 미연동")
    st.caption("🔴 Gemini: 미연동")
    st.caption("🔴 Supabase: 미연동")
    st.caption("_API 키 설정 후 실 데이터 전환_")

df = get_mock_reels(btype)


# ══════════════════════════════════════
# 📊 대시보드
# ══════════════════════════════════════
if menu == "📊 대시보드":
    st.title(f"📊 {btype} 릴스 성과 대시보드")
    st.caption("⚠️ 현재 목업 데이터입니다. Meta API 연동 후 실제 데이터로 전환됩니다.")

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
        fig = px.histogram(df, x="총점", nbins=10, color_discrete_sequence=["#4F7FFA"],
                           labels={"총점": "성과 점수", "count": "릴스 수"})
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=250,
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("등급별 현황")
        tc = df["등급"].value_counts().reindex(["S", "A", "B", "C"], fill_value=0)
        fig2 = px.pie(values=tc.values, names=tc.index, hole=0.5,
                      color=tc.index,
                      color_discrete_map={"S":"#ffc107","A":"#28a745","B":"#007bff","C":"#dc3545"})
        fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=250,
                           paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("🏆 상위 10개 릴스")
    top = df.head(10)[["릴스", "총점", "등급", "조회수", "저장", "공유", "촬영구도", "길이(초)"]].copy()
    top["조회수"] = top["조회수"].apply(lambda x: f"{x:,}")
    st.dataframe(top, use_container_width=True, hide_index=True)


# ══════════════════════════════════════
# 🔍 릴스 분석
# ══════════════════════════════════════
elif menu == "🔍 릴스 분석":
    st.title("🔍 AI 릴스 분석")

    tab1, tab2 = st.tabs(["📁 영상 업로드", "📂 내 릴스 목록"])

    with tab1:
        st.info("💡 `.env`에 `GEMINI_API_KEY` 설정 시 실제 AI 분석이 시작됩니다.")
        col1, col2 = st.columns(2)
        with col1:
            uploaded = st.file_uploader("릴스 영상 업로드 (.mp4)", type=["mp4", "mov"])
            caption_input = st.text_area("본문 캡션 (선택)", height=100,
                                         placeholder="☕ 카페 사장님들 주목! ...")
        with col2:
            if uploaded:
                st.video(uploaded)

        if st.button("🤖 AI 분석 시작", type="primary", use_container_width=True):
            if not uploaded:
                st.warning("영상을 먼저 업로드해주세요.")
            else:
                with st.spinner("Gemini가 영상을 분석 중입니다..."):
                    time.sleep(1.5)
                st.success("분석 완료! (목업 결과)")
                r1, r2, r3 = st.columns(3)
                r1.metric("예측 점수", "72.4점")
                r2.metric("등급", "A")
                r3.metric("예상 조회수", "2만~5만")
                st.divider()
                a1, a2 = st.columns(2)
                with a1:
                    st.markdown("**📷 촬영 분석**")
                    st.markdown("- 구도: 탑뷰, 클로즈업\n- 컷 속도: 빠름\n- 자막: 하단\n- 색감: 따뜻함")
                with a2:
                    st.markdown("**🎵 오디오/텍스트**")
                    st.markdown("- BGM: 신나는\n- 후킹 패턴: 숫자 포함 문구")
                    st.info("첫 3초 후킹과 탑뷰 구도가 이 업종에서 효과적입니다. "
                            "저장 유도 문구를 캡션에 추가하면 점수가 더 올라갈 수 있어요!")

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
    st.title(f"📋 이번 주 {btype} 트렌드")
    st.caption(f"기준: {datetime.now().strftime('%Y년 %m월 %d일')} | 상위 릴스 분석 기반")

    f1, f2, f3 = st.columns(3)
    f1.metric("최적 영상 길이", "30~45초")
    f2.metric("인기 BGM", "신나는")
    f3.metric("평균 상위 점수", "78.4점")

    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("📷 인기 촬영 구도")
        ac = df["촬영구도"].value_counts()
        fig = px.bar(x=ac.index, y=ac.values, color_discrete_sequence=["#4F7FFA"],
                     labels={"x": "구도", "y": "등장 횟수"})
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=220,
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

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
                      color_discrete_map={"S":"#ffc107","A":"#28a745","B":"#007bff","C":"#dc3545"},
                      hover_data=["촬영구도", "길이(초)"])
    fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=300,
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════
# 🎯 촬영 가이드
# ══════════════════════════════════════
elif menu == "🎯 촬영 가이드":
    st.title("🎯 맞춤 촬영 가이드")
    st.caption(f"업종: {btype} | 트렌드 분석 기반 자동 생성")
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
