# Reels-analyzer — iOS 디자인 리디자인

## 문제와 방향

기존 화면은 큰 설정 버튼, 같은 무게로 반복되는 지표, 한영 혼용 문구 때문에 다음 행동이 잘 보이지 않았다. 앱 모드도 웹 화면을 좁힌 배치에 가까웠다. 리디자인의 목표는 **다음에 할 일을 먼저 보여주고, 조작과 콘텐츠의 계층을 구분하는 것**이다.

## 조사한 원칙 → 구현

| Apple의 기준 | Reels-analyzer에 적용한 결정 |
| --- | --- |
| [Typography](https://developer.apple.com/design/human-interface-guidelines/typography): 크기·굵기·색으로 계층 구성, 적은 수의 글꼴 사용 | 큰 제목 34px, 섹션 22px, 본문 16px, 보조 문구 13px. 과도한 대문자·자간·초굵은 글자 제거. 제목은 짧고 본문은 읽기 편한 줄 간격 적용. |
| [Materials](https://developer.apple.com/design/human-interface-guidelines/materials): 반투명 소재는 조작·내비게이션 계층에 집중 | 사이드바와 앱 하단 탭에만 블러 적용. 콘텐츠는 불투명한 그룹형 표면. 웹의 블러로 원칙을 해석한 것이며 네이티브 Liquid Glass 구현은 아님. |
| [Tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars): 지속적으로 보이는 이동, 아이콘과 짧은 이름 | 앱에 홈·발견·스튜디오·인사이트·플레이북 5개 고정 탭. 설정은 상단. 웹에서는 같은 목적지를 사이드바로 표시. |
| [Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons): 주 행동을 강조하고 충분한 터치 영역 제공 | 대부분의 조작을 44px 이상으로 설계. 한 화면의 다음 행동에 파란색 사용. 키보드 포커스·누름·비활성 상태 정의. Apple의 pt 기준을 웹 CSS px로 해석한 값이며 물리적으로 동일하다고 가정하지 않음. |
| [Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode): 배경과 전경의 계층·대비 유지 | 검정 바탕, 단계별 회색 표면, 밝은 보조 글자로 별도 구성. 사용자가 요청한 명시적 테마 전환 버튼을 유지. |

## 타이포그래피와 디테일

- Apple 기기는 `-apple-system`, `BlinkMacSystemFont`, `Apple SD Gothic Neo` 등 기기에 설치된 시스템 글꼴 사용. SF 폰트를 임의로 배포하지 않는다.
- 비 Apple 환경은 `Noto Sans CJK KR`, `Noto Sans KR`, OS sans-serif로 대체한다. 네트워크 폰트 다운로드 없이 한글 표시.
- 한글은 단어 단위 줄바꿈을 우선하되, 긴 프로젝트명도 화면 밖으로 넘치지 않게 처리한다.
- 지표 숫자는 같은 폭 숫자와 절제된 굵기, 설명은 낮은 강조도 사용.
- 아이콘은 24×24 기준의 일관된 직접 제작 SVG. SF Symbols 파일을 복제하지 않는다.
- 접근성 설정의 동작 줄이기·투명도 줄이기를 지원하는 CSS 제공. 키보드 포커스 표시와 작은 화면 재배치를 유지한다.

## 정보 구조

홈: **다음 프로젝트 행동 → 주간 목표 → 제작 현황 → 최근 프로젝트 / 발견**. 주간 목표 수정은 접힌 설정으로 이동. 새 프로젝트는 요청할 때 폼을 열고, 기존 프로젝트는 바로 이어서 작업한다. 실제 프로젝트 데이터와 성과만 사용하며, 자료가 없는 화면에는 설명과 다음 행동을 제공한다.

설정: 연결 상태를 그룹형 목록으로 표시. 폼·탭·입력·메뉴·분석 그래프를 같은 토큰으로 통일한다. 앱 화면과 테마는 세션·URL에 유지한다.

## 구현 범위

Streamlit 웹 UI에 iOS 원칙을 적용했다. 네이티브 앱, Dynamic Type, 시스템 SF Symbols 또는 실제 Liquid Glass 렌더러를 제공하는 것은 아니다. 시스템 글꼴은 OS별로 다르다. Streamlit 데이터 테이블 내부 캔버스는 프레임워크 테마의 영향을 받으며, 이번 CSS 테마로 모든 내부 픽셀까지 바꾸지는 않는다.
