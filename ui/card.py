import pandas as pd
import plotly.express as px

from ui.data import display_frame
from ui.theme import LABELS, stretch
from ui.criteria import role_criteria, ROLE_ORDER

FEATURE_LABELS = {
    "visibility": "Наблюдаемость", "excluded": "Исключён по данным банка", "aggregator_like": "Проверить тип счёта в АБС",
    "truncated": "Обрыв исходящих на колене 4", "p_forward": "Оценка вероятности продолжения за границей",
    "is_seed": "Исходный клиент (seed)", "in_deg": "Разных плательщиков", "out_deg": "Разных получателей",
    "in_kzt": "Входящая сумма в выгрузке, ₸", "out_kzt": "Исходящая сумма в выгрузке, ₸",
    "tracked_in": "Атрибутированный вход от seed, ₸", "tracked_share_in": "Доля атрибутированного входа",
    "seed_exp_topo": "Seed с путём по структуре", "seed_exp_chrono": "Seed с маршрутом по датам",
    "seed_exp_fast": "Seed с маршрутом ≤2 дней", "from_key": "Ключевых плательщиков", "to_key": "Ключевых получателей",
}
VISIBILITY_LABELS = {"full": "Полная в пределах выгрузки", "out_unseen": "Исходящие за коленом 4 не собраны",
                     "in_unseen_seed": "Входящие seed неполны", "external_funding": "Есть финансирование извне наблюдаемого потока"}


def feature_value(name, value):
    if pd.isna(value):
        return "Нет данных"
    if name == "visibility":
        return VISIBILITY_LABELS.get(value, str(value))
    if name in {"excluded", "aggregator_like", "truncated", "is_seed"}:
        return "Да" if value else "Нет"
    if name in {"p_forward", "tracked_share_in"}:
        return f"{float(value):.1%}"
    if name in {"in_kzt", "out_kzt", "tracked_in"}:
        return f"{float(value):,.0f}"
    return str(value)


def counterparties(tx, gid, direction):
    anchor, peer = ("dst", "src") if direction == "in" else ("src", "dst")
    return (tx.loc[tx[anchor].eq(int(gid))].groupby(peer, as_index=False)
            .agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"), first_date=("date", "min"), last_date=("date", "max"))
            .sort_values(["sum_kzt", peer], ascending=[False, True]).head(5))


def render_card(st, row, bundle, tx, graph_renderer=None):
    gid = int(row["gid"])
    st.subheader(row["role_label"])
    cols = st.columns(3)
    cols[0].metric("Приоритет проверки", f"{row['priority_score']:.3f}")
    cols[1].metric("Сила признаков роли", f"{row['role_score']:.2f}")
    cols[2].metric("Уверенность", row.get("confidence_level", "не передана"))
    st.caption("Скор роли — эвристическая оценка, не вероятность виновности.")
    if row.get("ambiguous", False):
        alternative = row.get("role_alt", "не передана")
        st.warning(f"Неоднозначная роль. Альтернатива: {LABELS.get(alternative, alternative)}")
    st.markdown("**Почему проверить этот узел**")
    top = bundle.tables["top_nodes"]
    ranked = top.loc[top.gid.eq(gid)]
    if not ranked.empty:
        st.write(str(ranked.iloc[0].why))
    st.info(row["evidence"])
    if row.get("depth") == 4:
        st.warning("Исходящие на четвёртом колене не собраны. Нулевой выход не доказывает, что деньги остались у клиента; роль конечного получателя здесь — оценка по калибровке.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Сигналы**")
        for text in str(row.get("signals", "Сигналы не переданы")).split(" | "):
            if text and text != "nan":
                st.write(f"• {text}")
    with right:
        st.markdown("**Контр-сигналы**")
        counters = [t for t in str(row.get("counter_signals", "")).split(" | ") if t and t != "nan"]
        if not counters and not ranked.empty and "Контр:" in str(ranked.iloc[0].why):
            counters = [str(ranked.iloc[0].why).split("Контр:", 1)[1].strip()]
        for text in counters:
            st.write(f"⚠ {text}")
        if not counters:
            st.caption("Отдельные контр-сигналы не сформированы; общие ограничения выгрузки сохраняются.")
    requests = bundle.tables["data_requests"]
    st.markdown("**Что запросить дальше**")
    selected_requests = requests.loc[requests.gid.eq(gid)]
    if selected_requests.empty:
        st.caption("Специальные запросы не сформированы. Сверьте основание роли и ограничения выгрузки перед решением.")
    for r in selected_requests.itertuples():
        st.write(f"• {r.request}: {r.reason}")
    st.caption("Справку с переводами и запросами можно скачать во вкладке «Доказательства» → «Только выбранный узел».")
    if graph_renderer:
        st.markdown("**Связи выбранного узла**")
        graph_renderer()
    with st.expander("Точное правило роли и порядок выбора"):
        rule = next(r for r in role_criteria() if r["роль"] == row["role"])
        st.write(rule["ворота"])
        st.write("Скор: " + rule["скор"])
        st.caption(ROLE_ORDER)
    components = {c.removeprefix("prio_"): row[c] for c in ["prio_role", "prio_money", "prio_brokerage", "prio_volume", "prio_temporal"] if c in row and pd.notna(row[c])}
    if components:
        names = {"role": "Роль", "money": "След денег seed", "brokerage": "Потеря достижимости", "volume": "Оборот", "temporal": "Временные признаки"}
        frame = pd.DataFrame({"Компонент": [names.get(k, k) for k in components], "Вклад": components.values()})
        st.plotly_chart(px.bar(frame, x="Вклад", y="Компонент", orientation="h", color_discrete_sequence=["#193f64"]), **stretch(st.dataframe))
        st.caption(f"Множитель приоритета: {row.get('prio_multiplier', 'не передан')}")
    details = [c for c in FEATURE_LABELS if c in row and (c != "p_forward" or row.get("depth") == 4)]
    with st.expander("Признаки, наблюдаемость и прослеживаемый поток", expanded=True):
        st.dataframe(pd.DataFrame({"Признак": [FEATURE_LABELS[c] for c in details], "Значение": [feature_value(c, row[c]) for c in details]}), hide_index=True, **stretch(st.dataframe))
    if tx is not None:
        left, right = st.columns(2)
        for column, direction, title in [(left,"in","Топ-5 входящих"),(right,"out","Топ-5 исходящих")]:
            with column:
                st.markdown(f"**{title}**")
                st.dataframe(display_frame(counterparties(tx, gid, direction)), hide_index=True, **stretch(st.dataframe),
                             column_config={"src": "Плательщик (gid)", "dst": "Получатель (gid)",
                                            "sum_kzt": st.column_config.NumberColumn("Сумма, ₸", format="%.0f"),
                                            "n_tx": "Переводов", "first_date": st.column_config.DateColumn("Первая дата", format="DD.MM.YYYY"),
                                            "last_date": st.column_config.DateColumn("Последняя дата", format="DD.MM.YYYY")})
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
