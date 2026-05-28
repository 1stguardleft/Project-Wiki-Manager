# 상품 관리 - SKU 식별 - 구현 (2차)

**문서 버전:** v2.0 (2차)
**도메인 / 서브도메인:** 상품 관리 / SKU 식별
**SDLC 단계:** 구현
**변경 요점 (vs 1차):** UNIQUE 인덱스, 정규식 검증, findBySku 메서드, 단건 조회 컨트롤러.

## 1. 구현 범위

DDL에 UNIQUE 인덱스 추가, DTO에 @Pattern 적용, Repository/Controller에 SKU 단건 조회 추가.

## 2. 구현 항목 체크리스트

- [ ] DDL: `ALTER TABLE product ADD CONSTRAINT uk_product_sku UNIQUE(sku);`
- [ ] DTO: `@Pattern(regexp = "^[A-Z0-9-]{3,30}$")`
- [ ] `existsBySku`, `findBySku` derived query
- [ ] `GET /api/products/sku/{sku}` 핸들러
- [ ] [[전역예외처리]]: `DataIntegrityViolationException` → 409 + DUPLICATE_SKU
- [ ] 마이그레이션: 기존 중복 SKU 정리 스크립트 제공
- [ ] 단위/통합 테스트

## 3. 적용 기술

- Hibernate Validator(@Pattern)
- Spring Data derived query
- DB UNIQUE 제약 + Service 사전 체크

## 4. 단계별 작업 순서

1. 정규식 정의 → 2. DTO 적용 → 3. existsBySku/findBySku → 4. UNIQUE 마이그레이션(중복 정리 → DDL) → 5. 핸들러 → 6. 예외 매핑 → 7. 테스트

## 5. 위험 요소

| 위험 | 대응 |
|---|---|
| 기존 중복 SKU로 UNIQUE 적용 실패 | 마이그레이션 전 중복 보고서 + 일괄 수정 |
| 형식 변경으로 외부 시스템 영향 | 점진 적용 (`@Pattern` 우선 enforced) |

## 6. 검증 포인트

- 형식 미준수 → 400
- 중복 → 409
- 미존재 SKU 조회 → 404

## 7. 연관 작업

| 연관 | 관계 |
|---|---|
| [[상품기본정보]] | sku 컬럼 공유 |
| [[전역예외처리]] | UNIQUE 위반 변환 |
