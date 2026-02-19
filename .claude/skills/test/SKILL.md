---
name: test
description: pandoc-hwpx extension을 별도 디렉토리에서 설치+렌더링하는 E2E 테스트. "테스트해줘", "extension 동작 확인", "설치 테스트" 등의 요청 시 사용.
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Glob
argument-hint: "[테스트 디렉토리 경로 (선택)]"
---

# Extension E2E 테스트

pandoc-hwpx extension을 별도 프로젝트 디렉토리에서 `quarto add`로 설치하고,
테스트 qmd 파일을 렌더링하여 정상 동작을 검증한다.

## 실행 절차

1. 테스트 디렉토리 준비:
   - `$ARGUMENTS`가 있으면 해당 디렉토리 사용
   - 없으면 임시 디렉토리 생성: `mktemp -d`

2. extension 설치:
   ```bash
   cd <테스트디렉토리>
   quarto add bit2r/pandoc-hwpx --no-prompt
   ```

3. 설치 확인:
   - `_extensions/bit2r/hwpx/hwpx-filter.lua` 존재 확인
   - `_extensions/bit2r/hwpx/templates/blank.hwpx` 존재 확인
   - **blank.hwpx 누락 시**: 원본 프로젝트에서 복사하고 사용자에게 경고

4. 테스트 qmd 파일 생성 (기본 요소 포함):
   - 제목/부제/저자/날짜 메타데이터
   - 굵게, 기울임, 코드 등 인라인 서식
   - 순서/비순서 목록
   - 표 (캡션 포함)
   - 수식 (인라인 + 디스플레이)
   - 코드 블록
   - callout (note, warning, tip 최소 3종)
   - 각주
   - 인용문
   - 링크
   - 수평선

5. 렌더링:
   ```bash
   quarto render test.qmd --to hwpx-docx 2>&1
   ```

6. 검증:
   - 렌더링 성공 여부 (exit code)
   - `.hwpx` 파일 생성 확인
   - 파일 크기 > 0
   - `[hwpx] Successfully created` 로그 확인
   - callout 타입 감지 로그 확인

7. 결과 보고:
   - PASS/FAIL
   - 생성된 파일 경로 및 크기
   - 발견된 문제점

8. 사용자에게 한글에서 열어볼지 확인
