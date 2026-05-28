---
title: 공통 API 응답 설계 문서
slug: 공통-인프라-공통-api-응답-설계
type: deliverable
sdlc_phase: design
domain: 공통/인프라
subdomain: 공통 API 응답
status: active
source_count: 2
sources:
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-144314-공통API응답.md.md
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-203204-공통API응답.md.md
updated: '2026-05-28'
---

# 공통 API 응답 설계

**문서 버전:** v2.0  
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

---

<!-- crossref:auto -->
## 7. 연관 도메인 / 서브도메인 / 관계

_이 표는 상호참조 Agent가 자동으로 유지합니다 — 직접 편집한 내용은 다음 적재 시 덮어쓰여집니다._

| 도메인 | 서브도메인 (페이지) | 관계 | 핵심 사유 | 함께 볼 때 |
|---|---|---|---|---|
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-구현]] | 구현 | 공통 API 응답 설계를 구현하는 문서. | 공통 API 응답의 설계와 구현을 함께 검토하여 일관성을 확인해야 한다. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-요구사항]] | 구현 | 공통 API 응답 요구사항을 구현하는 문서. | 공통 API 응답의 설계와 요구사항을 함께 검토하여 일관성을 확인해야 한다. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-구현]] | 구체화 | 구현 문서가 설계 문서를 구체화함. | API 응답의 설계를 이해한 후, 실제 구현을 확인하기 위해 구현 문서를 참조해야 함. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-테스트]] | 검증 | 테스트 문서가 설계 문서를 검증함. | API 응답 설계를 검증하기 위해 테스트 문서를 함께 확인해야 함. |
<!-- /crossref:auto -->
