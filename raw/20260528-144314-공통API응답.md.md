# 공통/인프라 - 공통 API 응답 - 설계 (1차)

**문서 버전:** v1.0 (1차)
**도메인 / 서브도메인:** 공통/인프라 / 공통 API 응답
**SDLC 단계:** 설계

## 1. 설계 개요

`ApiResponse<T>` 제네릭 DTO를 정의하고, 모든 Controller가 이를 반환하도록 표준화한다.

## 2. 구성 요소

| 계층 | 구성 요소 | 역할 |
|---|---|---|
| DTO | ApiResponse<T> | 공통 응답 |
| Util | ApiResponse.success(data) / ApiResponse.fail() | 정적 팩토리 |

## 3. 데이터 / 항목

| 필드 | 형식 |
|---|---|
| success | boolean |
| data | T |

## 4. 인터페이스

별도 엔드포인트 없음. 모든 Controller가 `ApiResponse<T>`를 반환.

## 5. 설계 규칙

- 응답 본문은 항상 `ApiResponse<T>` 직렬화 형태.
- HTTP 상태코드는 별도로 설정 (`@ResponseStatus` 또는 `ResponseEntity`).

## 6. 의존 서브도메인

| 연관 기능 | 의존 내용 |
|---|---|
| [[전역예외처리]] | 실패 응답 생성 |
