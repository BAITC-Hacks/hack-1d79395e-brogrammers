"""Russian presentation labels and values; analysis tables are never modified."""
from __future__ import annotations

import math
import pandas as pd

from ui.data import ID_COLUMNS, BOOL_COLUMNS
from ui.theme import LABELS

VISIBILITY_LABELS = {
    "full": "Наблюдаемая часть выгрузки",
    "out_unseen": "Исходящие не видны: 4-е колено",
    "in_unseen_seed": "Внешние входящие seed не видны",
    "external_funding": "Признаки внешнего финансирования",
}
STRATEGY_LABELS = {
    "priority": "По приоритету проверки", "betweenness": "По посредничеству",
    "out_deg": "По числу получателей", "in_deg": "По числу плательщиков",
    "random": "Случайно: среднее", "all_seeds": "Удаление всех seed",
}
COMPONENT_LABELS = {
    "role": "Роль", "money": "Атрибутированные деньги и seed",
    "brokerage": "Структурная связность", "volume": "Наблюдаемый оборот",
    "temporal": "Временные признаки",
}
COLUMN_LABELS = {
    "gid": "gid", "src": "Отправитель (gid)", "dst": "Получатель (gid)",
    "target_gid": "Целевой узел (gid)", "seed_gid": "Источник seed (gid)",
    "rank": "Место", "role": "Роль", "role_label": "Роль (гипотеза)",
    "role_score": "Сила признаков роли", "priority_score": "Приоритет проверки",
    "evidence": "Основание роли", "why": "Обоснование приоритета",
    "cluster_id": "Кластер", "role_alt": "Альтернативная роль", "ambiguous": "Близкие оценки ролей",
    "confidence_level": "Уверенность по правилам", "visibility": "Наблюдаемость",
    "excluded": "Исключён по сведениям банка", "aggregator_like": "Признаки агрегатора",
    "seed_above_bottom": "Seed выше нижнего уровня", "is_seed": "Исходный seed",
    "truncated": "Обрыв наблюдения", "depth": "Колено", "p_forward": "Оценка дальнейшей пересылки",
    "in_deg": "Плательщиков", "out_deg": "Получателей", "in_tx": "Входящих переводов",
    "out_tx": "Исходящих переводов", "in_kzt": "Входящая сумма", "out_kzt": "Исходящая сумма",
    "pass_through": "Отправлено / получено", "in_hhi": "Концентрация входящих (HHI)",
    "out_hhi": "Концентрация исходящих (HHI)", "betweenness": "Посредничество в графе",
    "from_key": "Ключевых плательщиков", "to_key": "Ключевых получателей",
    "fast_out_share": "Исходящих в пределах быстрого окна", "max_sync_payers": "Пик плательщиков за день",
    "near_threshold_share": "Переводов около порога выгрузки", "active_in_days": "Дней с входящими",
    "payer_one_off_share": "Разовых плательщиков", "tracked_in": "Атрибутировано входящих",
    "tracked_out": "Атрибутировано исходящих", "tracked_share_in": "Доля атрибутированных входящих",
    "tracked_out_share": "Доля атрибутированных исходящих", "tracked_kept": "Модельный остаток потока",
    "seed_exp_topo": "Seed со структурным маршрутом", "seed_exp_chrono": "Seed с маршрутом по датам",
    "seed_exp_fast": "Seed с быстрым маршрутом", "signals": "Поддерживающие признаки",
    "counter_signals": "Контр-сигналы", "prio_multiplier": "Множитель приоритета",
    "n_nodes": "Узлов", "n_seed": "Seed", "sum_kzt_internal": "Внутренний оборот",
    "tracked_kzt_internal": "Атрибутированный внутренний оборот", "top_gids": "Лидеры кластера (gid)",
    "hypothesis": "Гипотеза о структуре", "fingerprints": "Структурные мотивы",
    "n_trials": "Прогонов", "seed_reach_p05": "5-й процентиль", "seed_reach_p95": "95-й процентиль",
    "strategy": "Порядок удаления", "n_removed": "Удалено узлов",
    "seed_reach_share": "Сохранившаяся достижимость", "largest_wcc": "Узлов в крупнейшем компоненте",
    "level": "Условие маршрута", "n_nonseed_nodes": "Узлов без seed", "share": "Доля узлов",
    "tracked_kept_kzt": "Модельный остаток потока", "bucket": "Входящих переводов", "n": "Узлов в калибровке",
    "request": "Что запросить", "reason": "Зачем", "scope": "Область аудита",
    "check": "Проверка", "count": "Количество", "ok": "Без замечаний",
    "sum_kzt": "Сумма", "n_tx": "Переводов", "date": "Дата",
    "first_date": "Первая дата", "last_date": "Последняя дата",
    "first_day": "Первый день июля", "last_day": "Последний день июля",
    "path_rank": "Маршрут №", "hops": "Переходов", "path_gids": "Маршрут (gid)",
    "path_days": "Дни июля", "path_amounts": "Суммы переходов", "bottleneck_kzt": "Минимальная сумма на пути",
    "tracked_kzt": "Атрибутированная сумма", "step": "Шаг", "day": "День июля",
}
COLUMN_LABELS.update({f"prio_{name}": f"Компонент: {label.lower()}" for name, label in COMPONENT_LABELS.items()})
COLUMN_LABELS.update({f"n_{role}": f"Узлов: {label}" for role, label in LABELS.items()})
MONEY_COLUMNS = {"in_kzt", "out_kzt", "sum_kzt", "sum_kzt_internal", "tracked_in", "tracked_out", "tracked_kept", "tracked_kzt", "tracked_kzt_internal", "tracked_kept_kzt", "bottleneck_kzt"}
PERCENT_COLUMNS = {"fast_out_share", "near_threshold_share", "payer_one_off_share", "p_forward", "tracked_share_in", "tracked_out_share", "seed_reach_share", "share", "seed_reach_p05", "seed_reach_p95"}
DATE_COLUMNS = {"date", "first_date", "last_date"}
MOTIF_LABELS = {"fan_in": "сбор", "fan_out": "рассылка", "chain": "цепь транзита", "scatter_gather": "рассылка и сбор", "cycle": "контур", "fragmentation": "суммы около порога выгрузки"}
LEVEL_LABELS = {"topology": "Структурная связь", "chrono_any": "Хронология, до 31 дня", "chrono_7d": "Хронология, до 7 дней", "chrono_2d": "Хронология, до 2 дней"}
AUDIT_LABELS = {"is_seed": "Seed в топе", "payer": "Разовые плательщики в топе", "excluded": "Исключённые счета в топе", "aggregator_like": "Признаки агрегатора", "visibility != full": "Неполная наблюдаемость", "seed_exp_chrono == 0 (non-seed)": "Нет маршрута от seed (не-seed)"}


def _missing(value):
    return value is None or bool(pd.isna(value))


def money(value, decimals=0):
    if _missing(value) or not math.isfinite(float(value)):
        return "—"
    return f"{float(value):,.{decimals}f}".replace(",", " ") + " ₸"


def percent(value, digits=0):
    if _missing(value) or not math.isfinite(float(value)):
        return "—"
    return f"{float(value):.{digits}%}"


def boolean(value):
    if _missing(value):
        return "—"
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"false", "0", "no", "нет"}:
            return "Нет"
        if token in {"true", "1", "yes", "да"}:
            return "Да"
        return value
    return "Да" if bool(value) else "Нет"


def format_value(column, value):
    if _missing(value):
        return "—"
    if column in ID_COLUMNS:
        return str(value) if isinstance(value, str) else str(int(value))
    if column in MONEY_COLUMNS:
        return money(value)
    if column in PERCENT_COLUMNS:
        return percent(value, 1)
    if column in BOOL_COLUMNS:
        return boolean(value)
    if column in {"role", "role_label", "role_alt"}:
        return LABELS.get(value, value) or "—"
    if column == "visibility":
        return VISIBILITY_LABELS.get(value, value)
    if column == "strategy":
        return STRATEGY_LABELS.get(value, value)
    if column == "level":
        return LEVEL_LABELS.get(value, value)
    if column == "check":
        return AUDIT_LABELS.get(value, value)
    if column == "fingerprints":
        return "; ".join(MOTIF_LABELS.get(token, token) for token in str(value).split(";") if token) or "Нет выраженных мотивов"
    if column in DATE_COLUMNS:
        return pd.Timestamp(value).strftime("%d.%m.%Y")
    if column == "path_gids":
        return str(value).replace(">", " → ")
    if column in {"pass_through", "in_hhi", "out_hhi", "prio_multiplier"}:
        return f"{float(value):.2f}"
    if column in {"role_score", "priority_score", "betweenness"} or column.startswith("prio_"):
        return f"{float(value):.3f}"
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def display_table(frame, *, rename=True):
    """Return display values without rounding identifiers or changing the source.

    Ranks, counts and scores remain numeric so table sorting still works.
    Money, fractions, booleans and categorical labels are formatted for readers.
    """
    result = frame.copy()
    formatted = ID_COLUMNS | MONEY_COLUMNS | PERCENT_COLUMNS | BOOL_COLUMNS | DATE_COLUMNS | {
        "role", "role_label", "role_alt", "visibility", "strategy", "level", "check", "fingerprints", "path_gids"
    }
    for column in result.columns:
        if column in ID_COLUMNS:
            # Nullable Int64.map may pass floats when missing values exist;
            # converting directly to pandas strings preserves every gid digit.
            result[column] = result[column].astype("string").fillna("—")
        elif column in formatted:
            result[column] = result[column].map(lambda value, name=column: format_value(name, value))
    if rename:
        result = result.rename(columns=COLUMN_LABELS)
    return result
