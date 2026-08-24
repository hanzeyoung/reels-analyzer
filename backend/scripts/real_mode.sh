#!/bin/bash
# 실측(real API) 진입점. `.env`는 절대 건드리지 않는다 — 이 명령의 프로세스
# (및 그 자식 프로세스)에만 APIFY_MODE/VISION_MODE/WRITER_MODE=real을 준다.
#
# .env 파일을 손으로 real로 바꿔놓고 되돌리는 걸 잊으면, make dev(운영)와 pytest(테스트)가
# 같은 .env를 공유해서 테스트가 실제 API를 호출해버리는 사고가 난다(P6.5, 2026-08-24).
# 여기서는 `env`로 이 프로세스 트리에만 한정된 환경변수를 주기 때문에, 명령이 정상
# 종료하든 예외로 죽든 부모 셸의 환경과 .env는 처음부터 변경된 적이 없어 "원복"이라는
# 단계 자체가 필요 없다 — 프로세스가 끝나면 그 값도 함께 사라진다.
#
# 사용:
#   backend/scripts/real_mode.sh python3 some_real_check.py
#   backend/scripts/real_mode.sh uvicorn app.main:app --port 8000
#   backend/scripts/real_mode.sh make dev      # 자식 프로세스(uvicorn/worker/vite) 전부 상속
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "사용법: $0 <실행할 명령...>" >&2
    exit 1
fi

exec env APIFY_MODE=real VISION_MODE=real WRITER_MODE=real "$@"
