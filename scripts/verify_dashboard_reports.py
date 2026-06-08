#!/usr/bin/env python3
"""Audit the dashboard workbook pages from the database.

Usage examples:
  python scripts/verify_dashboard_reports.py
  python scripts/verify_dashboard_reports.py --annee 2025 --json-out /tmp/dashboard-2025.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.views.dashboard import (  # noqa: E402
    WORKBOOK_SHEETS,
    _build_dataset,
    _build_sheet_page,
    _build_widgets,
)
from wsgi import app  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Vérifie les calculs du dashboard IRVA.")
    parser.add_argument("--filiere", default="")
    parser.add_argument("--annee", default="")
    parser.add_argument("--mois", default="")
    parser.add_argument("--statut", default="complet")
    parser.add_argument("--q", default="")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--full", action="store_true", help="Inclut les lignes détaillées dans le snapshot JSON.")
    return parser.parse_args()


def build_filters(args):
    return {
        "filiere": args.filiere.strip(),
        "annee": str(args.annee).strip(),
        "mois": str(args.mois).strip(),
        "statut": args.statut.strip() or "complet",
        "q": args.q.strip(),
    }


def collect_snapshot(filters, full=False):
    with app.app_context():
        with app.test_request_context("/admin"):
            dataset = _build_dataset(filters)
            widgets = _build_widgets(dataset, filters)
            pages = {}
            for sheet in WORKBOOK_SHEETS:
                page = _build_sheet_page(sheet["key"], dataset, filters)
                pages[sheet["key"]] = simplify_page(page, full=full)

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "dataset": {
            "active_count": len(dataset["active"]),
            "all_count": len(dataset["all"]),
            "draft_count": len(dataset["drafts"]),
        },
        "widgets": [
            {
                "key": widget["key"],
                "sheet_name": widget["sheet_name"],
                "title": widget["title"],
                "value": widget["value"],
                "value_label": widget["value_label"],
            }
            for widget in widgets
        ],
        "pages": pages,
    }
    snapshot["checks"] = run_checks(snapshot)
    return snapshot


def simplify_page(page, full=False):
    simplified = {
        "title": page["title"],
        "summary": page["summary"],
        "audit_rules": page.get("audit_rules", []),
        "sections": [],
    }
    for section in page["sections"]:
        entry = {"type": section["type"], "title": section["title"]}
        if section["type"] == "cards":
            entry["cards"] = section["cards"]
        elif section["type"] == "table":
            entry["columns"] = section["columns"]
            entry["row_count"] = len(section.get("rows", []))
            entry["rows"] = section.get("rows", [])
        elif section["type"] == "notes":
            entry["items"] = section.get("items", [])
        elif section["type"] == "chart":
            chart = section["chart"]
            entry["labels_count"] = len(chart.get("data", {}).get("labels", []))
            entry["dataset_count"] = len(chart.get("data", {}).get("datasets", []))
            if full:
                entry["chart"] = chart
        simplified["sections"].append(entry)
    return simplified


def run_checks(snapshot):
    pages = snapshot["pages"]
    active_count = snapshot["dataset"]["active_count"]
    all_count = snapshot["dataset"]["all_count"]
    draft_count = snapshot["dataset"]["draft_count"]

    checks = []
    checks.append(check("all sheets built", len(pages) == len(WORKBOOK_SHEETS), expected=len(WORKBOOK_SHEETS), actual=len(pages)))
    checks.append(
        check(
            "decharge row count matches all_count",
            get_row_count(pages, "decharge-donnees", "Formulaires") == all_count,
            expected=all_count,
            actual=get_row_count(pages, "decharge-donnees", "Formulaires"),
        )
    )
    checks.append(
        check(
            "brouillon row count matches draft_count",
            get_row_count(pages, "brouillon", "Brouillons ouverts") == draft_count,
            expected=draft_count,
            actual=get_row_count(pages, "brouillon", "Brouillons ouverts"),
        )
    )
    checks.append(
        check(
            "tableau calcul row count matches all_count",
            get_row_count(pages, "tableau-calcul", "Vue normalisee") == all_count,
            expected=all_count,
            actual=get_row_count(pages, "tableau-calcul", "Vue normalisee"),
        )
    )
    checks.append(
        check(
            "anim par mag sums to active_count",
            sum_first_numeric_column(pages, "anim-par-mag", "Classement magasins", 3) == active_count,
            expected=active_count,
            actual=sum_first_numeric_column(pages, "anim-par-mag", "Classement magasins", 3),
        )
    )
    checks.append(
        check(
            "synthese des donnees row totals sum to active_count",
            sum_last_numeric_column(pages, "synthese-des-donnees", "Croisement enseigne x filiere") == active_count,
            expected=active_count,
            actual=sum_last_numeric_column(pages, "synthese-des-donnees", "Croisement enseigne x filiere"),
        )
    )
    checks.append(
        check(
            "synthese globale filiere counts sum to active_count",
            sum_second_column(pages, "synthese-global", "Repartition par filiere") == active_count,
            expected=active_count,
            actual=sum_second_column(pages, "synthese-global", "Repartition par filiere"),
        )
    )
    return checks


def check(name, ok, expected=None, actual=None):
    return {
        "name": name,
        "ok": bool(ok),
        "expected": expected,
        "actual": actual,
    }


def get_section(page_map, page_key, title):
    for section in page_map[page_key]["sections"]:
        if section["title"] == title:
            return section
    raise KeyError(f"Section '{title}' not found in page '{page_key}'")


def get_row_count(page_map, page_key, title):
    return get_section(page_map, page_key, title).get("row_count", 0)


def _to_int(value):
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(" ", "").strip()
        return int(cleaned) if cleaned and cleaned not in {"—", ""} else 0
    return 0


def sum_first_numeric_column(page_map, page_key, title, index):
    section = get_section(page_map, page_key, title)
    total = 0
    for row in section.get("rows", []):
        total += _to_int(row[index])
    return total


def sum_last_numeric_column(page_map, page_key, title):
    section = get_section(page_map, page_key, title)
    total = 0
    for row in section.get("rows", []):
        total += _to_int(row[-1])
    return total


def sum_second_column(page_map, page_key, title):
    section = get_section(page_map, page_key, title)
    total = 0
    for row in section.get("rows", []):
        total += _to_int(row[1])
    return total


def main():
    args = parse_args()
    snapshot = collect_snapshot(build_filters(args), full=args.full)
    failures = [item for item in snapshot["checks"] if not item["ok"]]

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Snapshot generated: {snapshot['generated_at']}")
    print(f"Filters: {json.dumps(snapshot['filters'], ensure_ascii=False)}")
    print(
        "Dataset:",
        f"active={snapshot['dataset']['active_count']}",
        f"all={snapshot['dataset']['all_count']}",
        f"draft={snapshot['dataset']['draft_count']}",
    )
    for item in snapshot["checks"]:
        status = "OK" if item["ok"] else "FAIL"
        print(f"[{status}] {item['name']} (expected={item['expected']}, actual={item['actual']})")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
