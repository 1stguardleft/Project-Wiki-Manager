# 상품 관리 - SKU 식별 - 설계 (2차)

**문서 버전:** v2.0 (2차)
**도메인 / 서브도메인:** 상품 관리 / SKU 식별
**SDLC 단계:** 설계
**변경 요점 (vs 1차):** UNIQUE 제약 + 정규식 검증 + `findBySku` 추가.

## 1. 설계 개요

SKU는 DB UNIQUE + Service 사전 검증으로 중복을 차단하고, 형식은 정규식으로 검증한다.

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
