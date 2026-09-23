import pandas as pd
import plotly.express as px

from ui.data import display_frame


def counterparties(tx, gid, direction):
    anchor, peer = ("dst", "src") if direction == "in" else ("src", "dst")
    return (tx.loc[tx[anchor].eq(int(gid))].groupby(peer, as_index=False)
            .agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"), first_date=("date", "min"), last_date=("date", "max"))
            .sort_values(["sum_kzt", peer], ascending=[False, True]).head(5))


def render_card(st, row, bundle, tx):
    gid = int(row["gid"])
    st.subheader(row["role_label"])
    cols = st.columns(3)
    cols[0].metric("Приоритет проверки", f"{row['priority_score']:.3f}")
    cols[1].metric("Сила признаков роли", f"{row['role_score']:.2f}")
    cols[2].metric("Уверенность", row.get("confidence_level", "не передана"))
    st.caption("Скор роли — эвристическая оценка, не вероятность виновности.")
    if row.get("ambiguous", False):
        st.warning(f"Неоднозначная роль. Альтернатива: {row.get('role_alt', 'не передана')}")
    st.info(row["evidence"])
    left, right = st.columns(2)
    with left:
        st.markdown("**Сигналы**")
        for text in str(row.get("signals", "Сигналы не переданы")).split(" | "):
            if text and text != "nan":
                st.write(f"• {text}")
    with right:
        st.markdown("**Контр-сигналы**")
        for text in str(row.get("counter_signals", "Контр-сигналы не переданы")).split(" | "):
            if text and text != "nan":
                st.write(f"⚠ {text}")
    components = {c.removeprefix("prio_"): row[c] for c in ["prio_role", "prio_money", "prio_brokerage", "prio_volume", "prio_temporal"] if c in row and pd.notna(row[c])}
    if components:
        frame = pd.DataFrame({"Компонент": components.keys(), "Вклад": components.values()})
        st.plotly_chart(px.bar(frame, x="Вклад", y="Компонент", orientation="h", color_discrete_sequence=["#193f64"]), use_container_width=True)
        st.caption(f"Множитель приоритета: {row.get('prio_multiplier', 'не передан')}")
    details = [c for c in ["visibility", "excluded", "aggregator_like", "truncated", "p_forward", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "tracked_in", "tracked_share_in", "seed_exp_topo", "seed_exp_chrono", "seed_exp_fast"] if c in row]
    with st.expander("Признаки, наблюдаемость и прослеживаемый поток", expanded=True):
        st.dataframe(pd.DataFrame({"Признак": details, "Значение": [str(row[c]) for c in details]}), hide_index=True, use_container_width=True)
    if tx is not None:
        left, right = st.columns(2)
        for column, direction, title in [(left,"in","Топ-5 входящих"),(right,"out","Топ-5 исходящих")]:
            with column:
                st.markdown(f"**{title}**")
                st.dataframe(display_frame(counterparties(tx, gid, direction)), hide_index=True, use_container_width=True)
    else:
        st.warning("Транзакции не загружены: таблицы контрагентов и XLSX недоступны.")
    st.markdown("**Пути денег**")
    paths = bundle.tables["paths"]
    selected = paths.loc[paths.target_gid.eq(gid)]
    if selected.empty:
        st.caption("Пути для этого узла не переданы. Это не доказывает отсутствие маршрутов.")
    for r in selected.itertuples():
        st.code(str(r.path_gids).replace(">", " → "), language=None)
        st.caption(f"Дни июля: {r.path_days} · суммы: {r.path_amounts} · минимум по пути: {r.bottleneck_kzt:,.0f} ₸")
    clusters = bundle.tables["clusters"]
    cluster = clusters.loc[clusters.cluster_id.eq(row["cluster_id"])]
    if not cluster.empty:
        st.markdown(f"**Кластер {row['cluster_id']}**")
        st.write(cluster.iloc[0].hypothesis)
    requests = bundle.tables["data_requests"]
    st.markdown("**Что запросить дальше**")
    st.dataframe(display_frame(requests.loc[requests.gid.eq(gid)]), hide_index=True, use_container_width=True)
