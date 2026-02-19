# 진행 현황 (PROGRESS)

> 마지막 업데이트: 2026-02-19
> 현재 브랜치: `feature/lua-only-extension`

## 완료된 마일스톤

### M1: 초기 구현 (commit 95e57f9)
- Pandoc JSON AST → HWPX 변환기 최초 구현
- Python 기반 엔진
- 기본 블록/인라인 요소 처리

### M2: 프로젝트 구조 정리 (commit a63a9dd)
- 디렉토리 구조 재편성
- Tufte 스타일 README 작성
- 아키텍처 다이어그램 추가

### M3: Quarto 전용 인터페이스 (commit 26a3063)
- 독립 실행 CLI 제거
- Quarto extension 방식으로 전환
- `_extensions/hwpx/` 구조 확립
- `_extension.yml`: docx 포맷에 Lua 필터 등록

### M4: 순수 Lua 전환 (commit 2cc3cf6)
- Python 엔진 완전 제거
- `hwpx-filter.lua` 단일 파일로 전체 변환 엔진 구현 (~1500줄)
- Python/Pillow 의존성 제거
- PNG/JPEG 헤더를 Lua로 직접 파싱
- 시스템 `zip`/`unzip`만 필요

### M5: gt 테이블 호환성 (commit eced98b)
- OpenXML `<w:tbl>` RawBlock 파싱 → HWPX `<hp:tbl>` 변환
- R gt 패키지 출력을 HWPX 테이블로 변환
- HTML 테이블도 `pandoc.read(html)` 통해 변환

### M6: 기능 완성 5종 (현재)
- Figure 캡션: Quarto FloatRefTarget + Pandoc Figure 블록 처리
- Callout 블록: `__quarto_custom_type=Callout` → 배경색 1셀 테이블 렌더링
- 중첩 목록: 레벨별 마커 (●→○→■→▪) / 번호 (1.→가.→(1)→(가))
- Code-fold: `code-fold: true` 메타데이터 감지 → .cell-code Div 생략
- docx 최소화: 성공 시 `pandoc.Pandoc({})` 반환 → docx 10KB

## 현재 지원 기능

### 완전 동작
- [x] 마크다운 텍스트 (단락, 제목 H1~H6, 인용문, 목록)
- [x] 인라인 서식 (굵게, 기울임, 취소선, 밑줄, 위/아래첨자, 인라인 코드)
- [x] 하이퍼링크 (fieldBegin/End)
- [x] PNG/JPEG 이미지 (자동 크기 감지 + BinData 임베딩)
- [x] 코드 블록 (D2Coding 폰트)
- [x] LaTeX 수식 (인라인 + 디스플레이 → HWP 수식 스크립트)
- [x] 표 (rowspan/colspan, 헤더/바디)
- [x] 목차 (toc: true)
- [x] 참고문헌 (citeproc)
- [x] 각주 (footNote + subList)
- [x] R 코드 실행 결과 (knitr → 이미지/테이블)
- [x] Python 코드 실행 결과 (jupyter → 이미지/테이블)
- [x] gt 테이블 (OpenXML RawBlock 파싱)
- [x] ggplot2 그래프 (PNG 이미지 임베딩)
- [x] 메타데이터 (title, subtitle, author, date)
- [x] HTML 테이블 (pandoc.read 후 변환)
- [x] Figure 캡션 (Quarto FloatRefTarget + Pandoc Figure)
- [x] Callout 블록 (배경색 1셀 테이블, 좌측 색상 바)
- [x] 중첩 목록 (레벨별 마커/번호 + 들여쓰기)
- [x] Code-fold (code-fold: true → 코드 숨김)
- [x] docx 최소화 (빈 문서 반환)

### 부분 동작 / 제한사항
- [ ] Callout 타입별 색상: 현재 모든 callout이 note(파랑)로 통일 (Quarto가 타입 정보 소실)
- [ ] Mermaid 다이어그램: Quarto가 PNG로 렌더링하면 이미지로 포함 가능하나 최적화 필요
- [ ] 교차참조: `@fig-`, `@tbl-` 텍스트만 통과, 링크 없음

### 미지원
- [ ] 코드 구문 강조 (syntax highlighting)
- [ ] SVG/GIF/WebP 이미지
- [ ] 수식 번호
- [ ] 페이지 번호/머리글/바닥글 커스터마이징
- [ ] HWPX 테마/스타일 커스터마이징
- [ ] 탭셋, 레이아웃 컬럼

## 알려진 이슈
- `.docx` 파일이 중간 산출물로 생성되나 빈 문서 (10KB)로 최소화됨
- Quarto의 `__quarto_custom` 노드 시스템이 callout 타입 정보를 소실함
- 한글 Windows에서 일부 폰트 호환성 미확인
