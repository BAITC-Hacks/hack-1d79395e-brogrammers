"""Explainable AML role gates, scores and evidence (TEAM_PLAN 7.2–7.3).

All amounts and routes describe the supplied extract only. A role is a
hypothesis for an analyst, not a finding about an account holder.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd

from graf.config import (
    AGG_MAX_HHI, AGG_MIN_ACTIVE_DAYS, AGG_MIN_IN_DEG, AGG_MIN_ONE_OFF,
    AMBIGUOUS_MARGIN, CONF_LEVELS, CONS_MIN_IN_DEG, COORD_MIN_KEY_LINKS,
    DIST_MIN_OUT_DEG, EXT_FUNDING_MAX_TRACKED_OUT, EXT_FUNDING_PT,
    HHI_DOMINANT, PAYER_MAX_KZT, PAYER_MAX_OUT_DEG, PAYER_MAX_OUT_TX,
    PAYER_TARGET_MIN_IN_DEG, TERMINAL_PT_MAX, TRANSIT_PT,
    TRUNC_TERMINAL_MIN_P,
)


ROLE_LABELS = {
    "coordinator": "кандидат в организаторы",
    "payer": "разовый плательщик (возможный покупатель/потерпевший)",
    "consolidator": "признаки точки консолидации",
    "distributor": "признаки веерного распределения",
    "transit": "признаки транзитного счёта",
    "terminal": "конечный получатель в пределах выгрузки",
    "peripheral": "периферия, признаков роли не выявлено",
}

_BASE_COLUMNS = {
    "gid", "depth", "is_seed", "in_deg", "out_deg", "in_tx", "out_tx",
    "in_kzt", "out_kzt", "pass_through", "in_hhi", "out_hhi",
}
_METRIC_DEFAULTS = {
    "fast_out_share": 0.0, "max_sync_payers": 0,
    "payer_one_off_share": 0.0, "active_in_days": 0,
    "p_forward": 0.0, "truncated": False,
    "tracked_in": 0.0, "tracked_out": 0.0,
    "tracked_share_in": 0.0, "tracked_out_share": 0.0,
    "seed_exp_chrono": 0,
}


def _number(value: object, default: float = 0.0) -> float:
    return float(value) if pd.notna(value) else default


def _fraction(value: object) -> float:
    return min(1.0, max(0.0, _number(value)))


def _money(value: object) -> str:
    amount = _number(value)
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f} млн ₸"
    if amount >= 1_000:
        return f"{amount / 1_000:.0f} тыс. ₸"
    return f"{amount:.0f} ₸"


def _read_excluded(path: Path) -> dict[int, tuple[str, str]]:
    """Read bank-supplied account types without rounding 17-digit gids."""
    if not path.exists():
        return {}
    table = pd.read_csv(path, dtype="string", keep_default_na=False)
    required = {"gid", "account_type", "reason"}
    if not required.issubset(table):
        raise ValueError(f"{path}: required columns {sorted(required)}")
    excluded: dict[int, tuple[str, str]] = {}
    for row in table.itertuples(index=False):
        raw = str(row.gid).strip()
        if not raw:
            continue
        gid = int(raw)
        if gid in excluded:
            raise ValueError(f"{path}: duplicate gid {gid}")
        excluded[gid] = (str(row.account_type).strip(), str(row.reason).strip())
    return excluded


def _max_payer_share(graph: nx.DiGraph, gid: int, in_kzt: float) -> float:
    if in_kzt <= 0:
        return 0.0
    return max(
        (float(data.get("sum_kzt", 0.0)) / in_kzt
         for _, _, data in graph.in_edges(gid, data=True)),
        default=0.0,
    )


def _signals(role: str, row, from_key: int, to_key: int) -> list[str]:
    """Two or three plain, numeric observations supporting the role."""
    if role == "coordinator":
        degrees = f"связей вход/выход {row.in_deg}/{row.out_deg}"
        keys = f"ключевых соседей {from_key}→{to_key}"
        if row.in_deg >= CONS_MIN_IN_DEG and row.out_deg >= DIST_MIN_OUT_DEG:
            return [
                degrees + f" (порог {CONS_MIN_IN_DEG}/{DIST_MIN_OUT_DEG})",
                keys,
            ]
        return [
            keys + f" (порог {COORD_MIN_KEY_LINKS}/{COORD_MIN_KEY_LINKS})",
            degrees,
        ]
    if role == "payer":
        return [
            f"исходящих переводов {row.out_tx}",
            f"отправлено {_money(row.out_kzt)}",
            f"получателей {row.out_deg}",
        ]
    if role == "consolidator":
        return [
            f"плательщиков {row.in_deg}",
            f"пик за день {row.max_sync_payers}",
            f"входящих {_money(row.in_kzt)}",
        ]
    if role == "distributor":
        return [
            f"получателей {row.out_deg}",
            f"отправлено {_money(row.out_kzt)}",
            f"быстро отправлено {100 * _fraction(row.fast_out_share):.0f}%",
        ]
    if role == "transit":
        return [
            f"пропуск {row.pass_through:.2f}",
            f"быстро отправлено {100 * _fraction(row.fast_out_share):.0f}%",
            f"маршрутов seed {row.seed_exp_chrono}",
        ]
    if role == "terminal":
        if row.depth == 4:
            return [
                f"оценка 1−p_forward={1 - _fraction(row.p_forward):.0%} "
                f"по калибровке (порог {TRUNC_TERMINAL_MIN_P:.0%})",
                "колено 4, исходящие не видны",
            ]
        if row.out_deg > 0:
            return [
                f"исходящие {row.pass_through:.2%} входящих (порог <{TERMINAL_PT_MAX:.0%})",
                f"колено {row.depth}, исходящих связей {row.out_deg}",
                f"прослежено {100 * _fraction(row.tracked_share_in):.0f}% входящих",
            ]
        return [
            f"колено {row.depth}",
            f"исходящих связей {row.out_deg}",
            f"прослежено {100 * _fraction(row.tracked_share_in):.0f}% входящих",
        ]
    return [
        f"входящих связей {row.in_deg}",
        f"исходящих связей {row.out_deg}",
        f"маршрутов seed {row.seed_exp_chrono}",
    ]


def _counter_signals(
    row, graph: nx.DiGraph, excluded_info: tuple[str, str] | None,
    external_funding: bool, aggregator_like: bool,
) -> list[tuple[str, str]]:
    """Return (full text, short evidence text), ordered by review importance."""
    counters: list[tuple[str, str]] = []
    if excluded_info is not None:
        account_type, reason = excluded_info
        detail = f"тип счёта «{account_type}»" if account_type else "тип счёта"
        if reason:
            detail += f", {reason}"
        counters.append((f"исключён: {detail} по данным АБС", "исключён по данным АБС"))
    if row.depth == 4:
        pct = 100 * _fraction(row.p_forward)
        counters.append((
            f"обрезан 4-м коленом, p_forward = {pct:.0f}%",
            f"обрыв 4-го колена, p={pct:.0f}%",
        ))
    if external_funding:
        ratio = _number(row.pass_through)
        counters.append((
            f"отправил в {ratio:.1f} раза больше, чем получил в выгрузке: "
            "источник средств вне данных",
            f"внешние средства ×{ratio:.1f}",
        ))
    elif not row.is_seed and _number(row.pass_through) > EXT_FUNDING_PT:
        ratio = _number(row.pass_through)
        counters.append((
            f"исходящие превышают наблюдаемые входящие ×{ratio:.1f}; "
            "возможен начальный остаток или средства вне выборки",
            f"исходящие/входящие ×{ratio:.1f}; баланс неполон",
        ))
    if row.is_seed:
        counters.append((
            "seed: входящие вне выборки не видны",
            "входящие seed вне выборки",
        ))
    if not row.is_seed and row.seed_exp_chrono == 0:
        counters.append((
            "0 хронологически возможных маршрутов от seed",
            "маршрутов от seed 0",
        ))
    if row.in_kzt >= 500_000 and row.tracked_share_in < 0.05:
        pct = 100 * _fraction(row.tracked_share_in)
        counters.append((
            f"лишь {pct:.0f}% входящих прослеживается до денег курьеров",
            f"прослежено {pct:.0f}% входящих",
        ))
    if row.in_hhi >= HHI_DOMINANT:
        largest_pct = 100 * _max_payer_share(graph, int(row.gid), row.in_kzt)
        counters.append((
            f"крупнейший плательщик дал {largest_pct:.0f}% входящих "
            f"(HHI {row.in_hhi:.2f})",
            f"1 плательщик {largest_pct:.0f}%",
        ))
    if aggregator_like:
        counters.append((
            "проверьте тип счёта в АБС: признаки агрегатора "
            f"({row.in_deg} плательщиков, {row.active_in_days} дней)",
            f"похож на агрегатор: {row.in_deg} плательщиков",
        ))
    return counters


def _evidence(label: str, score: float, signals: list[str], counters: list[tuple[str, str]]) -> str:
    head = f"{label} ({score:.2f}): {signals[0]}; {signals[1]}. Контр: "
    tail = counters[0][1] if counters else "не выявлен"
    available = 200 - len(head)
    if len(tail) > available:
        tail = tail[:max(0, available - 1)].rstrip() + "…"
    return head + tail


def assign_roles(
    features: pd.DataFrame,
    graph: nx.DiGraph,
    excluded_path: Path | None = None,
) -> pd.DataFrame:
    """Assign roles while preserving the input row order and every prior feature.

    Gates are evaluated first. The key set is the union of K, D and T gate
    passers, even if a key node's final role becomes coordinator or payer.
    """
    missing = _BASE_COLUMNS - set(features)
    if missing:
        raise ValueError(f"roles require columns: {sorted(missing)}")
    if not features["gid"].is_unique:
        raise ValueError("features.gid must be unique")
    result = features.copy()
    for column, default in _METRIC_DEFAULTS.items():
        if column not in result:
            result[column] = default
    if excluded_path is None:
        excluded_path = Path(__file__).resolve().parent.parent / "config" / "excluded_accounts.csv"
    excluded = _read_excluded(Path(excluded_path))

    # The seed extract omits some incoming transfers. Its pass-through ratio
    # must never determine a role, even when a numeric value is present.
    gate_k = result["in_deg"].ge(CONS_MIN_IN_DEG)
    gate_d = result["out_deg"].ge(DIST_MIN_OUT_DEG)
    gate_t = (
        ~result["is_seed"].astype(bool)
        & result["in_deg"].ge(1) & result["out_deg"].ge(1)
        & result["pass_through"].between(*TRANSIT_PT, inclusive="both")
    )
    key_gids = set(map(int, result.loc[gate_k | gate_d | gate_t, "gid"]))
    result["from_key"] = [
        sum(int(gid) in key_gids for gid in graph.predecessors(int(row.gid)))
        for row in result.itertuples(index=False)
    ]
    result["to_key"] = [
        sum(int(gid) in key_gids for gid in graph.successors(int(row.gid)))
        for row in result.itertuples(index=False)
    ]
    in_degree_by_gid = dict(zip(result["gid"].map(int), result["in_deg"].map(int)))

    role_rows = []
    for i, row in enumerate(result.itertuples(index=False)):
        gid = int(row.gid)
        is_seed = bool(row.is_seed)
        pt = _number(row.pass_through, float("nan"))
        k, d, t = bool(gate_k.iloc[i]), bool(gate_d.iloc[i]), bool(gate_t.iloc[i])
        e = (
            row.depth <= 3 and row.in_deg >= 1
            and (row.out_deg == 0 or (not is_seed and pt < TERMINAL_PT_MAX))
        )
        estimated_e = (
            row.depth == 4 and 1 - _fraction(row.p_forward) >= TRUNC_TERMINAL_MIN_P
        )
        coordinator = (
            (k and d)
            or (row.from_key >= COORD_MIN_KEY_LINKS
                and row.to_key >= COORD_MIN_KEY_LINKS)
        )
        payer = (
            not is_seed and row.out_deg <= PAYER_MAX_OUT_DEG
            and row.out_tx <= PAYER_MAX_OUT_TX
            and row.out_kzt <= PAYER_MAX_KZT
            and any(in_degree_by_gid.get(int(dst), 0) >= PAYER_TARGET_MIN_IN_DEG
                    for dst in graph.successors(gid))
            and not t
        )

        scores: dict[str, float] = {}
        if coordinator:
            scores["coordinator"] = 0.5 + 0.5 * min(1.0, (row.from_key + row.to_key) / 20)
        if payer:
            scores["payer"] = 0.8
        if k:
            scores["consolidator"] = (
                0.4 * min(1.0, row.in_deg / 15)
                + 0.2 * (1 - _fraction(row.in_hhi))
                + 0.2 * min(1.0, row.max_sync_payers / 5)
                + 0.2 * min(1.0, 2 * _fraction(row.tracked_share_in))
            )
        if d:
            scores["distributor"] = (
                0.5 * min(1.0, row.out_deg / 40)
                + 0.3 * (1 - _fraction(row.out_hhi))
                + 0.2 * _fraction(row.fast_out_share)
            )
        if t:
            scores["transit"] = (
                0.5 * max(0.0, 1 - abs(1 - pt) / 0.2)
                + 0.3 * _fraction(row.fast_out_share)
                + 0.2 * (row.seed_exp_chrono > 0)
            )
        if e:
            scores["terminal"] = 0.7 + 0.3 * _fraction(row.tracked_share_in)

        if coordinator:
            role = "coordinator"
        elif payer:
            role = "payer"
        else:
            ordinary = [r for r in ("consolidator", "distributor", "transit", "terminal") if r in scores]
            if ordinary:
                role = max(ordinary, key=scores.__getitem__)
            elif estimated_e:
                role = "terminal"
                scores[role] = 1 - _fraction(row.p_forward)
            else:
                role = "peripheral"
                scores[role] = 0.3 if bool(row.truncated) else 0.5

        score = min(1.0, max(0.0, scores[role]))
        alternatives = sorted(
            ((candidate, value) for candidate, value in scores.items() if candidate != role),
            key=lambda pair: (-pair[1], pair[0]),
        )
        alt = alternatives[0][0] if alternatives else ""
        ambiguous = bool(alt and abs(score - alternatives[0][1]) < AMBIGUOUS_MARGIN)
        confidence = (
            "высокая" if score >= CONF_LEVELS[1] else
            "средняя" if score >= CONF_LEVELS[0] else "низкая"
        )
        external_funding = (
            not is_seed and pt > EXT_FUNDING_PT
            and row.tracked_out_share < EXT_FUNDING_MAX_TRACKED_OUT
        )
        visibility = (
            "out_unseen" if row.depth == 4 else
            "in_unseen_seed" if is_seed else
            "external_funding" if external_funding else "full"
        )
        aggregator_like = (
            row.in_deg >= AGG_MIN_IN_DEG
            and row.payer_one_off_share >= AGG_MIN_ONE_OFF
            and row.in_hhi <= AGG_MAX_HHI
            and row.active_in_days >= AGG_MIN_ACTIVE_DAYS
        )
        excluded_info = excluded.get(gid)
        signals = _signals(role, row, int(row.from_key), int(row.to_key))
        counters = _counter_signals(
            row, graph, excluded_info, external_funding, aggregator_like
        )
        role_rows.append({
            "role": role, "role_score": score,
            "role_label": ROLE_LABELS[role], "role_alt": alt,
            "ambiguous": ambiguous, "confidence_level": confidence,
            "visibility": visibility, "excluded": excluded_info is not None,
            "aggregator_like": aggregator_like,
            "seed_above_bottom": is_seed and role in {
                "coordinator", "consolidator", "distributor"
            },
            "signals": " | ".join(signals),
            "counter_signals": " | ".join(full for full, _ in counters),
            "evidence": _evidence(ROLE_LABELS[role], score, signals, counters),
        })
    role_table = pd.DataFrame(role_rows, index=result.index)
    for column in role_table:
        result[column] = role_table[column]
    return result


def run(context: dict) -> None:
    """Pipeline stage: update ``context['features']`` in place by replacement."""
    context["features"] = assign_roles(
        context["features"], context["graph"], context.get("excluded_path")
    )
