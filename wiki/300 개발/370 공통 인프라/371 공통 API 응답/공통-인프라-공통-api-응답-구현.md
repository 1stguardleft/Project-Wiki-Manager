---
title: 공통 API 응답 구현 문서
slug: 공통-인프라-공통-api-응답-구현
type: deliverable
sdlc_phase: implementation
domain: 공통/인프라
subdomain: 공통 API 응답
status: active
source_count: 2
sources:
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-150001-공통API응답.md.md
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-204902-공통API응답.md.md
updated: '2026-05-28'
---

# 공통 API 응답 구현

**문서 버전:** v2.0  
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
- [ ] success/data 직렬화 정확
- [ ] null 데이터 시 data:null 처리

## 3. 적용 기술

- Jackson, Spring Data Page
- `@JsonInclude(Include.ALWAYS)`

## 4. 단계별 작업 순서

1. DTO 확장 
2. 변환 유틸 
3. 핸들러 변경 
4. 클라이언트 영향 평가 
5. 마이그레이션

## 5. 위험 요소

| 위험 | 대응 |
|---|---|
| 1차 응답에 message 필드가 없어 클라이언트 코드 영향 | 추가 필드는 무시 가능 (downward 호환) |

## 6. 검증 포인트

- timestamp 포맷 일관
- PageResponse 필드 누락 0
- 직렬화 테스트

## 7. 연관 작업

| 연관 | 관계 |
|---|---|
| [[전역예외처리]] | errorCode 채움 |

---

<!-- crossref:auto -->
## 8. 연관 도메인 / 서브도메인 / 관계

_이 표는 상호참조 Agent가 자동으로 유지합니다 — 직접 편집한 내용은 다음 적재 시 덮어쓰여집니다._

| 도메인 | 서브도메인 (페이지) | 관계 | 핵심 사유 | 함께 볼 때 |
|---|---|---|---|---|
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-설계]] | 구현 | API 응답 설계가 구현에 반영된다. | 설계 문서를 통해 API 응답의 구조를 이해한 후, 구현 문서를 참고하여 실제 코드를 작성해야 한다. |
| 공통/인프라 | 공통 API 응답 [[공통-인프라-공통-api-응답-요구사항]] | 구현 | 요구사항이 구현에 직접적으로 반영된다. | 요구사항 문서를 통해 API 응답의 필수 요소를 이해한 후, 구현 문서를 참고하여 코드를 작성해야 한다. |
| 공통/인프라 | 전역 예외 처리 [[공통-인프라-전역-예외-처리-구현]] | 구현 | 전역 예외 처리 구현이 실패 응답 생성과 연결된다. | 전역 예외 처리 문서를 통해 실패 응답 생성 방식을 이해하고, 구현 문서에서 이를 적용해야 한다. |
<!-- /crossref:auto -->
