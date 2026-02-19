---
name: debug-ast
description: Pandoc AST 디버깅 로그를 hwpx-filter.lua에 추가하거나 제거. "AST 확인", "디버깅 켜줘", "블록 타입 확인" 등의 요청 시 사용.
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep
argument-hint: "[on|off (기본: on)]"
---

# Pandoc AST 디버깅

hwpx-filter.lua의 `process_blocks()` 함수에 디버깅 로그를 추가하거나 제거한다.
Quarto가 Pandoc AST를 어떤 형태로 전달하는지 확인할 때 사용한다.

## 디버깅 로그 내용

`[hwpx-debug]` 접두사로 stderr에 출력:

- **Div**: custom_type, classes, attributes
- **RawBlock**: format, 첫 80자
- **Table**: 행/열 수, 캡션 유무
- **Figure**: 캡션 텍스트
- **Header**: level, 텍스트

## 실행 절차

### `on` (기본) — 디버깅 추가

1. `_extensions/hwpx/hwpx-filter.lua`의 `process_blocks()` 함수 시작 부분을 찾는다
2. 각 블록 타입 분기(if/elseif) 앞에 디버깅 출력 추가:
   ```lua
   io.stderr:write(string.format('[hwpx-debug] Block: %s\n', t))
   ```
3. Div의 경우 추가 정보:
   ```lua
   if t == 'Div' then
     local attrs = block.attr and block.attr.attributes or {}
     local custom_type = attrs['__quarto_custom_type'] or ''
     local classes = table.concat(block.classes or {}, ',')
     io.stderr:write(string.format('[hwpx-debug]   custom_type=%s classes=[%s]\n', custom_type, classes))
     for k,v in pairs(attrs) do
       io.stderr:write(string.format('[hwpx-debug]   attr: %s=%s\n', k, v))
     end
   end
   ```
4. 렌더링 후 로그 확인:
   ```bash
   quarto render examples/example.qmd --to hwpx-docx 2>&1 | grep '\[hwpx-debug\]'
   ```

### `off` — 디버깅 제거

1. `[hwpx-debug]` 를 포함하는 모든 줄을 hwpx-filter.lua에서 제거
2. 변경 확인

## 주의사항

- 디버깅 로그는 반드시 작업 후 제거할 것 (`/debug-ast off`)
- 커밋 전에 디버깅 코드가 남아있지 않은지 확인
- stderr 출력이므로 HWPX 생성에는 영향 없음
