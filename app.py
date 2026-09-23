"""Track B: Streamlit viewer for the immutable A/B file contract."""
import importlib.util
import os
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from ui.data import load_bundle, load_raw, fingerprint, display_frame, chronology_filter
from ui.theme import COLORS, LABELS, LIMITS, DISCLAIMER, inject_style
from ui.graphs import directed_graph, ego_html, layer_figure
from ui.card import render_card

load_dotenv()
st.set_page_config(page_title="Граф денег · AML", page_icon="◈", layout="wide")
inject_style(st)


@st.cache_data(show_spinner=False)
def cached_bundle(path, stamp):
    return load_bundle(path)


@st.cache_data(show_spinner=False)
def cached_raw(path, stamp):
    return load_raw(path)


@st.cache_data(show_spinner=False)
def cached_chrono(nodes, tx, gap):
    return chronology_filter(nodes, tx, gap)


@st.cache_data(show_spinner=False)
def cached_ego(nodes, edges, selected, hops):
    return ego_html(directed_graph(nodes, edges), selected, hops)


def open_node(gid):
    st.session_state["gid"] = str(gid)
    st.session_state["page"] = "Узел"
    st.query_params["gid"] = str(gid)
    st.rerun()


def show_graph(nodes, edges, selected=None, hops=1):
    html, shown, total = cached_ego(nodes, edges, selected, hops)
    if not shown:
        st.info("Нет узлов для отображения.")
        return
    st.caption(f"Показано {shown} из {total} узлов. Стрелка — направление перевода; ширина — log(суммы).")
    if shown < total:
        st.warning("Граф сокращён до 250 узлов: сначала ближайшие, затем по приоритету. Метрики не пересчитаны.")
    components.html(html, height=600, scrolling=False)


def main():
    with st.sidebar:
        st.markdown("## ◈ Граф денег")
        st.caption("РАБОЧЕЕ МЕСТО AML-АНАЛИТИКА")
        default_out = os.getenv("GRAF_OUT") or ("out" if Path("out/nodes_roles.csv").exists() else "out_stub")
        out_dir = st.text_input("Папка выгрузок", value=default_out)
        data_dir = st.text_input("Исходные данные: папка или ZIP", value=os.getenv("GRAF_DATA", "data"))
        if st.button("Обновить выгрузки", use_container_width=True):
            st.cache_data.clear()
            for key in ["xlsx_all", "xlsx_node", "assistant_messages", "ai_card"]:
                st.session_state.pop(key, None)
            st.rerun()
    st.title("Граф денег")
    st.caption("ОТ СВЯЗЕЙ — К ОБОСНОВАННОМУ ПРИОРИТЕТУ ПРОВЕРКИ")
    try:
        stamp = fingerprint(out_dir)
        bundle = cached_bundle(out_dir, stamp)
    except (FileNotFoundError, ValueError, KeyError, OSError) as exc:
        st.info(str(exc))
        st.code("python tools/make_stub_outputs.py --data data --out out_stub\nstreamlit run app.py", language="bash")
        st.caption("После получения ядра A: python run.py --data data --out out")
        return
    token = (str(Path(out_dir).resolve()), stamp, fingerprint(data_dir))
    if st.session_state.get("source_token") != token:
        for key in ["xlsx_all", "xlsx_node", "assistant_messages", "ai_card"]:
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
    query_gid = st.query_params.get("gid")
    if "gid" not in st.session_state:
        st.session_state.gid = query_gid if query_gid else ids[0]
    with st.sidebar:
        st.divider()
        search = st.text_input("Поиск gid / префикс", placeholder="18 цифр или начало номера", key="search")
        matches = [gid for gid in ids if gid.startswith(search.strip())] if search.strip() else []
        if search.strip():
            if matches:
                chosen = st.selectbox("Совпадения", matches[:100])
                st.caption(f"Найдено {len(matches)}. Показано до 100.")
                if st.button("Открыть узел", use_container_width=True):
                    open_node(chosen)
            else:
                st.info("Такой gid не найден. Проверьте номер или смените папку выгрузок.")
        roles = st.multiselect("Роли на карте и в топе", list(LABELS), default=list(LABELS), format_func=LABELS.get)
        mode = st.radio("Слой анализа", ["Структура", "Деньги курьеров"])
        gap = 31
        if mode == "Деньги курьеров":
            try:
                has_flow = importlib.util.find_spec("graf.flow") is not None
            except ModuleNotFoundError:
                has_flow = False
            if has_flow and tx is not None:
                gap = st.slider("Максимальная задержка Δ, дней", 1, 31, 2)
            else:
                gap = st.select_slider("Задержка Δ, дней", options=[2, 31], value=2)
                st.caption("До подключения graf.flow доступны готовые расчёты для 2 и 31 дней.")
        st.divider()
        for role, color in COLORS.items():
            st.markdown(f'<span style="color:{color}">●</span> {LABELS[role]}', unsafe_allow_html=True)
        st.caption("Чёрная обводка — seed. Пунктирная рамка на ego-графе — неполная наблюдаемость.")
    filtered = nodes.loc[nodes.role.isin(roles)].copy()
    if mode == "Деньги курьеров":
        try:
            counts, explanation = cached_chrono(nodes, tx, gap)
            active = nodes.gid.map(counts).fillna(0).gt(0)
            seeds = nodes.get("is_seed", pd.Series(False, index=nodes.index))
            st.info(f"Узлов в следе {int((active & ~seeds).sum())} из {int((~seeds).sum())} не-seed · {explanation}")
            filtered = filtered.loc[filtered.gid.isin(nodes.loc[active | seeds, "gid"])]
            st.caption("Seed оставлены как источники. Линии — наблюдаемые структурные связи между узлами следа; не доказанные денежные маршруты.")
        except (ValueError, KeyError, NotImplementedError) as exc:
            st.warning(f"Денежный слой недоступен: {exc}")
            filtered = filtered.iloc[0:0]
    columns = st.columns(4)
    columns[0].metric("Узлов в выгрузке", f"{len(nodes):,}")
    columns[1].metric("Видимых связей", f"{len(edges):,}")
    columns[2].metric("Кластеров", len(bundle.tables["clusters"]))
    columns[3].metric("В текущем фильтре", len(filtered))
    page = st.radio("Раздел", ["Топ-лист", "Узел", "Карта по коленам", "Кластеры", "Устойчивость", "Доказательства", "Ассистент"],
                    horizontal=True, key="page", label_visibility="collapsed")
    if page == "Топ-лист":
        st.subheader("Кого проверить первым")
        top = bundle.tables["top_nodes"]
        top = top.loc[top.gid.isin(filtered.gid)].reset_index(drop=True)
        shown = [c for c in ["rank", "gid", "role_label", "priority_score", "confidence_level", "visibility", "why"] if c in top]
        event = st.dataframe(display_frame(top[shown]), hide_index=True, use_container_width=True,
                             on_select="rerun", selection_mode="single-row", key=f"top_{out_dir}_{mode}_{','.join(roles)}")
        if event.selection.rows:
            selected = str(top.iloc[event.selection.rows[0]].gid)
            if st.button(f"Открыть карточку {selected}"):
                open_node(selected)
        st.markdown("**Seed выше нижнего уровня — пересмотреть уровень**")
        st.dataframe(display_frame(bundle.tables["seeds_review"]), hide_index=True, use_container_width=True)
        st.markdown("**Распределение ролей**")
        counts = nodes.role_label.value_counts().rename_axis("Роль").reset_index(name="Узлов")
        st.dataframe(counts, hide_index=True, use_container_width=True)
        if not bundle.tables["audit"].empty:
            with st.expander("Аудит приоритетов"):
                st.dataframe(bundle.tables["audit"], hide_index=True, use_container_width=True)
    elif page == "Узел":
        gid = st.session_state.gid
        selected = nodes.loc[nodes.gid.astype(str).eq(str(gid))]
        if selected.empty:
            st.info("Выбранный gid отсутствует в этой выгрузке. Найдите узел в боковой панели.")
        else:
            st.caption(f"УЗЕЛ {gid} · КАРТОЧКА ПО ПОЛНОЙ ВЫГРУЗКЕ")
            hops = st.radio("Радиус ego-графа", [1, 2], horizontal=True)
            show_graph(nodes, edges, gid, hops)
            render_card(st, selected.iloc[0].to_dict(), bundle, tx)
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
        if "depth" not in filtered:
            st.info("Для карты нужна колонка depth от участника A.")
        elif filtered.empty:
            st.info("Нет узлов в текущем фильтре.")
        else:
            network = st.checkbox("Сетевая раскладка", disabled=not bool(bundle.graph.get("nodes")))
            fig, total_edges = layer_figure(filtered, edges, bundle.graph, st.session_state.gid, network)
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="layers")
            st.caption(f"Показано до 400 из {total_edges} рёбер по сумме; стрелки — у топ-100. Выбор точки открывает доступ к карточке.")
            if event.selection.points:
                custom = event.selection.points[0].get("customdata")
                if custom and str(custom[0]) in ids and st.button(f"Открыть узел {custom[0]}"):
                    open_node(custom[0])
        st.dataframe(bundle.tables["ablation_links"], hide_index=True, use_container_width=True)
        st.caption("Абляция сравнивает достижимость узлов; её доли не являются долями переводов или сумм.")
        st.dataframe(bundle.tables["tracked_by_depth"], hide_index=True, use_container_width=True)
    elif page == "Кластеры":
        clusters = bundle.tables["clusters"]
        st.dataframe(clusters, hide_index=True, use_container_width=True)
        if not clusters.empty:
            cid = st.selectbox("Кластер", clusters.cluster_id.tolist())
            row = clusters.loc[clusters.cluster_id.eq(cid)].iloc[0]
            st.write(row.hypothesis)
            if "fingerprints" in row and pd.notna(row.fingerprints):
                st.caption(" · ".join(str(row.fingerprints).split(";")))
            show_graph(filtered.loc[filtered.cluster_id.eq(cid)], edges)
    elif page == "Устойчивость":
        resilience = bundle.tables["resilience"]
        st.subheader("Что меняется при удалении узлов")
        st.caption("Структурный сценарий. Не прогноз реального поведения участников сети.")
        if resilience.empty:
            st.info("Ожидается resilience.csv от участника A.")
        else:
            regular = resilience.loc[resilience.strategy.ne("all_seeds")]
            st.plotly_chart(px.line(regular.sort_values("n_removed"), x="n_removed", y="seed_reach_share", color="strategy", markers=True,
                                    labels={"n_removed": "Удалено узлов", "seed_reach_share": "Доля достижимости от seed", "strategy": "Стратегия"}), use_container_width=True)
            all_seeds = resilience.loc[resilience.strategy.eq("all_seeds")]
            st.markdown("**Сценарий удаления всех seed**")
            st.dataframe(all_seeds, hide_index=True, use_container_width=True)
            if not all_seeds.empty:
                st.caption(f"Крупнейшая слабосвязная компонента после удаления seed: {int(all_seeds.iloc[0].largest_wcc)} узлов.")
    elif page == "Доказательства":
        st.subheader("Проверяемые основания в одном файле")
        if tx is None:
            st.warning("Для XLSX укажите исходные parquet или ZIP в боковой панели.")
        else:
            from graf.evidence_xlsx import evidence_frames, workbook_bytes, build_node_evidence
            st.caption("Вся база: топ-30 из top_nodes.csv, связанные транзакции, пути, критерии и ограничения. По узлу: выбранный gid.")
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
                st.dataframe(display_frame(frames[sheet]) if sheet != "Признаки" else frames[sheet], hide_index=True, use_container_width=True)
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
            st.caption("Без API работают все локальные разделы и XLSX. Ключ не нужен для pytest.")
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


main()
st.caption(DISCLAIMER)
