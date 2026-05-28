---
title: 공통 API 응답 테스트 문서
slug: 공통-인프라-공통-api-응답-테스트
type: deliverable
sdlc_phase: test
domain: 공통/인프라
subdomain: 공통 API 응답
status: active
source_count: 2
sources:
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-151317-공통API응답.md.md
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-205351-공통API응답.md.md
updated: '2026-05-28'
---

# 공통 API 응답 테스트

**문서 버전:** v2.0  
**도메인 / 서브도메인:** 공통/인프라 / 공통 API 응답  
**SDLC 단계:** 테스트  
**변경 요점 (vs 1차):** message/errorCode/timestamp/PageResponse 검증.

## 1. 테스트 범위

확장 필드 직렬화 정확성, 페이지네이션 응답 표준 준수, 모든 도메인 API가 표준 응답 형태 100%.

## 2. 정상 시나리오

| TC-ID | 시나리오 | 전제 | 실행 | 기대 결과 |
|---|---|---|---|---|
| API-N1 | 성공 응답 | - | GET | message, errorCode=null, timestamp 포함 |
| API-N2 | 실패 응답 | 검증 실패 | POST | errorCode 채워짐 |
| API-N2 | 데이터 null | 응답 데이터 없음 | DELETE | `{success:true, data:null}` |
| API-N3 | 페이지 응답 | Page<T> 반환 | GET 페이지 | content/totalElements/totalPages 모두 포함 |

## 3. 경계·예외 시나리오

| TC-ID | 시나리오 | 전제 | 실행 | 기대 결과 |
|---|---|---|---|---|
| API-E1 | 1차 클라이언트 | message 무시 | API 호출 | 무시해도 정상 동작(downward 호환) |
| API-E1 | 직렬화 실패 | 순환 참조 객체 | API 호출 | 500 + `{success:false, data:null}` |
| API-E2 | timestamp 누락 | - | 모든 API | 응답에 항상 포함 |

## 4. 합격 기준

- 표준 필드 누락 0건
- 1차 클라이언트 호환성 유지

---

<!-- crossref:auto -->
## 5. 연관 도메인 / 서브도메인 / 관계

_이 표는 상호참조 Agent가 자동으로 유지합니다 — 직접 편집한 내용은 다음 적재 시 덮어쓰여집니다._

| 도메인 | 서브도메인 (페이지) | 관계 | 핵심 사유 | 함께 볼 때 |
|---|---|---|---|---|
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-설계]] | 검증 | 응답 테스트가 설계 문서를 검증한다. | API 응답의 설계가 완료된 후, 해당 테스트 문서를 통해 설계된 구조가 올바르게 작동하는지 확인할 때 함께 봐야 한다. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-구현]] | 검증 | 응답 테스트가 구현 문서를 검증한다. | API 응답 구현이 완료된 후, 해당 테스트 문서를 통해 응답의 정확성을 검증할 때 함께 봐야 한다. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-요구사항]] | 검증 | 응답 테스트가 요구사항 문서를 검증한다. | API 응답 요구사항이 정의된 후, 해당 테스트 문서를 통해 요구사항이 충족되는지를 검증할 때 함께 봐야 한다. |
<!-- /crossref:auto -->
