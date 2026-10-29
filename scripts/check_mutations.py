"""Контрольные поломки выполняются только в копии проекта во временной папке."""

import json
import shutil

# Запускаем доверенный интерпретатор без shell, параметры заданы в этом файле.
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTATIONS = [
    (
        "Нулевая площадь разрешена",
        "campus/__init__.py",
        "not 0 < value <= maximum",
        "not 0 <= value <= maximum",
    ),
    (
        "Верхняя граница отвергается",
        "campus/__init__.py",
        "not 0 < value <= maximum",
        "not 0 < value < maximum",
    ),
    (
        "Объём складывается вместо умножения",
        "campus/__init__.py",
        'data["area"] * data["height"]',
        'data["area"] + data["height"]',
    ),
    (
        "Номер больше не уникален в корпусе",
        "campus/schema.sql",
        "UNIQUE(building_id, number)",
        "CHECK(1 = 1)",
    ),
]


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix="campus-mutants-") as directory:
        workspace = Path(directory)
        for name in ("campus", "tests", "migrations"):
            shutil.copytree(
                ROOT / name, workspace / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        shutil.copy(ROOT / "pyproject.toml", workspace / "pyproject.toml")
        for title, filename, old, new in MUTATIONS:
            path = workspace / filename
            original = path.read_text()
            if original.count(old) != 1:
                raise RuntimeError(f"Мутация больше не соответствует коду: {title}")
            path.write_text(original.replace(old, new))
            try:
                # Абсолютный sys.executable, фиксированные аргументы, shell не используется.
                result = subprocess.run(  # nosec B603
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "--tb=short",
                        "tests/test_logic.py",
                        "tests/test_app.py",
                    ],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            finally:
                path.write_text(original)
            # Код 1 означает провал assert. Ошибка конфигурации/сбора не засчитывается.
            detected = result.returncode == 1 and " failed" in result.stdout
            results.append({"mutation": title, "detected": detected})
            print(("ОБНАРУЖЕНА: " if detected else "НЕ ОБНАРУЖЕНА: ") + title)
            if not detected:
                print(result.stdout[-4000:] + result.stderr[-1000:])
    report = ROOT / "reports/mutations.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    if not all(result["detected"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
