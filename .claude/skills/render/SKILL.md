---
name: render
description: Quarto qmd 파일을 HWPX로 렌더링하고 한글 프로그램에서 열기. "렌더링해줘", "빌드", "hwpx 생성", "한글로 열어줘" 등의 요청 시 사용.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
argument-hint: "[파일경로 (기본: examples/example.qmd)]"
---

# HWPX 렌더링

Quarto `.qmd` 파일을 `.hwpx`로 렌더링하고 한글 프로그램에서 연다.

## 실행 절차

1. 대상 파일 결정:
   - `$ARGUMENTS`가 있으면 해당 파일 사용
   - 없으면 `examples/example.qmd` 사용

2. 프로젝트 루트 확인:
   ```
   프로젝트 루트: 이 .claude가 있는 디렉토리의 부모
   ```

3. 렌더링 실행:
   ```bash
   cd <파일이 있는 디렉토리>
   quarto render <파일명> --to hwpx-docx 2>&1
   ```

4. 결과 확인:
   - `[hwpx] Successfully created` 메시지 확인
   - 실패 시 에러 로그 분석 후 사용자에게 보고

5. 성공 시 한글에서 열기:
   ```bash
   open <생성된 .hwpx 파일>
   ```

6. 사용자에게 결과 요약:
   - 생성된 파일 경로
   - 감지된 callout 타입 수
   - 파일 크기
