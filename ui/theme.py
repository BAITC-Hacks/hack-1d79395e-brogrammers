COLORS = {
    "coordinator": "#d62728", "consolidator": "#ff7f0e",
    "distributor": "#9467bd", "transit": "#e6c200",
    "terminal": "#555555", "peripheral": "#c7c7c7", "payer": "#17becf",
}
LABELS = {
    "coordinator": "кандидат в организаторы",
    "consolidator": "признаки точки консолидации",
    "distributor": "признаки веерного распределения",
    "transit": "признаки транзитного счёта",
    "terminal": "конечный получатель в пределах выгрузки",
    "peripheral": "периферия, признаков роли не выявлено",
    "payer": "разовый плательщик (возможный покупатель/потерпевший)",
}
DISCLAIMER = "Инструмент приоритизации проверки. Выводы — гипотезы, не установление вины."
LIMITS = [
    "Глубина 4: исходящие не собраны; отсутствие выхода не доказывает удержание денег.",
    "Входящие извне сети не видны; у seed коэффициент пропуска не интерпретируется.",
    "Только внутрибанковские переводы за июль 2026, суммы от 5 000 ₸.",
    "Есть только даты: порядок переводов внутри дня и тождество денег не установлены.",
    "Тип счёта неизвестен. aggregator_like — повод запросить сведения из АБС, не факт.",
    "Прослеживаемый поток — модель атрибуции, не доказательство происхождения средств.",
]


def inject_style(st):
    st.markdown("""<style>
    .block-container {padding-top:1.25rem; max-width:1500px; padding-bottom:2rem}
    h1 {letter-spacing:-.035em; font-size:2rem} h2,h3 {letter-spacing:-.02em}
    [data-testid="stRadio"] label {line-height:1.35}
    [data-testid="stAlert"] {border-radius:10px}
    [data-testid="stMetric"] {background:#f1f5f9; border-radius:12px;
      padding:16px; color:#122237; border:1px solid #dce4ed}
    [data-testid="stSidebar"] {border-right:1px solid #dce4ed}
    </style>""", unsafe_allow_html=True)
