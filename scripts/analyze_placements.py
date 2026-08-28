#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_placements.py — ядро минусации площадок РСЯ Яндекс.Директа.

Вход: сырой TSV-ответ отчёта Директа (CUSTOM_REPORT по площадкам РСЯ).
Выход: candidates.json (полные данные), minus_list.txt (готовый к вставке
список по кампаниям), report.md (человекочитаемый разбор с доказательствами).

Скрипт ничего не пишет в аккаунт. Он только читает отчёт и классифицирует
площадки по порогам. Решение и заливку в «Запрещённые площадки» делает человек.

Логика порогов (всё настраивается флагами):
  Объём данных (гейт достоверности):
    - rate-сигналы (CTR / отказы / CR) верим только при clicks >= MIN_CLICKS (по умолч. 30).
    - money-сигнал (расход без конверсий) верим по деньгам: расход >= tCPA — уже улика,
      число кликов тут не требуем (дорогая ниша может слить 2x CPA за 15 кликов).
    - мусор по названию (игры/фонарик/кэшбэк/обои/...) минусуем превентивно даже при ~5 кликах.

  Сигнал 1 — расход есть, конверсий 0:
    - расход >= 2 * tCPA  -> 🔴 минусовать точно
    - tCPA <= расход < 2*tCPA -> 🟠 кандидат

  Сигнал 2 — конверсии есть, но CPA сильно выше базы (средний CPA кампании или tCPA):
    - CPA площадки >= 2.0 * база при достаточном объёме -> 🟠 кандидат (сильный)
    - 1.5 <= CPA/база < 2.0 при достаточном объёме -> 🟠 кандидат

  Сигнал 3 — аномальный CTR / фрод-скликивание (норма РСЯ 0.3–0.8%):
    - CTR > 5% при низком CR / 0 конверсий -> 🔴 (почти наверняка автоклики)
    - CTR > 3% и 0 конверсий -> 🟠 кандидат (подозрение на фрод)
    - усиливается дешёвым кликом и отказами > 30%.

  Отказы (если к кампании привязан счётчик): BounceRate > 30% при clicks >= MIN_CLICKS -> усиливает кандидата.

Категории на выходе:
  🔴 minus_sure        — минусовать точно
  🟠 minus_candidate   — кандидат на минус (решает человек)
  🟡 watch             — под наблюдением (пограничные цифры / watchlist по имени)
  ⚪ insufficient      — мало данных, ждём
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

# На Windows консоль часто в cp1251 и падает на эмодзи (🔴 🟠 ✅ ...) при печати
# финальной сводки. Переключаем потоки вывода на UTF-8, чтобы скрипт не падал на
# выводе (файлы и так пишутся в UTF-8). Логику анализа это не меняет.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ---------- словарь паттернов имён площадок ----------
# Загружается из assets/placement_patterns.json, если файл есть; иначе встроенный дефолт.
DEFAULT_PATTERNS = {
    # мусор: минусуем превентивно даже при малом объёме
    "trash": [
        r"game", r"games", r"игр", r"play", r"flash", r"poki", r"crazygames",
        r"фонар", r"flashlight", r"обои", r"wallpaper", r"погод", r"weather",
        r"кэшбэк", r"кешбэк", r"cashback", r"едадил", r"edadeal", r"купон", r"coupon",
        r"promokod", r"промокод", r"скидк", r"чита", r"читалк", r"книг.*онлайн",
        r"flibusta", r"litres-pirat", r"vpn", r"proxy", r"расширени", r"extension",
        r"взлом", r"crack", r"keygen", r"torrent", r"\.apk",
    ],
    # watchlist: под вопросом, смотрим по цифрам (могут давать заявки)
    "watch": [
        r"otzovik", r"отзовик", r"irecommend", r"айрекоменд", r"otzyv",
        r"rutube", r"kinopoisk", r"кинопоиск", r"видеохост", r"yandex\.video",
        r"agregator", r"агрегатор", r"sravni", r"price", r"market\.",
    ],
}


def load_patterns(skill_dir):
    path = os.path.join(skill_dir, "assets", "placement_patterns.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "trash": [re.compile(p, re.I) for p in data.get("trash", [])],
                "watch": [re.compile(p, re.I) for p in data.get("watch", [])],
            }
        except Exception as e:
            sys.stderr.write(f"warn: не смог прочитать placement_patterns.json ({e}), беру дефолт\n")
    return {
        "trash": [re.compile(p, re.I) for p in DEFAULT_PATTERNS["trash"]],
        "watch": [re.compile(p, re.I) for p in DEFAULT_PATTERNS["watch"]],
    }


def name_class(placement, patterns):
    p = placement or ""
    for rx in patterns["trash"]:
        if rx.search(p):
            return "trash"
    for rx in patterns["watch"]:
        if rx.search(p):
            return "watch"
    return None


# ---------- парсинг TSV ----------
NUMERIC = {
    "impressions", "clicks", "ctr", "cost", "avgcpc", "conversions",
    "conversionrate", "costperconversion", "revenue", "goalsroi", "bouncerate",
    "bounces", "avgpageviews",
}


def to_num(v):
    if v is None:
        return 0.0
    v = str(v).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if v in ("", "--", "-"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def parse_tsv(path):
    with open(path, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    if not lines:
        raise SystemExit("Пустой отчёт.")
    # Заголовок Директа может содержать строку названия отчёта и итоги — ищем строку с известными полями.
    header_idx = 0
    for i, ln in enumerate(lines):
        low = ln.lower()
        if "placement" in low or "campaignname" in low or "cost" in low:
            header_idx = i
            break
    header = [h.strip() for h in lines[header_idx].split("\t")]
    rows = []
    for ln in lines[header_idx + 1:]:
        if ln.lower().startswith("total") or ln.lower().startswith("итог"):
            continue
        cells = ln.split("\t")
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        row = {}
        for h, c in zip(header, cells):
            key = h.strip()
            kl = key.lower()
            row[kl] = to_num(c) if kl in NUMERIC else c.strip()
        rows.append(row)
    return header, rows


# ---------- агрегация до уровня (кампания, площадка) ----------
def aggregate(rows, money_in_micros):
    div = 1_000_000.0 if money_in_micros else 1.0
    placements = {}  # (campaign_key, placement) -> agg
    camp_totals = defaultdict(lambda: {"cost": 0.0, "conv": 0.0})

    for r in rows:
        camp = r.get("campaignname") or r.get("campaignid") or "—"
        camp_id = r.get("campaignid", "")
        place = r.get("placement") or "(не указана)"
        key = (camp, place)
        if key not in placements:
            placements[key] = {
                "campaign": camp, "campaign_id": camp_id, "placement": place,
                "ad_network": r.get("adnetworktype", ""),
                "impr": 0.0, "clicks": 0.0, "cost": 0.0, "conv": 0.0,
                "revenue": 0.0, "bounce_num": 0.0, "bounce_den": 0.0,
                "by_device": defaultdict(lambda: {"clicks": 0.0, "cost": 0.0, "conv": 0.0}),
                "by_geo": defaultdict(lambda: {"clicks": 0.0, "cost": 0.0, "conv": 0.0}),
            }
        a = placements[key]
        impr = r.get("impressions", 0.0)
        clicks = r.get("clicks", 0.0)
        cost = r.get("cost", 0.0) / div
        conv = r.get("conversions", 0.0)
        revenue = r.get("revenue", 0.0) / div
        a["impr"] += impr
        a["clicks"] += clicks
        a["cost"] += cost
        a["conv"] += conv
        a["revenue"] += revenue
        # отказы: BounceRate в % -> взвешиваем по кликам, чтобы агрегировать корректно
        br = r.get("bouncerate", None)
        if br:
            a["bounce_num"] += br * clicks
            a["bounce_den"] += clicks
        dev = r.get("device", "")
        if dev:
            d = a["by_device"][dev]
            d["clicks"] += clicks; d["cost"] += cost; d["conv"] += conv
        geo = r.get("locationofpresencename", "")
        if geo:
            g = a["by_geo"][geo]
            g["clicks"] += clicks; g["cost"] += cost; g["conv"] += conv

        camp_totals[camp]["cost"] += cost
        camp_totals[camp]["conv"] += conv

    # производные метрики
    for a in placements.values():
        a["ctr"] = (a["clicks"] / a["impr"] * 100) if a["impr"] else 0.0
        a["cr"] = (a["conv"] / a["clicks"] * 100) if a["clicks"] else 0.0
        a["avg_cpc"] = (a["cost"] / a["clicks"]) if a["clicks"] else 0.0
        a["cpa"] = (a["cost"] / a["conv"]) if a["conv"] else None
        a["roas"] = (a["revenue"] / a["cost"]) if a["cost"] else None
        a["bounce"] = (a["bounce_num"] / a["bounce_den"]) if a["bounce_den"] else None
        a["by_device"] = {k: v for k, v in a["by_device"].items()}
        a["by_geo"] = {k: v for k, v in a["by_geo"].items()}

    camp_avg_cpa = {}
    for c, t in camp_totals.items():
        camp_avg_cpa[c] = (t["cost"] / t["conv"]) if t["conv"] else None
    return placements, camp_avg_cpa


# ---------- классификация ----------
def classify(a, tcpa, camp_avg_cpa, patterns, min_clicks, ctr_warn, ctr_fraud,
             bounce_thr, cpa_mult_cand, cpa_mult_strong):
    cost, clicks, conv, ctr = a["cost"], a["clicks"], a["conv"], a["ctr"]
    cpa = a["cpa"]
    nclass = name_class(a["placement"], patterns)
    reasons = []
    severity = "watch" if nclass == "watch" else "insufficient"

    money_sufficient = tcpa is not None and cost >= tcpa
    rate_sufficient = clicks >= min_clicks
    base_cpa = camp_avg_cpa if camp_avg_cpa else tcpa

    def bump(level):
        nonlocal severity
        order = {"insufficient": 0, "ok": 0, "watch": 1, "minus_candidate": 2, "minus_sure": 3}
        if order[level] > order[severity]:
            severity = level

    # --- мусор по названию: превентивный минус ---
    if nclass == "trash":
        if clicks >= 5 or cost > 0:
            if conv == 0:
                bump("minus_sure")
                reasons.append(f"Мусорная площадка по названию ({a['placement']}), конверсий нет — минус превентивно.")
            else:
                bump("minus_candidate")
                reasons.append(f"Мусорная площадка по названию ({a['placement']}), но есть {int(conv)} конв. — перепроверь.")
        else:
            bump("watch")
            reasons.append(f"Мусорный паттерн в названии ({a['placement']}), но почти нет данных.")

    # --- Сигнал 1: расход без конверсий ---
    if conv == 0 and tcpa:
        if cost >= 2 * tcpa:
            bump("minus_sure")
            reasons.append(f"Расход {cost:.0f} ₽ ≥ 2× целевого CPA ({tcpa:.0f} ₽) и 0 конверсий — минус.")
        elif cost >= tcpa:
            bump("minus_candidate")
            reasons.append(f"Расход {cost:.0f} ₽ ≥ целевого CPA ({tcpa:.0f} ₽) и 0 конверсий — кандидат.")
        elif not money_sufficient and not rate_sufficient and nclass is None:
            reasons.append(f"0 конверсий, но расход {cost:.0f} ₽ < CPA и кликов {int(clicks)} < {min_clicks} — мало данных, ждём.")

    # --- Сигнал 2: конверсии есть, но CPA выше базы ---
    if conv > 0 and cpa and base_cpa and (clicks >= min_clicks or conv >= 1):
        ratio = cpa / base_cpa
        if ratio >= cpa_mult_strong:
            bump("minus_candidate")
            reasons.append(f"CPA площадки {cpa:.0f} ₽ ≥ {cpa_mult_strong:g}× базы ({base_cpa:.0f} ₽) — сильный кандидат.")
        elif ratio >= cpa_mult_cand:
            bump("minus_candidate")
            reasons.append(f"CPA площадки {cpa:.0f} ₽ в {ratio:.1f}× выше базы ({base_cpa:.0f} ₽) — кандидат.")

    # --- Сигнал 3: аномальный CTR / фрод ---
    if rate_sufficient:
        if ctr > ctr_fraud and (conv == 0 or a["cr"] < 0.3):
            bump("minus_sure" if conv == 0 else "minus_candidate")
            reasons.append(f"CTR {ctr:.1f}% > {ctr_fraud:g}% при низком CR — почти наверняка автоклики/фрод.")
        elif ctr > ctr_warn and conv == 0:
            bump("minus_candidate")
            reasons.append(f"CTR {ctr:.1f}% > {ctr_warn:g}% (норма РСЯ 0.3–0.8%) и 0 конверсий — подозрение на фрод.")

    # --- Отказы ---
    if a["bounce"] is not None and a["bounce"] > bounce_thr and rate_sufficient:
        if severity in ("minus_candidate", "minus_sure"):
            reasons.append(f"Отказы {a['bounce']:.0f}% > {bounce_thr:g}% — усиливает решение.")
        else:
            bump("watch")
            reasons.append(f"Отказы {a['bounce']:.0f}% > {bounce_thr:g}% при {int(clicks)} кликах — плохая аудитория, под наблюдение.")

    # дешёвый клик как контекст для фрода
    if severity in ("minus_candidate", "minus_sure") and a["avg_cpc"] and a["avg_cpc"] < 3:
        reasons.append(f"Дешёвый клик ({a['avg_cpc']:.1f} ₽) — частый признак трафика-мусора.")

    if not reasons:
        # нет сигналов: различаем «норма» (данных достаточно) и «мало данных»
        data_enough = clicks >= min_clicks or (tcpa and cost >= tcpa)
        if severity == "insufficient" and data_enough:
            severity = "ok"
            reasons.append("Сигналов на минус нет, данных достаточно — площадка в норме, оставляем.")
        else:
            reasons.append("Сигналов на минус нет, но данных мало — ждём накопления.")
    return severity, reasons


def main():
    ap = argparse.ArgumentParser(description="Минусация площадок РСЯ Яндекс.Директа (read-only).")
    ap.add_argument("--input", required=True, help="Сырой TSV-ответ отчёта Директа по площадкам РСЯ.")
    ap.add_argument("--outdir", default=".", help="Куда писать candidates.json / minus_list.txt / report.md.")
    ap.add_argument("--tcpa", type=float, default=None, help="Целевой CPA глобально (₽).")
    ap.add_argument("--tcpa-map", default=None, help='JSON {"Имя кампании": tCPA} — целевой CPA по кампаниям.')
    ap.add_argument("--money-in-micros", action="store_true",
                    help="Деньги в отчёте в микро — делить на 1e6. По умолчанию считаем рубли: "
                         "коннектор Директа отдаёт отчёты уже в рублях.")
    ap.add_argument("--min-clicks", type=int, default=30, help="Порог кликов для rate-сигналов (CTR/отказы/CR).")
    ap.add_argument("--ctr-warn", type=float, default=3.0, help="CTR выше этого (%%) + 0 конв -> подозрение.")
    ap.add_argument("--ctr-fraud", type=float, default=5.0, help="CTR выше этого (%%) -> почти наверняка фрод.")
    ap.add_argument("--bounce", type=float, default=30.0, help="Отказы выше этого (%%) -> плохая аудитория.")
    ap.add_argument("--cpa-cand", type=float, default=1.5, help="CPA/база ≥ этого -> кандидат.")
    ap.add_argument("--cpa-strong", type=float, default=2.0, help="CPA/база ≥ этого -> сильный кандидат.")
    args = ap.parse_args()

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns = load_patterns(skill_dir)
    os.makedirs(args.outdir, exist_ok=True)

    tcpa_map = {}
    if args.tcpa_map:
        with open(args.tcpa_map, encoding="utf-8") as f:
            tcpa_map = json.load(f)

    header, rows = parse_tsv(args.input)
    # фильтр: только РСЯ и только с показами > 0
    rows = [r for r in rows
            if (r.get("adnetworktype", "").upper() in ("", "AD_NETWORK"))
            and r.get("impressions", 0.0) > 0]

    placements, camp_avg_cpa = aggregate(rows, money_in_micros=args.money_in_micros)

    results = []
    for (camp, place), a in placements.items():
        tcpa = tcpa_map.get(camp, args.tcpa)
        sev, reasons = classify(
            a, tcpa, camp_avg_cpa.get(camp), patterns,
            args.min_clicks, args.ctr_warn, args.ctr_fraud, args.bounce,
            args.cpa_cand, args.cpa_strong,
        )
        results.append({
            "campaign": camp, "campaign_id": a["campaign_id"], "placement": place,
            "severity": sev, "reasons": reasons,
            "impressions": round(a["impr"]), "clicks": round(a["clicks"]),
            "ctr": round(a["ctr"], 2), "cost": round(a["cost"], 2),
            "avg_cpc": round(a["avg_cpc"], 2), "conversions": round(a["conv"], 2),
            "cr": round(a["cr"], 2), "cpa": round(a["cpa"], 2) if a["cpa"] else None,
            "revenue": round(a["revenue"], 2) if a["revenue"] else None,
            "roas": round(a["roas"], 2) if a["roas"] else None,
            "bounce": round(a["bounce"], 1) if a["bounce"] is not None else None,
            "tcpa": tcpa, "camp_avg_cpa": round(camp_avg_cpa.get(camp), 2) if camp_avg_cpa.get(camp) else None,
            "by_device": a["by_device"], "by_geo": a["by_geo"],
        })

    order = {"minus_sure": 0, "minus_candidate": 1, "watch": 2, "ok": 3, "insufficient": 4}
    results.sort(key=lambda r: (order[r["severity"]], -r["cost"]))

    # ---- candidates.json ----
    with open(os.path.join(args.outdir, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump({"placements": results,
                   "params": {k: getattr(args, k) for k in
                              ("tcpa", "min_clicks", "ctr_warn", "ctr_fraud", "bounce", "cpa_cand", "cpa_strong")}},
                  f, ensure_ascii=False, indent=2)

    # ---- minus_list.txt (готов к вставке, по кампаниям) ----
    by_camp = defaultdict(lambda: {"sure": [], "cand": []})
    for r in results:
        if r["severity"] == "minus_sure":
            by_camp[r["campaign"]]["sure"].append(r["placement"])
        elif r["severity"] == "minus_candidate":
            by_camp[r["campaign"]]["cand"].append(r["placement"])
    with open(os.path.join(args.outdir, "minus_list.txt"), "w", encoding="utf-8") as f:
        f.write("# Минус-площадки РСЯ — готовый список для вставки в «Запрещённые площадки и внешние сети»\n")
        f.write("# Заливаешь сам, по каждой кампании отдельно. 🔴 — точно, 🟠 — реши сам.\n\n")
        for camp in sorted(by_camp):
            f.write(f"=== {camp} ===\n")
            if by_camp[camp]["sure"]:
                f.write("🔴 минусовать точно:\n")
                for p in by_camp[camp]["sure"]:
                    f.write(f"{p}\n")
            if by_camp[camp]["cand"]:
                f.write("🟠 кандидаты (на твоё решение):\n")
                for p in by_camp[camp]["cand"]:
                    f.write(f"{p}\n")
            f.write("\n")

    # ---- report.md ----
    icon = {"minus_sure": "🔴", "minus_candidate": "🟠", "watch": "🟡", "ok": "✅", "insufficient": "⚪"}
    title = {"minus_sure": "Минусовать точно", "minus_candidate": "Кандидаты на минус",
             "watch": "Под наблюдением", "ok": "Норма", "insufficient": "Мало данных"}
    counts = defaultdict(int)
    waste = 0.0
    for r in results:
        counts[r["severity"]] += 1
        if r["severity"] in ("minus_sure", "minus_candidate") and r["conversions"] == 0:
            waste += r["cost"]
    with open(os.path.join(args.outdir, "report.md"), "w", encoding="utf-8") as f:
        f.write("# Минусация площадок РСЯ\n\n")
        f.write(f"Площадок проанализировано: **{len(results)}**. "
                f"🔴 {counts['minus_sure']} · 🟠 {counts['minus_candidate']} · "
                f"🟡 {counts['watch']} · ✅ {counts['ok']} · ⚪ {counts['insufficient']}.\n\n")
        f.write(f"Потенциальная экономия (расход на площадках под минус без конверсий): **≈ {waste:.0f} ₽**.\n\n")
        f.write("> Скилл ничего не отключает сам. Решение и заливку в «Запрещённые площадки» делаешь ты.\n\n")
        for sev in ("minus_sure", "minus_candidate", "watch"):
            grp = [r for r in results if r["severity"] == sev]
            if not grp:
                continue
            f.write(f"## {icon[sev]} {title[sev]} ({len(grp)})\n\n")
            f.write("| Кампания | Площадка | Расход ₽ | Клики | CTR % | Конв. | CPA ₽ | Причина |\n")
            f.write("|---|---|--:|--:|--:|--:|--:|---|\n")
            for r in grp:
                cpa = f"{r['cpa']:.0f}" if r["cpa"] else "—"
                f.write(f"| {r['campaign']} | {r['placement']} | {r['cost']:.0f} | "
                        f"{r['clicks']} | {r['ctr']:.1f} | {r['conversions']:.0f} | {cpa} | "
                        f"{r['reasons'][0]} |\n")
            f.write("\n")

    print(f"OK: {len(results)} площадок. "
          f"🔴 {counts['minus_sure']} · 🟠 {counts['minus_candidate']} · "
          f"🟡 {counts['watch']} · ✅ {counts['ok']} · ⚪ {counts['insufficient']}. "
          f"Экономия ≈ {waste:.0f} ₽.")
    print(f"Файлы: {args.outdir}/candidates.json, minus_list.txt, report.md")


if __name__ == "__main__":
    main()
