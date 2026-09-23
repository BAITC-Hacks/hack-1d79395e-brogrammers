"""Read-only access to contract §4; exact int64 IDs, strings at UI/JSON boundary."""
from dataclasses import dataclass, field
from io import BytesIO
import json
from pathlib import Path
import zipfile

import pandas as pd
from streamlit import cache_data

from ui.theme import LABELS

ID_COLUMNS = {"gid", "src", "dst", "target_gid", "seed_gid"}
BOOL_COLUMNS = {"is_seed", "excluded", "aggregator_like", "seed_above_bottom", "truncated", "ambiguous", "ok"}
REQUIRED = {
    "nodes_roles": ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"],
    "clusters": ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"],
    "top_nodes": ["rank", "gid", "role", "priority_score", "why"],
}
OPTIONAL = {
    "seeds_review": ["gid", "role", "role_label", "evidence"],
    "paths": ["target_gid", "path_rank", "seed_gid", "hops", "path_gids", "path_days", "path_amounts", "bottleneck_kzt"],
    "resilience": ["strategy", "n_removed", "seed_reach_share", "largest_wcc"],
    "ablation_links": ["level", "n_nonseed_nodes", "share"],
    "tracked_by_depth": ["depth", "tracked_kept_kzt"],
    "truncation_calibration": ["bucket", "n", "p_forward"],
    "data_requests": ["gid", "request", "reason", "priority_score"],
    "audit": ["scope", "check", "count", "ok"],
}


def read_csv(path):
    columns = pd.read_csv(path, nrows=0).columns
    frame = pd.read_csv(path, dtype={c: "Int64" for c in ID_COLUMNS & set(columns)})
    for c in BOOL_COLUMNS & set(columns):
        values = frame[c].astype(str).str.lower().map({"true": True, "false": False, "1": True, "0": False})
        if values.isna().any():
            raise ValueError(f"{Path(path).name}: пустой или некорректный флаг {c}")
        frame[c] = values.astype(bool)
    return frame


def load_raw(data_dir):
    source = Path(data_dir)
    if source.is_file() and source.suffix == ".zip":
        with zipfile.ZipFile(source) as archive:
            frames = [pd.read_parquet(BytesIO(archive.read(f"data/{name}.parquet"))) for name in ("edges", "nodes", "transactions")]
    else:
        try:
            from graf.load import load
        except ModuleNotFoundError as exc:
            if exc.name not in {"graf", "graf.load"}:
                raise
            # B can start before A0; replaced automatically once graf.load exists.
            frames = [pd.read_parquet(source / f"{name}.parquet") for name in ("edges", "nodes", "transactions")]
        else:
            frames = list(load(source))
    edges, nodes, tx = frames
    for frame in frames:
        for c in ID_COLUMNS & set(frame.columns):
            frame[c] = frame[c].astype("int64")
    tx["date"] = pd.to_datetime(tx["date"]).dt.normalize()
    return edges, nodes, tx


@dataclass
class Bundle:
    tables: dict
    graph: dict = field(default_factory=lambda: {"nodes": [], "edges": []})
    meta: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)

    @property
    def nodes(self):
        return self.tables["nodes_roles"]

    @property
    def is_stub(self):
        return bool(self.meta.get("stub") or self.graph.get("meta", {}).get("stub"))


def load_bundle(out_dir):
    root = Path(out_dir)
    tables, missing = {}, []
    for name, columns in {**REQUIRED, **OPTIONAL}.items():
        path = root / f"{name}.csv"
        if not path.exists():
            if name in REQUIRED:
                raise FileNotFoundError(f"Нет {path}. Запустите tools/make_stub_outputs.py или получите выгрузку A.")
            missing.append(path.name)
            tables[name] = pd.DataFrame(columns=columns)
            continue
        frame = read_csv(path)
        absent = set(columns) - set(frame.columns)
        if absent:
            if name in OPTIONAL:
                missing.append(f"{path.name}: нет колонок {', '.join(sorted(absent))}")
                tables[name] = pd.DataFrame(columns=columns)
                continue
            raise ValueError(f"{path.name}: отсутствуют колонки {', '.join(sorted(absent))}")
        if name in {"nodes_roles", "top_nodes", "seeds_review"}:
            frame["role_label"] = frame.get("role_label", frame.role.map(LABELS)).fillna(frame.role.map(LABELS))
        tables[name] = frame
    nodes = tables["nodes_roles"]
    if nodes.empty or nodes.gid.isna().any() or nodes.gid.duplicated().any():
        raise ValueError("nodes_roles.csv: пустая таблица или неуникальные/пустые gid")
    if not nodes.role.isin(LABELS).all():
        raise ValueError("nodes_roles.csv: неизвестная роль")
    for c in ("priority_score", "role_score"):
        if not nodes[c].between(0, 1).all():
            raise ValueError(f"nodes_roles.csv: {c} должен быть в диапазоне 0–1")
    graph, meta = {"nodes": [], "edges": []}, {}
    for filename in ("graph.json", "run_meta.json"):
        path = root / filename
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            if filename == "graph.json":
                graph = obj
            else:
                meta = obj
        else:
            missing.append(filename)
    for node in graph.get("nodes", []):
        node["id"] = str(node["id"])
    for edge in graph.get("edges", []):
        edge["src"], edge["dst"] = str(edge["src"]), str(edge["dst"])
    return Bundle(tables, graph, meta, missing)


def fingerprint(path):
    root = Path(path)
    files = [root] if root.is_file() else sorted(root.glob("*"))
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files if p.is_file())


def status_a(path="docs/STATUS_A.md"):
    path = Path(path)
    return path.read_text(encoding="utf-8").replace("`", "") if path.exists() else ""


def flow_ready(path="docs/STATUS_A.md"):
    import re
    return any("graf.flow.chrono_reach" in line and re.search(r"\bготов\b", line)
               and not re.search(r"\bне\s+готов", line)
               for line in status_a(path).splitlines())


def choose_output(root="."):
    root = Path(root)
    status = status_a(root / "docs/STATUS_A.md")
    import re
    a1_ready = any(re.search(r"\bA1\b", line) and re.search(r"готово|завершен|завершён|done", line, re.I)
                   and "не готов" not in line.lower() for line in status.splitlines())
    return str(root / ("out" if a1_ready and (root / "out/nodes_roles.csv").exists() else "out_stub"))


@cache_data(show_spinner=False)
def cached_bundle(path, stamp):
    """stamp participates in the cache key so a new A export is read immediately."""
    return load_bundle(path)


@cache_data(show_spinner=False)
def cached_raw(path, stamp):
    return load_raw(path)


def display_frame(frame):
    frame = frame.copy()
    for c in ID_COLUMNS & set(frame.columns):
        frame[c] = frame[c].map(lambda x: "" if pd.isna(x) else str(int(x)))
    return frame


def json_records(frame):
    return json.loads(display_frame(frame).to_json(orient="records", date_format="iso", force_ascii=False))


def chronology_filter(nodes, tx, gap_days, ready=False):
    def fallback():
        column = {2: "seed_exp_fast", 31: "seed_exp_chrono"}.get(gap_days)
        if column is None or column not in nodes:
            raise ValueError("Без пересчёта по transactions.parquet доступны только готовые колонки seed_exp_fast / seed_exp_chrono для Δ=2 и Δ=31")
        return nodes.set_index("gid")[column].to_dict(), f"Готовая колонка выгрузки: Δ={gap_days} дней (без пересчёта A2)"
    if not ready or tx is None:
        return fallback()
    try:
        from graf.flow import chrono_reach
    except ModuleNotFoundError as exc:
        if exc.name not in {"graf", "graf.flow"}:
            raise
        return fallback()
    seeds = set(nodes.loc[nodes.is_seed, "gid"].astype(int))
    try:
        return chrono_reach(tx, seeds, gap_days, max_hops=4), f"Хронологический маршрут: Δ≤{gap_days} дней"
    except NotImplementedError:
        return fallback()
