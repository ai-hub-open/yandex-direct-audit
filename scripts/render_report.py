#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_report.py — собирает HTML-отчёт аудита из findings.json.

Путь: findings.json -> один самодостаточный HTML (встроенный CSS, стиль «дашборд»,
вёрстка под печать A4). Ни pip-пакетов, ни браузера, ни сети не требует — поэтому
работает и в песочнице Claude Desktop, где ничего этого нет.

Нужен PDF — открыть готовый файл в браузере и Ctrl+P -> Сохранить как PDF.

Использование:
    python -m scripts.render_report --input direct-audits/<slug>/findings.json
    python -m scripts.render_report --input <...>/findings.json --output <...>.html
"""

import argparse
import html
import json
import os
import sys

# Консоль Windows по умолчанию не в UTF-8, а итоговые сообщения — на русском.
# Переключаем потоки вывода, чтобы скрипт не падал на печати пути к отчёту
# (сам HTML и так пишется в UTF-8). На поведение рендера это не влияет.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ---------------------------------------------------------------- оформление

SEVERITY = {
    "high":   {"label": "Срочно",       "color": "#d64545", "bg": "#fdecec"},
    "medium": {"label": "Важно",        "color": "#c98a00", "bg": "#fcf4e1"},
    "low":    {"label": "Можно позже",  "color": "#2f9e60", "bg": "#e9f6ee"},
}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}

CSS = """
@page { size: A4; margin: 14mm 13mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif;
  color: #1a232e; font-size: 11px; line-height: 1.5; margin: 0;
  background: #fff;
}

/* На экране файл читают в браузере: даём поля, фон и чуть крупнее кегль.
   На печати всё это снимается и работает вёрстка @page под A4. */
@media screen {
  body { background: #eef1f5; font-size: 12.5px; }
  .page { max-width: 210mm; margin: 0 auto; padding: 26px 30px 60px;
          background: #fff; min-height: 100vh;
          box-shadow: 0 0 0 1px #dde3ea, 0 2px 18px rgba(26,35,46,.07); }
}
@media print {
  body { background: #fff; }
  .page { max-width: none; margin: 0; padding: 0; box-shadow: none; }
}
h1 { font-size: 22px; margin: 0 0 2px; letter-spacing: .2px; }
h2 { font-size: 15px; margin: 26px 0 12px; padding-bottom: 6px;
     border-bottom: 2px solid #e4e9ef; color: #243b53; }
.sub { color: #5a6b7b; font-size: 11px; margin: 2px 0 0; }
.period { font-size: 13px; font-weight: 600; color: #243b53; margin: 6px 0 2px; }
.kpi-line { color: #5a6b7b; font-size: 10.5px; margin-top: 6px; }

/* шапка */
.head { border-bottom: 3px solid #243b53; padding-bottom: 14px; margin-bottom: 4px; }

/* метрики */
.metrics { display: flex; gap: 10px; margin: 18px 0 6px; }
.metric { flex: 1; background: #f4f6f8; border: 1px solid #e4e9ef;
          border-radius: 10px; padding: 12px 14px; }
.metric .cap { font-size: 9.5px; text-transform: uppercase; letter-spacing: .6px;
               color: #6b7a8a; margin-bottom: 6px; }
.metric .val { font-size: 21px; font-weight: 700; color: #243b53; }
.metric .hint { font-size: 9px; color: #6b7a8a; margin-top: 5px; line-height: 1.4; }
.metric.warn .val { color: #d64545; }
.metric.good .val { color: #2f9e60; }

/* бар-чарт расхода */
.bars-cap { font-size: 9.5px; text-transform: uppercase; letter-spacing: .6px;
            color: #6b7a8a; margin: 18px 0 2px; }
.bars { margin: 6px 0 4px; }
.bar-row { display: flex; align-items: center; gap: 9px; margin: 7px 0; }
.bar-name { width: 108px; font-size: 10.5px; color: #344656; flex-shrink: 0; }
.bar-track { flex: 1; background: #eef1f4; border-radius: 6px; height: 16px; overflow: hidden; }
.bar-fill { height: 100%; background: linear-gradient(90deg,#3a5a82,#243b53); border-radius: 6px; }
.bar-val { width: 80px; text-align: right; font-size: 10.5px; color: #344656;
           font-variant-numeric: tabular-nums; flex-shrink: 0; }
.bar-kpi { width: 250px; text-align: right; font-size: 9px; color: #6b7a8a;
           flex-shrink: 0; white-space: nowrap; }
.bar-kpi.warn { color: #d64545; }
.bar-kpi.good { color: #2f9e60; }

/* топ-5 */
.top { background: #f9fafb; border: 1px solid #e4e9ef; border-radius: 10px;
       padding: 6px 14px; margin: 10px 0; }
.top-item { display: flex; align-items: baseline; gap: 10px; padding: 7px 0;
            border-bottom: 1px dashed #e4e9ef; }
.top-item:last-child { border-bottom: none; }
.top-num { font-weight: 700; color: #243b53; width: 18px; }
.top-camp { color: #6b7a8a; font-size: 10px; }
.top-money { margin-left: auto; font-weight: 700; color: #d64545;
             font-variant-numeric: tabular-nums; }

/* кампания */
.campaign { margin-top: 22px; }
.camp-head { display: flex; align-items: center; gap: 10px; }
.camp-title { font-size: 14px; font-weight: 700; color: #1a232e; }
.camp-status { color: #5a6b7b; font-size: 10.5px; }
.camp-bar { height: 4px; background: #243b53; border-radius: 2px;
            margin: 6px 0 12px; width: 100%; }

/* карточка действия */
.card { border: 1px solid #e4e9ef; border-left: 4px solid #ccc;
        border-radius: 8px; padding: 11px 13px; margin: 9px 0;
        break-inside: avoid; page-break-inside: avoid; }
.card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.badge { font-size: 9px; font-weight: 700; text-transform: uppercase;
         letter-spacing: .5px; padding: 2px 8px; border-radius: 20px; }
.area { font-size: 9.5px; color: #6b7a8a; }
.card-title { font-size: 12.5px; font-weight: 700; margin-left: 2px; }
.row { margin: 3px 0; }
.row .k { color: #6b7a8a; }
.do { font-size: 11.5px; font-weight: 600; color: #1a232e; margin: 2px 0 6px; }
.ready { background: #f4f6f8; border: 1px solid #dfe5ec; border-radius: 6px;
         padding: 8px 10px; margin: 6px 0; font-family: "Cascadia Mono",
         Consolas, "Courier New", monospace; font-size: 10.5px; color: #243b53;
         white-space: pre-wrap; }
.ready-cap { font-size: 9.5px; color: #6b7a8a; margin: 6px 0 2px; }
.verify { color: #2f6f8f; }
.conf { display: inline-block; font-size: 9.5px; color: #5a6b7b;
        background: #eef1f4; border-radius: 4px; padding: 1px 7px; }

/* ограничения */
.limits { background: #fbfbf6; border: 1px solid #ece9d8; border-radius: 8px;
          padding: 6px 16px; }
.limits li { margin: 6px 0; color: #5a5a45; }
.foot { margin-top: 24px; padding-top: 10px; border-top: 1px solid #e4e9ef;
        color: #9aa7b3; font-size: 9px; }
"""

# ---------------------------------------------------------------- помощники


def esc(text):
    return html.escape("" if text is None else str(text))


def money(value):
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    return "{:,}".format(n).replace(",", " ") + " ₽"


_MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _ru_one(iso):
    y, m, d = iso.split("-")
    return int(d), int(m), int(y)


def ru_period(period):
    """'2025-05-01..2025-05-31' -> '1–31 мая 2025' (даты по-русски, без символов)."""
    try:
        a, b = period.split("..")
        d1, m1, y1 = _ru_one(a)
        d2, m2, y2 = _ru_one(b)
    except Exception:                                       # noqa: BLE001
        return period
    if y1 == y2 and m1 == m2:
        return "{}–{} {} {}".format(d1, d2, _MONTHS[m1], y1)
    if y1 == y2:
        return "{} {} — {} {} {}".format(d1, _MONTHS[m1], d2, _MONTHS[m2], y1)
    return "{} {} {} — {} {} {}".format(d1, _MONTHS[m1], y1, d2, _MONTHS[m2], y2)


def sev_meta(sev):
    return SEVERITY.get(sev, {"label": sev or "—", "color": "#888", "bg": "#eee"})


# ---------------------------------------------------------------- блоки HTML


def render_metrics(summary):
    m = summary or {}
    cells = [
        ("Расход всего", money(m.get("total_cost")), "",
         "потрачено за период"),
        ("Средняя цена заявки", money(m.get("avg_cpa")), "",
         "сколько в среднем стоит одна заявка"),
        ("Потенциал экономии", money(m.get("recoverable")), "warn",
         "деньги, которые сейчас уходят впустую — вернутся после срочных правок"),
        ("Потенциал роста", money(m.get("growth_potential")), "good",
         "оценка: сколько можно добрать сверху, усилив то, что уже работает"),
    ]
    out = ['<div class="metrics">']
    for cap, val, cls, hint in cells:
        out.append(
            '<div class="metric {c}"><div class="cap">{cap}</div>'
            '<div class="val">{val}</div><div class="hint">{hint}</div></div>'.format(
                c=cls, cap=esc(cap), val=esc(val), hint=esc(hint))
        )
    out.append("</div>")
    return "".join(out)


def _bar_kpi(c):
    """Подпись справа от бара: фактическая цена заявки + статус по KPI, с цветом."""
    status = (c.get("kpi_status") or "").strip()
    parts = []
    if c.get("cpa") is not None:
        parts.append("цена заявки " + money(c.get("cpa")))
    if c.get("drr") is not None:
        parts.append("ДРР {}%".format(round(c.get("drr") * 100)))
    if status:
        parts.append(status)
    low = status.lower()
    if any(w in low for w in ("выше", "хуже", "превыш", "дорог")):
        cls = "warn"
    elif any(w in low for w in ("норм", "ниже", "лучше", "в kpi")):
        cls = "good"
    else:
        cls = ""
    return " · ".join(parts), cls


def render_bars(campaigns):
    camps = sorted(campaigns or [], key=lambda c: c.get("cost", 0), reverse=True)
    if not camps:
        return ""
    top = max((c.get("cost", 0) for c in camps), default=0) or 1
    rows = ['<div class="bars-cap">Расход по кампаниям</div>']
    rows.append('<div class="bars">')
    for c in camps:
        pct = max(3, round(c.get("cost", 0) / top * 100))
        kpi_text, kpi_cls = _bar_kpi(c)
        rows.append(
            '<div class="bar-row"><div class="bar-name">{name}</div>'
            '<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>'
            '<div class="bar-val">{val}</div>'
            '<div class="bar-kpi {cls}">{kpi}</div></div>'.format(
                name=esc(c.get("name", "—")), pct=pct, val=esc(money(c.get("cost"))),
                cls=kpi_cls, kpi=esc(kpi_text))
        )
    rows.append("</div>")
    return "".join(rows)


def render_top(findings):
    ranked = sorted(
        [f for f in findings if f.get("money_impact")],
        key=lambda f: f.get("money_impact", 0), reverse=True,
    )[:5]
    if not ranked:
        return ""
    out = ['<div class="top">']
    for i, f in enumerate(ranked, 1):
        out.append(
            '<div class="top-item"><span class="top-num">{i}</span>'
            '<span>{title}</span> <span class="top-camp">· {camp}</span>'
            '<span class="top-money">{money}</span></div>'.format(
                i=i, title=esc(f.get("title", "")), camp=esc(f.get("campaign", "")),
                money=esc(money(f.get("money_impact"))))
        )
    out.append("</div>")
    return "".join(out)


def render_card(f):
    s = sev_meta(f.get("severity"))
    parts = ['<div class="card" style="border-left-color:{c}">'.format(c=s["color"])]
    parts.append(
        '<div class="card-head">'
        '<span class="badge" style="background:{bg};color:{c}">{lab}</span>'
        '<span class="area">{area}</span>'
        '<span class="card-title">{title}</span></div>'.format(
            bg=s["bg"], c=s["color"], lab=esc(s["label"]),
            area=esc(f.get("area", "")), title=esc(f.get("title", "")))
    )
    parts.append('<div class="do">→ {rec}</div>'.format(rec=esc(f.get("recommendation", ""))))

    ready = f.get("ready_to_use")
    if ready:
        items = ready if isinstance(ready, list) else [ready]
        parts.append('<div class="ready-cap">Готово к вставке (скопируй целиком):</div>')
        parts.append('<div class="ready">{}</div>'.format(esc("\n".join(str(x) for x in items))))

    def row(key, val, cls=""):
        if not val:
            return ""
        return '<div class="row {cls}"><span class="k">{k}:</span> {v}</div>'.format(
            cls=cls, k=esc(key), v=esc(val))

    parts.append(row("Где в Директе", f.get("where")))
    parts.append(row("Почему", f.get("evidence")))
    parts.append(row("Проверить самому", f.get("how_to_verify"), "verify"))
    parts.append(row("Эффект", f.get("expected_effect")))
    conf = f.get("confidence")
    vol = f.get("volume_note")
    if conf or vol:
        label = "уверенность: {}".format(conf or "—")
        if vol:
            label += " · {}".format(vol)
        parts.append('<div class="row"><span class="conf">{}</span></div>'.format(esc(label)))
    parts.append("</div>")
    return "".join(parts)


def render_campaigns(meta, findings):
    by_camp = {}
    for f in findings:
        by_camp.setdefault(f.get("campaign", "Без кампании"), []).append(f)

    ordered = [c.get("name") for c in sorted(
        meta.get("campaigns", []), key=lambda c: c.get("cost", 0), reverse=True)]
    for name in by_camp:
        if name not in ordered:
            ordered.append(name)

    status = {c.get("name"): c for c in meta.get("campaigns", [])}
    out = []
    for name in ordered:
        items = by_camp.get(name)
        if not items:
            continue
        items.sort(key=lambda f: SEV_ORDER.get(f.get("severity"), 9))
        st = status.get(name, {})
        bits = []
        if st.get("type"):
            bits.append(esc(st["type"]))
        if st.get("cost") is not None:
            bits.append("расход " + esc(money(st["cost"])))
        if st.get("cpa") is not None:
            tail = " ({})".format(esc(st["kpi_status"])) if st.get("kpi_status") else ""
            bits.append("цена заявки " + esc(money(st["cpa"])) + tail)
        status_line = " · ".join(bits)
        out.append('<div class="campaign">')
        out.append(
            '<div class="camp-head"><span class="camp-title">{name}</span>'
            '<span class="camp-status">{st}</span></div><div class="camp-bar"></div>'.format(
                name=esc(name), st=status_line)
        )
        out.extend(render_card(f) for f in items)
        out.append("</div>")
    return "".join(out)


def build_html(data):
    meta = data.get("meta", {})
    findings = data.get("findings", [])
    kpi = meta.get("kpi", {})
    kpi_bits = []
    if kpi.get("cpa"):
        kpi_bits.append("цена заявки — не больше " + money(kpi["cpa"]))
    if kpi.get("drr"):
        kpi_bits.append("ДРР — не больше {}%".format(round(kpi["drr"] * 100)))
    kpi_line = " · ".join(kpi_bits) if kpi_bits else "KPI не заданы — оценка относительная"

    period_line = "Период анализа: " + ru_period(meta.get("period", "—"))
    compared = meta.get("compared_to")
    if compared:
        period_line += "  (сравнение с " + ru_period(compared) + ")"

    limits = meta.get("limitations", [])
    limits_html = ""
    if limits:
        lis = "".join("<li>{}</li>".format(esc(x)) for x in limits)
        limits_html = (
            '<h2>Чего не смогли проверить</h2>'
            '<div class="limits"><ul>{}</ul></div>'.format(lis)
        )

    return """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Аудит Яндекс.Директа</title>
<style>{css}</style></head><body>
<div class="page">
<div class="head">
  <h1>Аудит Яндекс.Директа</h1>
  <p class="period">{period}</p>
  <p class="sub">Аккаунт: {title}{login}</p>
  <p class="kpi-line">Цель (KPI): {kpi}</p>
</div>

{metrics}
{bars}

<h2>Главное — с чего начать</h2>
{top}

<h2>Что сделать в каждой кампании</h2>
{campaigns}

{limits}

<div class="foot">Отчёт подготовлен в режиме «только чтение». Скилл ничего не менял в аккаунте —
все пункты внедряются вручную. Решение по каждому пункту за маркетологом.</div>
</div>
</body></html>""".format(
        css=CSS,
        title=esc(meta.get("slug", "проект")),
        login=(" · логин {}".format(esc(meta["client_login"]))
               if meta.get("client_login") else ""),
        period=period_line,
        kpi=esc(kpi_line),
        metrics=render_metrics(meta.get("summary")),
        bars=render_bars(meta.get("campaigns")),
        top=render_top(findings) or "<p class='sub'>Денежных находок не выделено.</p>",
        campaigns=render_campaigns(meta, findings),
        limits=limits_html,
    )


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description="Сборка HTML-отчёта аудита из findings.json")
    ap.add_argument("--input", required=True, help="путь к findings.json")
    ap.add_argument("--output", help="путь к HTML (по умолчанию АУДИТ_<slug>.html рядом с input)")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)

    slug = data.get("meta", {}).get("slug", "audit")
    base = os.path.dirname(os.path.abspath(args.input))
    html_path = args.output or os.path.join(base, "АУДИТ_{}.html".format(slug))

    out_dir = os.path.dirname(os.path.abspath(html_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_html(data))

    print("Отчёт готов: {}".format(html_path))
    print("Открой в браузере. Нужна печатная версия — Ctrl+P → Сохранить как PDF (вёрстка под A4).")


if __name__ == "__main__":
    main()
