"""Offline presentation components for the analyst workspace."""
from __future__ import annotations

from html import escape
import math
from pathlib import Path

import pandas as pd


def inject_workspace_style(st):
    """Load the bundled stylesheet without external assets or scripts."""
    css = Path(__file__).with_suffix(".css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _number(value):
    return f"{value:,.0f}".replace(",", " ")


def _finite_sum(records, key):
    values = []
    for row in records:
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        values.append(value)
    return math.fsum(values) if values else None


def _summary(bundle, tx=None):
    """Derive header facts from the loaded bundle; never infer calendar dates."""
    nodes = bundle.nodes
    edges = bundle.graph.get("edges", [])
    seeds = int(nodes["is_seed"].fillna(False).sum()) if "is_seed" in nodes else None
    volume = _finite_sum(edges, "sum_kzt")
    count = len(tx) if tx is not None else _finite_sum(edges, "n_tx")
    period = "Нет исходных дат"
    if tx is not None and "date" in tx and not tx.empty:
        dates = pd.to_datetime(tx["date"], errors="coerce").dropna()
        if not dates.empty:
            first, last = dates.min(), dates.max()
            period = first.strftime("%d.%m.%Y") if first == last else f"{first:%d.%m.%Y} – {last:%d.%m.%Y}"
    return [
        ("Узлов в выгрузке", _number(len(nodes))),
        ("Исходных seed", _number(seeds) if seeds is not None else "Нет флага seed"),
        ("Переводов", _number(count) if count is not None else "Нет данных"),
        ("Оборот графа", _number(volume) + " ₸" if volume is not None else "Нет графа"),
        ("Период переводов", period),
    ]


def workspace_header(st, bundle, tx=None):
    """Render product identity and real dataset facts, before page navigation."""
    facts = "".join(
        '<div class="workspace-fact"><span class="workspace-fact-label">'
        + escape(label) + '</span><strong>' + escape(value) + '</strong></div>'
        for label, value in _summary(bundle, tx)
    )
    logo = '<svg viewBox="0 0 40 40" width="40" height="40" aria-hidden="true"><rect width="40" height="40" rx="9" fill="#00236f"/><path d="M11 27L20 12L29 26M11 27L29 26" fill="none" stroke="#a9c7ff" stroke-width="2"/><circle cx="20" cy="12" r="4" fill="white"/><circle cx="11" cy="27" r="4" fill="white"/><circle cx="29" cy="26" r="4" fill="white"/></svg>'
    status = "Демонстрационная выгрузка" if getattr(bundle, "is_stub", False) else "Анализ загруженной выгрузки"
    st.markdown(
        '<header class="workspace-header"><div class="workspace-brand-row">'
        '<div class="workspace-brand">' + logo + '<div><div class="workspace-brand-title">Граф денег</div>'
        '<div class="workspace-brand-subtitle">Финмониторинг · Рабочее место аналитика</div></div></div>'
        '<span class="workspace-status">' + escape(status) + '</span></div>'
        '<div class="workspace-facts" aria-label="Состав загруженных данных">' + facts + '</div></header>',
        unsafe_allow_html=True,
    )


def page_intro(st, kicker, title, description):
    """Render a consistent page heading; all supplied text is HTML escaped."""
    st.markdown(
        '<section class="workspace-page-intro"><div class="workspace-kicker">'
        + escape(str(kicker)) + '</div><h1>' + escape(str(title)) + '</h1><p>'
        + escape(str(description)) + '</p></section>', unsafe_allow_html=True,
    )
