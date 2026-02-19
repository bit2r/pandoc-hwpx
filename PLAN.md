# 개발 계획 (PLAN)

> 마지막 업데이트: 2026-02-19
> 목표: Quarto의 모든 주요 기능이 HWPX 출력에서 HTML/PDF/DOCX 수준으로 동작

## Phase 1: 핵심 품질 개선 (우선순위 높음)

### 1.1 Figure 캡션 지원
- **파일**: `hwpx-filter.lua` PART 13 (Block Processing)
- **작업**: `Image` 블록 처리 시 `fig-cap` 메타데이터를 읽어 이미지 아래에 캡션 단락 추가
- **관련 Pandoc AST**: `Para > Image(caption, src, attr)`에서 caption 추출
- **예상 난이도**: 낮음

### 1.2 교차참조 (Cross-reference) 텍스트 처리
- **파일**: `hwpx-filter.lua` PART 12 (Inline Processing)
- **작업**: Quarto 교차참조가 citeproc 이후 `Link` 또는 텍스트로 변환됨 → 적절한 텍스트 렌더링
- **참고**: Quarto의 `@fig-xxx`, `@tbl-xxx`, `@eq-xxx`는 Pandoc 처리 후 보통 텍스트/링크로 전달됨
- **예상 난이도**: 중간

### 1.3 Callout 블록 스타일링
- **파일**: `hwpx-filter.lua` PART 13 (Block Processing) — `Div` 처리 분기
- **작업**: `.callout-note`, `.callout-warning` 등 Quarto Div 클래스 감지 → 배경색 borderFill + 아이콘 텍스트 + 제목 스타일
- **관련 HWPX**: `<hh:borderFill>` 배경색, charPr 색상/굵기
- **예상 난이도**: 중간

### 1.4 중첩 목록 개선
- **파일**: `hwpx-filter.lua` PART 13 — `handle_bullet_list`, `handle_ordered_list`
- **작업**: indent_level에 따른 기호 변경 (●→○→■), 번호 체계 (1→가→(1))
- **예상 난이도**: 낮음

## Phase 2: 이미지/다이어그램 확장

### 2.1 SVG 이미지 지원
- **파일**: `hwpx-filter.lua` PART 4 (Image Dimension Reader) + PART 11 (Image Handling)
- **작업**: SVG 파일의 width/height 속성 파싱, HWPX에 PNG 변환 후 임베딩 또는 SVG 직접 임베딩 검토
- **의존성**: HWPX가 SVG를 지원하는지 확인 필요 (안 하면 래스터 변환 필요)
- **예상 난이도**: 높음

### 2.2 Mermaid 다이어그램 최적화
- **작업**: Quarto의 mermaid 블록 → PNG/SVG 출력 경로 확인 → 이미지 크기 최적화
- **참고**: Quarto가 자동으로 `mermaid-figure/` 디렉토리에 이미지 생성
- **예상 난이도**: 중간

### 2.3 GIF/WebP/BMP 이미지 지원
- **파일**: `hwpx-filter.lua` PART 4
- **작업**: GIF 헤더 파싱 (6+4 bytes), WebP RIFF 파싱, BMP 헤더 파싱
- **예상 난이도**: 낮음

## Phase 3: 코드 표현 강화

### 3.1 코드 구문 강조 (Syntax Highlighting)
- **파일**: `hwpx-filter.lua` PART 13 — `handle_code_block`
- **작업**: Pandoc의 `CodeBlock` attr에서 언어 정보 추출 → 키워드/문자열/주석 패턴 매칭 → 색상별 charPr 생성
- **접근법 A**: 간단한 정규식 기반 하이라이팅 (키워드=파랑, 문자열=초록, 주석=회색)
- **접근법 B**: Pandoc의 `--highlight-style` 출력 파싱
- **예상 난이도**: 높음

### 3.2 코드 접기 (code-fold) 지원
- **작업**: `code-fold: true` 설정 시 코드 블록을 건너뛰고 결과만 렌더링
- **참고**: HWPX는 접기/펼치기 기능이 없으므로 숨김 처리가 합리적
- **예상 난이도**: 낮음

## Phase 4: 문서 구조 고도화

### 4.1 페이지 번호/머리글/바닥글
- **파일**: `hwpx-filter.lua` PART 15 (XML Assembly)
- **작업**: HWPX 템플릿의 `<hp:headerFooter>` 영역에 페이지 번호, 커스텀 텍스트 삽입
- **메타데이터**: `header-text`, `footer-text` 등 YAML 옵션 추가
- **예상 난이도**: 중간

### 4.2 수식 번호
- **파일**: `hwpx-filter.lua` PART 5 (Math Converter) + PART 12 (Inline Processing)
- **작업**: `$$...$$` 디스플레이 수식에 자동 번호 부여 → 우측 정렬 `(1)` 형태
- **예상 난이도**: 중간

### 4.3 HWPX 테마/스타일 커스터마이징
- **작업**: 사용자가 YAML에서 폰트, 크기, 여백 등을 지정할 수 있도록
- **구현**: `doc.meta`에서 설정 읽기 → `LANG_FONT_MAP`, `CHAR_HEIGHT_MAP` 등 동적 재설정
- **예상 난이도**: 중간

## Phase 5: docx 중간 산출물 정리

### 5.1 docx 파일 자동 정리
- **현상**: hwpx 생성 후 중간 산출물인 .docx가 남음
- **해결 방안**: Lua 필터에서 Pandoc 완료 후 .docx 삭제, 또는 Quarto post-render 스크립트
- **주의**: Quarto 파이프라인과 충돌하지 않도록 주의
- **예상 난이도**: 낮음

### 5.2 독립 포맷 등록 검토
- **장기 목표**: `hwpx`가 아닌 `hwpx`로 직접 등록
- **제약**: Quarto custom format은 기존 Pandoc writer(html, docx, pdf 등)를 base로 해야 함
- **대안**: Pandoc custom writer (`Writer(doc, opts)`) 사용 가능성 검토
- **예상 난이도**: 높음

## 우선순위 요약

| 순위 | 작업 | 난이도 | 영향도 |
|---|---|---|---|
| 1 | Figure 캡션 | 낮음 | 높음 — 그림 캡션은 보고서 필수 |
| 2 | Callout 블록 | 중간 | 높음 — Quarto 핵심 기능 |
| 3 | 중첩 목록 개선 | 낮음 | 중간 |
| 4 | 교차참조 텍스트 | 중간 | 높음 — 학술/기술 문서 필수 |
| 5 | 코드 접기 | 낮음 | 중간 |
| 6 | 수식 번호 | 중간 | 중간 |
| 7 | 페이지 번호/머리글 | 중간 | 중간 |
| 8 | SVG 이미지 | 높음 | 중간 |
| 9 | 구문 강조 | 높음 | 낮음 — 코드 중심 문서가 아니면 |
| 10 | docx 정리 | 낮음 | 낮음 — 사용성 개선 |

## 작업 규칙

1. 모든 변경은 `hwpx-filter.lua` 단일 파일 내에서 수행 (모놀리식 구조 유지)
2. 새 기능 추가 시 `examples/example.qmd`에 해당 Quarto 기능 예제 추가
3. 변경 후 `quarto render examples/example.qmd --to hwpx`로 테스트
4. 한글 프로그램에서 `.hwpx` 파일 열림 확인
5. 외부 의존성 추가 금지 (순수 Lua + 시스템 zip/unzip만 허용)
