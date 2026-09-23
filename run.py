#!/usr/bin/env python3
"""One-command entry point for the directed money graph analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from graf import (
    check, clusters, config, features, fingerprints, flow, priority, resilience,
    roles, temporal, truncation,
)
from graf.evidence_xlsx import build_evidence
from graf.load import build_graph, load, sanity_check
from graf.outputs import write_outputs


def _load(context: dict) -> None:
    edges, nodes, tx = load(context["data_dir"])
    sanity_check(edges, nodes, tx)
    context.update(
        edges=edges,
        nodes=nodes,
        tx=tx,
        graph=build_graph(edges, nodes),
    )


def _features(context: dict) -> None:
    context["features"] = features.compute_features(
        context["edges"], context["nodes"], context["graph"]
    )


def _temporal(context: dict) -> None:
    context["features"] = temporal.add_temporal(
        context["features"], context["tx"], context["edges"]
    )


def _truncation(context: dict) -> None:
    calibration = truncation.calibrate(context["features"])
    context["features"] = truncation.apply(context["features"], calibration)
    calibration.to_csv(context["out_dir"] / "truncation_calibration.csv", index=False)


def _outputs(context: dict) -> None:
    context["row_counts"] = write_outputs(
        context["features"], context["edges"], context["graph"], context["out_dir"], context.get("clusters")
    )


def _evidence_xlsx(context: dict) -> None:
    workbook = context["out_dir"] / "evidence.xlsx"
    workbook.unlink(missing_ok=True)
    build_evidence(context["data_dir"], context["out_dir"])
    if not workbook.is_file():
        raise FileNotFoundError(f"evidence_xlsx did not create {workbook}")

def _check(context: dict) -> None:
    check.check_outputs(context["out_dir"])


STAGES = (
    ("load", _load),
    ("features", _features),
    ("temporal", _temporal),
    ("truncation", _truncation),
    ("flow", flow.run),
    ("roles", roles.run),
    ("clusters", clusters.run),
    ("fingerprints", fingerprints.run),
    ("priority", priority.run),
    ("resilience", resilience.run),
    ("outputs", _outputs),
    ("evidence_xlsx", _evidence_xlsx),
    ("check", _check),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    context = {"data_dir": args.data, "out_dir": args.out}
    stage_times: dict[str, float] = {}
    skipped: list[str] = []
    started = perf_counter()
    for name, stage in STAGES:
        stage_started = perf_counter()
        try:
            stage(context)
        except NotImplementedError as error:
            skipped.append(name)
            label = "предупреждение" if name == "evidence_xlsx" else "пропущено"
            print(f"{name}: {label} ({error})")
        except Exception as error:
            if name != "evidence_xlsx":
                raise
            skipped.append(name)
            print(f"{name}: предупреждение ({error})")
        finally:
            stage_times[name] = round(perf_counter() - stage_started, 4)
        print(f"{name}: {stage_times[name]:.3f} с")
    meta = {
        "data_dir": str(args.data),
        "out_dir": str(args.out),
        "parameters": {
            name: value for name, value in sorted(vars(config).items())
            if name.isupper()
        },
        "stages_sec": stage_times,
        "skipped_stages": skipped,
        "total_sec": round(perf_counter() - started, 4),
        "rows": context.get("row_counts", {}),
    }
    (args.out / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Готово за {meta['total_sec']:.2f} с: {args.out}")


if __name__ == "__main__":
    main()
