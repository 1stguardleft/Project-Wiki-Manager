# 공통/인프라 - 공통 API 응답 - 설계 (2차)

**문서 버전:** v2.0 (2차)
**도메인 / 서브도메인:** 공통/인프라 / 공통 API 응답
**SDLC 단계:** 설계
**변경 요점 (vs 1차):** ApiResponse 필드 확장, PageResponse 표준 신설.

## 1. 설계 개요

`ApiResponse<T>`에 message/errorCode/timestamp를 추가하고, 페이지네이션 응답은 `PageResponse<T>`로 표준화한다.

## 2. 구성 요소

| 계층 | 구성 요소 | 역할 |
|---|---|---|
| DTO | ApiResponse<T> | 공통 응답 (확장) |
| DTO | PageResponse<T> | 페이지 응답 표준 |
| Util | ApiResponse.success(data) / fail(code, message) | 팩토리 |

## 3. 데이터 / 항목

**ApiResponse**

| 필드 | 형식 |
|---|---|
| success | boolean |
| data | T |
| message | String |
| errorCode | String (nullable on success) |
| timestamp | ISO 8601 |

**PageResponse**

| 필드 | 형식 |
|---|---|
| content | List<T> |
| totalElements | long |
| totalPages | int |
| number / size | int |

## 4. 인터페이스

별도 엔드포인트 없음. 페이지네이션 API는 `ApiResponse<PageResponse<T>>` 형태.

## 5. 설계 규칙

- 직렬화 시 null 필드도 명시(`Include.ALWAYS`).
- timestamp는 서버 timezone에 따라 KST 사용.
- Spring `Page<T>` → PageResponse 매핑 유틸 제공.

## 6. 의존 서브도메인

| 연관 기능 | 의존 내용 |
|---|---|
| [[전역예외처리]] | message/errorCode 채움 |
