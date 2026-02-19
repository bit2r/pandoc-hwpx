# pandoc-hwpx

**Quarto의 HWPX 출력 포맷** — HTML, PDF, DOCX처럼 HWPX를 Quarto의 일급(first-class) 출력 포맷으로 만드는 프로젝트.

## 프로젝트 비전

Quarto에서 `.qmd` 문서를 작성하면 `html`, `pdf`, `docx`로 렌더링하듯이 **`hwpx`로도 동일하게 렌더링**할 수 있어야 한다.
사용자가 Quarto의 모든 기능(마크다운, LaTeX 수식, R/Python 코드 실행, Mermaid 다이어그램, 참고문헌, 교차참조 등)을 그대로 활용하면서, 출력 포맷만 HWPX로 바꾸면 한글 문서가 생성된다.

```yaml
# 사용자가 할 일은 출력 포맷만 바꾸는 것
format:
  hwpx-docx:    # ← 이것만 바꾸면 한글 문서 생성
    toc: true
    bibliography: references.bib
```

## Quarto 기능 지원 현황

### 완전 지원 (Fully Supported)

| Quarto 기능 | 구현 방식 |
|---|---|
| **마크다운 텍스트** | 단락, 제목(H1~H6), 인용문, 수평선, 정의 목록, 줄 블록 |
| **인라인 서식** | **굵게**, *기울임*, ~~취소선~~, 밑줄, 위첨자, 아래첨자, `인라인 코드` |
| **링크** | `fieldBegin/fieldEnd` 하이퍼링크 |
| **이미지** | PNG/JPEG 자동 크기 감지, BinData 임베딩, 크기 지정 지원 |
| **코드 블록** | 구문 강조 없이 D2Coding 폰트로 렌더링 |
| **수식 (LaTeX)** | `$...$` 인라인 및 `$$...$$` 디스플레이 수식 → HWP 수식 스크립트 |
| **표 (Table)** | rowspan/colspan, 헤더/바디/푸터, 캡션 |
| **목차 (TOC)** | `toc: true` 메타데이터 감지 → 목차 자동 생성 |
| **참고문헌 (Citation)** | `citeproc` 실행 → 본문 인용 및 참고문헌 목록 |
| **각주 (Footnote)** | `<hp:footNote>` + `<hp:subList>` |
| **R 코드 실행** | Quarto의 knitr 엔진이 코드 실행 → 결과(표/그림)를 HWPX에 포함 |
| **Python 코드 실행** | Quarto의 jupyter 엔진이 코드 실행 → 결과를 HWPX에 포함 |
| **gt 테이블 (R)** | OpenXML `<w:tbl>` RawBlock 파싱 → HWPX `<hp:tbl>` 변환 |
| **ggplot2 그래프 (R)** | PNG 이미지로 렌더링 → 이미지 임베딩 |
| **메타데이터** | title, subtitle, author, date → 제목 블록 및 문서 속성 |
| **순서/비순서 목록** | 레벨별 번호/기호 (●→○→■→▪, 1.→가.→(1)→(가)) |
| **Callout 블록** | `__quarto_custom_type=Callout` → 배경색 1셀 테이블 렌더링 |
| **Figure 캡션** | Quarto FloatRefTarget + Pandoc Figure → 콘텐츠+캡션 |
| **코드 접기 (code-fold)** | `code-fold: true` 메타데이터 감지 → .cell-code Div 생략 |
| **docx 최소화** | HWPX 성공 시 빈 pandoc.Pandoc({}) 반환 → docx 10KB |
| **인용부호** | 유니코드 스마트 따옴표 |
| **HTML 테이블** | `pandoc.read(html)` 파싱 후 HWPX 변환 |

### 미지원 / 개선 필요 (TODO)

| Quarto 기능 | 현재 상태 | 목표 |
|---|---|---|
| **Mermaid 다이어그램** | Quarto가 SVG/PNG로 렌더링하면 이미지로 포함 가능 | SVG 지원, 자동 크기 최적화 |
| **교차참조 (Cross-ref)** | `@fig-`, `@tbl-`, `@eq-` 텍스트만 통과 | 한글 문서 내 상호참조 링크 |
| **코드 구문 강조** | 단색 D2Coding 렌더링 | 키워드별 색상 charPr 매핑 |
| **Callout 타입별 색상** | 모든 callout이 note(파랑)로 통일 | 5가지 타입별 색상 구분 |
| **탭셋 (Tabset)** | 지원 안됨 | 선택적 콘텐츠 또는 순차 렌더링 |
| **레이아웃 컬럼** | 지원 안됨 | 다단 레이아웃 |
| **Observable JS** | 지원 안됨 (동적 콘텐츠) | 정적 스냅샷 렌더링 |
| **테마/스타일** | 고정 폰트/크기 | 사용자 정의 HWPX 테마 지원 |
| **페이지 번호/머리글** | 템플릿 기본값 사용 | 사용자 정의 머리글/바닥글 |
| **SVG 이미지** | 미지원 | SVG 헤더 파싱 또는 래스터 변환 |
| **GIF/WebP 이미지** | 미지원 | 포맷 확장 |
| **수식 번호** | 미지원 | 디스플레이 수식 자동 번호 |
| **figure 교차참조 라벨** | 캡션은 출력되나 @fig- 라벨 미연결 | 상호참조 링크 |

## 프로젝트 구조

```
pandoc-hwpx/
├── _extensions/hwpx/             # Quarto extension (quarto add 대상)
│   ├── _extension.yml           # format: hwpx (docx 기반 커스텀 포맷)
│   ├── hwpx-filter.lua          # 전체 변환 엔진 (순수 Lua, ~1500줄)
│   └── templates/
│       ├── blank.hwpx           # 기본 HWPX 템플릿 (ZIP 아카이브)
│       └── fonts/               # 번들 폰트 파일
├── examples/                     # 예제/테스트 문서
│   ├── example.qmd              # 종합 예제 (R코드, gt, ggplot2, 수식, 인용)
│   ├── references.bib           # 참고문헌
│   └── _quarto.yml              # 예제용 Quarto 설정
├── tests/
│   └── fixtures/                # 테스트 문서
├── CLAUDE.md                    # 이 파일 (프로젝트 가이드)
└── README.md
```

## 설치 및 사용법

```bash
# 설치
quarto add bit2r/pandoc-hwpx

# 렌더링
quarto render example.qmd --to hwpx
```

```yaml
# _quarto.yml
format:
  hwpx:
    toc: true
    bibliography: references.bib
```

## 아키텍처

```
.qmd → Quarto(knitr/jupyter) → Pandoc AST → Lua Filter → .hwpx
         코드 실행                  citeproc      XML 생성
         그림/표 생성               TOC 감지      ZIP 패키징
```

**핵심 원리**: Quarto가 코드를 실행하고 Pandoc AST를 만들면, Lua 필터가 AST를 HWPX XML로 변환한다.
R/Python 코드 실행은 Quarto 엔진(knitr/jupyter)이 담당하므로 Lua 필터는 실행 결과만 처리한다.
이것이 HTML/PDF/DOCX와 동일한 파이프라인을 공유하는 방식이다.

### Pandoc AST → HWPX 변환 흐름

1. **Quarto 전처리**: `.qmd` → R/Python 코드 실행 → 마크다운 + 이미지/테이블 결과
2. **Pandoc 파싱**: 마크다운 → Pandoc AST (블록/인라인 트리)
3. **citeproc**: 참고문헌 처리 (`@citation` → 인용 텍스트 + 참고문헌 목록)
4. **Lua Filter (`hwpx-filter.lua`)**: AST 순회 → HWPX XML 생성
5. **ZIP 패키징**: 템플릿 HWPX에 section0.xml, header.xml, content.hpf 교체 → `.hwpx`

### hwpx-filter.lua 구조

```
hwpx-filter.lua (~1500줄)
├── PART 1:  Constants/Config        # 폰트 매핑, 스타일 ID, 레이아웃 상수
├── PART 2:  State                   # 단락 ID, charPr 캐시, 이미지 목록
├── PART 3:  Utility Functions       # xml_escape, file I/O, shell helpers
├── PART 4:  Image Dimension Reader  # PNG/JPEG 헤더 파싱 (Pillow 대체)
├── PART 5:  Math Converter          # LaTeX → HWP 수식 스크립트
├── PART 6:  Lineseg Calculator      # 텍스트 줄바꿈 위치 계산
├── PART 7:  XML Builders            # paragraph, charPr, font, borderFill XML
├── PART 8:  CharPr Management       # 인라인 서식 → charPr ID 캐싱
├── PART 9:  Plain Text Extraction   # 인라인 → 텍스트 (lineseg용)
├── PART 10: Hyperlink / Footnote    # fieldBegin/End, footNote/subList
├── PART 11: Image Handling          # 이미지 경로 해석, 크기 계산, pic XML
├── PART 12: Inline Processing       # Strong, Emph, Code, Link, Image, Math, Note
├── PART 13: Block Processing        # Header, Para, CodeBlock, Table, List, Div
├── PART 14: Title Block / TOC       # 메타데이터 추출, 목차 생성
├── PART 15: XML Assembly            # section0.xml, header.xml, content.hpf 조립
├── PART 16: ZIP Assembly            # unzip 템플릿 → 수정 → zip 패키징
└── PART 17: Pandoc(doc)             # 메인 엔트리포인트
```

## 지원 요소 상세

### Block 요소

| Pandoc Block | HWPX 처리 |
|---|---|
| `Para`, `Plain` | `<hp:p>` + 인라인 서식 보존 + linesegarray |
| `Header(1~6)` | 개요 스타일 (H1=22pt/H2=16pt/H3=13pt) |
| `CodeBlock` | 줄별 `<hp:p>` (D2Coding, charPrIDRef=10) |
| `BulletList` | 레벨별 마커 (●→○→■→▪) + 들여쓰기 |
| `OrderedList` | 레벨별 번호 (1.→가.→(1)→(가)) + 들여쓰기 |
| `BlockQuote` | 전각 공백 들여쓰기 재귀 처리 |
| `Table` | `<hp:tbl>` + rowspan/colspan + occupied-cell 추적 |
| `HorizontalRule` | "━━━" 구분선 |
| `Div` | Quarto 셀 래퍼 패스스루, Callout 감지, code-fold 지원 |
| `Div(Callout)` | `__quarto_custom_type=Callout` → 배경색 1셀 테이블 |
| `Div(FloatRefTarget)` | `__quarto_custom_type=FloatRefTarget` → 콘텐츠+캡션 패스스루 |
| `Figure` | Pandoc 3.8 네이티브 Figure → 이미지 + 기울임 캡션 |
| `DefinitionList` | 용어 + 들여쓰기 정의 |
| `LineBlock` | 줄별 단락 생성 |
| `RawBlock(openxml)` | `<w:tbl>` → HWPX `<hp:tbl>` 변환 (gt 호환) |
| `RawBlock(html)` | `<table>` → `pandoc.read` 후 HWPX 변환 |

### Inline 요소

| Pandoc Inline | HWPX 처리 |
|---|---|
| `Strong` | charPr bold=1 |
| `Emph` | charPr italic=1 |
| `Underline` | charPr underline type="BOTTOM" |
| `Strikeout` | charPr strikeout shape="SOLID" |
| `Code` | D2Coding charPr (fontRef=2) |
| `Link` | fieldBegin/fieldEnd + 파란색+밑줄 |
| `Image` | `<hp:pic>` + PNG/JPEG 헤더 파싱 자동 크기 + BinData 임베딩 |
| `Note` | `<hp:footNote>` + `<hp:subList>` |
| `Math` | `<hp:equation>` + LaTeX→HWP 수식 스크립트 |
| `Quoted` | 유니코드 인용부호 |
| `Superscript/Subscript` | charPr supscript/subscript |
| `Cite` | citeproc 처리 후 텍스트 통과 |
| `Span` | 콘텐츠 투명 패스스루 |

## 폰트 매핑

| fontface lang | primary font | 용도 |
|---|---|---|
| HANGUL | NanumSquareOTF | 한글 본문/제목 |
| LATIN | NimbusSanL | 영문 산세리프 |
| HANJA | Noto Sans CJK KR | 한자 |
| SYMBOL | STIX Two Text | 수식/기호 |
| CODE (fontRef=2) | D2Coding | 코드블록/인라인 코드 |

## 기술 노트

### docx 기반 커스텀 포맷 구조
`_extension.yml`에서 `docx` 포맷에 Lua 필터를 추가하는 방식.
Quarto가 docx 파이프라인을 실행하면 Lua 필터가 docx와 함께 hwpx도 생성한다.
최종 `.docx`는 정리 마커(`.hwpx-cleanup`)로 후처리 가능.

### 시스템 의존성
- `zip`, `unzip` 명령 (macOS/Linux 기본 설치)
- Python, Pillow 불필요 — 순수 Lua 엔진

### namespace 호환성
한글 Mac은 XML namespace prefix를 하드코딩 인식 (hp:, hs:, hc:, hh:).
raw XML 문자열로 원본 prefix 유지.

### 이미지 자동 크기
PNG/JPEG 파일 헤더를 직접 파싱하여 픽셀 크기를 읽는다.
Pillow 없이 동작하며, 지원하지 않는 포맷은 기본 크기(30mm) 적용.

### linesegarray
한글 Mac에서 필수. 텍스트 길이 기반 줄바꿈 계산.
CJK ≈ char_height 폭, Latin ≈ char_height/2 폭.

### Quarto 코드 실행과의 관계
R/Python 코드 실행은 Quarto 엔진이 담당한다:
- **R 코드**: knitr 엔진 → 실행 결과를 Pandoc AST에 삽입 (이미지는 PNG, 테이블은 RawBlock)
- **Python 코드**: jupyter 엔진 → 동일한 방식
- **gt 테이블**: `as_raw_html()` 또는 OpenXML `<w:tbl>` RawBlock으로 전달됨
- **ggplot2/matplotlib 그래프**: PNG 파일로 저장 → `Image` 인라인으로 참조

Lua 필터는 이 실행 결과를 받아 HWPX XML로 변환하는 역할만 한다.

## 개발 원칙

1. **Quarto 파이프라인 호환**: Quarto의 기존 파이프라인(knitr/jupyter → Pandoc → Filter)을 그대로 활용한다. 별도 빌드 도구나 전처리기를 만들지 않는다.
2. **순수 Lua**: 외부 의존성(Python, Node.js 등)을 추가하지 않는다. Pandoc 내장 Lua API만 사용한다.
3. **Pandoc AST 완전 커버리지**: Pandoc AST의 모든 블록/인라인 타입을 처리한다. 미지원 타입은 graceful degradation (경고 + 텍스트 폴백).
4. **한글 Mac 호환성**: 생성된 .hwpx는 한글 macOS/Windows 모두에서 정상 열림을 보장한다.
5. **테스트**: `examples/example.qmd`로 종합 테스트. 새 기능 추가 시 해당 Quarto 기능을 예제에 포함한다.

## 테스트 방법

```bash
cd examples
quarto render example.qmd --to hwpx
# → example.hwpx 생성 확인
# → 한글 프로그램으로 열어 렌더링 확인
```

## 계보

- **quarto-hwpx**: 수식, lineseg, 한국어 폰트, 블록타입 → 이식
- **pypandoc-hwpx**: 인라인 서식, 이미지, 테이블, 하이퍼링크, 각주 → 이식
- **pandoc-hwpx**: 두 프로젝트 통합 → Python 엔진 → 순수 Lua 전환
