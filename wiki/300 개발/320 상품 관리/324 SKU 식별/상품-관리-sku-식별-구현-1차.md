---
title: SKU 식별 구현 문서
slug: 상품-관리-sku-식별-구현-1차
type: deliverable
sdlc_phase: implementation
domain: 상품 관리
subdomain: SKU 식별
status: active
source_count: 2
sources:
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-150400-SKU식별.md.md
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-205003-SKU식별.md.md
updated: '2026-05-28'
---

# 상품 관리 - SKU 식별 - 구현

**문서 버전:** v2.0  
**도메인 / 서브도메인:** 상품 관리 / SKU 식별  
**SDLC 단계:** 구현  
**변경 요점 (vs 1차):** UNIQUE 인덱스, 정규식 검증, findBySku 메서드, 단건 조회 컨트롤러.

## 1. 구현 범위

DDL에 UNIQUE 인덱스 추가, DTO에 @Pattern 적용, Repository/Controller에 SKU 단건 조회 추가. Product 엔티티에 `sku` 컬럼 추가 (NOT NULL). 별도 검증·인덱스 없음.

## 2. 구현 항목 체크리스트

- [ ] DDL: `ALTER TABLE product ADD CONSTRAINT uk_product_sku UNIQUE(sku);`
- [ ] DTO: `@Pattern(regexp = "^[A-Z0-9-]{3,30}$")`
- [ ] JPA `@Column(nullable = false)`
- [ ] `existsBySku`, `findBySku` derived query
- [ ] `GET /api/products/sku/{sku}` 핸들러
- [ ] [[전역예외처리]]: `DataIntegrityViolationException` → 409 + DUPLICATE_SKU
- [ ] 마이그레이션: 기존 중복 SKU 정리 스크립트 제공
- [ ] 단위/통합 테스트
- [ ] 엔티티 필드 추가
- [ ] DTO 동기화
- [ ] 등록·수정 검증 확인
- [ ] sku 누락 시 400 오류 발생

## 3. 적용 기술

- Hibernate Validator(@Pattern)
- Spring Data derived query
- DB UNIQUE 제약 + Service 사전 체크

## 4. 단계별 작업 순서

1. 정규식 정의 
2. DTO 적용 
3. existsBySku/findBySku 
4. UNIQUE 마이그레이션(중복 정리 → DDL) 
5. 핸들러 
6. 예외 매핑 
7. 테스트

## 5. 위험 요소

| 위험 | 대응 |
|---|---|
| 기존 중복 SKU로 UNIQUE 적용 실패 | 마이그레이션 전 중복 보고서 + 일괄 수정 |
| 형식 변경으로 외부 시스템 영향 | 점진 적용 (`@Pattern` 우선 enforced) |

## 6. 검증 포인트

- 형식 미준수 → 400
- 중복 → 409
- 미존재 SKU 조회 → 404
- sku 누락 시 400 오류 발생

## 7. 연관 작업

| 연관 | 관계 |
|---|---|
| [[상품기본정보]] | sku 컬럼 공유 |
| [[전역예외처리]] | UNIQUE 위반 변환 |

---

<!-- crossref:auto -->
## 8. 연관 도메인 / 서브도메인 / 관계

_이 표는 상호참조 Agent가 자동으로 유지합니다 — 직접 편집한 내용은 다음 적재 시 덮어쓰여집니다._

| 도메인 | 서브도메인 (페이지) | 관계 | 핵심 사유 | 함께 볼 때 |
|---|---|---|---|---|
| 상품 관리 | SKU 식별 [[상품-관리-sku-식별-설계-1차]] | 구현 | 설계 문서의 내용을 구현한 사례. | SKU 필드의 구현을 이해하기 위해 설계 문서와 함께 봐야 한다. |
| 상품 관리 | SKU 식별 [[상품-관리-sku-식별-요구사항-1차]] | 구현 | 요구사항 문서의 내용을 구현한 사례. | SKU 필드의 구현을 이해하기 위해 요구사항 문서와 함께 봐야 한다. |
| — | — [[상품-관리-sku-식별-설계-2차]] | 구현 | 설계 문서에서 정의한 내용을 구현함. | SKU 식별의 설계와 구현을 함께 검토하여 일관성을 확인할 수 있다. |
| — | — [[상품-관리-sku-식별-요구사항-2차]] | 구현 | 요구사항 문서의 내용을 구현함. | SKU 식별의 요구사항과 구현을 비교하여 기능이 제대로 반영되었는지 확인할 수 있다. |
<!-- /crossref:auto -->
