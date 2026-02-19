---
name: inspect
description: 생성된 HWPX 파일 내부 XML 구조를 검사. "hwpx 내용 확인", "XML 검사", "section0 확인", "header.xml 봐줘" 등의 요청 시 사용.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[hwpx파일경로 (기본: examples/example.hwpx)]"
---

# HWPX 내부 검사

생성된 `.hwpx` 파일(ZIP 아카이브)의 내부 XML 구조를 검사한다.

## 실행 절차

1. 대상 파일 결정:
   - `$ARGUMENTS`가 있으면 해당 파일 사용
   - 없으면 `examples/example.hwpx` 사용

2. 임시 디렉토리에 압축 해제:
   ```bash
   TMPDIR=$(mktemp -d)
   unzip -o <hwpx파일> -d "$TMPDIR"
   ```

3. 파일 목록 출력:
   ```bash
   find "$TMPDIR" -type f | sort
   ```

4. 주요 XML 파일 검사:
   - `Contents/section0.xml` — 문서 본문 (hp:p, hp:tbl, hp:pic 등)
   - `Contents/header.xml` — 스타일 정의 (charPr, paraPr, borderFill)
   - `Contents/content.hpf` — 매니페스트 (메타데이터, 이미지 참조)

5. 사용자가 특정 요소를 요청하면 해당 부분만 추출:
   - "callout" → borderFill + section0에서 callout 테이블 검색
   - "table" → hp:tbl 요소 검색
   - "image" → hp:pic + BinData 목록
   - "charPr" → header.xml의 charProperties
   - "paraPr" → header.xml의 paraProperties

6. XML은 한 줄로 되어 있으므로 가독성을 위해 주요 태그 기준으로 정리하여 보여준다.

7. 정리:
   ```bash
   rm -rf "$TMPDIR"
   ```

## 주의사항

- XML namespace prefix (hp:, hh:, hc:, hs:)를 정확히 구분할 것
- `hh:borderFills` (복수형 s) — borderFillList가 아님
- `hc:fillBrush` — `hh:fillBrush`가 아님
