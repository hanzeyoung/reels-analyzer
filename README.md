# 🎬 소상공인을 위한 AI 기반 릴스 성과 분석 플랫폼

> 팀명: **부자** | 조선대학교 SW중심대학사업 신기술SW창업프로젝트

---

## 현재 구현 기능

- 공개 릴스 수집, 키워드 관련성 필터링, 중복 제거와 성과 점수화
- 업로드 영상 전체 구간의 화면 변화량과 음량을 측정하고 훅, 정체 구간, 예상 이탈 시점 표시
- Gemini 의미 분석과 측정 신호를 합친 하이브리드 분석, 근거와 예측 신뢰도 표시
- Meta OAuth 또는 액세스 토큰으로 실제 조회, 도달, 저장, 공유, 시청시간 동기화
- 게시 전 AI 예상과 게시 후 실측 성과 비교, 계정별 예측 편향과 오차 보정
- 매장별 과거 성과를 누적해 구도, 길이, 훅, 업로드 시간 등의 상승 패턴 학습
- 분석 결과를 문제별 대본, 촬영 목록, 편집 지시, 휴대폰 촬영 코치로 연결
- 선택형 Supabase 이메일 로그인, 사용자별 로컬 라이브러리와 작업 소유권 분리
- 영상 분석 백그라운드 큐, 자동 재시도, 중복 방지, 실행 중 취소와 완료 결과 불러오기
- Meta 일일 자동 동기화 실행기, 사용자별 암호화 토큰 처리와 24시간·3일·7일 성과 변화 계산
- 경쟁 추적 재시도·실행 이력, 사용자별 알림 기준, 전송 이력과 Slack/Discord/일반 웹훅 중복 방지
- 음원 권리 증빙 파일·만료일 관리, 사용자 데이터 내보내기·삭제·보존 기간 정리
- Docker 앱·워커·Nginx 배포 구성, 구조화 로그·API 일일 한도, 앱 내 운영 현황판과 선택형 Sentry 연결
- 출처·Instagram 계정·기간별 성과 필터와 암호화 Meta OAuth 토큰 저장
- 지역·업종 공개 릴스의 경쟁 계정 스냅샷, 동일 게시물 성장량 비교와 주간 알림
- 비즈니스 사용 목적별 음원 위험 분류와 라이선스 증빙 기록

AI 점수와 예상 유지율은 예측값입니다. 앱은 이를 Instagram의 실제 유지율처럼 표현하지 않으며, Meta 계정에서 동기화한 값만 실측으로 표시합니다.

## 실사용 전 준비

1. `.env.example`을 `.env`로 복사하고 Gemini, Meta, Supabase 값을 입력합니다.
2. Meta 앱에 `META_REDIRECT_URI`와 Instagram 로그인 권한을 등록합니다.
3. Supabase SQL Editor에서 `sql/schema.sql`을 실행합니다.
4. 휴대폰 카메라 코치는 HTTPS 주소로 배포한 뒤 `MOBILE_COACH_BASE_URL`을 설정합니다.
   프로젝트의 촬영 목록·피사체 위치·자막이 QR 링크로 전달되며, 휴대폰에서 컷별 녹화 후 파일을 저장하거나 공유할 수 있습니다.
5. 경쟁 추적 알림을 받을 경우 `MARKET_ALERT_WEBHOOK_URL`을 설정하고 주간 작업을 설치합니다.

상세한 로컬 실행과 검증 절차는 `DEVELOPMENT.md`를 참고하세요.

### 로그인과 비회원 모드

- **비회원**도 홈, 릴스 검색, 설정을 볼 수 있습니다. 스튜디오·인사이트·플레이북·새 프로젝트·릴스 분석처럼 **회원 단위로 저장되는 기능**을 누르면 로그인 팝업이 뜹니다.
- 회원 데이터는 로그인 아이디별 폴더(`user_reels/<해시>/`)에 따로 저장됩니다. 비회원의 임시 데이터는 세션별 폴더(`user_reels/guests/`)에 두고 하루 뒤 정리합니다.
- 계정: Supabase가 설정돼 있으면 Supabase, 없으면 내장 이메일 계정(`user_reels/accounts.json`, 비밀번호는 scrypt 해시, 5회 실패 시 5분 잠금)을 사용합니다.
- 로그인 도입 전에 만든 데이터는 `python scripts/adopt_legacy_data.py 이메일` (미리보기) 후 `--apply`로 계정에 복사합니다. 원본은 지우지 않습니다.

| 환경변수 | 기본값 | 의미 |
|---|---|---|
| `LOGIN_ENABLED` | `true` | `false`면 로그인·비회원 구분 없이 예전처럼 동작 |
| `REQUIRE_APP_LOGIN` | `false` | `true`면 앱 전체를 로그인 필수로 막음 |
| `AUTH_BACKEND` | 자동 | `local` 또는 `supabase`로 강제 선택 |
| `ADMIN_MODE` | `false` | `true`면 설정에서 서비스별 필요 환경변수 이름과 시스템 현황 표시(운영자용) |

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
│   │   ├── scoring.py              # 성과 스코어링 알고리즘
│   │   ├── performance_insights.py # 실측 지표 정규화와 예측 비교
│   │   ├── creator_memory.py       # 개인 성공 패턴 학습
│   │   ├── market_watch.py         # 지역·경쟁 스냅샷
│   │   ├── audio_rights.py         # 음원 권리 확인 상태
│   │   └── timeline_analyzer.py     # 영상·음성 신호 기반 타임라인
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

```powershell
.\scripts\run_app.ps1
```

기본 앱 주소는 `http://127.0.0.1:8501`, 모바일 코치 정적 서버는 `http://127.0.0.1:8502/mobile-coach.html`입니다.

### 5. 주간 경쟁 추적

앱에서 추적 조건을 저장한 뒤 관리자 권한 PowerShell에서 아래 스크립트를 한 번 실행합니다.

```powershell
.\scripts\install_weekly_watch_task.ps1
```

기본 실행 시각은 매주 월요일 오전 9시입니다. 설치하지 않고 바로 시험하려면 `.\scripts\run_weekly_market_watch.ps1`을 실행합니다.

### 6. 백그라운드 분석과 Meta 자동 동기화

`run_app.ps1`은 영상 분석 워커를 함께 실행합니다. 워커만 실행하려면 다음 명령을 사용합니다.

```powershell
.\scripts\run_job_worker.ps1
```

장기 Meta 토큰을 `.env`에 설정한 뒤 일일 동기화 작업을 설치할 수 있습니다.

```powershell
.\scripts\install_meta_sync_task.ps1
```

로그인을 필수화하려면 Supabase Auth 이메일 로그인을 활성화한 뒤 `.env`에 `REQUIRE_APP_LOGIN=true`를 설정합니다.
OAuth 토큰을 재시작 뒤에도 유지하려면 Fernet 키를 생성해 서버의 `META_TOKEN_ENCRYPTION_KEY`에 설정합니다. 키가 없으면 토큰은 현재 앱 세션에만 남습니다.

Docker가 설치된 운영 환경에서는 `docker compose up -d --build`로 앱, 분석 워커, 모바일 코치 게이트웨이를 함께 실행할 수 있습니다. 실제 HTTPS는 운영 도메인의 TLS 프록시 또는 호스팅 플랫폼에서 종료해야 합니다.

### 7. 검증

```powershell
.\scripts\run_env_check.ps1
.\scripts\run_tests.ps1
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
