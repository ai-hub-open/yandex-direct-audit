#!/usr/bin/env python3
"""
normalize_report.py — нормализация TSV-отчёта Яндекс.Директа для аудита.

Что делает:
  - читает сырой TSV (вывод report_* тула или CUSTOM_REPORT);
  - конвертирует денежные поля из микро-валюты в рубли (если returnMoneyInMicros
    не был выключен на стороне MCP);
  - досчитывает CPA, ДРР, CR там, где есть нужные колонки;
  - ставит флаги по порогам (нулевые конверсии при расходе, высокий CTR в сети,
    CPA выше KPI и т.п.);
  - фильтрует до строк с существенным расходом или нарушением порогов;
  - ранжирует по расходу;
  - отдаёт JSON (полный + ranked-срез для рассуждения).

Использование:
  python -m scripts.normalize_report --input raw.tsv \
      --network search|network|auto \
      --kpi-cpa 1500 --kpi-drr 0.15 \
      --min-clicks 5 --top 50 \
      --out normalized.json

Скрипт намеренно консервативен: он НЕ решает, что отключать. Он лишь подсвечивает
строки-кандидаты с доказательствами, чтобы Claude и маркетолог приняли решение.
"""

import argparse
import csv
import io
import json
import sys
from typing import Any, Dict, List, Optional

MICRO = 1_000_000

# Поля, которые в Direct API приходят в микро-валюте.
MONEY_FIELDS = {
    "Cost", "AvgCpc", "AvgCpm", "CostPerConversion",
    "Revenue", "Profit", "Bid", "AvgEffectiveBid",
}

# Числовые поля (float).
FLOAT_FIELDS = {
    "Ctr", "ConversionRate", "BounceRate", "AvgPageviews",
    "GoalsRoi", "AvgImpressionPosition", "AvgClickPosition",
} | MONEY_FIELDS

# Целочисленные поля.
INT_FIELDS = {
    "Impressions", "Clicks", "Conversions", "Bounces", "Sessions",
}


def to_float(v: str) -> Optional[float]:
    if v is None:
        return None
    v = v.strip()
    if v in ("", "--", "-"):
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def to_int(v: str) -> Optional[int]:
    f = to_float(v)
    return int(f) if f is not None else None


def parse_tsv(text: str) -> List[Dict[str, str]]:
    """
    Парсит TSV. Терпим к шапке/суммарной строке отчёта Директа, если
    skipReportHeader/skipReportSummary не были выставлены: ищем строку,
    содержащую известные имена колонок.
    """
    lines = text.splitlines()
    # Найдём строку заголовка: ту, где есть хотя бы одно известное поле.
    known = INT_FIELDS | FLOAT_FIELDS | {
        "CampaignName", "CampaignId", "Placement", "Device", "Age",
        "Gender", "Query", "LocationOfPresenceName", "AdNetworkType",
        "HourOfDay", "DayOfWeek", "AdId", "AdGroupName",
    }
    header_idx = None
    for i, line in enumerate(lines):
        cells = line.split("\t")
        if any(c in known for c in cells):
            header_idx = i
            break
    if header_idx is None:
        raise SystemExit("Не нашёл строку заголовка с известными полями. "
                         "Проверь, что это TSV-отчёт Директа.")
    reader = csv.DictReader(
        io.StringIO("\n".join(lines[header_idx:])), delimiter="\t"
    )
    rows = [dict(r) for r in reader]
    # Отбросим хвостовую суммарную строку ("Total rows" и т.п.), если затесалась.
    rows = [r for r in rows if any((v or "").strip() for v in r.values())]
    return rows


def normalize_row(row: Dict[str, str], money_in_micros: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if k in INT_FIELDS:
            out[k] = to_int(v)
        elif k in FLOAT_FIELDS:
            f = to_float(v)
            if f is not None and k in MONEY_FIELDS and money_in_micros:
                f = round(f / MICRO, 2)
            out[k] = f
        else:
            out[k] = (v or "").strip()
    return out


def enrich(row: Dict[str, Any]) -> Dict[str, Any]:
    """Досчитываем CPA, ДРР, CR, если есть из чего."""
    cost = row.get("Cost")
    conv = row.get("Conversions")
    rev = row.get("Revenue")
    clicks = row.get("Clicks")

    if cost is not None and conv:
        row["_CPA"] = round(cost / conv, 2)
    else:
        row["_CPA"] = None

    if cost is not None and rev:
        row["_DRR"] = round(cost / rev, 4)  # доля, 0.15 = 15%
    else:
        row["_DRR"] = None

    if conv is not None and clicks:
        row["_CR"] = round(conv / clicks, 4)
    else:
        row["_CR"] = None
    return row


def flag(row: Dict[str, Any], network: str, kpi_cpa: Optional[float],
         kpi_drr: Optional[float], min_clicks: int) -> List[str]:
    flags: List[str] = []
    cost = row.get("Cost") or 0
    clicks = row.get("Clicks") or 0
    conv = row.get("Conversions")
    ctr = row.get("Ctr")  # в Direct TSV CTR обычно в процентах
    cpa = row.get("_CPA")
    drr = row.get("_DRR")

    is_network = network == "network" or (
        network == "auto" and row.get("AdNetworkType") == "AD_NETWORK"
    )

    # Слив: расход есть, кликов достаточно, конверсий ноль.
    if cost > 0 and clicks >= min_clicks and (conv == 0 or conv is None):
        if conv == 0:
            flags.append("zero_conversions_with_spend")
        else:
            flags.append("no_conversion_data")  # возможно нет связки с Метрикой

    # Высокий CTR в сети — подозрение на фрод/клик под кнопкой.
    if is_network and ctr is not None and ctr >= 2.0:
        flags.append("network_ctr_high_suspicious")

    # Низкий CTR на поиске.
    if not is_network and ctr is not None and ctr < 2.0 and clicks >= min_clicks:
        flags.append("search_ctr_low")

    # CPA выше KPI.
    if kpi_cpa and cpa is not None and cpa > kpi_cpa:
        flags.append("cpa_above_kpi")

    # ДРР выше KPI.
    if kpi_drr and drr is not None and drr > kpi_drr:
        flags.append("drr_above_kpi")

    # Мало данных для вывода по конверсиям.
    if (conv is not None) and conv < 10:
        flags.append("low_volume_hypothesis")

    return flags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="путь к сырому TSV-отчёту")
    ap.add_argument("--network", default="auto",
                    choices=["search", "network", "auto"],
                    help="тип размещения для порогов CTR")
    ap.add_argument("--kpi-cpa", type=float, default=None)
    ap.add_argument("--kpi-drr", type=float, default=None,
                    help="доля, например 0.15 для 15%%")
    ap.add_argument("--min-clicks", type=int, default=5,
                    help="минимум кликов, чтобы строка считалась значимой")
    ap.add_argument("--top", type=int, default=50,
                    help="сколько строк отдать в ranked-срезе")
    ap.add_argument("--money-in-micros", dest="micros", action="store_true",
                    default=False,
                    help="деньги в отчёте в микро — делить на 1e6 (для ручных выгрузок)")
    ap.add_argument("--money-in-rub", dest="micros", action="store_false",
                    help="деньги уже в рублях (дефолт; коннектор отдаёт рубли)")
    ap.add_argument("--out", default=None, help="куда писать JSON (иначе stdout)")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    rows = parse_tsv(text)
    norm = [enrich(normalize_row(r, args.micros)) for r in rows]
    for r in norm:
        r["_flags"] = flag(r, args.network, args.kpi_cpa,
                           args.kpi_drr, args.min_clicks)

    # Ranked-срез: строки с флагами ИЛИ с заметным расходом, по убыванию расхода.
    flagged = [r for r in norm if r["_flags"]]
    flagged.sort(key=lambda r: (r.get("Cost") or 0), reverse=True)
    ranked = flagged[: args.top]

    total_cost = round(sum((r.get("Cost") or 0) for r in norm), 2)
    waste_cost = round(
        sum((r.get("Cost") or 0) for r in norm
            if "zero_conversions_with_spend" in r["_flags"]), 2
    )

    result = {
        "summary": {
            "rows_total": len(norm),
            "rows_flagged": len(flagged),
            "total_cost": total_cost,
            "estimated_zero_conversion_spend": waste_cost,
            "money_unit": "rub",
            "note": "Деньги сконвертированы в рубли" if args.micros
                    else "Деньги пришли уже в рублях",
        },
        "ranked": ranked,
        "all": norm,
    }

    out_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_text)
        print(f"OK: {len(norm)} строк, {len(flagged)} с флагами → {args.out}")
        print(f"Суммарный расход: {total_cost} ₽; "
              f"расход без конверсий: {waste_cost} ₽")
    else:
        sys.stdout.write(out_text)


if __name__ == "__main__":
    main()
