# pandoc-hwpx

Quarto 문서(`.qmd`)를 한글과컴퓨터 **HWPX** 문서로 변환하는 Quarto extension.

HTML, PDF, DOCX처럼 **HWPX를 Quarto의 일급(first-class) 출력 포맷**으로 만드는 것이 목표다.

> HWPX는 한글과컴퓨터의 개방형 문서 포맷이다. 내부는 ZIP 아카이브이며 OOXML과 유사한 XML 구조를 갖는다. 이 extension은 순수 Lua로 Pandoc AST를 읽어 HWPX의 XML을 직접 조립한다. Python 의존성 없음.

------------------------------------------------------------------------

## Architecture

<p align="center">

<img src="man/figures/architecture.svg" alt="pandoc-hwpx architecture" width="800"/>

</p>

`quarto render`가 `.qmd`를 처리하면 Quarto 엔진(knitr/jupyter)이 코드를 실행하고, 내부 Pandoc이 AST를 생성한다. 단일 Lua 필터(`hwpx-filter.lua`, \~1,950줄)가 AST를 직접 처리하여 HWPX XML을 조립하고, 시스템 `zip` 명령으로 `.hwpx` 파일을 패키징한다.

```         
.qmd → Quarto(knitr/jupyter) → Pandoc AST → hwpx-filter.lua → .hwpx
         코드 실행                 citeproc       XML 생성
         그림/표 생성              TOC 감지       ZIP 패키징
```

------------------------------------------------------------------------

## Install

``` bash
quarto add bit2r/pandoc-hwpx
```

시스템 요구사항: `zip`, `unzip` 명령 (macOS/Linux 기본 설치). Python, Node.js 등 외부 의존성 없음.

------------------------------------------------------------------------

## Usage

### `_quarto.yml` 설정

``` yaml
format:
  hwpx-docx:
    toc: true
    bibliography: references.bib
```

### 렌더링

``` bash
quarto render document.qmd --to hwpx-docx
# → document.hwpx 생성
```

> **참고**: Quarto 커스텀 포맷은 `{ext}-{base}` 형식이 필수이므로 `hwpx-docx`로 지정한다. 실제 출력은 `.hwpx` 파일이며, `.docx`는 빈 파일(\~10KB)로 최소화된다.

------------------------------------------------------------------------

## Converter Engine

`hwpx-filter.lua`는 약 1,950줄의 순수 Lua 필터로, Pandoc AST를 5단계에 걸쳐 HWPX로 변환한다.

| Stage | Operation | Detail |
|:------------------:|:-----------------------------|:---------------------|
| 1 | Meta extraction | title, subtitle, author, date, citeproc |
| 2 | Template loading | `blank.hwpx` 내장 템플릿 unzip |
| 3 | Block processing | Header, Table, Callout, Figure, List, CodeBlock, ... |
| 4 | Inline formatting | Bold, Italic, Code, Link, Image, Math, Footnote |
| 5 | XML assembly + ZIP | section0.xml + header.xml + content.hpf → zip |

### Built-in Modules

| Module | Description |
|:---|:---|
| `math_converter` | LaTeX → HWP 수식 스크립트 변환 |
| `lineseg_calculator` | 한글 Mac용 줄바꿈 위치 계산 (CJK/Latin 폭 구분) |
| `image_dimensions` | PNG/JPEG 파일 헤더 직접 파싱 (Pillow 없이) |
| `openxml_parser` | gt `<w:tbl>` → HWPX `<hp:tbl>` 변환 |
| `callout_renderer` | 5가지 타입별 스타일 callout (소스 파일 기반 타입 감지) |
| `charPr_manager` | 인라인 서식 → charPr ID 동적 캐싱 |

------------------------------------------------------------------------

## Supported Elements

### Blocks

| Pandoc Block | HWPX 처리 |
|:---|:---|
| `Header` 1--6 | 개요 스타일 (H1=22pt / H2=16pt / H3=13pt), 단락 간격 자동 조정 |
| `Para`, `Plain` | `<hp:p>` + 인라인 서식 보존 + linesegarray |
| `CodeBlock` | D2Coding, 줄별 `<hp:p>` |
| `Table` | `<hp:tbl>`, rowspan/colspan, occupied-cell 추적, 캡션 |
| `BulletList` | 레벨별 마커 (●→○→■→▪) + 중첩 들여쓰기 |
| `OrderedList` | 레벨별 번호 (1.→가.→(1)→(가)) + 중첩 들여쓰기 |
| `BlockQuote` | 전각 공백 들여쓰기 재귀 처리 |
| `DefinitionList` | 용어(굵게) + 들여쓰기 정의 |
| `HorizontalRule` | "━━━" 구분선 |
| `Div` | Quarto 셀 래퍼 투명 패스스루, code-fold 지원 |
| `Div(Callout)` | 5가지 타입별 배경색+좌측 테두리 테이블 (note/warning/tip/caution/important) |
| `Div(FloatRefTarget)` | Quarto Figure → 이미지 + 캡션 |
| `Figure` | Pandoc 네이티브 Figure → 이미지 + 중앙정렬 캡션 (9pt 이탤릭) |
| `LineBlock` | 줄별 단락 생성 |
| `RawBlock(openxml)` | gt `<w:tbl>` → `<hp:tbl>` OpenXML 파서 (헤더 굵게 처리) |
| `RawBlock(html)` | HTML `<table>` → `pandoc.read` → HWPX 변환 |

### Inlines

| Pandoc Inline | HWPX 처리                                                |
|:--------------|:---------------------------------------------------------|
| `Strong`      | charPr bold                                              |
| `Emph`        | charPr italic                                            |
| `Underline`   | charPr underline                                         |
| `Strikeout`   | charPr strikeout                                         |
| `Code`        | D2Coding charPr                                          |
| `Link`        | fieldBegin/fieldEnd, 파란색 밑줄                         |
| `Image`       | `<hp:pic>`, PNG/JPEG 헤더 파싱 자동 크기, BinData 임베딩 |
| `Math`        | `<hp:equation>`, LaTeX → HWP 수식 스크립트               |
| `Note`        | `<hp:footNote>` + `<hp:subList>`                         |
| `Quoted`      | 유니코드 스마트 인용부호                                 |
| `Superscript` | charPr supscript                                         |
| `Subscript`   | charPr subscript                                         |
| `Cite`        | citeproc 처리 후 텍스트 통과                             |
| `Span`        | 콘텐츠 투명 패스스루                                     |

### Quarto Features

| Feature | HWPX 처리 |
|:-----------------------|:-----------------------------------------------|
| **TOC** (`toc: true`) | 목차 자동 생성 (레벨별 들여쓰기, 최상위 굵게) |
| **Bibliography** | citeproc → 본문 인용 + 참고문헌 목록 |
| **Callout** | 5가지 타입(note/warning/tip/caution/important) 자동 감지, 타입별 색상 |
| **Figure** | 이미지 + 중앙정렬 캡션 (전용 paraPr/charPr) |
| **code-fold** (`code-fold: true`) | `.cell-code` Div 생략 |
| **R 코드 실행** (knitr) | 결과(표/그림)를 HWPX에 포함 |
| **Python 코드 실행** (jupyter) | 결과를 HWPX에 포함 |
| **gt 테이블** | OpenXML `<w:tbl>` 파싱 → `<hp:tbl>` (헤더 굵게) |
| **ggplot2 / matplotlib** | PNG 이미지 임베딩 |
| **docx 최소화** | HWPX 성공 시 빈 docx (\~10KB) 반환 |

------------------------------------------------------------------------

## Callout Styles

Quarto의 5가지 callout 타입을 자동 감지하여 타입별 색상으로 렌더링한다.

| Type        | Title | Border    | Background |
|:------------|:------|:----------|:-----------|
| `note`      | 참고  | `#0969DA` | `#DBEAFE`  |
| `warning`   | 경고  | `#BF8700` | `#FEF3C7`  |
| `tip`       | 팁    | `#1A7F37` | `#DCFCE7`  |
| `caution`   | 주의  | `#CF222E` | `#FEE2E2`  |
| `important` | 중요  | `#8250DF` | `#F3E8FF`  |

> Quarto의 custom type 변환 과정에서 callout 타입 정보가 소실되므로, 소스 `.qmd` 파일에서 `::: {.callout-TYPE}` 패턴을 파싱하여 타입을 복원한다.

------------------------------------------------------------------------

## Typography

한국어 문서를 위한 폰트 매핑. 모든 폰트는 extension에 번들되어 있다.

| Language | Font             | Purpose               |
|:---------|:-----------------|:----------------------|
| HANGUL   | NanumSquare      | 한글 본문, 제목       |
| LATIN    | NimbusSanL       | 영문 산세리프         |
| HANJA    | Noto Sans CJK KR | 한자                  |
| SYMBOL   | STIX Two Text    | 수식, 기호            |
| CODE     | D2Coding         | 코드블록, 인라인 코드 |

------------------------------------------------------------------------

## Project Layout

```         
pandoc-hwpx/
├── _extensions/hwpx/         Quarto extension
│   ├── _extension.yml        format: hwpx-docx (docx 기반 커스텀 포맷)
│   ├── hwpx-filter.lua       pure Lua engine, ~1,950 lines
│   └── templates/
│       ├── blank.hwpx        기본 HWPX 템플릿 (ZIP 아카이브)
│       └── fonts/            번들 폰트 파일
├── examples/                 example documents
│   ├── example.qmd           종합 테스트 (R, gt, ggplot2, 수식, callout, 인용)
│   └── references.bib        참고문헌
├── man/figures/              architecture diagram
└── tests/
```

------------------------------------------------------------------------

## Technical Notes

### HWPX 파일 구조

```         
output.hwpx (ZIP)
├── mimetype
├── META-INF/container.xml
├── Contents/
│   ├── content.hpf           패키지 매니페스트 (메타데이터, 이미지 참조)
│   ├── header.xml            스타일 정의 (fontface, charPr, paraPr, borderFill)
│   └── section0.xml          문서 본문 (hp:p, hp:tbl, hp:pic, hp:equation)
└── BinData/                  이미지, 폰트 파일
```

### XML Namespace 호환성

한글 프로그램(macOS/Windows)은 XML namespace prefix를 하드코딩으로 인식한다. 반드시 `hp:`, `hs:`, `hc:`, `hh:` prefix를 유지해야 한다.

주의할 네임스페이스 구분: - `hh:borderFill` — borderFill 정의 (복수형 `hh:borderFills`) - `hc:fillBrush` — 배경 채우기 (`hh:`가 아닌 `hc:` 네임스페이스) - `hp:switch` / `hp:case` / `hp:default` — 템플릿 호환 paraPr 구조

### 이미지 자동 크기

PNG/JPEG 파일 헤더를 직접 파싱하여 픽셀 크기를 읽는다. Pillow 없이 동작하며, 지원하지 않는 포맷은 기본 크기(30mm)를 적용한다.

### linesegarray

한글 Mac에서 필수인 줄바꿈 위치 정보. CJK 문자는 `char_height` 폭, Latin 문자는 `char_height/2` 폭으로 계산한다.

### docx 기반 커스텀 포맷

`_extension.yml`에서 `docx` 포맷에 Lua 필터를 추가하는 구조. Quarto가 docx 파이프라인을 실행하면 Lua 필터가 `.hwpx`를 생성한다. HWPX 생성 성공 시 빈 `pandoc.Pandoc({})`을 반환하여 `.docx`를 최소화(\~10KB)한다.

------------------------------------------------------------------------

## Feature Comparison: DOCX vs ODT vs HWPX

Quarto의 주요 기능이 세 가지 문서 포맷에서 어떻게 지원되는지 비교한다.

> **범례**: Full = 완전 지원, Partial = 부분 지원, None = 미지원, N/A = 해당 없음

### 텍스트 및 서식

| Feature                 | DOCX | ODT  | HWPX | 비고                        |
|:------------------------|:----:|:----:|:----:|:----------------------------|
| **굵게/기울임/취소선**  | Full | Full | Full |                             |
| **밑줄**                | Full | Full | Full |                             |
| **위첨자/아래첨자**     | Full | Full | Full |                             |
| **인라인 코드**         | Full | Full | Full | HWPX: D2Coding 폰트         |
| **제목 H1-H6**          | Full | Full | Full | HWPX: 개요 스타일+크기 자동 |
| **인용문 (BlockQuote)** | Full | Full | Full |                             |
| **수평선**              | Full | Full | Full |                             |
| **줄 블록 (LineBlock)** | Full | Full | Full |                             |

### 목록

| Feature               |  DOCX   | ODT  | HWPX | 비고                            |
|:------------|:-----------:|:-----------:|:-----------:|:---------------------|
| **순서/비순서 목록**  |  Full   | Full | Full |                                 |
| **중첩 목록 (4단계)** |  Full   | Full | Full | HWPX: ●→○→■→▪ / 1.→가.→(1)→(가) |
| **정의 목록**         | Partial | Full | Full | DOCX: 들여쓰기 소실 가능        |

### 표

| Feature             |  DOCX   |   ODT    | HWPX | 비고                           |
|:------------|:-----------:|:-----------:|:-----------:|:------------------|
| **기본 표**         |  Full   |   Full   | Full |                                |
| **rowspan/colspan** | Partial | **None** | Full | ODT: Pandoc 미지원 (#6636)     |
| **표 캡션**         |  Full   |   Full   | Full |                                |
| **gt 테이블 (R)**   | Partial | Partial  | Full | HWPX: OpenXML 파서로 직접 변환 |
| **HTML 테이블**     |  Full   |   Full   | Full | HWPX: pandoc.read() 후 변환    |

### 이미지

| Feature | DOCX | ODT | HWPX | 비고 |
|:------------|:-----------:|:-----------:|:-----------:|:------------------|
| **PNG/JPEG** | Full | Full | Full | HWPX: 헤더 파싱 자동 크기 |
| **SVG** | Partial | Partial | **None** | DOCX/ODT도 불안정 |
| **GIF/WebP** | None | None | None |  |
| **자동 크기 감지** | Full | Partial | Full | HWPX: 바이너리 헤더 직접 파싱 |
| **ggplot2/matplotlib** | Full | Full | Full | PNG 이미지로 임베딩 |

### 수식

| Feature | DOCX | ODT | HWPX | 비고 |
|:-----------|:----------:|:----------:|:----------:|:-------------------------|
| **인라인 수식** | Full | Full | Full | DOCX: OMML, ODT: MathML, HWPX: HWP 스크립트 |
| **디스플레이 수식** | Full | Full | Full |  |
| **수식 번호** | Full | Partial | None |  |

### 코드

| Feature | DOCX | ODT | HWPX | 비고 |
|:-------------|:------------:|:------------:|:------------:|:-----------------|
| **코드 블록** | Full | Full | Full |  |
| **구문 강조** | Full | Full | **None** | HWPX: D2Coding 단색 렌더링 |
| **code-fold** | **None** | **None** | **Full** | HWPX만 코드 숨김 구현 |
| **코드 주석 (annotation)** | Full | None | None |  |

### 링크 및 참조

| Feature | DOCX | ODT | HWPX | 비고 |
|:-------------|:------------:|:------------:|:------------:|:----------------|
| **하이퍼링크** | Full | Full | Full | HWPX: fieldBegin/fieldEnd |
| **각주** | Full | Full | Full | HWPX: hp:footNote + hp:subList |
| **미주 (Endnote)** | None | None | None |  |
| **참고문헌 (citeproc)** | Full | Full | Full |  |
| **교차참조** (@fig-, @tbl-) | Full | Partial | Partial | HWPX: 텍스트만 통과, 링크 미구현 |

### Quarto 고급 기능

| Feature | DOCX | ODT | HWPX | 비고 |
|:--------------|:------------:|:------------:|:------------:|:----------------|
| **목차 (TOC)** | Full | Full | Full |  |
| **Callout (5가지 타입)** | Full | **None** | Full | ODT: 인용문으로 폴백 |
| **Figure 캡션** | Full | Full | Full | HWPX: 9pt 이탤릭 중앙정렬 |
| **R 코드 실행 (knitr)** | Full | Full | Full |  |
| **Python 코드 실행 (jupyter)** | Full | Full | Full |  |
| **Mermaid 다이어그램** | Full | Full | Partial | PNG 렌더링 시 포함 가능 |
| **탭셋 (Tabset)** | None | None | None | HTML 전용 |
| **레이아웃 컬럼** | None | None | None | HTML/Typst 전용 |
| **Observable JS** | None | None | None | HTML 전용 |

### 문서 스타일 및 레이아웃

| Feature                | DOCX |   ODT   | HWPX | 비고                      |
|:-----------------------|:----:|:-------:|:----:|:--------------------------|
| **커스텀 테마/스타일** | Full |  Full   | None | DOCX/ODT: reference-doc   |
| **머리글/바닥글**      | Full | Partial | None | HWPX: 템플릿 기본값       |
| **페이지 번호**        | Full | Partial | None |                           |
| **섹션 번호**          | Full |  Full   | None |                           |
| **docx 최소화**        | N/A  |   N/A   | Full | HWPX 성공 시 빈 docx 반환 |

### HWPX가 우위인 기능

| Feature | 설명 |
|:----------------------|:------------------------------------------------|
| **code-fold** | DOCX/ODT는 무시하지만 HWPX는 코드 숨김을 실제 구현 |
| **Table rowspan/colspan** | ODT는 미지원, DOCX는 불안정하지만 HWPX는 완전 지원 |
| **gt 테이블** | OpenXML `<w:tbl>`을 직접 파싱하여 네이티브 HWPX 테이블로 변환 |
| **Callout (vs ODT)** | ODT는 인용문 폴백이지만 HWPX는 5가지 타입별 색상 렌더링 |
| **한국어 타이포그래피** | NanumSquare + D2Coding 번들, CJK 최적화 lineseg 계산 |

------------------------------------------------------------------------

## Roadmap

| Feature                             | Status                               |
|:------------------------|:---------------------------------------------|
| Mermaid 다이어그램                  | SVG/PNG 렌더링 시 이미지로 포함 가능 |
| 교차참조 (`@fig-`, `@tbl-`, `@eq-`) | 텍스트만 통과, 상호참조 링크 미구현  |
| 코드 구문 강조                      | 키워드별 색상 charPr 매핑 필요       |
| 탭셋 (Tabset)                       | 미지원                               |
| 레이아웃 컬럼                       | 미지원                               |
| 테마/스타일                         | 사용자 정의 HWPX 테마 지원 필요      |
| 페이지 번호/머리글                  | 템플릿 기본값 사용 중                |
| SVG/GIF/WebP 이미지                 | 미지원                               |
| 수식 번호                           | 미지원                               |

------------------------------------------------------------------------

## Heritage

이 extension은 세 프로젝트의 장점을 통합한 것이다.

| Project | Contribution |
|:---|:---|
| **quarto-hwpx** | 수식 변환, lineseg 계산, 한국어 폰트 매핑 |
| **pypandoc-hwpx** | 인라인 서식, 이미지 임베딩, 테이블 rowspan/colspan, 하이퍼링크, 각주 |
| **pandoc-hwpx** (Python) | 두 프로젝트 통합 후 순수 Lua로 전환 |

------------------------------------------------------------------------

## License

MIT