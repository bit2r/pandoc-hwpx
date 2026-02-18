# pandoc-hwpx

Quarto 문서(.qmd)를 한글과컴퓨터 HWPX 문서(.hwpx)로 변환하는 Quarto extension.
순수 Lua 엔진 — Python 의존성 없음.

## 프로젝트 구조

순수 Quarto extension: `quarto add bit2r/pandoc-hwpx`

```
pandoc-hwpx/
├── _extensions/hwpx/             # Quarto extension (quarto add 대상)
│   ├── _extension.yml           # format: hwpx-docx
│   ├── hwpx-filter.lua          # 전체 변환 엔진 (순수 Lua, ~1200줄)
│   └── templates/
│       ├── blank.hwpx           # 기본 HWPX 템플릿
│       └── fonts/               # 번들 폰트 파일
├── examples/                     # 예제/테스트 문서
│   ├── example.qmd              # 예제 Quarto 문서
│   ├── references.bib           # 참고문헌
│   └── _quarto.yml              # 예제용 Quarto 설정
├── tests/
│   └── fixtures/
│       └── example.qmd          # 테스트 문서
├── CLAUDE.md                    # 이 파일
└── README.md
```

## 설치

```bash
quarto add bit2r/pandoc-hwpx
```

## 사용법

```yaml
# _quarto.yml
format:
  hwpx-docx:
    toc: true
    bibliography: references.bib
```

```bash
quarto render example.qmd --to hwpx-docx
```

## 아키텍처

```
.qmd → Quarto render → Pandoc → Lua Filter (hwpx-filter.lua) → .hwpx
```

단일 Lua 필터가 Pandoc AST를 직접 처리하여 HWPX XML을 생성한다.
citeproc 실행, TOC 감지, 블록/인라인 변환, XML 조립, ZIP 패키징을 모두 수행한다.
시스템 `zip`/`unzip` 명령으로 HWPX ZIP 아카이브를 생성한다.

### hwpx-filter.lua 구조

```
hwpx-filter.lua (~1200줄)
├── Constants/Config        # 폰트 매핑, 스타일 ID, 레이아웃 상수
├── Utility Functions       # xml_escape, file I/O, shell helpers
├── Image Dimension Reader  # PNG/JPEG 헤더 파싱 (Pillow 대체)
├── Math Converter          # LaTeX → HWP 수식 스크립트
├── Lineseg Calculator      # 텍스트 줄바꿈 위치 계산
├── XML Builders            # paragraph, charPr, font, borderFill XML
├── CharPr Management       # 인라인 서식 → charPr ID 캐싱
├── Inline Processing       # Strong, Emph, Code, Link, Image, Math, Note
├── Block Processing        # Header, Para, CodeBlock, Table, List, Div
├── Table Handling          # rowspan/colspan, occupied-cell 추적
├── Title Block / TOC       # 메타데이터 추출, 목차 생성
├── XML Assembly            # section0.xml, header.xml, content.hpf 조립
├── ZIP Assembly            # unzip 템플릿 → 수정 → zip 패키징
└── Pandoc(doc)             # 메인 엔트리포인트
```

## 지원 요소

### Block 요소

| Pandoc Block | HWPX 처리 |
|---|---|
| `Para`, `Plain` | `<hp:p>` + 인라인 서식 보존 + linesegarray |
| `Header(1~6)` | 개요 스타일 (H1=22pt/H2=16pt/H3=13pt) |
| `CodeBlock` | 줄별 `<hp:p>` (D2Coding, charPrIDRef=10) |
| `BulletList` | "●" 텍스트 prefix |
| `OrderedList` | "1." 텍스트 prefix |
| `BlockQuote` | 전각 공백 들여쓰기 재귀 처리 |
| `Table` | `<hp:tbl>` + rowspan/colspan + occupied-cell 추적 |
| `HorizontalRule` | "━━━" 구분선 |
| `Div` | Quarto 셀 래퍼 투명 패스스루 |
| `DefinitionList` | 용어 + 들여쓰기 정의 |
| `LineBlock` | 줄별 단락 생성 |

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

## 폰트 매핑

| fontface lang | primary font | 용도 |
|---|---|---|
| HANGUL | NanumSquareOTF | 한글 본문/제목 |
| LATIN | NimbusSanL | 영문 산세리프 |
| HANJA | Noto Sans CJK KR | 한자 |
| SYMBOL | STIX Two Text | 수식/기호 |
| CODE (fontRef=2) | D2Coding | 코드블록/인라인 코드 |

## 기술 노트

### 시스템 의존성
- `zip`, `unzip` 명령 (macOS/Linux 기본 설치)
- Python, Pillow 불필요

### namespace 호환성
한글 Mac은 XML namespace prefix를 하드코딩 인식 (hp:, hs:, hc:, hh:).
raw XML 문자열로 원본 prefix 유지.

### 이미지 자동 크기
PNG/JPEG 파일 헤더를 직접 파싱하여 픽셀 크기를 읽는다.
Pillow 없이 동작하며, 지원하지 않는 포맷은 기본 크기(30mm) 적용.

### linesegarray
한글 Mac에서 필수. 텍스트 길이 기반 줄바꿈 계산.
CJK ≈ char_height 폭, Latin ≈ char_height/2 폭.

## 계보

- **quarto-hwpx**: 수식, lineseg, 한국어 폰트, 블록타입 → 이식
- **pypandoc-hwpx**: 인라인 서식, 이미지, 테이블, 하이퍼링크, 각주 → 이식
- **pandoc-hwpx**: 두 프로젝트 통합 → Python 엔진 → 순수 Lua 전환
