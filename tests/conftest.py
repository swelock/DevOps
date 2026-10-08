"""Понятный отчёт поверх обычного pytest, без изменения результатов тестов."""

import math
import shutil
import textwrap

SCENARIOS = {
    "test_crud": (
        "Создание, просмотр, изменение и удаление",
        "Запись создаётся, читается, изменяется и удаляется; объём пересчитывается.",
    ),
    "test_unique_number_is_scoped_to_building": (
        "Уникальность номера помещения",
        "Повтор номера в одном корпусе запрещён, в другом корпусе разрешён.",
    ),
    "test_update_conflict_rolls_back": (
        "Откат неудачного изменения",
        "При конфликте номера прежние номер и площадь остаются без изменений.",
    ),
    "test_restrict_parent_delete": (
        "Удаление связанных справочников",
        "Справочник нельзя удалить до удаления его помещений; после этого можно.",
    ),
    "test_invalid_room_does_not_write": (
        "Защита от неправильных данных помещения",
        "Ошибочный ввод получает HTTP 400; в базе не появляется помещение.",
    ),
    "test_missing_parent": (
        "Ссылки на существующие записи",
        "Несуществующий корпус или подразделение отклоняется; прежняя связь сохраняется.",
    ),
    "test_invalid_payload": (
        "Проверка тела запроса",
        "Вместо неверного JSON-объекта сервер возвращает HTTP 400.",
    ),
    "test_http_errors": (
        "Понятные ошибки HTTP",
        "Неверные адреса, методы, JSON и размер запроса получают ожидаемые коды ошибок.",
    ),
    "test_names_trimmed_and_unique": (
        "Названия справочников",
        "Крайние пробелы удаляются; одинаковое название повторно не добавляется.",
    ),
    "test_sql_text_is_data": (
        "SQL-текст не выполняется как команда",
        "Строка с DROP TABLE сохраняется как название; таблица помещений остаётся доступной.",
    ),
    "test_persistence_and_environment": (
        "Сохранение данных и настройка пути",
        "Новый экземпляр приложения читает прежнюю запись из БД, заданной через окружение.",
    ),
    "test_schema_enforces_rules_without_api": (
        "Ограничения самой базы данных",
        "Даже прямой SQL не позволяет записать нулевую площадь или неверную связь.",
    ),
    "test_health_and_ui": (
        "Доступность приложения и файлов интерфейса",
        "HTML, CSS и JS доступны; /health успешен, а при удалении таблицы возвращает 503.",
    ),
    "test_head_is_read_only": (
        "HEAD не изменяет данные",
        "Запрос возвращает заголовки без тела и не удаляет существующее помещение.",
    ),
    "test_postgresql_adapter_changes_parameter_markers": (
        "Подготовка SQL для PostgreSQL",
        "Адаптер заменяет ? на %s и сохраняет параметры; соединение здесь имитируется.",
    ),
    "test_unknown_database_engine_is_rejected": (
        "Ошибочная настройка СУБД",
        "Неизвестный тип базы отклоняется с ошибкой конфигурации.",
    ),
}

RESOURCES = {"buildings": "Корпуса", "departments": "Подразделения", "rooms": "Помещения"}
FIELDS = {
    "area": "Площадь",
    "height": "Высота",
    "building_id": "Ссылка на корпус",
    "department_id": "Ссылка на подразделение",
    "number": "Номер помещения",
}


def describe_value(value):
    if value is None:
        return "null (нет значения)"
    if isinstance(value, bool):
        return f"{value} (логическое значение вместо числа)"
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN (не число)" if math.isnan(value) else "Infinity (бесконечность)"
    if isinstance(value, str):
        return f"строка из {len(value)} символов" if len(value) > 30 else repr(value)
    return repr(value)


def describe_case(item):
    params = item.callspec.params if hasattr(item, "callspec") else {}
    if "resource" in params:
        return RESOURCES.get(params["resource"], params["resource"])
    if "field" in params:
        return f"{FIELDS[params['field']]}: {describe_value(params['value'])}"
    if "key" in params:
        return f"{FIELDS[params['key']]}: несуществующий ID 999"
    if "payload" in params:
        payload = params["payload"]
        if payload is None:
            return "null вместо объекта с полями"
        if isinstance(payload, list):
            return "Массив вместо объекта с полями"
        if isinstance(payload, str):
            return "Строка вместо объекта с полями"
        if not payload:
            return "Пустой объект: обязательное название отсутствует"
        if "extra" in payload:
            return "Лишнее поле extra, которого нет в контракте API"
        if not payload["name"].strip():
            return "Название состоит только из пробелов"
        return f"Название из {len(payload['name'])} символов (максимум 100)"
    return "Основной сценарий"


class ExplainedReport:
    def __init__(self):
        self.items = []
        self.results = {}

    def pytest_collection_finish(self, session):
        self.items = list(session.items)

    def pytest_runtest_logreport(self, report):
        previous = self.results.get(report.nodeid)
        # Ошибка setup/teardown не должна потеряться за успешной фазой call.
        if report.failed or (previous != "failed" and report.skipped):
            self.results[report.nodeid] = report.outcome
        elif report.when == "call" and previous not in {"failed", "skipped"}:
            self.results[report.nodeid] = report.outcome

    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        if config.option.collectonly:
            return
        terminalreporter.write_sep("=", "ПОНЯТНЫЙ ОТЧЁТ О ТЕСТАХ")
        terminalreporter.write_line("Проверяем код и API на временной SQLite, не рабочую базу.")
        terminalreporter.write_line("ПРОЙДЕН = приложение ведёт себя как ожидается.")
        terminalreporter.write_line(
            "Отказ на ошибочном вводе — правильный результат, не сбой теста."
        )
        previous_group = None
        totals = {"passed": 0, "failed": 0, "skipped": 0, "not_run": 0}
        labels = {
            "passed": "ПРОЙДЕН",
            "failed": "ОШИБКА",
            "skipped": "ПРОПУЩЕН",
            "not_run": "НЕ ВЫПОЛНЕН",
        }
        for item in self.items:
            name = item.originalname or item.name
            title, expected = SCENARIOS.get(name, (name, "Условия assert должны выполняться."))
            if name != previous_group:
                terminalreporter.write_line("")
                terminalreporter.write_line(title, bold=True)
                terminalreporter.write_line(
                    textwrap.fill(
                        f"Ожидается: {expected}",
                        width=max(40, shutil.get_terminal_size().columns - 1),
                        initial_indent="  ",
                        subsequent_indent="  ",
                    )
                )
                previous_group = name
            outcome = self.results.get(item.nodeid, "not_run")
            totals[outcome] += 1
            terminalreporter.write_line(
                f"  [{labels[outcome]}] {describe_case(item)}",
                green=outcome == "passed",
                red=outcome == "failed",
                yellow=outcome in {"skipped", "not_run"},
            )
            if outcome == "failed":
                terminalreporter.write_line(f"    Код: {item.nodeid}")
                terminalreporter.write_line("    Причина и различие ожидаемого/полученного — выше.")
        terminalreporter.write_line("")
        terminalreporter.write_line(
            f"Итого: успешно {totals['passed']}, ошибок {totals['failed']}, "
            f"пропущено {totals['skipped']}, не выполнено {totals['not_run']}.",
            bold=True,
        )
        if exitstatus:
            terminalreporter.write_line(
                f"Прогон неуспешен (код pytest {int(exitstatus)}). Причина указана выше.",
                red=True,
            )
        terminalreporter.write_line(
            "Этот прогон не проверяет клики в браузере, SSH и systemd на VM."
        )


def pytest_addoption(parser):
    parser.addoption("--explain", action="store_true", help="Понятный отчёт о тестах на русском")


def pytest_configure(config):
    if config.getoption("--explain"):
        config.pluginmanager.register(ExplainedReport(), "campus-explained-report")
