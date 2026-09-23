# AGENTS.md — «Граф денег» (HackAlem AI, кейс Freedom)

## Сначала прочитай
**docs/TEAM_PLAN.md** — единый план команды. Два трека:
- **A — ядро:** `run.py`, `graf/*` кроме `evidence_xlsx.py` и `assistant.py`, `out/`;
- **B — интерфейс и доказательства:** `app.py`, `ui/*`, `graf/evidence_xlsx.py`, `graf/assistant.py`, `tools/*`, `README.md`.

Пользователь скажет «я участник A/B, выполни задачу X». **Правь только файлы своего трека** (TEAM_PLAN, раздел 3). Не хватает чего-то из чужого трека — скажи пользователю, какую колонку или функцию попросить у напарника. Контракт между треками — TEAM_PLAN, раздел 4; не меняй его сам.

## Задача
По графу внутрибанковских переводов (81 seed, 4 колена, только исходящие, июль 2026, даты без времени, переводы ≥ 5 000 ₸) назначить роль каждому из 2 248 узлов, кластеризовать, ранжировать «кого проверять первым и почему», показать на экране, выгрузить доказательную базу.

## Жёсткие требования ТЗ
- `python run.py --data data --out out` — одна команда, < 5 минут, без ручных шагов. Результат: `out/nodes_roles.csv` (ровно 2248 строк), `clusters.csv`, `top_nodes.csv` (≥ 20).
- `nodes_roles.csv`: обязательные колонки первыми — `gid, role, role_score, cluster_id, priority_score, evidence`.
  - role ∈ {consolidator, transit, distributor, terminal, coordinator, peripheral} + документированное расширение `payer`;
  - evidence — непустой, ≤ 200 символов, **с числами**.
- **Нельзя** хардкодить gid, делать «чёрный ящик», обогащать внешними данными, выдумывать атрибуты клиентов.
- Формулировки — гипотезы: «признаки консолидации», «**кандидат в организаторы**», «атрибутированный прослеживаемый поток». Слово «организатор» без «кандидат» не использовать.

## Ловушки данных и AML
- `depth = 4` и `out_deg = 0` — обрыв обхода, а не «сток». См. `truncation.py`.
- У seed `in_kzt` занижен, поэтому `pass_through` у seed не используем.
- Много узлов отправляют больше, чем получили в выгрузке, — у них внешнее финансирование (`visibility = external_funding`). Это контр-сигнал, а не признак организатора.
- Разовые мелкие плательщики в точку сбора — роль `payer` (возможный покупатель или потерпевший), приоритет низкий.
- Типа счёта в данных нет. Технические счета и агрегаторы исключаются только через `config/excluded_accounts.csv`, который банк заполняет из АБС. Поведенческий `aggregator_like` — только предупреждение.
- Время — только ДАТА. Хронологический маршрут: даты не убывают, задержка на шаге ≤ Δ дней.
- Граф направленный. Louvain — на неориентированной проекции, это оговорено в README.
- 19 seed без рёбер тоже попадают в выгрузку.
- `nx.pagerank` и `nx.hits` требуют scipy.
- **gid ≈ 1e17 > 2^53:** в JSON, Plotly, pyvis и XLSX — только строкой.

## Стек
Python 3.11/3.12, pandas, pyarrow, numpy, scipy, networkx, streamlit, plotly, pyvis, openpyxl, openai (только `assistant.py`), pytest. Пайплайн не зависит от LLM и интернета.

## OpenAI Responses API (`graf/assistant.py`)
- Инструменты описываются **плоско**: `{"type":"function","name":...,"description":...,"parameters":{...},"strict":true}`. В каждом object `"additionalProperties": false`, все поля в `"required"`; необязательное поле — тип с null.
- Цикл:
  1. `resp = client.responses.create(model=os.getenv("OPENAI_MODEL"), input=..., tools=...)`.
  2. Для каждого item в `resp.output` с `type == "function_call"`: `result = dispatch(item.name, json.loads(item.arguments))`.
  3. Следующий вызов: `client.responses.create(..., previous_response_id=resp.id, input=[{"type":"function_call_output","call_id":item.call_id,"output":json.dumps(result, ensure_ascii=False)}])`.
  4. Итог — `resp.output_text`.

## Команды
```
python run.py --data data --out out
python -m graf.check out
pytest -q
streamlit run app.py
python tools/make_stub_outputs.py   (трек B, заглушка в out_stub/)
```

## Git
- Ветки `a-core` (A) и `b-ui` (B). В `main` — только в точках синхронизации (TEAM_PLAN, раздел 5).
- Один коммит на задачу, в конце сообщения `[codex]`.
- Каждый участник записывает свои промты в `docs/codex_prompts_A.md` или `docs/codex_prompts_B.md`.
