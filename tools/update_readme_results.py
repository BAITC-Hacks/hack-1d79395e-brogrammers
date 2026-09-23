"""Refresh README from A's exports after A4; never changes out/."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.data import load_bundle, status_a


def table(frame):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    rows = [list(frame.columns)] + frame.astype(str).values.tolist()
    result = ['| ' + ' | '.join(map(cell, rows[0])) + ' |', '| ' + ' | '.join(['---']*len(rows[0])) + ' |']
    result += ['| ' + ' | '.join(map(cell, row)) + ' |' for row in rows[1:]]
    return '\n'.join(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='out')
    args=parser.parse_args()
    ready=any(re.search(r'\bA4\b',line) and 'готово' in line and 'не готово' not in line for line in status_a().splitlines())
    if not ready:
        print('A4 ещё не отмечен готовым: README сохраняет плейсхолдеры.')
        return
    b=load_bundle(args.out)
    if b.is_stub:
        raise ValueError('README результатов нельзя заполнять заглушкой')
    required=['audit','truncation_calibration','ablation_links','tracked_by_depth','resilience']
    if any(b.tables[t].empty for t in required):
        raise ValueError('A4 отмечен готовым, но не все таблицы результатов получены')
    top=b.tables['top_nodes'].sort_values('rank')
    first=b.nodes.loc[b.nodes.gid.eq(top.iloc[0].gid)].iloc[0]
    latest=b.tables['resilience'].sort_values('n_removed').groupby('strategy',sort=True).tail(1)
    values={
        'FINAL_RESULTS_FROM_A4':f"Реальная выгрузка `{args.out}`: {len(b.nodes)} узлов, {len(b.graph.get('edges', []))} рёбер, {len(b.tables['clusters'])} кластеров, топ-{len(top)}. Время из `run_meta.json`: {b.meta.get('total_sec', 'нет данных')} с. Пропущенные этапы: {b.meta.get('skipped_stages', [])}.",
        'EVIDENCE_EXAMPLE_FROM_A4':str(first.evidence),
        'AUDIT_AND_TRUNCATION_FROM_A4':'Аудит (`audit.csv`):\n\n'+table(b.tables['audit'])+'\n\nКалибровка (`truncation_calibration.csv`):\n\n'+table(b.tables['truncation_calibration']),
        'ABLATION_AND_TRACKED_FROM_A4':'Абляция (`ablation_links.csv`):\n\n'+table(b.tables['ablation_links'])+'\n\nАтрибутированное оседание, ₸ (`tracked_by_depth.csv`):\n\n'+table(b.tables['tracked_by_depth']),
        'RESILIENCE_FROM_A4':'Последняя точка каждой стратегии (`resilience.csv`):\n\n'+table(latest),
    }
    path=Path('README.md'); text=path.read_text(encoding='utf-8')
    for key,value in values.items():
        replacement=f'<!-- VALUE:{key} -->\n{value}\n<!-- ENDVALUE:{key} -->'
        pattern=rf'<!-- VALUE:{key} -->.*?<!-- ENDVALUE:{key} -->|\{{\{{{key}\}}\}}'
        text=re.sub(pattern,lambda _:replacement,text,flags=re.S)
    path.write_text(text, encoding='utf-8')
    print('README обновлён по реальным выгрузкам A4; out/ не изменён.')


if __name__=='__main__':
    main()
