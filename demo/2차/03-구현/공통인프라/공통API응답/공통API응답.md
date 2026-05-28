# 공통/인프라 - 공통 API 응답 - 구현 (2차)

**문서 버전:** v2.0 (2차)
**도메인 / 서브도메인:** 공통/인프라 / 공통 API 응답
**SDLC 단계:** 구현
**변경 요점 (vs 1차):** 필드 확장, PageResponse 유틸.

## 1. 구현 범위

ApiResponse 필드 확장, PageResponse 신설, Spring Page → PageResponse 변환 유틸.

## 2. 구현 항목 체크리스트

- [ ] ApiResponse에 message/errorCode/timestamp 필드 추가
- [ ] `ApiResponse.success(T data, String message)` 오버로드
- [ ] `ApiResponse.fail(String errorCode, String message)` 시그니처 변경
- [ ] PageResponse<T> DTO + `PageResponse.from(Page<T>)` 정적 변환
- [ ] 기존 호출부 마이그레이션 (1차 메서드는 한 릴리스 호환)
- [ ] 직렬화/역직렬화 테스트

## 3. 적용 기술

- Jackson, Spring Data Page
- `@JsonInclude(Include.ALWAYS)`

## 4. 단계별 작업 순서

1. DTO 확장 → 2. 변환 유틸 → 3. 핸들러 변경 → 4. 클라이언트 영향 평가 → 5. 마이그레이션

## 5. 위험 요소

| 위험 | 대응 |
|---|---|
| 1차 응답에 message 필드가 없어 클라이언트 코드 영향 | 추가 필드는 무시 가능 (downward 호환) |

## 6. 검증 포인트

- timestamp 포맷 일관
- PageResponse 필드 누락 0

## 7. 연관 작업

| 연관 | 관계 |
|---|---|
| [[전역예외처리]] | errorCode 채움 |
