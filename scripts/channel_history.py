#!/usr/bin/env python3
"""channel_history.py — история каналов клиента по контракту (references/channel-history.md).

Считает выводы по порогам одинаково в каждом прогоне — без арифметики в голове модели.
Без внешних зависимостей (только стандартная библиотека). Read-only: в аккаунт не пишет.

Подкоманды:
  build     — собрать channel_history.json + channel_history.md: строки Директа по типам
              кампаний из TSV-отчёта (--direct-tsv) + строки из spec (другие каналы, черновики)
  validate  — проверить готовый channel_history.json (свой или пришедший от стратега/менеджера)

spec.json — шапка и ручные строки (ключи — как в контракте):
  {
    "site": "example.ru",
    "period": "2026-04-01..2026-09-30",              # выбирает человек, по умолчанию не ставим
    "lead_definition": {"goal_ids": [123], "names": ["Заявка"], "how": "ключевые цели стратегий"},
    "thresholds": {"min_clicks": 30, "min_days": 14, "target_cpa": 3000, "expensive_ratio": 1.5},
    "created_by": "yandex-direct-audit 2026-10-08",
    "rows": [
      {"channel": "vk_ads", "campaign_type": "—", "status": "ran", "spend": 50000,
       "clicks": null, "leads": 0, "source": "client", "note": "весна 2026"},
      {"channel": "yandex_direct", "campaign_type": "rsya", "account": "login-1",
       "status": "never_ran", "source": "direct", "note": "не прошла модерацию"}
    ]
  }
В ручных строках можно передать "days" (дней с показами) — он нужен только для вывода
«мало данных» и в файл не пишется (в контракте такого поля нет, число уходит в verdict_reason).

TSV Директа — report_campaign за период с полями CampaignId, Date, Impressions, Clicks, Cost и
конверсиями по выбранным целям (Conversions или Conversions_<цель>_<модель> — суммируются).
--campaign-types — JSON {"<CampaignId>": "search" | "rsya" | "unified" | ...} из 01_account_map.json.

Примеры:
  python -m scripts.channel_history build --spec spec.json \\
      --direct-tsv campaigns_daily.tsv --campaign-types types.json \\
      --account login-1 --counter-id 12345678 --link green \\
      --out-dir direct-audits/acme

  python -m scripts.channel_history validate --input marketing-campaigns/acme/channel_history.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys

# Windows-консоль по умолчанию cp1252/cp866 — без этого падает вывод кириллицы и ✅/⚠️.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

MICRO = 1_000_000
DEFAULT_THRESHOLDS = {"min_clicks": 30, "min_days": 14, "target_cpa": None, "expensive_ratio": 1.5}

HEADER_KEYS = ["site", "period", "lead_definition", "thresholds", "created_by"]
ROW_KEYS = ["channel", "campaign_type", "account", "status", "spend", "clicks", "leads", "cpa",
            "counter_id", "link", "source", "verdict", "verdict_reason", "note"]
STATUSES = {"ran", "never_ran", "archived"}
VERDICTS = {"works", "expensive", "no_leads", "no_data", "never_ran"}
SOURCES = {"direct", "metrika", "client"}
LINKS = {"green", "yellow", "red", None}
KNOWN_CHANNELS = {"yandex_direct", "vk_ads", "telegram_ads", "other"}

VERDICT_RU = {"works": "работает", "expensive": "дорого", "no_leads": "не дал лидов",
              "no_data": "мало данных", "never_ran": "не запускали"}
TYPE_ORDER = ["search", "unified", "rsya", "retargeting"]
TYPE_RU = {"search": "Поиск", "rsya": "РСЯ", "unified": "ЕПК", "retargeting": "ретаргет", "—": "—"}
CHANNEL_RU = {"yandex_direct": "Яндекс Директ", "vk_ads": "VK Ads", "telegram_ads": "Telegram Ads",
              "other": "Другое"}


# ---------------------------------------------------------------- форматирование

def rub(v) -> str:
    if v is None:
        return "—"
    return f"{round(v):,}".replace(",", " ") + " ₽"


def num(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:.1f}"
    return f"{int(v):,}".replace(",", " ")


# ---------------------------------------------------------------- TSV Директа

def _to_float(v):
    if v is None:
        return None
    v = str(v).strip().replace(",", ".")
    if v in ("", "--", "-"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_tsv(text: str) -> list[dict]:
    """Терпим к шапке/итоговой строке отчёта: ищем строку заголовка с CampaignId."""
    lines = text.splitlines()
    header_idx = next((i for i, l in enumerate(lines) if "CampaignId" in l.split("\t")), None)
    if header_idx is None:
        raise SystemExit("ошибка: в TSV нет колонки CampaignId — это отчёт report_campaign?")
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])), delimiter="\t")
    rows = []
    for r in reader:
        cid = (r.get("CampaignId") or "").strip()
        if not cid.isdigit():          # итоговая строка «Total rows: N» и пустые
            continue
        rows.append(r)
    return rows


def direct_rows(tsv_text: str, types: dict, account, counter_id, link, money_in_micros: bool) -> list[dict]:
    """Свернуть дневной отчёт по кампаниям до строк «Директ × тип кампании»."""
    agg: dict[str, dict] = {}
    unknown = set()
    for r in parse_tsv(tsv_text):
        cid = r["CampaignId"].strip()
        ctype = types.get(cid)
        if ctype is None:
            unknown.add(cid)
            continue
        a = agg.setdefault(ctype, {"spend": 0.0, "clicks": 0, "leads": 0.0, "dates": set()})
        impressions = _to_float(r.get("Impressions")) or 0
        cost = _to_float(r.get("Cost")) or 0.0
        a["spend"] += cost / MICRO if money_in_micros else cost
        a["clicks"] += int(_to_float(r.get("Clicks")) or 0)
        a["leads"] += sum(_to_float(v) or 0 for k, v in r.items() if k and k.startswith("Conversions"))
        if impressions > 0 and r.get("Date"):
            a["dates"].add(r["Date"].strip())
    if unknown:
        print(f"⚠️  кампании без типа в --campaign-types пропущены: {', '.join(sorted(unknown))}",
              file=sys.stderr)
    out = []
    order = {t: i for i, t in enumerate(TYPE_ORDER)}
    for ctype, a in sorted(agg.items(), key=lambda kv: (order.get(kv[0], len(order)), kv[0])):
        out.append({
            "channel": "yandex_direct", "campaign_type": ctype, "account": account, "status": "ran",
            "spend": round(a["spend"], 2), "clicks": a["clicks"], "leads": round(a["leads"], 2),
            "days": len(a["dates"]) if a["dates"] else None,
            "counter_id": counter_id, "link": link, "source": "direct", "note": "",
        })
    return out


# ---------------------------------------------------------------- выводы

def verdict(row: dict, th: dict) -> tuple[str, str]:
    """Вывод по порогам из шапки. Возвращает (verdict, verdict_reason)."""
    status = row.get("status") or "ran"
    spend, clicks, leads, days = row.get("spend"), row.get("clicks"), row.get("leads"), row.get("days")
    note = (row.get("note") or "").strip()
    if status == "never_ran":
        return "never_ran", f"причина: {note or 'не указана — спросить у маркетолога'}"

    min_clicks, min_days = th["min_clicks"], th["min_days"]
    data_gate = f"порог «мало данных»: <{min_clicks} кликов / <{min_days} дней"
    if (clicks is not None and clicks < min_clicks) or (days is not None and days < min_days):
        parts = [f"{num(clicks)} кликов" if clicks is not None else None,
                 f"{days} дн. показов" if days is not None else None]
        return "no_data", f"{', '.join(p for p in parts if p)} ({data_gate})"

    client = row.get("source") == "client"
    if not leads:
        if clicks is not None:
            span = f" за {days} дн." if days is not None else ""
            return "no_leads", f"0 лидов при {num(clicks)} кликах{span}, расход {rub(spend)}"
        return "no_leads", f"0 лидов, расход {rub(spend)}" + (" (со слов клиента)" if client else "")

    cpa = spend / leads if spend is not None else None
    target, ratio = th.get("target_cpa"), th["expensive_ratio"]
    if cpa is None:
        return "works", f"{num(leads)} лидов, расход неизвестен — «дорого» не оценивается"
    if target:
        limit = target * ratio
        if cpa > limit:
            return "expensive", (f"CPA {rub(cpa)} > {rub(target)} × {ratio} = {rub(limit)} "
                                 f"при {num(leads)} лидах")
        return "works", f"CPA {rub(cpa)} ≤ {rub(target)} × {ratio} при {num(leads)} лидах"
    return "works", f"{num(leads)} лидов, CPA {rub(cpa)} (целевой CPA не задан — «дорого» не оценивается)"


def finalize_row(row: dict, th: dict) -> dict:
    spend, leads = row.get("spend"), row.get("leads")
    v, reason = verdict(row, th)
    out = {k: row.get(k) for k in ROW_KEYS}
    out["campaign_type"] = row.get("campaign_type") or "—"
    out["account"] = row.get("account") or ""
    out["status"] = row.get("status") or "ran"
    out["source"] = row.get("source") or "client"
    out["note"] = row.get("note") or ""
    out["cpa"] = round(spend / leads, 2) if spend is not None and leads else None
    out["verdict"], out["verdict_reason"] = v, reason
    return out


# ---------------------------------------------------------------- markdown

def render_md(doc: dict) -> str:
    th = doc["thresholds"]
    ld = doc["lead_definition"]
    ld_txt = ld if isinstance(ld, str) else (
        ", ".join(ld.get("names") or []) + (f" (цели {', '.join(map(str, ld.get('goal_ids') or []))})"
                                            if ld.get("goal_ids") else "") +
        (f" — {ld['how']}" if ld.get("how") else ""))
    target = rub(th.get("target_cpa")) if th.get("target_cpa") else "не задан"
    lines = [
        f"# История каналов: {doc['site']}",
        "",
        f"- **Период:** {doc['period']}",
        f"- **Что считали лидом:** {ld_txt}",
        f"- **Пороги:** «мало данных» — меньше {th['min_clicks']} кликов или {th['min_days']} дней показов; "
        f"«дорого» — CPA выше целевого ({target}) × {th['expensive_ratio']}",
        f"- **Собрал:** {doc['created_by']}",
        "",
        "| Канал | Тип | Статус | Расход | Клики | Лиды | CPA | Вывод | Почему | Источник |",
        "|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for r in doc["rows"]:
        lines.append("| " + " | ".join([
            CHANNEL_RU.get(r["channel"], r["channel"]), TYPE_RU.get(r["campaign_type"], r["campaign_type"]),
            r["status"], rub(r["spend"]), num(r["clicks"]), num(r["leads"]), rub(r["cpa"]),
            f"**{VERDICT_RU[r['verdict']]}**", r["verdict_reason"] + (f"; {r['note']}" if r["note"] and r["verdict"] != "never_ran" else ""),
            r["source"],
        ]) + " |")
    lines += ["", "Пороги — не догма: у бизнеса бывают свои представления о «мало данных» и «дорого». "
              "Поправьте их в шапке и пересоберите файл. Контракт полей — references/channel-history.md.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- проверка

def validate_doc(doc: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for k in HEADER_KEYS:
        if doc.get(k) in (None, "", {}):
            errors.append(f"шапка: нет поля «{k}»")
    th = doc.get("thresholds") or {}
    for k in ("min_clicks", "min_days", "expensive_ratio"):
        if not isinstance(th.get(k), (int, float)):
            errors.append(f"thresholds.{k} должен быть числом")
    rows = doc.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("rows: пусто — нет ни одной строки")
        return errors, warnings
    for i, r in enumerate(rows, 1):
        where = f"строка {i} ({r.get('channel')}/{r.get('campaign_type')})"
        missing = [k for k in ROW_KEYS if k not in r]
        if missing:
            errors.append(f"{where}: нет полей {', '.join(missing)}")
        if r.get("channel") not in KNOWN_CHANNELS:
            warnings.append(f"{where}: канал «{r.get('channel')}» вне списка {sorted(KNOWN_CHANNELS)}")
        if r.get("channel") == "yandex_direct" and r.get("campaign_type") in (None, "", "—"):
            errors.append(f"{where}: для Директа campaign_type обязателен")
        for field, allowed in (("status", STATUSES), ("verdict", VERDICTS), ("source", SOURCES), ("link", LINKS)):
            if field in r and r[field] not in allowed:
                errors.append(f"{where}: {field}=«{r[field]}» не из {sorted(a for a in allowed if a)}")
        if not (r.get("verdict_reason") or "").strip():
            errors.append(f"{where}: пустой verdict_reason — вывод без чисел и порога")
        spend, leads, cpa = r.get("spend"), r.get("leads"), r.get("cpa")
        if spend is not None and leads:
            if cpa is None or abs(cpa - spend / leads) > max(1.0, 0.01 * spend / leads):
                errors.append(f"{where}: cpa={cpa}, а spend/leads={round(spend / leads, 2)}")
        if leads == 0 and cpa is not None:
            errors.append(f"{where}: при 0 лидов cpa должен быть null")
        if r.get("status") == "never_ran" and r.get("verdict") != "never_ran":
            errors.append(f"{where}: status=never_ran, а verdict={r.get('verdict')}")
        if isinstance(th.get("min_clicks"), (int, float)) and r.get("verdict") in VERDICTS:
            expected, _ = verdict(r, {**DEFAULT_THRESHOLDS, **th})
            # days в файле нет — «мало данных» по дням отсюда не пересчитать, его не трогаем
            if expected != r["verdict"] and r["verdict"] != "no_data":
                warnings.append(f"{where}: по порогам шапки выходит «{expected}», в файле «{r['verdict']}»")
    return errors, warnings


# ---------------------------------------------------------------- команды

def _read_json(path: str):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def cmd_build(args) -> int:
    spec = _read_json(args.spec)
    th = {**DEFAULT_THRESHOLDS, **(spec.get("thresholds") or {})}
    missing = [k for k in ("site", "period", "lead_definition") if not spec.get(k)]
    if missing:
        print(f"ошибка: в spec нет {', '.join(missing)} — период и «что считать лидом» "
              f"выбирает человек, их не подставляем", file=sys.stderr)
        return 2

    rows = []
    if args.direct_tsv:
        if not args.campaign_types:
            print("ошибка: --direct-tsv требует --campaign-types", file=sys.stderr)
            return 2
        with open(args.direct_tsv, encoding="utf-8-sig") as fh:
            tsv = fh.read()
        types = {str(k): v for k, v in _read_json(args.campaign_types).items()}
        rows += direct_rows(tsv, types, args.account, args.counter_id, args.link, args.money_in_micros)
    rows += spec.get("rows") or []
    if not rows:
        print("ошибка: нет ни одной строки — дай --direct-tsv или rows в spec", file=sys.stderr)
        return 2

    doc = {
        "site": spec["site"], "period": spec["period"], "lead_definition": spec["lead_definition"],
        "thresholds": th, "created_by": spec.get("created_by") or "yandex-direct-audit",
        "rows": [finalize_row(r, th) for r in rows],
    }
    errors, warnings = validate_doc(doc)
    for w in warnings:
        print(f"⚠️  {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"❌ {e}", file=sys.stderr)
        return 1

    os.makedirs(args.out_dir, exist_ok=True)
    jpath = os.path.join(args.out_dir, "channel_history.json")
    mpath = os.path.join(args.out_dir, "channel_history.md")
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(mpath, "w", encoding="utf-8") as fh:
        fh.write(render_md(doc))
    print(f"✅ {jpath}\n✅ {mpath}")
    for r in doc["rows"]:
        print(f"  {CHANNEL_RU.get(r['channel'], r['channel'])} / {TYPE_RU.get(r['campaign_type'], r['campaign_type'])}: "
              f"{VERDICT_RU[r['verdict']]} — {r['verdict_reason']}")
    return 0


def cmd_validate(args) -> int:
    doc = _read_json(args.input)
    errors, warnings = validate_doc(doc)
    for w in warnings:
        print(f"⚠️  {w}")
    for e in errors:
        print(f"❌ {e}")
    if errors:
        print(f"Не по контракту: ошибок {len(errors)}. Контракт — references/channel-history.md.")
        return 1
    print(f"✅ по контракту: строк {len(doc['rows'])}, предупреждений {len(warnings)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="channel_history", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="собрать channel_history.json + .md")
    b.add_argument("--spec", required=True, help="JSON: шапка (site, period, lead_definition, thresholds) + ручные строки")
    b.add_argument("--direct-tsv", default=None, help="TSV report_campaign с CampaignId, Date, Impressions, Clicks, Cost, Conversions*")
    b.add_argument("--campaign-types", default=None, help='JSON {"<CampaignId>": "search|rsya|unified|..."}')
    b.add_argument("--account", default="", help="логин кабинета Директа для строк из TSV")
    b.add_argument("--counter-id", type=int, default=None)
    b.add_argument("--link", choices=["green", "yellow", "red"], default=None, help="связка Директ↔Метрика")
    b.add_argument("--money-in-micros", action="store_true",
                   help="Cost в TSV в микро (ручная выгрузка); отчёты коннектора — уже в рублях")
    b.add_argument("--out-dir", required=True, help="куда писать: lead/<slug> или direct-audits/<slug>")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="проверить channel_history.json на соответствие контракту")
    v.add_argument("--input", required=True)
    v.set_defaults(func=cmd_validate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
