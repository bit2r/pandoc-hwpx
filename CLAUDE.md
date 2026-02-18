# pandoc-hwpx

Quarto 문서(.qmd)를 한글과컴퓨터 HWPX 문서(.hwpx)로 변환하는 Quarto extension.
Python 변환 엔진 + Lua 필터 래퍼 구조.

## 프로젝트 구조

Quarto extension (Python 엔진 내장): `pip install pandoc-hwpx` (PyPI) + `quarto add bit2r/pandoc-hwpx` (GitHub)

```
pandoc-hwpx/
├── pandoc_hwpx/                  # Python 엔진 (pip install 대상)
│   ├── __init__.py              # 패키지 초기화
│   ├── __main__.py              # Lua 필터 내부 호출 전용 엔트리포인트
│   ├── converter.py             # 메인 엔진 (PandocHwpxConverter 클래스)
│   ├── math_converter.py        # LaTeX → HWP 수식 스크립트 변환
│   ├── lineseg.py               # linesegarray 계산기
│   └── templates/
│       ├── blank.hwpx           # 기본 HWPX 템플릿 (Skeleton.hwpx 기반)
│       └── fonts/               # 번들 폰트 파일 (9.4MB)
├── _extensions/hwpx/             # Quarto extension (quarto add 대상)
│   ├── _extension.yml           # format: hwpx-docx
│   └── hwpx-filter.lua          # Lua 필터 (67줄 래퍼)
├── examples/                     # 예제/테스트 문서
│   ├── example.qmd              # 예제 Quarto 문서
│   ├── references.bib           # 참고문헌
│   └── _quarto.yml              # 예제용 Quarto 설정
├── tests/
│   └── fixtures/
│       └── example.qmd          # 테스트 문서
├── pyproject.toml               # 빌드 설정, 의존성: Pillow
├── CLAUDE.md                    # 이 파일
└── README.md
```

## 설치

```bash
# Python 엔진 설치 (PyPI)
pip install pandoc-hwpx

# Quarto extension 설치 (GitHub)
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
.qmd → Quarto render → Pandoc → Lua Filter → Python Engine → .hwpx
```

Lua 필터(`hwpx-filter.lua`)가 Pandoc 내부에서 JSON AST를 가로채
`pandoc.pipe('python3', {'-m', 'pandoc_hwpx', '-o', path, '--input-dir', dir}, json_ast)`로
Python 엔진을 호출한다. citeproc 실행과 TOC 감지도 Lua 필터가 처리한다.

`__main__.py`는 Lua 필터 내부 호출 전용이며, 사용자가 직접 실행하지 않는다.

### 핵심 클래스: PandocHwpxConverter

```
converter.py
├── __init__()           # 템플릿 로드, 스타일 초기화, 메타데이터 추출
├── convert()            # 메인 엔트리포인트
├── _process_blocks()    # 블록 요소 재귀 처리
├── _process_inlines()   # 인라인 요소 + 서식 보존 처리
├── _handle_header()     # 제목 (동적 스타일 매핑)
├── _handle_para_or_plain()  # 본문 (인라인 서식, 수식, 이미지 분리)
├── _handle_code_block() # 코드블록 (D2Coding, 줄별 분리)
├── _handle_table()      # 테이블 (rowspan/colspan, occupied-cell 추적)
├── _handle_bullet_list()    # 불릿 목록 (네이티브/텍스트 이중 모드)
├── _handle_ordered_list()   # 번호 목록 (네이티브/텍스트 이중 모드)
├── _handle_div()        # Div (Quarto 래퍼 투명 처리)
├── _handle_image()      # 이미지 (Pillow 자동 크기, BinData 임베딩)
├── _create_field_begin/end()  # 하이퍼링크 (fieldBegin/fieldEnd)
├── _create_footnote()   # 각주 (footNote + subList)
├── _update_header_xml() # header.xml 폰트/스타일 주입
├── _update_content_hpf()# content.hpf 메타데이터 + 이미지 매니페스트
└── _write_hwpx()        # ZIP 조립 + 이미지 임베딩
```

## 지원 요소

### Block 요소

| Pandoc Block | HWPX 처리 |
|---|---|
| `Para`, `Plain` | `<hp:p>` + 인라인 서식 보존 + linesegarray |
| `Header(1~6)` | 개요 스타일 (동적 매핑 또는 H1=22pt/H2=16pt/H3=13pt) |
| `CodeBlock` | 줄별 `<hp:p>` (D2Coding, charPrIDRef=10) |
| `BulletList` | 네이티브 numbering 또는 "●" 텍스트 prefix |
| `OrderedList` | 네이티브 numbering 또는 "1." 텍스트 prefix |
| `BlockQuote` | 전각 공백 들여쓰기 재귀 처리 |
| `Table` | `<hp:tbl>` + rowspan/colspan + occupied-cell 추적 |
| `HorizontalRule` | "━━━" 구분선 |
| `Div` | Quarto 셀 래퍼 투명 패스스루 |
| `DefinitionList` | 용어 + 들여쓰기 정의 |
| `LineBlock` | 줄별 단락 생성 |

### Inline 요소

| Pandoc Inline | HWPX 처리 |
|---|---|
| `Strong` | charPr bold=1 (동적 복제) |
| `Emph` | charPr italic=1 |
| `Underline` | charPr underline type="BOTTOM" |
| `Strikeout` | charPr strikeout shape="SOLID" |
| `Code` | D2Coding charPr (fontRef=2) |
| `Link` | fieldBegin/fieldEnd + 파란색+밑줄 |
| `Image` | `<hp:pic>` + Pillow 자동 크기 + BinData 임베딩 |
| `Note` | `<hp:footNote>` + `<hp:subList>` |
| `Math` | `<hp:equation>` + LaTeX→HWP 수식 스크립트 |
| `Quoted` | 유니코드 인용부호 |
| `Superscript/Subscript` | charPr supscript/subscript |

### Quarto 코드 실행 결과

| 출력 유형 | Div 클래스 | HWPX 처리 |
|---|---|---|
| ggplot/matplotlib 이미지 | cell-output-display | `<hp:pic>` 임베딩 |
| kable/gt 표 | cell-output-display | `<hp:tbl>` 변환 |
| 텍스트 출력 | cell-output-stdout | D2Coding 코드블록 |
| 소스 코드 | cell (cell-code) | D2Coding 코드블록 |

## 폰트 매핑

| fontface lang | primary font | 용도 |
|---|---|---|
| HANGUL | NanumSquareOTF | 한글 본문/제목 |
| LATIN | NimbusSanL | 영문 산세리프 |
| HANJA | Noto Sans CJK KR | 한자 |
| SYMBOL | STIX Two Text | 수식/기호 |
| CODE (fontRef=2) | D2Coding | 코드블록/인라인 코드 |

## 기술 노트

### namespace 호환성
한글 Mac은 XML namespace prefix를 하드코딩 인식 (hp:, hs:, hc:, hh:).
Built-in 모드에서는 raw XML 문자열로 원본 prefix 유지.

### linesegarray
한글 Mac에서 필수. 텍스트 길이 기반 줄바꿈 계산.
CJK ≈ char_height 폭, Latin ≈ char_height/2 폭.

### 의존성
- Python 표준 라이브러리: zipfile, json, re, xml, argparse, copy
- Pillow: 이미지 크기 자동 계산 (선택, 없으면 기본 크기 사용)

## 계보

- **quarto-hwpx**: 수식, lineseg, 한국어 폰트, 블록타입 → 이식
- **pypandoc-hwpx**: 인라인 서식, 이미지, 테이블, 하이퍼링크, 각주, 네이티브 목록 → 이식
- **pandoc-hwpx**: 두 프로젝트의 장점 통합 + Quarto 코드 실행 결과 지원
