#!/usr/bin/env python3
"""
Backfill des champs `code_departement` et `region` à partir du code postal.

Usage:
  python scripts/backfill_regions.py
  python scripts/backfill_regions.py --dry-run
"""

from __future__ import annotations

import argparse

from app.utils import infer_department_code, infer_region
from models import CompteRendu, db
from wsgi import app


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill des régions à partir du code postal")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien en base")
    return parser.parse_args()


def main():
    args = parse_args()

    with app.app_context():
        updated = 0
        unchanged = 0

        records = CompteRendu.query.order_by(CompteRendu.id).all()
        for cr in records:
            next_dept = infer_department_code(cr.code_postal)
            next_region = infer_region(cr.code_postal, next_dept)

            changed = False
            if next_dept and cr.code_departement != next_dept:
                cr.code_departement = next_dept
                changed = True
            if next_region and cr.region != next_region:
                cr.region = next_region
                changed = True

            if changed:
                updated += 1
            else:
                unchanged += 1

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()

        print(f"updated={updated} unchanged={unchanged} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
