"""Compact factual overview of a node; embedded data is always HTML escaped."""
from html import escape
import math
import pandas as pd
from ui.card import _next_request, _priority_brief, _texts, priority_components
from ui.formatting import format_value, money
from ui.theme import COLORS, LABELS

STYLE = """<style>
.aml-node-overview{color:#14243b;font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0 0 18px;line-height:1.5}
.aml-node-overview *{box-sizing:border-box}
.aml-node-overview .aml-node-header{background:#fff;border:1px solid #e1e6f0;border-radius:14px;padding:20px 24px}
.aml-node-overview .aml-header-line{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
.aml-node-overview .aml-eyebrow{font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700;color:#67788e}
.aml-node-overview .aml-node-id{font:700 24px/1.5 ui-monospace,Consolas,monospace;overflow-wrap:anywhere;margin:3px 0 8px}
.aml-node-overview .aml-role-pill{display:inline-block;padding:4px 10px;border:1px solid;border-radius:6px;font-size:12px;font-weight:650;background:#fff;max-width:100%}
.aml-node-overview .aml-rank{text-align:right;font-size:12px;color:#66768c}
.aml-node-overview .aml-rank strong{display:block;font-size:22px;color:#173d7d}
.aml-node-overview .aml-summary{margin-top:16px;padding:13px 16px;background:#eff4ff;border-radius:9px;border-left:3px solid #255baf}
.aml-node-overview .aml-summary p{margin:5px 0;font-size:13px}
.aml-node-overview .aml-mini-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:15px}
.aml-node-overview .aml-stat-label{font-size:11px;color:#6b7a8f}
.aml-node-overview .aml-stat-value{font-size:17px;font-weight:700;color:#123269}
.aml-node-overview .aml-small{font-size:11px;color:#687a91;margin:9px 0 0}
.aml-node-overview .aml-panel-grid{display:grid;grid-template-columns:1fr 1fr 1.08fr;gap:12px;margin-top:12px}
.aml-node-overview .aml-node-panel{background:#fff;border:1px solid #e1e6f0;border-radius:12px;padding:17px 18px;min-width:0}
.aml-node-overview .aml-panel-title{font-size:13px;font-weight:750;color:#163d77;margin:0 0 11px}
.aml-node-overview ul{margin:0;padding-left:17px;font-size:12px}
.aml-node-overview li{padding:0 0 7px;overflow-wrap:anywhere}
.aml-node-overview .aml-counter li::marker{color:#b2751a}
.aml-node-overview .aml-support li::marker{color:#367b61}
.aml-node-overview .aml-score-row{margin:0 0 9px}
.aml-node-overview .aml-score-label{display:flex;justify-content:space-between;gap:8px;font-size:11px;margin-bottom:3px}
.aml-node-overview .aml-score-track{height:5px;background:#eaf0f8;border-radius:5px;overflow:hidden}
.aml-node-overview .aml-score-fill{height:100%;background:#315fa9;border-radius:5px}
.aml-node-overview .aml-next-request{padding:12px 16px;margin-top:12px;border-radius:9px;background:#f2f5fb;font-size:12px;border:1px solid #e0e7f2}
.aml-node-overview details{margin-top:11px;font-size:12px}
.aml-node-overview summary{cursor:pointer;color:#214d89;font-weight:650}
.aml-node-overview details p{margin:7px 0;overflow-wrap:anywhere}
@media(max-width:1000px){.aml-node-overview .aml-panel-grid{grid-template-columns:1fr 1fr}.aml-node-overview .aml-node-panel:last-child{grid-column:1/-1}.aml-node-overview .aml-mini-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.aml-node-overview .aml-panel-grid{grid-template-columns:1fr}.aml-node-overview .aml-node-header{padding:16px}.aml-node-overview .aml-node-id{font-size:19px}}
</style>"""

def _value(value, default="—"):
    return default if value is None or pd.isna(value) else str(value)

def _safe(value, default="—"):
    return escape(_value(value, default), quote=True)

def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None

def _list(items):
    return "<ul>" + "".join(f"<li>{_safe(item)}</li>" for item in items) + "</ul>"

def node_overview_html(row, bundle):
    """Build read-only panels using persisted model facts and exact identifiers."""
    role = _value(row.get("role"), "")
    label = _value(row.get("role_label"), LABELS.get(role, "Роль не передана"))
    if role == "terminal" and row.get("depth") == 4:
        label += " (оценка на границе)"
    color = COLORS.get(role, "#55657d")
    rank = _number(row.get("rank"))
    rank_html = f"№ {int(rank)}" if rank is not None else "Вне топ-30"
    priority = format_value("priority_score", row.get("priority_score"))
    strength = format_value("role_score", row.get("role_score"))
    why = _value(row.get("why"), "")
    evidence = _value(row.get("evidence"), "Основание роли не передано.")
    supports = _texts(row.get("signals")) or ["Дополнительные сигналы по правилам не сформированы."]
    counters = _texts(row.get("counter_signals"))
    if not counters and "Контр: " in why:
        counters = [why.split("Контр: ", 1)[1]]
    if not counters:
        counters = ["Специфические контр-сигналы не выявлены. Общие ограничения выгрузки сохраняются."]
    if row.get("depth") == 4:
        boundary = "На 4-м колене исходящие не собраны: отсутствие выхода не доказывает удержание денег."
        if not any("4" in item and ("исходящ" in item or "границ" in item) for item in counters):
            counters.append(boundary)
    components = priority_components(row)
    bars = []
    for name, contribution in components.itertuples(index=False, name=None):
        value = float(contribution)
        width = min(100.0, max(0.0, value * 100))
        bars.append(f'<div class="aml-score-row"><div class="aml-score-label"><span>{_safe(name)}</span><strong>{value:.3f}</strong></div><div class="aml-score-track"><div class="aml-score-fill" style="width:{width:.3f}%"></div></div></div>')
    subtotal = float(components["Вклад"].sum()) if not components.empty else None
    multiplier = _number(row.get("prio_multiplier"))
    equation = f"{subtotal:.3f} × {multiplier:.2f} = {priority}" if subtotal is not None and multiplier is not None else "Компоненты или множитель не переданы."
    stats = [("Входящие в выгрузке", money(row.get("in_kzt"))), ("Исходящие в выгрузке", money(row.get("out_kzt"))), ("Атрибутировано входящих", money(row.get("tracked_in"))), ("Seed с маршрутом по датам", format_value("seed_exp_chrono", row.get("seed_exp_chrono")))]
    stats_html = "".join(f'<div><div class="aml-stat-label">{_safe(name)}</div><div class="aml-stat-value">{_safe(value)}</div></div>' for name, value in stats)
    counts = " · ".join(f"{name}: {format_value(key, row.get(key))}" for name, key in [("Входящих переводов", "in_tx"), ("исходящих переводов", "out_tx"), ("дней с входящими", "active_in_days")])
    flags = []
    for key, text in [("is_seed", "Исходный клиент (seed)"), ("excluded", "Исключён по сведениям банка"), ("aggregator_like", "Тип счёта требует проверки в АБС")]:
        flag = row.get(key)
        if flag is not None and pd.notna(flag) and bool(flag):
            flags.append(text)
    flag = row.get("ambiguous")
    if flag is not None and pd.notna(flag) and bool(flag):
        flags.append("Близкая альтернативная роль: " + str(format_value("role_alt", row.get("role_alt"))))
    flags_html = f'<p class="aml-small">{_safe(" · ".join(flags))}</p>' if flags else ""
    full_why = f'<details><summary>Полное обоснование приоритета</summary><p>{_safe(why)}</p></details>' if why else ""
    bars_html = "".join(bars) or '<p class="aml-small">Компоненты приоритета не переданы.</p>'
    return f"""<section class="aml-node-overview" aria-label="Аналитический обзор узла">
<div class="aml-node-header"><div class="aml-header-line"><div><div class="aml-eyebrow">Карточка узла · наблюдаемые переводы</div><div class="aml-node-id">{_safe(format_value("gid", row.get("gid")))}</div><span class="aml-role-pill" style="border-color:{color};color:#14243b">{_safe(label)}</span></div><div class="aml-rank">Очередь проверки<strong>{rank_html}</strong>Приоритет {_safe(priority)}</div></div>
<div class="aml-summary"><div class="aml-eyebrow">Основание роли</div><p>{_safe(evidence)}</p><p><strong>Почему этот приоритет:</strong> {_safe(_priority_brief(row))}</p></div>
<div class="aml-mini-stats">{stats_html}</div><p class="aml-small">{_safe(counts)}</p><p class="aml-small">Атрибуция связывает часть суммы с переводами seed по модели. Маршрут по датам не доказывает движение одних и тех же денег.</p>{flags_html}</div>
<div class="aml-panel-grid"><div class="aml-node-panel aml-support"><h3 class="aml-panel-title">Поддерживающие признаки</h3>{_list(supports)}<p class="aml-small">Сила признаков: {_safe(strength)} · уверенность по правилам: {_safe(row.get("confidence_level"), "не передана")}. Это эвристическая оценка, не вероятность виновности.</p></div><div class="aml-node-panel aml-counter"><h3 class="aml-panel-title">Контр-сигналы и ограничения</h3>{_list(counters)}</div><div class="aml-node-panel"><h3 class="aml-panel-title">Из чего сложился приоритет</h3>{bars_html}<p class="aml-small">Взвешенные вклады на общей шкале 0–1, до множителя.</p><p class="aml-small"><strong>{_safe(equation)}</strong></p>{full_why}</div></div>
<div class="aml-next-request"><strong>Следующий запрос:</strong> {_safe(_next_request(row, bundle))}</div></section>"""

def render_node_overview(st, row, bundle):
    """Render factual header, evidence, signals and actual weighted priority."""
    st.markdown(STYLE + node_overview_html(row, bundle), unsafe_allow_html=True)
