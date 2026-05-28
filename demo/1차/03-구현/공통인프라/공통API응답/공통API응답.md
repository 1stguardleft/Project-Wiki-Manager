# 공통/인프라 - 공통 API 응답 - 구현 (1차)

**문서 버전:** v1.0 (1차)
**도메인 / 서브도메인:** 공통/인프라 / 공통 API 응답
**SDLC 단계:** 구현

## 1. 구현 범위

ApiResponse<T> 제네릭 DTO와 정적 팩토리 메서드 작성.

## 2. 구현 항목 체크리스트

- [ ] `class ApiResponse<T> { boolean success; T data; }`
- [ ] `static <T> ApiResponse<T> success(T data)`
- [ ] `static ApiResponse<Void> fail()`
- [ ] 모든 Controller에 적용 (점진 마이그레이션)
- [ ] 직렬화 테스트

## 3. 적용 기술

- Jackson 직렬화
- Spring Web

## 4. 단계별 작업 순서

1. DTO 정의 → 2. 한 도메인 적용해 검증 → 3. 전 도메인 적용

## 5. 위험 요소

| 위험 | 대응 |
|---|---|
| 일부 도메인이 표준을 따르지 않음 | PR 리뷰로 강제 |

## 6. 검증 포인트

- success/data 직렬화 정확
- null 데이터 시 data:null

## 7. 연관 작업

| 연관 | 관계 |
|---|---|
| [[전역예외처리]] | 실패 응답 생성 |
