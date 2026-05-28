"""KPI aggregation for the project performance dashboard.

Computes the four KPIs defined in the service plan from on-disk artifacts so
the dashboard can show current value + how it was calculated:

  ① 문서 중복 제거율 (목표 ≥60%) — `wiki/log.md`의 merge / 전체 적재 결정
  ② 문서 탐색 시간 (목표 50%↓) — 시스템 외부 측정 필요. 데이터 없음.
  ③ 정제 정확도   (목표 ≥80%) — `merge_store`의 coverage 평균
  ④ 자동 처리 비율 (목표 ≥70%) — 전체 적재 − 수동(manual/pending)
"""
from __future__ import annotations

import re

from app import config
from app.agents import merge_store

# Each KPI carries its own calculation breakdown (`steps`) so the UI can show
# exactly how the number was derived — keeps the dashboard "transparent".


_INGEST_HEADER = re.compile(
    r"^##\s*\[(?P<ts>[^\]]+)\]\s*ingest\s*\|\s*(?P<title>.+)$")
_DETAIL_LINE = re.compile(r"action=(?P<action>\w+)")
# 회차 접미사(예: " (1차)", " (2차 신규)") 제거 — 동일 문서의 재적재 여부를
# 판정하기 위한 정규화. 본문 제목이 같으면 한 주제로 묶인다.
_VERSION_SUFFIX = re.compile(r"\s*\([^()]*\d+\s*차[^()]*\)\s*$")


def _topic_key(title: str) -> str:
    """Strip the (N차 …) suffix so 1차/2차 of the same doc share a key."""
    return _VERSION_SUFFIX.sub("", title).strip()


def _read_ingest_log() -> list[dict]:
    """Parse `wiki/log.md` into a list of {ts, title, action} ingest entries.

    Each entry is the header line `## [ts] ingest | title` followed by an
    `action=...` detail line. `edit` / `delete` actions (the action= verb on
    non-ingest entries) are ignored — only initial ingestion decisions count
    toward the merge / create ratio.
    """
    if not config.LOG_FILE.exists():
        return []
    entries: list[dict] = []
    lines = config.LOG_FILE.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        m = _INGEST_HEADER.match(lines[i])
        if not m:
            i += 1
            continue
        action = ""
        # detail is normally the next non-empty line
        for j in range(i + 1, min(i + 4, len(lines))):
            d = _DETAIL_LINE.search(lines[j])
            if d:
                action = d.group("action")
                break
        entries.append({"ts": m.group("ts"), "title": m.group("title").strip(),
                        "action": action})
        i += 1
    return entries


def _pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return round(100.0 * num / den, 1)


def _deduplication_rate(ingest: list[dict]) -> dict:
    """KPI ①: 재적재 기회 중 실제로 병합된 비율.

    1차 적재처럼 코퍼스가 비어 있던 시점의 적재는 무조건 create이므로 분모에
    포함하면 비율이 비대해진다(중복 제거 *능력*과 무관). 동일 주제(회차 접미사
    제거 후 같은 제목)가 이미 한 번 적재된 적이 있는 항목만 분모에 넣는다.
    """
    total = len(ingest)
    seen: set[str] = set()
    first_ingest = 0      # 분모 제외: 그 주제의 첫 적재 (코퍼스에 비교 대상 없음)
    reingest_total = 0    # 분모: 재적재 기회 (이미 같은 주제가 한 번 들어와 있음)
    reingest_merges = 0   # 분자: 그 중 실제로 병합으로 처리된 건
    for e in ingest:
        key = _topic_key(e["title"])
        if key not in seen:
            seen.add(key)
            first_ingest += 1
            continue
        reingest_total += 1
        if e["action"] == "merge":
            reingest_merges += 1
    value = _pct(reingest_merges, reingest_total)
    has_data = reingest_total > 0
    return {
        "key": "dedup_rate",
        "name": "문서 중복 제거율",
        "target": 60.0,
        "current": value if has_data else 0.0,
        "unit": "%",
        "status": "measured" if has_data else "empty",
        "summary": ("동일 주제가 이미 한 번 적재된 뒤 다시 들어온 문서 중 "
                    "기존 페이지로 병합된 비율") if has_data else
                   "재적재 기회가 아직 발생하지 않았습니다 (모두 첫 적재)",
        "formula": "재적재 중 merge 건수 ÷ 재적재 기회 × 100",
        "steps": [
            {"label": "전체 적재 결정 (log.md ingest 항목)", "value": total},
            {"label": "첫 적재 (분모 제외)", "value": first_ingest,
             "detail": "그 주제의 첫 적재 — 코퍼스에 비교 대상이 없어 무조건 신규 생성"},
            {"label": "재적재 기회 (분모)", "value": reingest_total,
             "detail": "같은 주제(회차 접미사 무시)가 이미 적재된 뒤 다시 들어온 건"},
            {"label": "그 중 병합 처리 (분자)", "value": reingest_merges},
            {"label": "중복 제거율", "value": f"{value}%",
             "detail": f"{reingest_merges} / {reingest_total}"},
        ],
        "sources": ["wiki/log.md"],
        "notes": ("'(N차)' 접미사를 제거한 제목이 같으면 동일 주제로 봅니다. "
                  "1차 적재 21건은 코퍼스가 비어 있던 시점이라 분모에서 제외됩니다."),
    }


def _search_time(ingest: list[dict]) -> dict:
    """KPI ②: cannot be measured from inside the system."""
    return {
        "key": "search_time",
        "name": "문서 탐색 시간 감소",
        "target": 50.0,
        "current": None,
        "unit": "%",
        "status": "unmeasured",
        "summary": "시스템 내부 측정 데이터가 없어 외부 사용자 실험이 필요한 지표입니다",
        "formula": "(도입 전 평균 탐색 시간 − 도입 후 평균 탐색 시간) ÷ 도입 전 × 100",
        "steps": [
            {"label": "도입 전 평균 탐색 시간", "value": "—",
             "detail": "시스템 외부 측정 필요"},
            {"label": "도입 후 평균 탐색 시간", "value": "—",
             "detail": "시스템 외부 측정 필요"},
            {"label": "사용자 행동 추적", "value": "미수집",
             "detail": "검색→페이지 도달 latency·시도 횟수 등을 쌓고 있지 않음"},
        ],
        "sources": ["—"],
        "notes": ("본래 KPI 정의가 '이전 환경 대비 50% 감소'라서, 비교 기준이 "
                  "본 시스템 바깥에 있습니다. 정량화하려면 (a) 사용자 인터뷰·실험 "
                  "또는 (b) 검색→첫 도달 평균 시도 횟수 같은 프록시 지표를 새로 "
                  "추적해야 합니다."),
    }


def _purification_accuracy(records: list[dict]) -> dict:
    """KPI ③: verify 노드가 산출한 coverage(0~1)의 평균."""
    with_cov = [r for r in records if isinstance(r.get("coverage"), (int, float))]
    n = len(with_cov)
    avg = sum(r["coverage"] for r in with_cov) / n if n else 0.0
    above = sum(1 for r in with_cov if r["coverage"] >= 0.8)
    value = round(avg * 100, 1)
    return {
        "key": "purification_accuracy",
        "name": "정제 정확도",
        "target": 80.0,
        "current": value,
        "unit": "%",
        "status": "measured" if n > 0 else "empty",
        "summary": "병합 결과가 양 출처의 정보를 보존한 평균 비율 (verify Agent 측정)"
                   if n > 0 else "병합 이력이 없어 측정할 수 없습니다",
        "formula": "Σ coverage ÷ 병합 건수 × 100",
        "steps": [
            {"label": "측정된 병합 건수", "value": n,
             "detail": "coverage가 기록된 merge_store 레코드"},
            {"label": "평균 coverage", "value": f"{round(avg, 3)}"},
            {"label": "coverage ≥ 0.8 비율", "value": _pct(above, n) if n else 0.0,
             "detail": f"{above} / {n}"},
            {"label": "정제 정확도", "value": f"{value}%"},
        ],
        "sources": ["wiki/graph/merges.json (merge_store)"],
    }


def _automation_rate(ingest: list[dict], records: list[dict]) -> dict:
    """KPI ④: 사람 개입 없이 끝난 적재 결정 비율.

    수동 보류 = merge_store 레코드 중 `status == 'pending'`. 그 외(create, 그리고
    auto_resolved / accepted / rejected / reconciled로 끝난 merge)는 모두 자동.
    """
    total = len(ingest)
    pending = sum(1 for r in records if r.get("status") == "pending")
    auto = max(total - pending, 0)
    value = _pct(auto, total)

    # policy breakdown for the explanation panel
    by_policy: dict[str, int] = {}
    for r in records:
        by_policy[r.get("policy") or "(none)"] = by_policy.get(r.get("policy") or "(none)", 0) + 1
    policy_lines = [{"label": f"  · {k}", "value": v} for k, v in sorted(by_policy.items())]

    return {
        "key": "automation_rate",
        "name": "자동 처리 비율",
        "target": 70.0,
        "current": value,
        "unit": "%",
        "status": "measured" if total > 0 else "empty",
        "summary": "사람 검토 없이 파이프라인이 끝까지 처리한 적재 비율" if total > 0
                   else "적재 이력이 아직 없습니다",
        "formula": "(전체 적재 − 수동 검토 대기) ÷ 전체 적재 × 100",
        "steps": [
            {"label": "전체 적재 결정", "value": total},
            {"label": "수동 검토 대기 (status=pending)", "value": pending},
            {"label": "자동 처리 완료", "value": auto},
            {"label": "자동 처리 비율", "value": f"{value}%",
             "detail": f"{auto} / {total}"},
            *( [{"label": "병합 정책 분포", "value": ""}, *policy_lines]
               if policy_lines else [] ),
        ],
        "sources": ["wiki/log.md", "wiki/graph/merges.json"],
    }


def compute() -> dict:
    """Aggregate all four KPIs into a single payload for the dashboard."""
    ingest = _read_ingest_log()
    records = merge_store.list_records()
    return {
        "metrics": [
            _deduplication_rate(ingest),
            _search_time(ingest),
            _purification_accuracy(records),
            _automation_rate(ingest, records),
        ],
        "totals": {
            "ingest_decisions": len(ingest),
            "merge_records": len(records),
        },
    }
