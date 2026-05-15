# 🎬 소상공인을 위한 AI 기반 릴스 성과 분석 플랫폼

> 팀명: **부자** | 조선대학교 SW중심대학사업 신기술SW창업프로젝트

---

## 📁 폴더 구조

```
reels-analyzer/
├── main.py                  # Streamlit 앱 진입점
├── requirements.txt
├── .env.example             # 환경변수 템플릿 (복사 후 .env로 사용)
├── .gitignore
├── app/
│   ├── api/
│   │   ├── meta_graph.py    # Meta Graph API (인스타그램 데이터 수집)
│   │   └── gemini.py        # Gemini 1.5 Pro (멀티모달 분석)
│   ├── core/
│   │   └── scoring.py       # 성과 스코어링 알고리즘
│   └── db/
│       └── supabase_client.py  # Supabase DB 연결 및 CRUD
├── sql/
│   └── schema.sql           # DB 테이블 생성 스크립트
└── docs/
```

---

## 🚀 시작하기

### 1. 레포 클론 & 가상환경

```bash
git clone https://github.com/your-org/reels-analyzer.git
cd reels-analyzer

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열어서 API 키들 입력
```

### 3. Supabase DB 세팅

1. [supabase.com](https://supabase.com) 접속 → 새 프로젝트 생성
2. SQL Editor → `sql/schema.sql` 내용 전체 복붙 → Run
3. `.env`에 `SUPABASE_URL`, `SUPABASE_ANON_KEY` 입력

### 4. 앱 실행

```bash
streamlit run main.py
```

---

## 🔑 필요한 API 키

| 서비스 | 용도 | 발급처 |
|--------|------|--------|
| Meta Graph API | 인스타그램 릴스 수집 | [developers.facebook.com](https://developers.facebook.com) |
| Google Gemini | 멀티모달 영상 분석 | [aistudio.google.com](https://aistudio.google.com) |
| Supabase | 데이터베이스 | [supabase.com](https://supabase.com) |
| BFL (Flux 1.1 Pro) | 가이드 이미지 생성 | [api.bfl.ml](https://api.bfl.ml) |
| ElevenLabs | AI 음성 나레이션 | [elevenlabs.io](https://elevenlabs.io) |

---

## ⚙️ 스코어링 알고리즘

```
총점 = (조회수 × 0.2) + (좋아요 × 0.3) + (저장+공유 × 0.5)
```

| 등급 | 점수 |
|------|------|
| S | 80점 이상 |
| A | 60~79점 |
| B | 40~59점 |
| C | 40점 미만 |

---

## 👥 팀원 역할

| 이름 | 역할 |
|------|------|
| 한재영 | 메인 개발 / Meta Graph API / 백엔드 로직 |
| 진정민 | 프론트엔드 / Streamlit 대시보드 / 데이터 시각화 |
| 박진서 | DB 설계 / SQL / Supabase |
| 김시윤 | 아이디어 기획 / UX 설계 / UI 디자인 / DB 보조 |
