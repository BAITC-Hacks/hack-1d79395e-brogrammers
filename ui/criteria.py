"""Human-readable role rules shared by the node card and evidence workbook."""
from graf import config as c
from ui.theme import LABELS


def role_criteria():
    gates = {
        "coordinator": f"(in_deg ≥ {c.CONS_MIN_IN_DEG} И out_deg ≥ {c.DIST_MIN_OUT_DEG}) ИЛИ (from_key ≥ {c.COORD_MIN_KEY_LINKS} И to_key ≥ {c.COORD_MIN_KEY_LINKS}). key: прошедшие ворота consolidator, distributor или transit.",
        "consolidator": f"in_deg ≥ {c.CONS_MIN_IN_DEG}",
        "distributor": f"out_deg ≥ {c.DIST_MIN_OUT_DEG}",
        "transit": f"Не seed; in_deg ≥ 1; out_deg ≥ 1; {c.TRANSIT_PT[0]} ≤ pass_through ≤ {c.TRANSIT_PT[1]}",
        "terminal": f"depth ≤ 3; in_deg ≥ 1; (out_deg = 0 ИЛИ (не seed И pass_through < {c.TERMINAL_PT_MAX})). Иначе оценка при depth = 4 и 1 − p_forward ≥ {c.TRUNC_TERMINAL_MIN_P}, только если другие ворота не выбраны; исходящие на depth=4 не собраны.",
        "payer": f"Не seed; out_deg ≤ {c.PAYER_MAX_OUT_DEG}; out_tx ≤ {c.PAYER_MAX_OUT_TX}; out_kzt ≤ {c.PAYER_MAX_KZT}; хотя бы один получатель с in_deg ≥ {c.PAYER_TARGET_MIN_IN_DEG}; ворота transit НЕ пройдены.",
        "peripheral": "Ни одна предыдущая роль не выбрана.",
    }
    scores = {
        "coordinator": "0.5 + 0.5·min(1, (from_key + to_key)/20)",
        "consolidator": "0.4·min(1, in_deg/15) + 0.2·(1 − clip(in_hhi)) + 0.2·min(1, max_sync_payers/5) + 0.2·min(1, 2·clip(tracked_share_in))",
        "distributor": "0.5·min(1, out_deg/40) + 0.3·(1 − clip(out_hhi)) + 0.2·clip(fast_out_share)",
        "transit": "0.5·max(0, 1 − |1 − pass_through|/0.2) + 0.3·clip(fast_out_share) + 0.2·[seed_exp_chrono > 0]",
        "terminal": "depth ≤ 3: 0.7 + 0.3·clip(tracked_share_in); depth = 4: 1 − clip(p_forward)",
        "payer": "0.8", "peripheral": "0.3 при truncated, иначе 0.5",
    }
    return [dict(роль=role, role_label=label, ворота=gates[role], скор=scores[role],
                 источник="graf.roles / graf.config; clip(x)=min(1,max(0,x))") for role, label in LABELS.items()]


ROLE_ORDER = ("Порядок: coordinator → payer → наибольший скор среди прошедших ворота "
              "consolidator / distributor / transit / terminal (при равенстве — этот порядок) "
              "→ оценочный terminal на колене 4 → peripheral. Итоговый скор ограничен 0–1. "
              "pass_through = out_kzt / in_kzt; у seed не используется для назначения роли.")
