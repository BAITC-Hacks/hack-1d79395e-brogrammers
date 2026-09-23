"""Readable node overview, evidence and optional analytic detail."""
import pandas as pd
import plotly.express as px

from graf.config import FAST_DAYS, PRIORITY_WEIGHTS
from ui.formatting import COLUMN_LABELS, COMPONENT_LABELS, display_table, format_value, money, percent
from ui.theme import LABELS


def counterparties(tx, gid, direction):
    anchor, peer = ("dst", "src") if direction == "in" else ("src", "dst")
    return (tx.loc[tx[anchor].eq(int(gid))].groupby(peer, as_index=False)
            .agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"), first_date=("date", "min"), last_date=("date", "max"))
            .sort_values(["sum_kzt", peer], ascending=[False, True]).head(5))


def _texts(value):
    if value is None or pd.isna(value):
        return []
    return [part.strip() for part in str(value).split(" | ") if part.strip()]


def priority_components(row):
    """Actual additive contributions before the explicit priority multiplier."""
    return pd.DataFrame([
        {"Компонент": COMPONENT_LABELS[name], "Вклад": float(row[f"prio_{name}"]) * weight}
        for name, weight in PRIORITY_WEIGHTS.items()
        if f"prio_{name}" in row and pd.notna(row[f"prio_{name}"])
    ], columns=["Компонент", "Вклад"])


def _priority_brief(row):
    """Two strongest non-role contributions, explained through observed facts."""
    facts = {}
    if pd.notna(row.get("tracked_in")) and pd.notna(row.get("seed_exp_chrono")):
        facts["money"] = (
            f"атрибутировано {money(row['tracked_in'])}, "
            f"маршрут по датам от {int(row['seed_exp_chrono'])} seed"
        )
    if pd.notna(row.get("in_kzt")) and pd.notna(row.get("out_kzt")):
        facts["volume"] = f"сумма входящих и исходящих {money(row['in_kzt'] + row['out_kzt'])}"
    if row.get("in_deg", 0) > 0 and row.get("out_deg", 0) > 0 and pd.notna(row.get("prio_brokerage")):
        facts["brokerage"] = f"при удалении теряется {percent(row['prio_brokerage'], 2)} достижимости от seed"
    if pd.notna(row.get("max_sync_payers")) and pd.notna(row.get("fast_out_share")):
        from graf.config import SYNC_MIN_PAYERS
        if row['max_sync_payers'] >= SYNC_MIN_PAYERS:
            facts["temporal"] = f"до {int(row['max_sync_payers'])} разных плательщиков за один день"
        else:
            facts["temporal"] = f"{percent(row['fast_out_share'])} исходящих в пределах {FAST_DAYS} дней после поступления"
    order = sorted(
        (name for name in facts if pd.notna(row.get(f"prio_{name}"))),
        key=lambda name: -float(row[f"prio_{name}"]) * PRIORITY_WEIGHTS[name],
    )
    if order:
        return "; ".join(facts[name] for name in order[:2]) + "."
    return "Дополнительные факты для объяснения приоритета не переданы."


def _next_request(row, bundle):
    if bundle is None or "data_requests" not in bundle.tables:
        return "План запросов не передан в эту карточку."
    requests = bundle.tables["data_requests"]
    selected = requests.loc[requests.gid.eq(int(row["gid"]))]
    if selected.empty:
        return "Специальных запросов по заданным правилам нет; общие ограничения данных сохраняются."
    return str(selected.iloc[0]["request"])


def render_summary(st, row, bundle=None):
    """Compact interpretation suitable for placing above the node graph."""
    heading = row.get("role_label") or LABELS.get(row.get("role"), "Роль не передана")
    if row.get("role") == "terminal" and row.get("depth") == 4:
        heading += " (оценка на границе)"
    st.subheader(heading)
    st.info(row.get("evidence", "Основание роли не передано."))
    columns = st.columns(3)
    columns[0].metric("Приоритет проверки", format_value("priority_score", row.get("priority_score")))
    columns[1].metric(
        "Атрибутировано входящих", money(row.get("tracked_in")),
        help="Часть входящей суммы, которую модель связывает с переводами исходных клиентов (seed). Это оценка по выгрузке, а не доказательство происхождения денег.",
    )
    columns[2].metric(
        "Источников с маршрутом к узлу", format_value("seed_exp_chrono", row.get("seed_exp_chrono")),
        help="Число исходных клиентов, от которых к этому узлу существует маршрут с неубывающими датами. Маршрут не доказывает движение одних и тех же денег.",
    )
    st.caption(
        f"Сила признаков роли: {format_value('role_score', row.get('role_score'))}; "
        f"уверенность по правилам: {row.get('confidence_level', 'не передана')}. "
        "Это эвристическая оценка, не вероятность виновности."
    )
    st.markdown("**Почему этот приоритет:** " + _priority_brief(row))
    counters = _texts(row.get("counter_signals"))
    if counters:
        st.warning(f"Главный контр-сигнал: {counters[0]}")
    elif "Контр: " in str(row.get("why", "")):
        st.caption("Ограничение вывода: " + str(row["why"]).split("Контр: ", 1)[1])
    else:
        st.caption("Специфический контр-сигнал не выявлен. Атрибуция модельная; даты не доказывают происхождение средств.")
    st.markdown("**Следующий шаг:** " + _next_request(row, bundle))
    if row.get("ambiguous", False):
        st.caption("Близкая альтернативная роль: " + format_value("role_alt", row.get("role_alt")))



def render_counterparties(st, row, bundle, tx, on_open_node=None):
    """Show observed incoming/outgoing peers and optionally open selected nodes."""
    gid = int(row["gid"])
    if tx is None:
        st.caption("Транзакции не загружены: суммы по контрагентам недоступны. Готовые признаки и маршруты показаны из выгрузки.")
        return
    known_gids = set(bundle.nodes["gid"].astype("string"))
    left, right = st.columns(2)
    for column, direction, peer, title in [
        (left, "in", "src", "Кто переводил на этот счёт"),
        (right, "out", "dst", "Кому переводил этот счёт"),
    ]:
        with column:
            st.markdown(f"**{title}**")
            table = counterparties(tx, gid, direction)
            if table.empty:
                st.caption("Входящие переводы в выгрузке отсутствуют." if direction == "in" else "Исходящие переводы в выгрузке отсутствуют.")
                continue
            key = f"peer_{gid}_{direction}"
            # Capture IDs directly from the integer column, not from a mixed
            # pandas row, which could round an 18-digit gid through float64.
            peer_ids = tuple(table[peer].astype("string"))
            options = {}
            if on_open_node is not None:
                def select_peer(widget_key=key, ids=peer_ids):
                    state = st.session_state.get(widget_key, {})
                    selected = state.get("selection", {}).get("rows", [])
                    if not selected:
                        return
                    index = selected[0]
                    if type(index) is not int or not 0 <= index < len(ids):
                        return
                    peer_gid = ids[index]
                    if isinstance(peer_gid, str) and peer_gid in known_gids:
                        on_open_node(peer_gid)
                options = {"on_select": select_peer, "selection_mode": "single-row"}
                st.caption("До 5 крупнейших контрагентов. Выберите строку, чтобы открыть карточку.")
            else:
                st.caption("До 5 крупнейших контрагентов по наблюдаемой сумме переводов.")
            st.dataframe(display_table(table[[peer, "sum_kzt", "n_tx"]]), hide_index=True, width="stretch", key=key, **options)


def render_card(st, row, bundle, tx, summary=True, on_open_node=None, show_counterparties=True):
    """Render details; callers can place render_summary above their own graph."""
    gid = int(row["gid"])
    if summary:
        render_summary(st, row, bundle)

    with st.expander("Основания и критерии роли"):
        left, right = st.columns(2)
        with left:
            st.markdown("**Поддерживающие признаки**")
            for text in _texts(row.get("signals")) or ["Дополнительные сигналы не переданы."]:
                st.write(f"• {text}")
        with right:
            st.markdown("**Контр-сигналы**")
            for text in _texts(row.get("counter_signals")) or ["Специфические контр-сигналы по заданным правилам не выявлены."]:
                st.write(f"• {text}")
        from graf.evidence_xlsx import role_criteria
        criteria = role_criteria().set_index("роль")
        role = row.get("role")
        if role in criteria.index:
            st.markdown("**Правило выбранной роли**")
            st.write(criteria.loc[role, "ворота"])
            st.caption("Скор: " + criteria.loc[role, "скор"])
        st.caption("Порядок выбора: " + criteria.loc["Порядок выбора", "ворота"])

    with st.expander("Как сложился приоритет"):
        components = priority_components(row)
        if not components.empty:
            chart = px.bar(components, x="Вклад", y="Компонент", orientation="h", color_discrete_sequence=["#3b82f6"])
            chart.update_layout(height=260, margin=dict(l=0, r=15, t=5, b=0), yaxis_title=None,
                                xaxis_title="Вклад до применения множителей")
            chart.update_traces(hovertemplate="%{y}: %{x:.3f}<extra></extra>")
            st.plotly_chart(chart, width="stretch")
            subtotal = components["Вклад"].sum()
            multiplier = row.get("prio_multiplier", 1.0)
            st.caption(
                f"В каждом столбце признак уже умножен на свой вес. "
                f"Сумма {subtotal:.3f} × множитель {float(multiplier):.2f} "
                f"= приоритет {float(row['priority_score']):.3f}. "
                "Очередь проверки не является планом блокировки счетов."
            )
        else:
            st.caption("Компоненты приоритета не переданы.")
        if row.get("why") and pd.notna(row["why"]):
            st.write(row["why"])

    details = [name for name in [
        "visibility", "excluded", "aggregator_like", "truncated", "is_seed", "depth",
        "p_forward", "in_deg", "out_deg", "in_tx", "out_tx", "in_kzt", "out_kzt",
        "pass_through", "in_hhi", "out_hhi", "from_key", "to_key", "fast_out_share",
        "max_sync_payers", "near_threshold_share", "tracked_in", "tracked_out",
        "tracked_kept", "tracked_share_in", "tracked_out_share", "seed_exp_topo",
        "seed_exp_chrono", "seed_exp_fast",
    ] if name in row and (name != "p_forward" or bool(row.get("truncated", False)))]
    values = [
        "Не интерпретируется у seed" if name == "pass_through" and bool(row.get("is_seed", False))
        else format_value(name, row[name]) for name in details
    ]
    with st.expander("Все признаки, наблюдаемость и атрибутированный поток"):
        st.dataframe(pd.DataFrame({"Признак": [COLUMN_LABELS.get(name, name) for name in details], "Значение": values}),
                     hide_index=True, width="stretch")
        st.caption(f"Быстрое окно — от 0 до {FAST_DAYS} дней после наблюдаемого поступления. "
                   "Наблюдаемость описывает выгрузку; полный баланс счёта неизвестен.")

    if show_counterparties:
        render_counterparties(st, row, bundle, tx, on_open_node=on_open_node)

    st.markdown("**Хронологически возможные маршруты**")
    paths = bundle.tables["paths"]
    selected = paths.loc[paths.target_gid.eq(gid)]
    if selected.empty:
        st.caption("Подготовленные маршруты для этого узла отсутствуют. Это не доказывает отсутствие пути от seed.")
    else:
        st.caption("Маршрут совместим с датами переводов; он не доказывает движение одних и тех же денег.")
    for path in selected.itertuples():
        st.code(str(path.path_gids).replace(">", " → "), language=None)
        amounts = " → ".join(money(float(value)) for value in str(path.path_amounts).split(">"))
        days = str(path.path_days).replace(">", " → ")
        st.caption(f"Дни июля: {days} · суммы: {amounts} · минимум по пути: {money(path.bottleneck_kzt)}")

    clusters = bundle.tables["clusters"]
    cluster = clusters.loc[clusters.cluster_id.eq(row["cluster_id"])]
    if not cluster.empty:
        st.markdown(f"**Кластер {int(row['cluster_id'])}**")
        st.write(cluster.iloc[0].hypothesis)
    requests = bundle.tables["data_requests"]
    selected_requests = requests.loc[requests.gid.eq(gid)]
    st.markdown("**Что запросить дальше**")
    if selected_requests.empty:
        st.caption("Специальные запросы по заданным правилам не сформированы. Общие ограничения данных сохраняются.")
    else:
        shown = [name for name in ["request", "reason"] if name in selected_requests]
        st.dataframe(display_table(selected_requests[shown]), hide_index=True, width="stretch")
