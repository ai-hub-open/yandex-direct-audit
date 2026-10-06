#!/usr/bin/env python3
"""changes_log.py — журнал правок аккаунта для режима ВЕДЕНИЯ (append-only).

Используется только в режиме ведения (см. references/lead-write-safety.md).
Ведёт <workspace>/changes_log.jsonl — по одной строке на каждую правку,
залитую в аккаунт Директа, с before/after для отката.

Без внешних зависимостей (только стандартная библиотека).

Подкоманды:
  record        — дописать одну правку (before обязателен; after — если запись удалась)
  list          — показать журнал (весь или по циклу)
  rollback-plan — собрать план отката: для обратимых применённых правок вернуть before

Примеры:
  python -m scripts.changes_log record --workspace lead/acme \
      --cycle 2026-08-28 --object-type campaign --object-id 12345 \
      --field ExcludedSites --tool campaigns_update --class reversible \
      --before '["games.example"]' --after '["games.example","spam.example"]' \
      --status applied --note "чистка площадок РСЯ"

  python -m scripts.changes_log rollback-plan --workspace lead/acme --cycle 2026-08-28
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

LOG_NAME = "changes_log.jsonl"
REVERSIBLE = "reversible"
IRREVERSIBLE = "irreversible"
VALID_CLASS = {REVERSIBLE, IRREVERSIBLE}
VALID_STATUS = {"pending", "applied", "failed"}


def _log_path(workspace: str) -> str:
    return os.path.join(workspace, LOG_NAME)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _maybe_json(value):
    """before/after могут прийти как JSON или как обычная строка — храним как есть."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _read_entries(workspace: str) -> list[dict]:
    path = _log_path(workspace)
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"⚠️  пропущена битая строка журнала: {line[:80]}", file=sys.stderr)
    return entries


def cmd_record(args: argparse.Namespace) -> int:
    if args.klass not in VALID_CLASS:
        print(f"ошибка: --class должен быть {VALID_CLASS}", file=sys.stderr)
        return 2
    if args.status not in VALID_STATUS:
        print(f"ошибка: --status должен быть {VALID_STATUS}", file=sys.stderr)
        return 2

    os.makedirs(args.workspace, exist_ok=True)
    existing = _read_entries(args.workspace)
    seq = len(existing) + 1
    entry = {
        "id": f"{args.cycle}-{seq:04d}",
        "ts": _now_iso(),
        "cycle": args.cycle,
        "object_type": args.object_type,
        "object_id": args.object_id,
        "field": args.field,
        "tool": args.tool,
        "class": args.klass,
        "status": args.status,
        "before": _maybe_json(args.before),
        "after": _maybe_json(args.after),
        "note": args.note,
    }
    with open(_log_path(args.workspace), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"✅ записано: {entry['id']}  {entry['object_type']}#{entry['object_id']} "
          f"{entry['field']} [{entry['class']}/{entry['status']}]")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = _read_entries(args.workspace)
    if args.cycle:
        entries = [e for e in entries if e.get("cycle") == args.cycle]
    if not entries:
        print("журнал пуст")
        return 0
    for e in entries:
        print(f"{e.get('id'):<16} {e.get('ts'):<20} "
              f"{e.get('object_type')}#{e.get('object_id')} "
              f"{e.get('field')} [{e.get('class')}/{e.get('status')}] "
              f"{e.get('note') or ''}")
    return 0


def cmd_rollback_plan(args: argparse.Namespace) -> int:
    entries = _read_entries(args.workspace)
    if args.cycle:
        entries = [e for e in entries if e.get("cycle") == args.cycle]

    # Откатываемы только обратимые правки, которые реально применились.
    plan = [e for e in entries
            if e.get("class") == REVERSIBLE and e.get("status") == "applied"]
    skipped = [e for e in entries
               if e.get("class") == IRREVERSIBLE and e.get("status") == "applied"]

    out = {
        "workspace": args.workspace,
        "cycle": args.cycle,
        "generated": _now_iso(),
        "restore": [
            {
                "id": e["id"],
                "tool": e.get("tool"),
                "object_type": e.get("object_type"),
                "object_id": e.get("object_id"),
                "field": e.get("field"),
                "set_back_to": e.get("before"),   # вернуть это значение через тот же тул + гейт
                "was_changed_to": e.get("after"),
                "note": e.get("note"),
            }
            for e in plan
        ],
        "cannot_auto_rollback": [
            {"id": e["id"], "object_type": e.get("object_type"),
             "object_id": e.get("object_id"), "field": e.get("field"),
             "reason": "необратимая правка — откат только вручную"}
            for e in skipped
        ],
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    if not plan:
        print("\n(нечего откатывать: нет обратимых применённых правок)", file=sys.stderr)
    if skipped:
        print(f"\n⚠️  {len(skipped)} необратимых правок — откат только вручную", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="changes_log", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("record", help="дописать одну правку")
    r.add_argument("--workspace", required=True, help="папка проекта ведения, напр. lead/<slug>")
    r.add_argument("--cycle", required=True, help="id цикла (дата), напр. 2026-08-28")
    r.add_argument("--object-type", required=True,
                   help="campaign|adgroup|ad|keyword|bidmodifier|...")
    r.add_argument("--object-id", required=True)
    r.add_argument("--field", required=True, help="что менялось: ExcludedSites, Bid, Status, ...")
    r.add_argument("--tool", required=True, help="суффикс write-тула, напр. campaigns_update")
    r.add_argument("--class", dest="klass", required=True, choices=sorted(VALID_CLASS),
                   help="reversible | irreversible")
    r.add_argument("--before", default=None, help="значение ДО (JSON или строка) — обязательно по смыслу")
    r.add_argument("--after", default=None, help="значение ПОСЛЕ (JSON или строка)")
    r.add_argument("--status", default="applied", choices=sorted(VALID_STATUS))
    r.add_argument("--note", default=None)
    r.set_defaults(func=cmd_record)

    l = sub.add_parser("list", help="показать журнал")
    l.add_argument("--workspace", required=True)
    l.add_argument("--cycle", default=None, help="фильтр по циклу")
    l.set_defaults(func=cmd_list)

    rb = sub.add_parser("rollback-plan", help="план отката обратимых правок")
    rb.add_argument("--workspace", required=True)
    rb.add_argument("--cycle", default=None, help="фильтр по циклу")
    rb.set_defaults(func=cmd_rollback_plan)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
