from __future__ import annotations

DISTRICTS: tuple[tuple[str, str], ...] = (
    ("admiralteyskiy", "Адмиралтейский"),
    ("vasileostrovskiy", "Василеостровский"),
    ("vyborgskiy", "Выборгский"),
    ("kalininskiy", "Калининский"),
    ("kirovskiy", "Кировский"),
    ("kolpinskiy", "Колпинский"),
    ("krasnogvardeyskiy", "Красногвардейский"),
    ("krasnoselskiy", "Красносельский"),
    ("kronshtadtskiy", "Кронштадтский"),
    ("kurortniy", "Курортный"),
    ("moskovskiy", "Московский"),
    ("nevskiy", "Невский"),
    ("petrogradskiy", "Петроградский"),
    ("petrodvortsoviy", "Петродворцовый"),
    ("primorskiy", "Приморский"),
    ("pushkinskiy", "Пушкинский"),
    ("frunzenskiy", "Фрунзенский"),
    ("tsentralniy", "Центральный"),
)

DISTRICT_BY_CODE = {code: title for code, title in DISTRICTS}
DISTRICT_CODE_BY_TITLE = {title: code for code, title in DISTRICTS}
DISTRICT_API_ID_BY_CODE = {
    "admiralteyskiy": "1",
    "vasileostrovskiy": "2",
    "vyborgskiy": "3",
    "kalininskiy": "4",
    "kirovskiy": "5",
    "kolpinskiy": "6",
    "krasnogvardeyskiy": "7",
    "krasnoselskiy": "8",
    "kronshtadtskiy": "9",
    "kurortniy": "10",
    "moskovskiy": "11",
    "nevskiy": "12",
    "petrogradskiy": "13",
    "petrodvortsoviy": "14",
    "primorskiy": "15",
    "pushkinskiy": "16",
    "frunzenskiy": "17",
    "tsentralniy": "18",
}
