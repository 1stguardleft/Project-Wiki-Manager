---
title: 상품 관리 SKU 식별 설계 문서
slug: 상품-관리-sku-식별-설계-1차
type: deliverable
sdlc_phase: design
domain: 상품 관리
subdomain: SKU 식별
status: active
source_count: 2
sources:
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-144846-SKU식별.md.md
- /home/lstguardleft/workspace/Project-Wiki-Manager/raw/20260528-203321-SKU식별.md.md
updated: '2026-05-28'
---

# 상품 관리 - SKU 식별 - 설계

**문서 버전:** v2.0  
**도메인 / 서브도메인:** 상품 관리 / SKU 식별  
**SDLC 단계:** 설계  
**변경 요점 (vs 1차):** UNIQUE 제약 + 정규식 검증 + `findBySku` 추가.

## 1. 설계 개요

SKU는 DB UNIQUE + Service 사전 검증으로 중복을 차단하고, 형식은 정규식으로 검증한다. 형식 검증이 없을 경우 자유 문자열로 입력될 수 있으며, 이로 인해 데이터의 무결성이 저해될 수 있다. 또한, UNIQUE 제약이 없으면 SKU의 중복이 발생할 수 있으며, 인덱스가 없을 경우 검색 시 풀스캔이 발생할 수 있다.

## 2. 구성 요소

| 계층 | 구성 요소 | 역할 |
|---|---|---|
| Entity | Product | sku UNIQUE 컬럼 |
| Repository | ProductRepository | existsBySku, findBySku |
| Service | ProductService | 형식 검증 + 중복 사전 체크 |
| Controller | ProductController | SKU 단건 조회 |

## 3. 데이터 모델

| 컬럼 | 타입 | 제약 |
|---|---|---|
| sku | varchar(30) | NOT NULL, UNIQUE |

인덱스: `idx_product_sku` (UNIQUE)

## 4. API 인터페이스

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /api/products/sku/{sku} | SKU로 단건 조회 (2차 신규) |

## 5. 처리 흐름

- 등록/수정: 정규식 검증 → `existsBySku` 사전 체크 → save (UNIQUE 예외 fallback)
- 조회: `findBySku(sku)` → 미존재 시 404

## 6. 설계 규칙

- 정규식 `^[A-Z0-9-]{3,30}$`.
- DB UNIQUE 위반 시 [[전역예외처리]]가 409 + DUPLICATE_SKU로 변환.

## 7. 의존 서브도메인

| 연관 기능 | 의존 내용 |
|---|---|
| [[상품기본정보]] | sku 컬럼 |



> ℹ️ 변경: UNIQUE 제약, 형식 검증, 인덱스 추가. 최신 문서(v2.0)에서 반영된 내용으로, SKU의 중복 방지 및 형식 검증을 통해 데이터 무결성을 강화함. 형식 검증이 없을 경우 자유 문자열로 입력될 수 있으며, UNIQUE 제약이 없으면 SKU의 중복이 발생할 수 있다. 인덱스가 없을 경우 검색 시 풀스캔이 발생할 수 있다.

---

<!-- crossref:auto -->
## 8. 연관 도메인 / 서브도메인 / 관계

_이 표는 상호참조 Agent가 자동으로 유지합니다 — 직접 편집한 내용은 다음 적재 시 덮어쓰여집니다._

| 도메인 | 서브도메인 (페이지) | 관계 | 핵심 사유 | 함께 볼 때 |
|---|---|---|---|---|
| 상품 관리 | SKU 식별 [[상품-관리-sku-식별-구현-1차]] | 구현 | 설계 문서의 SKU 식별이 구현 문서에 반영됨. | SKU 식별의 설계와 구현을 함께 검토하여 기능의 일관성을 확인해야 한다. |
| 상품 관리 | SKU 식별 [[상품-관리-sku-식별-요구사항-1차]] | 구현 | 요구사항 문서의 내용이 설계에 반영됨. | SKU 식별 요구사항을 이해하기 위해 설계 문서를 함께 참고해야 한다. |
| — | — [[상품-관리-sku-식별-요구사항-2차]] | 구현 | 요구사항 문서에서 SKU의 UNIQUE 제약을 정의함. | SKU의 중복 방지 및 형식 검증을 이해하기 위해 두 문서를 함께 검토해야 함. |
<!-- /crossref:auto -->
