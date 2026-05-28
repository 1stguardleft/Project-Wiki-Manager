# 공통/인프라 - 공통 API 응답 - 테스트 (2차)

**문서 버전:** v2.0 (2차)
**도메인 / 서브도메인:** 공통/인프라 / 공통 API 응답
**SDLC 단계:** 테스트
**변경 요점 (vs 1차):** message/errorCode/timestamp/PageResponse 검증.

## 1. 테스트 범위

확장 필드 직렬화 정확성, 페이지네이션 응답 표준 준수.

## 2. 정상 시나리오

| TC-ID | 시나리오 | 전제 | 실행 | 기대 결과 |
|---|---|---|---|---|
| API-N1 | 성공 응답 | - | GET | message, errorCode=null, timestamp 포함 |
| API-N2 | 실패 응답 | 검증 실패 | POST | errorCode 채워짐 |
| API-N3 | 페이지 응답 | Page<T> 반환 | GET 페이지 | content/totalElements/totalPages 모두 포함 |

## 3. 경계·예외 시나리오

| TC-ID | 시나리오 | 전제 | 실행 | 기대 결과 |
|---|---|---|---|---|
| API-E1 | 1차 클라이언트 | message 무시 | API 호출 | 무시해도 정상 동작(downward 호환) |
| API-E2 | timestamp 누락 | - | 모든 API | 응답에 항상 포함 |

## 4. 합격 기준

- 표준 필드 누락 0건
- 1차 클라이언트 호환성 유지
