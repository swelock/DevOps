# Реальный конфликт слияния в ЛР1

17.09.2026 в основном репозитории выполнена учебная симуляция параллельной
правки документации. Автор всех коммитов — настроенный локальный Git-пользователь;
участие второго человека не имитировалось.

Общая база: `00dbed4`, строка README «Учёт корпусов и помещений.».
В `feature/lr1-campus` коммит `32a00bc` добавил подразделения.
Отдельная ветка `docs/room-metrics` создана от `main`; коммит `6e4230b`
уточнил характеристики помещений на той же строке.

Запущено:

```bash
git switch feature/lr1-campus
git merge --no-ff docs/room-metrics -m "merge: reconcile room metrics documentation"
```

Git остановил слияние:

```text
Auto-merging README.md
CONFLICT (content): Merge conflict in README.md
Automatic merge failed; fix conflicts and then commit the result.
```

`git status --short` показал `UU README.md`. Конфликт:

```text
<<<<<<< HEAD
Учёт корпусов, подразделений и помещений.
=======
Учёт корпусов и помещений с расчётом площади и объёма.
>>>>>>> docs/room-metrics
```

Решение: сохранить подразделения и уточнить, что площадь вводится,
а объём рассчитывается. Итоговая строка:

> Учёт корпусов, подразделений и помещений с хранением площади и расчётом объёма.

После ручного объединения обеих правок выполнены `make verify`,
`git add README.md docs/CONFLICT.md` и merge-коммит. Ничья история не переписывалась.

Показать преподавателю:

```bash
git log --graph --oneline --all
git log --merges --oneline feature/lr1-campus
git show 32a00bc:README.md
git show 6e4230b:README.md
```

Повторять конфликт в рабочей ветке не требуется: две стороны и merge-коммит
сохранены. При необходимости повторения используйте отдельный временный clone
и обе указанные ревизии, чтобы не менять текущую рабочую историю.
