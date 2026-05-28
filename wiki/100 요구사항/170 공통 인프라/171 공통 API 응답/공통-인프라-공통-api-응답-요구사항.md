---
title: 공통 API 응답 요구사항
slug: 공통-인프라-공통-api-응답-요구사항
type: deliverable
sdlc_phase: requirements
domain: 공통/인프라
subdomain: 공통 API 응답
status: active
source_count: 2
sources:
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-142142-공통API응답.md.md
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-202620-공통API응답.md.md
updated: '2026-05-28'
---

# 공통 API 응답 요구사항

**문서 버전:** v2.0  
**도메인 / 서브도메인:** 공통/인프라 / 공통 API 응답  
**SDLC 단계:** 요구사항  
**변경 요점 (vs 1차):** message/errorCode/timestamp 필드 추가, 페이지네이션 메타 표준화.

## 1. 개요

운영·디버깅 관점을 강화하기 위해 응답에 사용자에게 보여 줄 메시지와 머신리더블 errorCode, 발생 시각을 함께 반환한다. 페이지네이션 응답도 표준화한다. 1차에서 응답에 message·errorCode·timestamp는 포함하지 않음.

## 2. 사용자 시나리오

- 프론트엔드가 errorCode로 화면 동작을 분기한다(예: DUPLICATE_EMAIL → 이메일 입력 강조).
- 운영자가 timestamp로 사용자 신고 시점을 빠르게 매칭한다.

## 3. 기능 요구사항

| ID | 요구사항 | 설명 | 우선순위 |
|---|---|---|---|
| 응답-01 | 성공/실패 표시 | success boolean | 필수 |
| 응답-02 | data | 실제 데이터 | 필수 |
| 응답-03 | message | 사용자 안내 메시지 (신규) | 필수 |
| 응답-04 | errorCode | 머신 리더블 코드 (신규) | 필수 |
| 응답-05 | timestamp | 응답 생성 시각 (신규) | 필수 |
| 응답-06 | 페이지네이션 메타 | content/totalElements/totalPages 표준 (신규) | 필수 |

## 4. 응답 구조

| 필드 | 형식 | 설명 |
|---|---|---|
| success | boolean | 성공/실패 |
| data | object/array/null | 데이터 |
| message | 문자열 | 사용자용 메시지 |
| errorCode | 문자열 | 실패 시 식별자 (성공 시 null) |
| timestamp | ISO 8601 | 응답 생성 시각 |

## 5. 업무 규칙

- 성공 시 errorCode = null, message는 비어 있어도 OK.
- 실패 시 errorCode 필수 (UNKNOWN_ERROR 폴백 허용).
- timestamp는 UTC 또는 KST 일관 적용.
- 페이지네이션 응답은 `data` 안에 `content/totalElements/totalPages/number/size`.

## 6. 비기능 요구사항

- 직렬화 추가 지연 무시 가능.

## 7. 예외 처리

해당 응답 표준 자체. 응답 직렬화 실패 | 500 (전역 예외 처리에서 처리)

---

<!-- crossref:auto -->
## 8. 연관 도메인 / 서브도메인 / 관계

_이 표는 상호참조 Agent가 자동으로 유지합니다 — 직접 편집한 내용은 다음 적재 시 덮어쓰여집니다._

| 도메인 | 서브도메인 (페이지) | 관계 | 핵심 사유 | 함께 볼 때 |
|---|---|---|---|---|
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-구현]] | 구현 | 요구사항이 구현 문서에 적용된다. | 공통 API 응답의 요구사항을 이해한 후, 이를 구현하는 방법을 확인하기 위해 두 문서를 함께 봐야 한다. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-설계]] | 구체화 | 요구사항이 설계 문서로 구체화된다. | 공통 API 응답의 요구사항을 이해한 후, 이를 설계하는 방법을 확인하기 위해 두 문서를 함께 봐야 한다. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-테스트]] | 검증 | 요구사항이 테스트 문서에서 검증된다. | 공통 API 응답의 요구사항을 이해한 후, 이를 검증하는 테스트 방법을 확인하기 위해 두 문서를 함께 봐야 한다. |
<!-- /crossref:auto -->
