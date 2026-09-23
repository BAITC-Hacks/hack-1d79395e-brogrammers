# TEAM_PLAN — «Граф денег» (HackAlem AI, кейс Freedom)
Один план на двоих. Два трека: **A — аналитическое ядро**, **B — интерфейс, доказательная база, ИИ-ассистент, README**. Каждый работает локально на своём ноутбуке в своей ветке и пушит в общий GitHub-репозиторий организаторов. В трёх точках синхронизации сливаемся в `main`.

**Как говорить с Codex:**
- «Я участник A. Прочитай AGENTS.md и docs/TEAM_PLAN.md. Выполни задачу A2.»
- «Я участник B. … Выполни задачу B3.»

Codex не должен трогать файлы чужого трека (раздел 3).

---

## 1. Что строим (коротко)
Инструмент AML-аналитика. По выгрузке переводов 81 seed-клиента на 4 колена (2 248 узлов, 3 119 рёбер, 4 840 транзакций, июль 2026, **только даты**, только внутрибанковские переводы ≥ 5 000 ₸) он:
1. назначает каждому узлу роль из словаря с уверенностью и объяснением **с числами**;
2. кластеризует сеть и пишет гипотезу по каждому кластеру;
3. ранжирует, **кого проверять первым и почему**;
4. показывает схему сети с направлением денег, ролями, кластерами и поиском по gid;
5. выгружает доказательную базу в XLSX.

**Идея «два слоя»:**
- **Структура** — роли по правилам с порогами.
- **Деньги курьеров:**
  - хронологически возможные маршруты от seed — даты по пути не убывают, задержка ≤ Δ дней;
  - осторожная атрибуция потока: узел не может переслать «курьерских» денег больше, чем получил.
- Приоритет — там, где слои сходятся. Контр-сигналы понижают приоритет.

**Факты данных для README и демо** (прототип; в README — цифры вашего пайплайна):
- курьеры (seed) отправили 55.3 млн ₸ из 365.9 млн оборота графа;
- хронологический маршрут от seed есть у 1346 из 2167 не-seed узлов (при Δ ≤ 2 дня — у 702);
- прослеживаемые деньги курьеров оседают в основном на колене 1 (≈ 39 млн); до колена 4 доходит ≈ 0.1 млн.

**Обязательные выгрузки ТЗ** (жюри проверяет механически): `nodes_roles.csv` (ровно 2248 строк), `clusters.csv`, `top_nodes.csv` (≥ 20). Полный пересчёт — ≤ 5 минут одной командой. Внешние данные и выдуманные атрибуты запрещены. gid в коде не хардкодить. Формулировки — гипотезы.

---

## 2. На чём делаем
| Что | Чем | Кто |
|---|---|---|
| Язык | **Python 3.11 или 3.12** — одна и та же версия у обоих | A, B |
| Окружение | `python -m venv .venv` (Windows: `.venv\Scripts\activate`, macOS/Linux: `source .venv/bin/activate`) | A, B |
| Данные / графы | pandas, pyarrow, numpy, **scipy** (без него падают `nx.pagerank`/`nx.hits`), networkx | A |
| Интерфейс | Streamlit, Plotly (карта по коленам), pyvis (ego-граф) | B |
| Excel | openpyxl (через `pandas.ExcelWriter`) | B |
| ИИ-ассистент | openai SDK, Responses API, tool calling; ключ в `.env` (`OPENAI_API_KEY`, `OPENAI_MODEL`); опционально | B |
| Тесты | pytest | A, B |
| Код | **Codex** (обязателен по правилам хакатона) + редактор (VS Code) | A, B |
| Git | Git + GitHub-репозиторий организаторов, у обоих права на push | A, B |

**`requirements.txt`** (фиксирует A в A0, дальше не меняется без договорённости):
```
pandas>=2.1
pyarrow>=14
numpy>=1.26
scipy>=1.11
networkx>=3.2
streamlit>=1.36
plotly>=5.20
pyvis>=0.3.2
openpyxl>=3.1
openai>=1.40
python-dotenv>=1.0
pytest>=8
```

**Данные.** Папка `data/` с тремя parquet из архива организаторов.
- Если репозиторий организаторов **приватный** — коммитим `data/` (87 КБ), чтобы жюри запускало без ручных шагов.
- Если публичный или вы не уверены — не коммитим. README объясняет, куда положить архив, а `run.py` выдаёт понятную ошибку. **Решите это в первые 5 минут и спросите организаторов.**

---

## 3. Кто что делает — владение файлами (главное правило против конфликтов)
| Файлы | Владелец | Второй участник |
|---|---|---|
| `run.py`, `graf/config.py`, `graf/load.py`, `graf/features.py`, `graf/temporal.py`, `graf/truncation.py`, `graf/flow.py`, `graf/roles.py`, `graf/clusters.py`, `graf/fingerprints.py`, `graf/priority.py`, `graf/resilience.py`, `graf/outputs.py`, `graf/check.py`, `config/excluded_accounts.csv`, `tests/test_core_*.py`, **`out/`** (коммитит только A) | **A** | только читает |
| `app.py`, `ui/*`, `graf/evidence_xlsx.py`, `graf/assistant.py`, `tools/make_stub_outputs.py`, `README.md`, `docs/scheme.*`, `docs/screenshots/`, `tests/test_ui_*.py`, `tests/test_assistant_*.py` | **B** | только читает |
| `AGENTS.md`, `docs/TEAM_PLAN.md`, `requirements.txt`, `.gitignore` | **общие**, создаёт A в A0 | правки только по договорённости в чате |
| `docs/codex_prompts_A.md` / `docs/codex_prompts_B.md` | A / B | каждый ведёт свой файл — это доказательство работы с Codex |

- **Ветки:** A работает в `a-core`, B — в `b-ui`. В `main` напрямую не коммитим, кроме A0 и точек синхронизации.
- **Точки стыковки кода.** B вызывает функции A только через контракт (раздел 4): читает `out/*` и импортирует `graf.flow.chrono_reach`. A вызывает код B в одном месте: `run.py` → `graf.evidence_xlsx.build_evidence(data_dir, out_dir)`. Заглушку создаёт A в A0, реализует B.
- **Когда что-то нужно от напарника**, пишите в чат: «нужна колонка X в nodes_roles.csv». Файл напарника не правьте.

---

## 4. Контракт между A и B (не менять без договорённости)
Все файлы — в папке `out/` (реальные данные, пишет A) или `out_stub/` (заглушка, пишет B для разработки, в git не идёт).

**Правило gid.** gid ≈ 1e17 больше 2^53, поэтому в JavaScript (Plotly, pyvis) и в Excel число теряет точность. В CSV gid — int64. **В `graph.json`, во всех подписях и hover и в XLSX — строкой.**

### 4.1 `nodes_roles.csv` (A) — 2248 строк
Обязательные колонки первыми, в таком порядке: `gid, role, role_score, cluster_id, priority_score, evidence`.

Дополнительные:
| Колонка | Тип | Смысл |
|---|---|---|
| rank | int | место в очереди (1 = первый), у всех узлов |
| role_label | str | подпись по-русски (раздел 7.2): «кандидат в организаторы», «признаки точки консолидации», … |
| role_alt, ambiguous | str, bool | вторая роль и флаг «отрыв скоров < 0.10» |
| confidence_level | str | высокая (≥ 0.75) / средняя (0.5–0.75) / низкая (< 0.5) по role_score |
| visibility | str | full / out_unseen / in_unseen_seed / external_funding |
| excluded, aggregator_like, seed_above_bottom, is_seed, truncated | bool | флаги |
| depth | int | колено 0–4 |
| in_deg, out_deg, in_tx, out_tx | int | |
| in_kzt, out_kzt, pass_through, in_hhi, out_hhi, betweenness | float | |
| from_key, to_key | int | число ключевых узлов среди плательщиков / получателей |
| fast_out_share, max_sync_payers, near_threshold_share | float/int | временные признаки |
| p_forward | float | для колена 4: вероятность, что деньги ушли дальше |
| tracked_in, tracked_out, tracked_share_in, tracked_out_share, tracked_kept | float | FlowLedger |
| seed_exp_topo, seed_exp_chrono, seed_exp_fast | int | сколько seed достигают узла: по рёбрам / хронологически / с Δ ≤ 2 дней |
| signals, counter_signals | str | фразы через « \| » |
| prio_role, prio_money, prio_brokerage, prio_volume, prio_temporal, prio_multiplier | float | компоненты приоритета |

### 4.2 `clusters.csv` (A)
`cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids ("g1;g2;g3;g4;g5"), hypothesis` + доп.: `fingerprints ("fan_in;cycle")`, `n_coordinator, n_consolidator, n_distributor, n_transit, n_terminal, n_payer`, `tracked_kzt_internal`.

### 4.3 `top_nodes.csv` (A) — топ-30, без payer и excluded
`rank, gid, role, priority_score, why` + доп.: `role_label, confidence_level, visibility, is_seed`.

### 4.4 Дополнительные выгрузки A
| Файл | Колонки |
|---|---|
| `seeds_review.csv` | gid, role, role_label, evidence — seed выше нижнего уровня |
| `paths.csv` | target_gid, path_rank (1–3), seed_gid, hops, path_gids ("g0>g1>g2"), path_days ("3>4>6"), path_amounts ("50000>48000"), bottleneck_kzt — для топ-30 |
| `resilience.csv` | strategy (priority / betweenness / out_deg / in_deg / random / all_seeds), n_removed, seed_reach_share, largest_wcc |
| `ablation_links.csv` | level (topology / chrono_any / chrono_7d / chrono_2d), n_nonseed_nodes, share |
| `tracked_by_depth.csv` | depth, tracked_kept_kzt |
| `truncation_calibration.csv` | bucket, n, p_forward |
| `data_requests.csv` | gid, request, reason, priority_score |
| `audit.csv` | scope (top10 / top30), check, count, ok |
| `graph.json` | `{"meta":{...}, "nodes":[{"id":"<gid строкой>", role, role_label, cluster_id, priority_score, rank, depth, is_seed, visibility, tracked_in, seed_exp_chrono, x, y}], "edges":[{"src":"<gid>", "dst":"<gid>", sum_kzt, n_tx, tracked_kzt, first_day, last_day}]}`; x, y — `spring_layout(seed=42)` |
| `run_meta.json` | время этапов, total_sec, параметры, число строк |

### 4.5 Функции A, которые использует B
- `graf.flow.chrono_reach(tx: DataFrame, seeds: set[int], gap_days: int, max_hops: int = 4) -> dict[int, int]` — gid → число seed с хронологическим маршрутом. Время на данных < 1 с.
- `graf.load.load(data_dir) -> (edges, nodes, tx)`.

### 4.6 Выгрузка B
`out/evidence.xlsx` — листы в разделе 8, задача B3.

---

## 5. Git-процесс
**Старт.**
- A (A0):
  1. `git clone <URL репо организаторов>`;
  2. скелет → `git add . && git commit -m "chore: skeleton [codex]" && git push origin main`;
  3. `git checkout -b a-core && git push -u origin a-core`.
- B — после сообщения A «скелет в main»: `git clone <URL>` → `git checkout -b b-ui && git push -u origin b-ui` → venv, `pip install -r requirements.txt`.

**Работа.** Маленькие коммиты после каждой задачи Codex, сообщение с `[codex]`, `git push` в свою ветку.

**Получить свежее от напарника, не дожидаясь синхронизации:** `git fetch origin && git merge origin/a-core` (для B) или `git merge origin/b-ui` (для A). Конфликтов не будет, если соблюдать владение файлами.

**Точка синхронизации — всегда в этом порядке:**
1. A: `git checkout main && git pull && git merge a-core && git push origin main && git checkout a-core && git merge main`.
2. B: `git checkout b-ui && git fetch origin && git merge origin/main`. Проверить, что `streamlit run app.py` работает на реальном `out/`, затем `git checkout main && git pull && git merge b-ui && git push origin main && git checkout b-ui`.
3. Оба: `git pull` на main, `python run.py --data data --out out`, `streamlit run app.py` — проверка вместе.

---

## 6. Таймлайн (T = старт работы по этому плану; при нехватке времени режьте по разделу 10)
| Время | Участник A — ядро | Участник B — интерфейс и доказательства |
|---|---|---|
| T+0:00–0:20 | **A0** скелет, requirements, AGENTS.md, этот план → push main | Окружение, чтение плана. После push A: clone, ветка `b-ui`, **B0** заглушка `out_stub/` |
| T+0:20–1:00 | **A1** признаки + грубые роли → `run.py` пишет контрактные выгрузки | **B1** каркас app: поиск gid, карточка, ego-граф, топ-лист (на `out_stub/`) |
| **T+1:00 SYNC 1** | merge → main (**страховка**: 3 валидных CSV в main) | merge main → `b-ui`, переход на реальный `out/` |
| T+1:05–1:45 | **A2** `flow.py`: хронология, FlowLedger, пути, абляция | **B2** карта по коленам + режим «Структура / Деньги курьеров» |
| T+1:45–2:30 | **A3** `roles.py`: ворота, скоры, payer, флаги, evidence | **B3** `evidence.xlsx` + скачивание по узлу |
| T+2:30–3:00 | **A4** кластеры, отпечатки, приоритет, устойчивость, аудит ловушек | **B4** вкладки «Кластеры», «Устойчивость», ассистент (опционально) |
| **T+3:00 SYNC 2** | merge → main | merge → main; совместный прогон |
| T+3:05–3:35 | **A5** вместе с B разбираете 3 gid и аудит; правка порогов и текстов | **B5** README с цифрами из `out/`, схема, скриншоты |
| T+3:35–3:50 | **A6** финальный `out/` в коммит, тесты, время < 5 мин | **B6** тест чистого клона **на своей машине** (это и есть «чистая машина жюри») |
| **T+3:50 SYNC 3 — FREEZE** | финальный merge, тег `v1.0` | |
| T+3:50–конец | Репетиция демо: A — пайплайн и 3 узла | Репетиция демо: B — экран, XLSX, ассистент |

---

## 7. ТРЕК A — аналитическое ядро
Пока A делает ядро, B строит интерфейс на заглушке по тому же контракту. Контракт — в разделе 4: всё, что обещано там, должно появиться в `out/`.

### 7.1 Константы `graf/config.py`
```
CONS_MIN_IN_DEG=5; DIST_MIN_OUT_DEG=10; COORD_MIN_KEY_LINKS=3; TRANSIT_PT=(0.8,1.2); TERMINAL_PT_MAX=0.1
FAST_DAYS=2; CHRONO_GAPS={"any":31,"7d":7,"2d":2}; PATH_GAP_DAYS=7; SYNC_MIN_PAYERS=3; HHI_DOMINANT=0.5
NEAR_THRESHOLD=(5000,7000); TRUNC_TERMINAL_MIN_P=0.6; AMBIGUOUS_MARGIN=0.10
PAYER_MAX_OUT_DEG=2; PAYER_MAX_OUT_TX=2; PAYER_MAX_KZT=100_000; PAYER_TARGET_MIN_IN_DEG=5
EXT_FUNDING_PT=2.0; EXT_FUNDING_MAX_TRACKED_OUT=0.10
AGG_MIN_IN_DEG=10; AGG_MIN_ONE_OFF=0.8; AGG_MAX_HHI=0.15; AGG_MIN_ACTIVE_DAYS=12
PRIORITY_WEIGHTS={"role":0.30,"money":0.30,"brokerage":0.20,"volume":0.10,"temporal":0.10}
ROLE_WEIGHT={"coordinator":1.0,"consolidator":0.8,"distributor":0.7,"transit":0.5,"terminal":0.3,"peripheral":0.1,"payer":0.05}
MULT={"no_chrono":0.5,"external_funding":0.7,"seed":0.6,"seed_above_bottom":0.8,"payer":0.2,"excluded":0.0}
CONF_LEVELS=(0.5,0.75); TOP_N=30; RANDOM_SEED=42
```

### 7.2 Роли: «ворота + скор»
Роль = coordinator, если пройдены его ворота. Иначе payer, если пройдены его ворота. Иначе argmax скоров среди ролей K, D, T, E с пройденными воротами. Иначе E′. Иначе peripheral.
- `role_score` = скор выбранной роли.
- `ambiguous`, если отрыв от второй < 0.10.
- Для seed pass_through **не используется**: входящие вне выборки не видны.

| Роль → role_label | Ворота | Скор 0–1 |
|---|---|---|
| coordinator → «кандидат в организаторы» | (in_deg ≥ 5 и out_deg ≥ 10) или (from_key ≥ 3 и to_key ≥ 3); key = узлы, прошедшие ворота K, D или T | 0.5 + 0.5·min(1, (from_key + to_key)/20) |
| payer → «разовый плательщик (возможный покупатель/потерпевший)» | не seed; out_deg ≤ 2; out_tx ≤ 2; out_kzt ≤ 100 тыс.; хотя бы один получатель с in_deg ≥ 5; **не** проходит ворота транзита | 0.8 |
| consolidator → «признаки точки консолидации» | in_deg ≥ 5 | 0.4·min(1, in_deg/15) + 0.2·(1 − in_hhi) + 0.2·min(1, max_sync_payers/5) + 0.2·min(1, 2·tracked_share_in) |
| distributor → «признаки веерного распределения» | out_deg ≥ 10 | 0.5·min(1, out_deg/40) + 0.3·(1 − out_hhi) + 0.2·fast_out_share |
| transit → «признаки транзитного счёта» | не seed; in ≥ 1; out ≥ 1; pass_through ∈ [0.8; 1.2] | 0.5·(1 − \|1 − pt\|/0.2) + 0.3·fast_out_share + 0.2·[seed_exp_chrono > 0] |
| terminal → «конечный получатель в пределах выгрузки» | depth ≤ 3; in ≥ 1; out = 0 или pt < 0.1 | 0.7 + 0.3·tracked_share_in |
| terminal (оценка) | depth = 4 и 1 − p_forward ≥ 0.6 | 1 − p_forward |
| peripheral → «периферия, признаков роли не выявлено» | остальное | 0.5 (0.3 при truncated) |

### 7.3 Флаги, сигналы, evidence
- `visibility`:
  - out_unseen — depth = 4;
  - in_unseen_seed — seed;
  - external_funding — не seed, pt > 2 и tracked_out_share < 0.10;
  - иначе full.
- `excluded` — gid есть в `config/excluded_accounts.csv`. Банк заполняет файл из АБС **по типу счёта** (технические, агрегаторы); в репо — пустой шаблон `gid,account_type,reason`.
- `aggregator_like` — in_deg ≥ 10, доля разовых плательщиков (n_tx = 1) ≥ 0.8, in_hhi ≤ 0.15, ≥ 12 дней с входящими. Это только предупреждение «проверьте тип счёта в АБС».
- **counter_signals** (фразы с числами):
  - «нет хронологически возможного маршрута от seed»;
  - «лишь 1% входящих прослеживается до денег курьеров» (tracked_share_in < 0.05 при in_kzt ≥ 500 тыс.);
  - «55% входящих — от одного плательщика» (in_hhi ≥ 0.5);
  - «отправил в 23 раза больше, чем получил в выгрузке: источник средств вне данных» (external_funding);
  - «обрезан 4-м коленом, p_forward = 26%»;
  - «seed: входящие вне выборки не видны»;
  - «исключён: технический счёт по данным АБС».
- **evidence** ≤ 200 символов: «{role_label} ({скор}): 2–3 сигнала с числами. Контр: главный контр-сигнал». Суммы — «1.2 млн ₸» / «450 тыс. ₸».

### 7.4 Приоритет
`priority = 0.30·ROLE_WEIGHT[role] + 0.30·money + 0.20·brokerage + 0.10·volume + 0.10·temporal`, затем × множители. Компоненты:
- money = 0.5·pct(tracked_in) + 0.5·pct(seed_exp_chrono);
- brokerage = доля seed-reach, теряемая при удалении узла (только для узлов с in > 0 и out > 0, остальным 0);
- volume = pct(log1p(in_kzt + out_kzt));
- temporal = max(fast_out_share, [max_sync_payers ≥ 3]);
- pct — ранговый перцентиль 0–1.

Множители (MULT):
- не seed и seed_exp_chrono = 0 → ×0.5;
- external_funding → ×0.7;
- seed → ×0.6, seed_above_bottom → ×0.8;
- payer → ×0.2;
- excluded → 0.

`why` = role_label + 2–3 крупнейшие компоненты словами и числами + главный контр-сигнал.

### 7.5 Задачи A с промтами для Codex

**A0 — скелет (T+0:00–0:20)**
```
Я участник A. Прочитай docs/TEAM_PLAN.md (разделы 2–5, 7.1) и starter.py.
Создай скелет: структура файлов из раздела 3 (включая заглушки файлов B: app.py, graf/evidence_xlsx.py с функцией
build_evidence(data_dir, out_dir) -> None, raise NotImplementedError; graf/assistant.py пустой модуль).
graf/load.py — перенеси load, sanity_check, build_graph из starter.py (DiGraph, атрибуты sum_kzt, n_tx, depth).
graf/config.py — все константы раздела 7.1 с комментариями. config/excluded_accounts.csv — только заголовок gid,account_type,reason.
run.py: argparse --data (data) --out (out); этапы load → features → temporal → truncation → flow → roles → clusters → fingerprints →
priority → resilience → outputs → evidence_xlsx → check; печатает время каждого этапа и пишет out/run_meta.json;
этап, который бросает NotImplementedError, пропускается с сообщением, но обязательные три CSV пишутся всегда.
requirements.txt — ровно список из раздела 2. .gitignore: .venv/, __pycache__/, out_stub/, .env, *.pyc.
Создай docs/codex_prompts_A.md и запиши туда этот промт. Коммит "chore: skeleton [codex]".
```

**A1 — признаки и первые выгрузки (T+0:20–1:00)**
```
Я участник A. Реализуй graf/features.py, graf/temporal.py, graf/truncation.py по разделам 4.1 и 7:
features: для ВСЕХ 2248 gid (включая 19 seed без рёбер) in/out_deg, in/out_tx, in/out_kzt, pass_through (NaN при in_kzt=0),
in_hhi/out_hhi (сумма квадратов долей контрагентов по sum_kzt), betweenness (направленный, без весов), is_seed, depth.
temporal (день = date из transactions): fast_out_share (доля исходящей суммы, отправленной в пределах FAST_DAYS дней после даты
любого входящего), max_sync_payers (максимум разных плательщиков за один день), near_threshold_share (доля исходящих в NEAR_THRESHOLD),
active_in_days, payer_one_off_share (доля плательщиков с n_tx=1).
truncation: calibrate() на не-seed depth 1–3 с in_deg>0: P(out_deg>0) по корзинам in_tx 1 / 2–3 / 4–10 / >10 → out/truncation_calibration.csv;
apply(): для depth==4 truncated=True, p_forward из корзины.
Временные роли для SYNC 1: простые пороги (in_deg≥5 → consolidator, out_deg≥10 → distributor, pt 0.8–1.2 → transit,
depth≤3 и out=0 → terminal, иначе peripheral), role_score=0.5, priority=pct(in_deg+out_deg), cluster_id по слабым компонентам,
evidence с числами. graf/outputs.py пишет nodes_roles.csv, clusters.csv, top_nodes.csv по контракту 4.1–4.3 (доп. колонки, которых
ещё нет, — заполнить значениями по умолчанию) и graph.json (gid строкой!).
graf/check.py: 2248 строк, обязательные колонки без пропусков, роль из словаря (+payer), evidence ≤200, top ≥20,
все cluster_id есть в clusters.csv. tests/test_core_features.py. Время run.py < 60 с.
```
→ **SYNC 1** (раздел 5).

**A2 — деньги курьеров (T+1:05–1:45)**
```
Я участник A. Реализуй graf/flow.py:
1) chrono_reach(tx, seeds, gap_days, max_hops=4) -> dict[gid, n_seeds] — сигнатура из контракта 4.5. Для каждого seed множества дней
прибытия на узлы; переход по транзакции (u->v, день d) разрешён, если у u есть день прибытия a с 0 <= d-a <= gap_days
(у seed деньги «есть» весь месяц — первый шаг в любой день). Не возвращаться в сам seed.
Считать seed_exp_topo (обычная достижимость ≤4 колена), seed_exp_chrono (gap=31), seed_exp_fast (gap=FAST_DAYS).
2) flow_ledger(tx, seeds, depth): транзакции по дням, внутри дня по возрастанию depth отправителя; для seed q=amount, для остальных
q=min(amount, balance[src]); balance[src]-=q; balance[dst]+=q (кроме seed). По узлам tracked_in/out/kept, tracked_share_in,
tracked_out_share; по рёбрам tracked_kzt (в graph.json). out/tracked_by_depth.csv.
3) money_paths(tx, seeds, targets, gap_days=PATH_GAP_DAYS, max_hops=4, k=3): DFS от каждого seed вперёд по транзакциям
с тем же правилом дней; для каждого target до 3 путей с максимальным bottleneck (минимальная сумма на пути), затем меньше колен →
out/paths.csv по контракту 4.4 (targets = топ-30 после A4; до A4 — топ-30 по текущему priority).
4) ablation_table() → out/ablation_links.csv (topology / chrono_any / chrono_7d / chrono_2d).
tests/test_core_flow.py: у seed tracked_out == out_kzt; ни у одного не-seed tracked_out > tracked_in + 1e-6;
chrono_reach(gap=31) ⊆ достижимости по рёбрам.
```
Сразу после A2: `git push`, в чат: «flow готов в a-core» — B может подтянуть `origin/a-core` для ползунка Δ.

**A3 — роли (T+1:45–2:30)**
```
Я участник A. Реализуй graf/roles.py строго по разделам 7.2–7.3: ворота и скоры, порядок coordinator → payer → argmax(K,D,T,E) → E' →
peripheral; key = K∪D∪T по воротам, from_key/to_key; role_label, role_alt, ambiguous, confidence_level (CONF_LEVELS); visibility,
excluded (из config/excluded_accounts.csv), aggregator_like, seed_above_bottom (seed с ролью coordinator/consolidator/distributor);
signals и counter_signals (фразы с числами, через " | "), evidence ≤200 символов по шаблону 7.3.
Формулировки — гипотезы («признаки …», «кандидат в организаторы»); слово «организатор» без «кандидат» не использовать.
tests/test_core_roles.py: роли из словаря, evidence непустой и ≤200, у coordinator/consolidator/distributor/transit/terminal
есть хотя бы 1 узел, у seed pass_through не входит в сигналы.
```

**A4 — кластеры, приоритет, устойчивость, аудит (T+2:30–3:00)**
```
Я участник A. 
graf/clusters.py: Louvain внутри каждой слабой компоненты (неориентированная проекция, weight="sum_kzt", seed=RANDOM_SEED);
cluster_id по убыванию размера.
graf/fingerprints.py: по кластеру флаги fan_in (consolidator с ≥3 плательщиками из кластера), fan_out (distributor с ≥10 получателями
в кластере), chain (≥3 transit подряд хронологически), scatter_gather (fan-out → ≥3 промежуточных → fan-in), cycle
(nx.simple_cycles(length_bound=6) внутри кластера), fragmentation (≥2 узла с near_threshold_share≥0.5); hypothesis — текст
«Признаки …» с числами и gid ключевых узлов.
graf/priority.py: раздел 7.4 (brokerage — через resilience.single_node_loss), prio_* колонки, rank, why.
graf/resilience.py: seed_reach(G); single_node_loss(v); removal_curve по не-seed для стратегий priority/betweenness/out_deg/in_deg/random
(N = 5, 10, 20, 23, 50) + строка all_seeds с largest_wcc → out/resilience.csv.
graf/outputs.py: все файлы контракта 4.1–4.4, top_nodes = топ-30 без payer/excluded, seeds_review.csv, data_requests.csv (seed →
«запросить входящие переводы»; depth 4 и p_forward ≥ 0.5 и rank ≤ 200 → «запросить выписку исходящих»; near_threshold_share ≥ 0.5 →
«запросить переводы < 5 000 ₸»; всем топ-30 → «запросить время транзакций для точного FlowTrace»).
graf/check.py: + аудит ловушек → out/audit.csv для top10/top30: число is_seed, payer, excluded, aggregator_like, visibility != full,
seed_exp_chrono==0 (не seed). Ошибка сборки, если в top10 есть payer или excluded. Печать таблицы аудита в конце run.py.
```
→ **SYNC 2** (раздел 5).

**A5 — доводка вместе с B (T+3:05–3:35)**
```
Я участник A. Выведи для топ-10 и для gid <3 gid, которые назовём> карточку: роль, ворота (какие пройдены, с порогами), скоры
всех ролей, компоненты приоритета, контр-сигналы. Если в топ-10 есть узел, который AML-эксперт оспорит (seed, внешнее
финансирование, нет хронологического маршрута) — предложи правку порога в config.py с обоснованием, не хардкодя gid.
Проверь run.py < 5 минут.
```

**A6 — финальные выгрузки (T+3:35–3:50)**
```
Я участник A. Удали out/, запусти python run.py --data data --out out с нуля, проверь check и аудит, pytest -q.
Закоммить out/*.csv, out/*.json, out/evidence.xlsx. Коммит "release: final outputs [codex]".
```

---

## 8. ТРЕК B — интерфейс, доказательная база, ассистент, README
Пока A делает ядро, B работает на **заглушке** `out_stub/` с теми же колонками (раздел 4). После SYNC 1 — на реальном `out/`. Файлы A не правь: если не хватает колонки — пиши A в чат.

### 8.1 Экран (Streamlit) — что должно быть
- **Sidebar:**
  - выбор папки: `out/`, если есть `out/nodes_roles.csv`, иначе `out_stub/`;
  - поиск gid с подсказками по префиксу;
  - фильтр ролей;
  - режим «Структура / Деньги курьеров» и ползунок Δ (1–31 дней) со счётчиком «узлов в следе N из 2167».
- **Вкладки:** «Топ-лист», «Узел», «Карта по коленам», «Кластеры», «Устойчивость», «Доказательства», «Ассистент».
- **Слова в интерфейсе:** всегда `role_label` («кандидат в организаторы», «признаки …»), никогда просто «организатор». Внизу каждой страницы: «Инструмент приоритизации проверки. Выводы — гипотезы, не установление вины».
- **Цвета ролей:** coordinator `#d62728`, consolidator `#ff7f0e`, distributor `#9467bd`, transit `#e6c200`, terminal `#555555`, peripheral `#c7c7c7`, payer `#17becf`. У seed чёрная обводка. Узлы с visibility ≠ full — пунктирная или полупрозрачная рамка.

### 8.2 Задачи B с промтами для Codex

**B0 — заглушка выгрузок (T+0:00–0:20, после clone)**
```
Я участник B. Прочитай AGENTS.md и docs/TEAM_PLAN.md (разделы 3–4, 8). Создай tools/make_stub_outputs.py: читает data/*.parquet
через graf.load.load, считает простые признаки (степени, суммы) и пишет в out_stub/ ВСЕ файлы контракта 4.1–4.4 с точными
колонками и типами: роли из словаря (+payer) случайно с seed=42 и правильными role_label, правдоподобные скоры и флаги, evidence-заглушка
с числами, 20 кластеров, paths.csv (3 пути для топ-30 по реальным рёбрам), graph.json (gid строкой, координаты spring_layout(seed=42)),
resilience/ablation/audit/tracked_by_depth/data_requests/seeds_review/truncation_calibration — правдоподобные числа.
Создай docs/codex_prompts_B.md и записывай туда свои промты.
```

**B1 — каркас приложения (T+0:20–1:00)**
```
Я участник B. Создай app.py и пакет ui/: ui/data.py (загрузка папки выгрузок с st.cache_data; gid читать int64, показывать строкой),
ui/theme.py (цвета и подписи ролей из 8.1), ui/graphs.py, ui/card.py. Sidebar и вкладки из 8.1.
Реализуй сейчас:
- «Топ-лист»: top_nodes + role_label, confidence_level, visibility; выбор строки → st.session_state["gid"] и переход к «Узлу»;
  отдельный блок «Seed выше нижнего уровня — пересмотреть уровень» из seeds_review.csv.
- «Узел»: карточка — role_label, уверенность, role_alt при ambiguous, priority и prio_* (горизонтальный bar), evidence, signals списком,
  counter_signals списком с ⚠, флаги (visibility, excluded, aggregator_like, truncated и p_forward), tracked_in и доля, seed_exp_*;
  топ-5 входящих и исходящих из transactions (контрагент, сумма, число переводов, даты); пути из paths.csv цепочкой «gid → gid» с датами;
  кластер и hypothesis; запросы из data_requests.csv.
- Ego-граф 1–2 шага (радио) в pyvis: стрелки по направлению денег, толщина ∝ log1p(sum_kzt), цвет по роли, выбранный узел крупнее,
  physics=False (координаты — spring_layout подграфа), подписи gid строкой, hover — role_label и сумма; st.components.v1.html(height=600).
Поиск по несуществующему gid — понятное сообщение.
```
→ **SYNC 1**: подтянуть main и проверить на реальном `out/`.

**B2 — карта по коленам и два слоя (T+1:05–1:45)**
```
Я участник B. Вкладка «Карта по коленам» (plotly go.Figure):
x = depth (0–4) + небольшой джиттер, y внутри колена — сортировка по cluster_id, затем по priority; колонка depth=4 затенена
(shape-прямоугольник) с подписью «обрыв обхода: исходящие не собраны»; рёбра — линии для топ-400 рёбер по sum_kzt
(прозрачность по сумме), направление — аннотации-стрелки для топ-100; цвет по роли, размер ∝ log1p(tracked_in) (минимум 4),
рамка толще у топ-30; hover: gid строкой, role_label, priority, evidence. Кнопка «Сетевая раскладка» — x, y из graph.json.
Клик/выбор gid в поиске подсвечивает узел и его соседей.
Режим «Деньги курьеров»: показывать только узлы, у которых chrono_reach(tx, seeds, Δ) > 0 (импорт graf.flow.chrono_reach,
пересчёт при движении ползунка, кэш по Δ); если graf.flow ещё не готов — использовать колонки seed_exp_chrono (Δ=31) и seed_exp_fast (Δ=2).
Счётчик «узлов в следе N из 2167» и маленькая таблица ablation_links.csv.
```

**B3 — доказательная база в XLSX (T+1:45–2:30)**
```
Я участник B. Реализуй graf/evidence_xlsx.py:
build_evidence(data_dir, out_dir) -> None — пишет out/evidence.xlsx;
build_node_evidence(gid, data_dir, out_dir) -> bytes — то же для одного узла (для кнопки в интерфейсе).
pandas.ExcelWriter(engine="openpyxl"). ВСЕ gid — строкой, формат ячейки "@" (иначе Excel покажет 1E+17 и потеряет цифры).
Жирные заголовки, закреплённая первая строка, автоширина колонок.
Листы:
1 «Сводка» — top_nodes + role_label, confidence_level, visibility, counter_signals;
2 «Признаки» — все колонки nodes_roles для топ-30 + строка «пороги» из graf.config;
3 «Транзакции-основания» — все транзакции, где src или dst в топ-30: src, dst, дата, сумма, колонка «подтверждает»
  (через "; "): «сбор» — dst consolidator/coordinator; «синхронный сбор» — ≥3 разных плательщика dst в этот день;
  «пересылка ≤2 дней» — у src было входящее за 0–2 дня до даты; «маршрут от seed» — пара и день есть в paths.csv;
  «веерная рассылка» — src distributor; иначе «контекст»;
4 «Пути денег» — paths.csv с разворотом по шагам;
5 «Критерии» — таблица ролей: ворота, скор, role_label; веса и множители приоритета (из graf.config);
6 «Границы данных» — ограничения выгрузки (4-е колено, входящие seed, порог 5000, только даты, только внутрибанковские)
  + data_requests.csv.
Вкладка «Доказательства» в app: предпросмотр листов (st.dataframe) и две кнопки st.download_button — «Вся база (XLSX)» и
«Только выбранный узел (XLSX)». tests/test_ui_xlsx.py: файл открывается, 6 листов, gid в «Сводке» — строка из 18 цифр.
```

**B4 — кластеры, устойчивость, ассистент (T+2:30–3:00)**
```
Я участник B. Вкладка «Кластеры»: clusters.csv (fingerprints бейджами), выбор кластера → pyvis-граф кластера по ролям.
Вкладка «Устойчивость»: line chart из resilience.csv (x = n_removed, y = seed_reach_share, линия на стратегию), отдельная отметка
all_seeds с largest_wcc и подпись-вывод. Затем, если есть время, graf/assistant.py по шпаргалке Responses API из AGENTS.md:
инструменты node_card(gid), neighbors(gid, direction, limit), money_trail(gid) (из paths.csv), common_receivers(gids, hops≤2),
top_nodes(role|null, cluster_id|null, n), cluster_info(cluster_id) — все читают только out/ и data/, каждый возвращает JSON с полем gids;
системный промт: по-русски, только по данным инструментов, гипотезы, ссылки на gid; validate(): все 18-значные числа в ответе
должны быть среди gids выходов инструментов, иначе «⚠ непроверенная ссылка». Вкладка «Ассистент» работает только при OPENAI_API_KEY,
иначе подсказка, как включить. tests/test_assistant_mock.py с фейковым клиентом, без ключа.
```
→ **SYNC 2**.

**B5 — README (T+3:05–3:35)**
```
Я участник B. Напиши README.md. Все числа бери из out/ (audit.csv, ablation_links.csv, tracked_by_depth.csv,
truncation_calibration.csv, resilience.csv, run_meta.json), ничего не выдумывай. Разделы:
1) Что это (3 строки) + скриншот карты;
2) Быстрый старт — одна команда: pip install -r requirements.txt && python run.py --data data --out out; затем streamlit run app.py;
   где взять data/;
3) Схема решения (mermaid): parquet → признаки → FlowTrace/FlowLedger → роли → кластеры/отпечатки → приоритет → выгрузки/XLSX → экран/ассистент;
4) Роли: таблица ворот, скоров, role_label, пример evidence; расширение словаря payer — зачем;
5) Приоритет: формула, веса, множители;
6) Ловушки данных и AML-ловушки: обрыв 4-го колена (калибровка), seed, порог 5000, только даты, только внутрибанковские,
   внешнее финансирование, потерпевшие/плательщики, технические счета (config/excluded_accounts.csv из АБС по типу),
   «кандидат в организаторы»; таблица аудита топ-10/топ-30;
7) «Структура ≠ деньги»: абляция связей и где оседают деньги курьеров по коленам;
8) Выгрузки: схемы CSV и листы evidence.xlsx;
9) Устойчивость сети;
10) ИИ-ассистент: как включить, инструменты, защита ссылок;
11) Ограничения;
12) Масштабирование до ~1 млн узлов: Polars/DuckDB, igraph/graph-tool, Leiden, сэмплированная betweenness, FlowTrace через
    индекс (src, date) и top-K фронтир, карта кластеров + ego-граф вместо полного графа;
13) Команда и работа с Codex: треки A/B, AGENTS.md, docs/TEAM_PLAN.md, docs/codex_prompts_A.md и _B.md, коммиты [codex].
Сделай скриншоты вкладок в docs/screenshots/.
```

**B6 — тест чистой машины (T+3:35–3:50)**
```
Я участник B. В новой папке: git clone репозитория, новый venv, pip install -r requirements.txt, ровно команда из README;
замерь время; проверь 3 CSV (2248 строк, top ≥ 20), evidence.xlsx открывается, streamlit run app.py работает без OPENAI_API_KEY.
Всё, что не сработало, — список A и себе; исправления — по владельцам файлов.
```

---

## 9. Финальная сборка — чек-лист (SYNC 3)
- [ ] `main` содержит обе ветки; `git log` показывает коммиты `[codex]` от обоих.
- [ ] Чистый клон: одна команда → 3 CSV + evidence.xlsx за < 5 минут; `pytest -q` зелёный.
- [ ] `nodes_roles.csv` — 2248 строк, evidence с числами, роли из словаря; `top_nodes.csv` ≥ 20; `clusters.csv` с гипотезами.
- [ ] Аудит: в топ-10 нет payer и excluded; seed и узлы на границе либо отсутствуют, либо с контр-сигналом в why.
- [ ] Экран: поиск любого gid → карточка и ego-граф; карта по коленам; «Структура / Деньги»; XLSX скачивается.
- [ ] README: одна команда, критерии ролей и порогов, выгрузки, ограничения, масштабирование, схема решения.
- [ ] Финальные `out/` закоммичены (выгрузки — обязательный артефакт).
- [ ] Тег `v1.0`, последний push до дедлайна.

## 10. Если времени меньше — что резать (сверху вниз)
1. Ассистент (B4, вторая часть).
2. Ползунок Δ — оставить два положения из колонок.
3. Отпечатки схем — гипотеза кластера по составу ролей.
4. Устойчивость — оставить только таблицу.
5. XLSX — только листы 1, 3, 4.

**Никогда не резать:** 3 обязательных CSV, роли с evidence, топ-лист, поиск gid на схеме, README с одной командой, флаги visibility/payer и аудит.

## 11. Демо на 5 минут (кто что говорит)
1. **A, 0:00–0:40.** Проблема. `python run.py` — этапы, check и аудит ловушек зелёные.
2. **B, 0:40–1:30.** Карта по коленам в режиме «Структура» → переключение на «Деньги курьеров» → ползунок Δ до 2 дней: «38% связей не могут быть движением курьерских денег».
3. **A, 1:30–3:30.** Три узла: топ-1, топ-3 (сборщик денег курьеров) и один «похожий на координатора», но с контр-сигналом. В коде gid не хардкодить — выбрать в интерфейсе по поиску.
4. **B, 3:30–4:20.** Скачать `evidence.xlsx` и показать листы «Транзакции-основания» и «Пути денег». Ассистент: «кто собирает деньги с этих пятерых?».
5. **A, 4:20–5:00.** Ограничения и что запросить следующим. Жюри называет случайный gid → поиск → карточка → ворота роли и числа.
