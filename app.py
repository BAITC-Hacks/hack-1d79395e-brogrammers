"""Track B: Streamlit viewer for the immutable A/B file contract."""
import importlib.util
import os
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from ui.data import cached_bundle, cached_raw, fingerprint, display_frame, chronology_filter, choose_output, flow_ready
from ui.theme import COLORS, LABELS, LIMITS, DISCLAIMER, inject_style
from ui.graphs import directed_graph, ego_html, layer_figure
from ui.card import render_card, render_summary, render_counterparties
from ui.formatting import display_table
from ui.navigation import selected_gid

load_dotenv()
st.set_page_config(page_title="Граф денег · AML", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
inject_style(st)


@st.cache_data(show_spinner=False)
def cached_chrono(nodes, tx, gap, ready):
    return chronology_filter(nodes, tx, gap, ready=ready)


@st.cache_data(show_spinner=False)
def cached_ego(nodes, edges, selected, hops):
    return ego_html(directed_graph(nodes, edges), selected, hops)


def open_node(gid):
    st.session_state["pending_gid"] = str(gid)
    st.rerun()


def back_node():
    history = st.session_state.get("node_history", [])
    if history:
        st.session_state["pending_gid"] = history.pop()
        st.session_state["skip_node_history"] = True


def navigate(page):
    st.session_state["page"] = page


def reset_filters():
    st.session_state["role_filter"] = list(LABELS)
    st.session_state["analysis_mode"] = "Структура"


def select_map_node():
    gid = selected_gid(st.session_state.get("layers", {}), st.session_state.get("visible_gids", []))
    if gid is not None:
        st.session_state["map_selected"] = gid
        st.session_state["gid"] = gid
        st.query_params["gid"] = gid


def show_graph(nodes, edges, selected=None, hops=1):
    html, shown, total = cached_ego(nodes, edges, selected, hops)
    if not shown:
        st.info("Нет узлов для отображения.")
        return
    st.caption(f"Показано {shown} из {total} узлов. Стрелка — направление перевода; толще линия — больше сумма.")
    if shown < total:
        st.warning("Граф сокращён до 250 узлов: сначала ближайшие, затем по приоритету. Метрики не пересчитаны.")
    st.caption("Подписи соседей сокращены; полный gid — при наведении. Колесо мыши или кнопки на графе меняют масштаб.")
    components.html(html, height=600, scrolling=False)


def main():
    if "pending_gid" in st.session_state:
        target_gid = st.session_state.pop("pending_gid")
        previous_gid = st.session_state.get("gid")
        skip_history = st.session_state.pop("skip_node_history", False)
        if not skip_history:
            if st.session_state.get("page") == "Узел" and previous_gid and previous_gid != target_gid:
                st.session_state["node_history"] = (st.session_state.get("node_history", []) + [previous_gid])[-30:]
            elif st.session_state.get("page") != "Узел":
                st.session_state["node_history"] = []
        st.session_state["gid"] = target_gid
        st.session_state["page"] = "Узел"
        st.session_state["map_selected"] = st.session_state["gid"]
        st.session_state["scroll_to_top"] = True
        st.query_params["gid"] = st.session_state["gid"]
    with st.sidebar:
        st.markdown("## ◈ Граф денег")
        st.caption("РАБОЧЕЕ МЕСТО АНАЛИТИКА")
        sidebar_controls = st.container()
        with st.expander("Источники данных", expanded=False):
            default_out = os.getenv("GRAF_OUT") or choose_output()
            out_dir = st.text_input("Папка выгрузок", value=default_out)
            data_dir = st.text_input("Исходные данные: папка или ZIP", value=os.getenv("GRAF_DATA", "data"))
            if st.button("Обновить выгрузки", width="stretch"):
                st.cache_data.clear()
                for key in ["xlsx_all", "xlsx_node", "assistant_messages", "ai_card", "node_history", "skip_node_history"]:
                    st.session_state.pop(key, None)
                st.rerun()
    st.title("Граф денег")
    st.caption("Кого проверить первым, на каких основаниях и каких данных не хватает.")
    try:
        stamp = fingerprint(out_dir)
        bundle = cached_bundle(out_dir, stamp)
    except (FileNotFoundError, ValueError, KeyError, OSError) as exc:
        st.info(str(exc))
        st.code("python run.py --data data --out out\nstreamlit run app.py", language="bash")
        st.caption("Проверьте папки в блоке «Источники данных» слева, затем обновите выгрузки.")
        return
    token = (str(Path(out_dir).resolve()), stamp, fingerprint(data_dir))
    if st.session_state.get("source_token") != token:
        for key in ["xlsx_all", "xlsx_node", "assistant_messages", "ai_card", "node_history", "skip_node_history"]:
            st.session_state.pop(key, None)
        st.session_state["source_token"] = token
    nodes = bundle.nodes
    if bundle.is_stub:
        st.warning("ДЕМОНСТРАЦИОННАЯ ЗАГЛУШКА. Роли, приоритеты, денежный след и устойчивость не являются результатами анализа. Суммы и связи взяты из исходных данных.")
    if bundle.missing:
        with st.expander(f"Неполная выгрузка: отсутствуют {len(bundle.missing)} файлов"):
            st.write(", ".join(bundle.missing))
    edges, tx = bundle.graph.get("edges", []), None
    try:
        raw_edges, _, tx = cached_raw(data_dir, fingerprint(data_dir))
        if "graph.json" in bundle.missing:
            edges = raw_edges.to_dict("records")
    except (FileNotFoundError, OSError, KeyError, ValueError) as exc:
        st.caption(f"Исходные транзакции недоступны: {exc}")
    ids = nodes.gid.astype(str).tolist()
    st.session_state["known_gids"] = ids
    query_gid = st.query_params.get("gid")
    if "gid" not in st.session_state:
        st.session_state.gid = query_gid if query_gid else ids[0]
    with sidebar_controls:
        search = st.text_input("Поиск gid / префикс", placeholder="18 цифр или начало номера", key="search")
        matches = [gid for gid in ids if gid.startswith(search.strip())] if search.strip() else []
        if search.strip():
            if matches:
                chosen = st.selectbox("Совпадения", matches[:100])
                st.caption(f"Найдено {len(matches)}. Показано до 100.")
                if st.button("Открыть узел", width="stretch"):
                    open_node(chosen)
            else:
                st.info("Такой gid не найден. Проверьте номер или смените папку выгрузок.")
        mode = st.radio("Слой анализа", ["Структура", "Деньги курьеров"], key="analysis_mode", help="Структура — все наблюдаемые связи. Деньги курьеров — узлы с хронологически возможным маршрутом от seed.")
        gap = 31
        if mode == "Деньги курьеров":
            try:
                has_flow = flow_ready() and importlib.util.find_spec("graf.flow") is not None
            except ModuleNotFoundError:
                has_flow = False
            if has_flow and tx is not None:
                gap = st.slider("Максимальная задержка Δ, дней", 1, 31, 2)
            else:
                gap = st.select_slider("Задержка Δ, дней", options=[2, 31], value=2)
                st.caption("Без исходных транзакций доступны сохранённые расчёты для 2 и 31 дней.")
        with st.expander("Фильтр ролей", expanded=False):
            roles = st.multiselect("Роли на карте и в топе", list(LABELS), default=list(LABELS), format_func=LABELS.get, key="role_filter")
            st.button("Сбросить фильтры", on_click=reset_filters, width="stretch")
        st.caption(f"Выбрано ролей: {len(roles)} из {len(LABELS)}")
        with st.expander("Обозначения на графе", expanded=False):
            for role, color in COLORS.items():
                st.markdown(f'<span style="color:{color}">●</span> {LABELS[role]}', unsafe_allow_html=True)
            st.caption("Самая толстая чёрная рамка — исходные клиенты (seed). Полупрозрачная рамка или заливка — неполная наблюдаемость; на ego-графе — контрастный пунктир. Усиленная рамка у остальных узлов — топ-30.")
            st.caption("Исходные клиенты (seed) — счета, от которых собрана сеть. Роли — гипотезы для проверки.")
        st.caption(f"Источник: {Path(out_dir).name}")
    filtered = nodes.loc[nodes.role.isin(roles)].copy()
    if mode == "Деньги курьеров":
        try:
            counts, explanation = cached_chrono(nodes, tx, gap, flow_ready())
            active = nodes.gid.map(counts).fillna(0).gt(0)
            seeds = nodes.get("is_seed", pd.Series(False, index=nodes.index))
            if st.session_state.get("page", "Топ-лист") != "Узел":
                st.info(f"Узлов в следе {int((active & ~seeds).sum())} из {int((~seeds).sum())} не-seed · {explanation}")
            filtered = filtered.loc[filtered.gid.isin(nodes.loc[active | seeds, "gid"])]
            if st.session_state.get("page", "Топ-лист") != "Узел":
                st.caption("Исходные клиенты (seed) оставлены как источники. Линии — наблюдаемые структурные связи между узлами следа; не доказанные денежные маршруты.")
        except (ValueError, KeyError, NotImplementedError) as exc:
            st.warning(f"Денежный слой недоступен: {exc}")
            filtered = filtered.iloc[0:0]
    st.session_state["visible_gids"] = filtered.gid.astype(str).tolist()
    page = st.radio("Раздел", ["Топ-лист", "Узел", "Карта по коленам", "Кластеры", "Устойчивость", "Доказательства", "Ассистент"],
                    horizontal=True, key="page", label_visibility="collapsed")
    if page != "Узел":
        overview = st.expander("Сводка исходной выгрузки", expanded=False) if page == "Топ-лист" else st.container()
        with overview:
            columns = st.columns(4)
            columns[0].metric("Узлов в выгрузке", f"{len(nodes):,}")
            columns[1].metric("Связей в выгрузке", f"{len(edges):,}")
            columns[2].metric("Кластеров", len(bundle.tables["clusters"]))
            columns[3].metric("Узлов после фильтров", len(filtered))
    if page in {"Топ-лист", "Карта по коленам"}:
        filter_info, filter_action = st.columns([4, 1.5])
        role_text = "все 7" if len(roles) == len(LABELS) else ", ".join(LABELS[role] for role in roles) or "не выбраны"
        layer_text = mode + (f" · Δ={gap} дн." if mode == "Деньги курьеров" else "")
        filter_info.caption(f"Активные фильтры · Роли: {role_text} · Слой: {layer_text} · Узлов: {len(filtered)} из {len(nodes)}")
        filter_action.button("Сбросить фильтры", on_click=reset_filters, key="reset_visible", width="stretch")
    if page == "Топ-лист":
        st.subheader("Кого проверить первым")
        top = bundle.tables["top_nodes"]
        top = top.loc[top.gid.isin(filtered.gid)].reset_index(drop=True)
        st.caption(f"В выбранных фильтрах: {len(top)} из {len(bundle.tables['top_nodes'])} узлов топ-листа. Нажмите строку, чтобы открыть карточку.")
        st.caption("Приоритет задаёт очередь проверки. Он не является вероятностью виновности или рекомендацией блокировки.")
        if top.empty:
            st.info("В топ-30 нет узлов с такими условиями. Данные в выгрузке есть — сбросьте фильтры, чтобы вернуться к списку.")
            st.button("Показать весь топ-лист", on_click=reset_filters)
        shown = [c for c in ["rank", "gid", "role_label", "priority_score", "confidence_level", "visibility", "why"] if c in top]
        table_key = f"top_{out_dir}_{mode}_{gap}_{','.join(roles)}"
        def select_top_row():
            rows = st.session_state[table_key].get("selection", {}).get("rows", [])
            if rows and rows[0] < len(top):
                st.session_state["pending_gid"] = str(top.iloc[rows[0]].gid)
        top_display = display_frame(top[shown])
        from ui.formatting import VISIBILITY_LABELS
        top_display["visibility"] = top_display["visibility"].map(VISIBILITY_LABELS).fillna(top_display["visibility"])
        st.dataframe(top_display, hide_index=True, width="stretch",
                     on_select=select_top_row, selection_mode="single-row", key=table_key,
                     column_config={"rank": "Место", "gid": "gid", "role_label": "Роль (гипотеза)",
                                    "priority_score": st.column_config.NumberColumn("Приоритет", format="%.3f"),
                                    "confidence_level": "Уверенность", "visibility": "Наблюдаемость", "why": st.column_config.TextColumn("Основания", width="large")})
        st.markdown("**Исходные клиенты (seed) для дополнительной проверки · вся выгрузка**")
        st.dataframe(display_frame(bundle.tables["seeds_review"].drop(columns=["role"], errors="ignore")),
                     hide_index=True, width="stretch",
                     column_config={"role_label": "Роль (гипотеза)", "evidence": "Основания"})
        st.markdown("**Распределение ролей · вся выгрузка**")
        counts = nodes.role_label.value_counts().rename_axis("Роль").reset_index(name="Узлов")
        st.dataframe(counts, hide_index=True, width="stretch")
        if not bundle.tables["audit"].empty:
            with st.expander("Аудит приоритетов"):
                st.dataframe(bundle.tables["audit"], hide_index=True, width="stretch")
    elif page == "Узел":
        gid = st.session_state.gid
        selected = nodes.loc[nodes.gid.astype(str).eq(str(gid))]
        if selected.empty:
            st.info("Выбранный gid отсутствует в этой выгрузке. Найдите узел в боковой панели.")
        else:
            st.caption(f"УЗЕЛ {gid} · КАРТОЧКА ПО ПОЛНОЙ ВЫГРУЗКЕ")
            if st.session_state.get("node_history"):
                st.button("← К предыдущему узлу", on_click=back_node,
                          help="Возврат к счёту, из карточки которого открыт этот контрагент; фильтры сохраняются.")
            actions = st.columns(3)
            actions[0].button("← К топ-листу", on_click=navigate, args=("Топ-лист",), width="stretch")
            actions[1].button("Показать на карте", on_click=navigate, args=("Карта по коленам",), width="stretch")
            prepared = st.session_state.get("xlsx_node")
            if prepared and prepared[0] == str(gid):
                actions[2].download_button("Скачать XLSX узла", prepared[1], f"evidence_{gid}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"card_download_{gid}", width="stretch")
            elif actions[2].button("Подготовить XLSX узла", key=f"card_xlsx_{gid}", width="stretch", disabled=tx is None,
                                  help="Шесть листов с данными только этого счёта. После подготовки здесь появится кнопка скачивания."):
                from graf.evidence_xlsx import build_node_evidence
                try:
                    with st.spinner("Собираю отчёт выбранного счёта…"):
                        st.session_state["xlsx_node"] = (str(gid), build_node_evidence(gid, data_dir, out_dir))
                    st.rerun()
                except (ValueError, OSError, KeyError) as exc:
                    st.error(f"Не удалось собрать XLSX: {exc}")
            if tx is None:
                st.caption("Чтобы подготовить XLSX, укажите исходные транзакции в разделе «Источники данных» слева.")
            st.button("Доказательства узла", on_click=navigate, args=("Доказательства",),
                      help="Открывает общий раздел доказательств с предпросмотром всех листов.")
            render_summary(st, selected.iloc[0].to_dict(), bundle)
            render_counterparties(st, selected.iloc[0].to_dict(), bundle, tx, on_open_node=open_node)
            st.subheader("Связи выбранного узла")
            hops = st.radio("Связи на расстоянии 1–2 переводов", [1, 2], horizontal=True,
                            help="1 — прямые плательщики и получатели. 2 — также контрагенты этих соседей.")
            show_graph(nodes, edges, gid, hops)
            render_card(st, selected.iloc[0].to_dict(), bundle, tx, summary=False, show_counterparties=False)
            if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"):
                if st.button("AI-карточка"):
                    from graf.assistant import node_card
                    with st.spinner("Проверяю данные узла…"):
                        try:
                            st.session_state.ai_card = (str(gid), node_card(str(gid), out_dir))
                        except Exception:
                            st.error("AI-сервис недоступен. Проверьте ключ, модель и соединение. Локальные данные доступны.")
                card = st.session_state.get("ai_card")
                if card and card[0] == str(gid):
                    st.write(card[1]["text"])
    elif page == "Карта по коленам":
        st.subheader("Структура сети и наблюдаемые границы")
        highlighted = st.session_state.get("map_selected") or (st.session_state.gid if st.query_params.get("gid") else None)
        if highlighted and highlighted not in ids:
            st.info("Ранее выбранный узел отсутствует в этой выгрузке. Найдите другой счёт через поиск слева.")
            highlighted = None
        elif highlighted and highlighted not in set(filtered.gid.astype(str)):
            st.info("Выбранный узел скрыт текущими фильтрами. Остальные узлы показаны без затемнения.")
            st.button("Показать выбранный узел: сбросить фильтры", on_click=reset_filters, key="reveal_node")
        if "depth" not in filtered:
            st.info("В выгрузке отсутствует глубина узлов. Пересчитайте данные командой из README.")
        elif filtered.empty:
            st.info("Нет узлов в текущем фильтре.")
        else:
            network = st.checkbox("Сетевая раскладка", disabled=not bool(bundle.graph.get("nodes")))
            st.caption("Нажмите узел: он и его соседи выделятся. Наведите курсор, чтобы увидеть роль и основания.")
            fig, total_edges = layer_figure(filtered, edges, bundle.graph, highlighted, network)
            st.plotly_chart(fig, width="stretch", on_select=select_map_node, selection_mode="points", key="layers")
            st.caption(f"Показано {min(400, total_edges)} из {total_edges} связей между видимыми узлами; стрелки — у {min(100, total_edges)} крупнейших. Полупрозрачная рамка или заливка — неполная наблюдаемость. Самая толстая чёрная рамка — исходные клиенты (seed), усиленная у остальных — топ-30.")
            if highlighted and highlighted in ids:
                st.caption(f"Выбран узел {highlighted}")
                if st.button(f"Открыть узел {highlighted}"):
                    open_node(highlighted)
        st.dataframe(display_table(bundle.tables["ablation_links"]), hide_index=True, width="stretch")
        st.caption("Сравнение условий маршрута: доли относятся к числу достижимых узлов, а не к переводам или суммам.")
        st.dataframe(display_table(bundle.tables["tracked_by_depth"]), hide_index=True, width="stretch")
    elif page == "Кластеры":
        clusters = bundle.tables["clusters"]
        st.subheader("Группы связанных счетов")
        st.caption("Кластер объединяет близкие по связям узлы. Его гипотеза требует проверки; это не установленная группа лиц.")
        st.dataframe(display_table(clusters), hide_index=True, width="stretch")
        if not clusters.empty:
            cid = st.selectbox("Кластер", clusters.cluster_id.tolist())
            row = clusters.loc[clusters.cluster_id.eq(cid)].iloc[0]
            st.write(row.hypothesis)
            if "fingerprints" in row and pd.notna(row.fingerprints):
                st.caption(" · ".join(str(row.fingerprints).split(";")))
            visible_cluster = filtered.loc[filtered.cluster_id.eq(cid)]
            total_cluster = int(nodes.cluster_id.eq(cid).sum())
            st.caption(f"Таблица и гипотеза — по всему кластеру. На схеме {len(visible_cluster)} из {total_cluster} узлов после фильтров ролей и слоя анализа.")
            if visible_cluster.empty:
                st.info("Фильтры скрыли все узлы этого кластера. Сбросьте их, чтобы увидеть связи.")
                st.button("Сбросить фильтры кластера", on_click=reset_filters)
            else:
                show_graph(visible_cluster, edges)
    elif page == "Устойчивость":
        resilience = bundle.tables["resilience"]
        st.subheader("Что меняется при удалении узлов")
        st.info("Очередь проверки учитывает прослеживаемые деньги и роли. Этот график решает другую задачу — сравнивает потерю связности при условном удалении узлов.")
        st.caption("Структурный сценарий. Не прогноз реального поведения участников сети и не рекомендация блокировки счетов.")
        if resilience.empty:
            st.info("Ожидается resilience.csv от участника A.")
        else:
            from ui.formatting import STRATEGY_LABELS
            regular = resilience.loc[resilience.strategy.ne("all_seeds")].copy()
            regular["strategy"] = regular.strategy.map(STRATEGY_LABELS).fillna(regular.strategy)
            resilience_fig = px.line(regular.sort_values("n_removed"), x="n_removed", y="seed_reach_share", color="strategy", markers=True,
                                     labels={"n_removed": "Удалено узлов", "seed_reach_share": "Осталось достижимых узлов", "strategy": "Стратегия"})
            random_curve = resilience.loc[resilience.strategy.eq("random")].sort_values("n_removed")
            if {"seed_reach_p05", "seed_reach_p95", "n_trials"}.issubset(random_curve.columns) and not random_curve.empty:
                resilience_fig.add_trace(go.Scatter(
                    x=random_curve.n_removed, y=random_curve.seed_reach_p95,
                    mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip",
                ))
                resilience_fig.add_trace(go.Scatter(
                    x=random_curve.n_removed, y=random_curve.seed_reach_p05,
                    mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor="rgba(100,116,139,0.14)", name="Случайно: диапазон 5–95%", hoverinfo="skip",
                ))
                trials = int(random_curve.n_trials.max())
                st.caption(f"Случайная стратегия — среднее по {trials} воспроизводимым порядкам удаления. Заливка — 5-й–95-й процентили результатов, а не доверительный интервал среднего.")
            resilience_fig.update_yaxes(tickformat=".0%")
            resilience_fig.update_layout(legend=dict(orientation="h", y=-0.22), margin=dict(t=20, b=90))
            st.plotly_chart(resilience_fig, width="stretch")
            all_seeds = resilience.loc[resilience.strategy.eq("all_seeds")]
            st.markdown("**Сценарий удаления всех seed**")
            st.dataframe(display_table(all_seeds), hide_index=True, width="stretch")
            if not all_seeds.empty:
                st.caption(f"Крупнейшая слабосвязная компонента после удаления seed: {int(all_seeds.iloc[0].largest_wcc)} узлов.")
    elif page == "Доказательства":
        st.subheader("Проверяемые основания в одном файле")
        if tx is None:
            st.warning("Для XLSX укажите исходные parquet или ZIP в боковой панели.")
        else:
            from graf.evidence_xlsx import evidence_frames, workbook_bytes, build_node_evidence
            st.caption("Вся база: топ-30, связанные транзакции и пути, критерии и все запросы дополнительных данных по сети. По узлу: только выбранный счёт и его основания.")
            st.info(f"Выбранный узел: {st.session_state.gid}. Для другой карточки воспользуйтесь поиском слева.")
            if st.button("Подготовить всю базу XLSX"):
                with st.spinner("Собираю шесть листов…"):
                    try:
                        frames = evidence_frames(data_dir, out_dir)
                        st.session_state.xlsx_all = (workbook_bytes(frames), frames)
                    except (ValueError, OSError, KeyError) as exc:
                        st.error(f"Не удалось собрать XLSX: {exc}")
            if "xlsx_all" in st.session_state:
                payload, frames = st.session_state.xlsx_all
                st.download_button("Вся база (XLSX)", payload, "evidence.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                sheet = st.selectbox("Предпросмотр листа", list(frames))
                preview = (display_frame(frames[sheet]) if sheet != "Признаки" else frames[sheet]).copy()
                for column in ("role", "role_alt", "роль"):
                    if column in preview:
                        preview[column] = preview[column].map(lambda value: LABELS.get(value, value))
                st.dataframe(preview, hide_index=True, width="stretch",
                             column_config={"date": st.column_config.DateColumn("Дата", format="DD.MM.YYYY"),
                                            "src": "Отправитель (gid)", "dst": "Получатель (gid)",
                                            "sum_kzt": st.column_config.NumberColumn("Сумма, ₸", format="%.2f")})
            gid = st.session_state.gid
            if st.button(f"Подготовить XLSX узла {gid}"):
                try:
                    st.session_state.xlsx_node = (str(gid), build_node_evidence(gid, data_dir, out_dir))
                except (ValueError, OSError, KeyError) as exc:
                    st.error(f"Не удалось собрать XLSX: {exc}")
            item = st.session_state.get("xlsx_node")
            if item and item[0] == str(gid):
                st.download_button("Только выбранный узел (XLSX)", item[1], f"evidence_{gid}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif page == "Ассистент":
        st.subheader("Вопрос по данным графа")
        if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL"):
            st.info("Чтобы включить ассистента, задайте OPENAI_API_KEY и OPENAI_MODEL в .env и перезапустите приложение.")
            st.caption("Поиск, карточки, графы и XLSX полностью работают без ассистента.")
        else:
            st.caption("Ассистент читает только локальные выгрузки. По вашему вопросу выбранные признаки передаются в OpenAI. Каждый вопрос — отдельный запрос по графу.")
            question = st.chat_input("Например: покажи первые пять точек консолидации и их контр-сигналы")
            if question:
                from graf.assistant import ask_graph
                with st.spinner("Проверяю связи и признаки…"):
                    try:
                        answer = ask_graph(question, out_dir)
                        st.session_state.assistant_messages = (st.session_state.get("assistant_messages", []) + [(question, answer)])[-6:]
                    except Exception:
                        st.error("AI-сервис недоступен. Проверьте ключ, модель и соединение. Локальные данные доступны.")
            for index, (question, answer) in enumerate(st.session_state.get("assistant_messages", [])):
                with st.chat_message("user"):
                    st.write(question)
                with st.chat_message("assistant"):
                    st.write(answer["text"])
                    for gid in answer["gids"][:20]:
                        if st.button(f"Узел {gid}", key=f"answer_{index}_{gid}"):
                            open_node(gid)
    with st.expander("Ограничения данных и интерпретации"):
        for item in LIMITS:
            st.write(f"• {item}")
    st.divider()
    scroll_requested = st.session_state.pop("scroll_to_top", False)
    if st.session_state.get("last_page") != page or scroll_requested:
        sequence = st.session_state.get("navigation_sequence", 0) + 1
        st.session_state["navigation_sequence"] = sequence
        # This is static application code; no data or user input enters HTML.
        # Section navigation should open at the summary, not at the scroll
        # offset retained from the previous long graph/card.
        st.html(
            "<script>requestAnimationFrame(() => {"
            "document.querySelector('[data-testid=stMain]')?.scrollTo({top:0});"
            "window.scrollTo({top:0});"
            f"}}); // navigation {sequence}\n</script>",
            unsafe_allow_javascript=True,
        )
    st.session_state["last_page"] = page


main()
st.caption(DISCLAIMER)
