# Результаты проверки

25 октября 2026 года. Python 3.14, Linux. Основные установленные зависимости
зафиксированы в requirements.txt.

## Автоматические тесты

`python -m pytest tests -q`: **27 passed**.

Проверены HTML и список городов, недоступность `.env` через сервер,
ограничения участников/интересов, уникальность имён, неизвестные города/районы,
исключение всех районов, один/два участника, SSE result/explanation/error,
отсутствующие интересы, уточнения без LLM, противоположные пожелания по шуму,
множественное число в тегах, неполные данные и некорректный affinity,
контракт параметров Qloo, точное совпадение имени, кэш, повтор 429, поиск 404,
безопасное сообщение об ошибке Qloo 401.

Среда выводит предупреждение Starlette о будущем переходе TestClient с httpx
на httpx2. Проверки проходят; рабочий клиент Qloo использует httpx.

## Настоящий Qloo

`scripts/live_check.py`: успешно, ключ загружается из `.env` и не печатается.

- Поиск Radiohead: успешно.
- Insights по Radiohead в центре Цюриха: 20 мест, affinity и explainability есть.
- Insights по Radiohead в центре Алматы: 20 мест, affinity и explainability есть.
- Полный POST /api/rank, 2 участника с исходными шестью интересами:
  - Zurich: 7 районов, первый Zurich West, group_fit 100,
    после фильтра 16 мест у каждого участника в этом районе.
  - Almaty: 4 района, первый Center, group_fit 100,
    после фильтра 20 и 15 мест в этом районе.
- Получены и result, и explanation; источник объяснения — template.
- `quiet, no bars, avoid Altstadt`: правила добавили исключения и Altstadt.

Результаты конкретного прогона — не гарантия будущего порядка.
100 здесь означает верх относительной шкалы приложения, а не идеальный район.
Сводка прогона: `artifacts/live-check.json`.

## Chromium / интерфейс

`scripts/browser_check.py`: успешно.

- Реальный HTML/JS и API FastAPI; ответы Qloo в этой проверке подставные.
- 7 карточек для Цюриха, 4 для Алматы; пояснение отображается.
- Повторный запуск во время запроса не создаёт второй запрос.
- Уточнения накапливаются; смена города очищает ограничения и результаты.
- HTTP 503 и сетевая ошибка видны; кнопки после ошибки доступны.
- При недоступном CDN карты сохраняются города и работает рейтинг.
- Пустые данные отображаются как insufficient data без null в интерфейсе.
- Во втором сценарии настоящая MapLibre загрузилась с CDN;
  GeoJSON-источник карты получил 7 полигонов районов.
- В первом сценарии нет необработанных исключений JavaScript.
- Снимок тестового состояния: `artifacts/browser-check.png`.

## Ограничения проверки

Настоящий Uvicorn также проверен по локальному HTTP: `/`, `/api/cities`, `/docs`
вернули 200. Проверочный процесс остановлен после запросов.

Первый прогон выполнен без ключей LLM: использованы правила и шаблонные объяснения.
Позднее Gemini проверен с предоставленным ключом — результаты ниже. OpenRouter
по сети не проверялся.
Тест не подтверждает точность координат районов, полноту базы Qloo,
реальный уровень шума или объективную пригодность района для жизни.

Для установки зависимостей, обращения к Qloo и запуска TestClient/Chromium
потребовался выход из сетевых ограничений песочницы. Внутри песочницы
TestClient зависал; те же проверки вне неё завершились успешно.

После переноса модулей в пакет `culturefit/` 27 тестов пройдены повторно.
Команда запуска: `uvicorn culturefit.main:app --reload`.

## Обновление Gemini и интерфейса

Проверено 25 октября 2026 года:

- API списка моделей Google вернул HTTP 200 с настроенным ключом.
- `gemini-flash-latest` при проверке вернула HTTP 503 UNAVAILABLE.
- `gemini-2.5-flash` вернула HTTP 404 NOT_FOUND.
- `gemini-3.5-flash`: успешно выполнены генерация контрольного ответа, разбор
  исключений bars/clubs и Altstadt, а также объяснение результата; оба прикладных
  ответа имеют `source=gemini`. Эта модель выбрана в локальном `.env`.
- Ключ читается из `.env`, прямых ключей в исходном коде нет.
- Дополнена обработка ответов Gemini из нескольких текстовых частей; внутренние
  части с флагом `thought` не выдаются как объяснение.
- Дополнены фильтры для множественного числа, которое может вернуть Gemini.
- **28 passed**: автоматические тесты, включая заголовок авторизации Gemini,
  объединение текстовых частей и исключение Bar/Nightclub по bars/nightclubs.
- Chromium: успешные поиск, уточнения, сброс при смене города, обработка ошибок
  HTTP/сети, отсутствие карты, неполные данные, 7/4 карточки и карта с 7 полигонами.
- Проверены ширины 1280 и 390 px: горизонтальной прокрутки нет; маркер карты
  выбирает карточку района. Снимки нового интерфейса в `artifacts/design-*.png`.

Обновлённый интерфейс сохраняет тот же API: профили участников, карта с маркерами,
относительные оценки, конкретные заведения, объяснение и журнал поиска.
Исходники разделены на `index.html`, `styles.css`, `app.js`.

Финальный живой прогон после обновления: Qloo вернул все 7 районов Цюриха и
4 района Алматы для двух участников. В обоих городах объяснения получены с
`source=gemini`; уточнение пожеланий также обработано Gemini.

## Исправление шкалы и качества свидетельств

После введения MIN_SPREAD=0.08, радиуса Цюриха 700 м и очистки служебных
тегов выполнено **35 тестов, все прошли**. Отдельно проверено, что данные без
affinity остаются null и что очищенные теги доходят до запроса объяснения LLM.

Живой Qloo проверен на двух исходных профилях в Цюрихе при 1200/700 м и
Алматы при 1500 м. Чувствительность к порогу, оценки, повторы, реальный
location и why записаны в `SCORING_VALIDATION.md`.

Браузерная проверка ночного интерфейса прошла: SSE, ошибки, неполные данные,
низкая уверенность, why-граф, круги на карте, reduced motion и мобильные панели.
Дополнительные проверки подтвердили отсутствие служебного тега
`Wheelchair accessible parking lot` в карточках и в SVG-графе.

## In-memory limits — 27 October 2026

- **46 tests passed**, with no external Qloo or LLM requests. A fake clock
  covers the exact rolling-hour boundary and midnight UTC reset.
- Per-IP quotas allow six rank requests and twenty refinement requests per
  rolling hour. Tests cover independent IPs/endpoints, the first forwarded
  address, socket fallback, `Retry-After`, and HTTP 429 before provider work or SSE.
- A shared budget allows 150 outbound LLM attempts per UTC day, including
  failures and individual OpenRouter model attempts. Tests cover cached answers,
  missing keys, competing in-flight requests, and the rules/template fallback.
- An exhausted daily budget preserves the existing `step`, `result`, and
  `explanation` events and the refinement response shape.
- Chromium displayed real local HTTP 429 messages for both endpoints. A rejected
  refinement did not start a rank request. Desktop/mobile map, drawer, and SSE
  checks also passed without JavaScript exceptions. Providers were synthetic.
- No dependencies were added. Limits are process-local and reset on restart;
  production runs one worker and one instance.

## Responsive design review — 28 October 2026

The review found a clipped search button at 1366 × 768, a hidden action on
phones, cramped side panels at 820 px, and very small venue/tag labels.
The search action and feedback now stay visible below the scrolling form.
Tablets use the bottom-sheet navigation, text is larger, and the evidence diagram
can scroll horizontally instead of shrinking its labels. Results headings scroll
with the cards, and reopening an area starts its explanation at the top.

Chromium checks passed at 1366 × 768, 820 × 1180, 390 × 844, and 320 × 568.
They cover form submission from the persistent button, visible errors, complete
circle bounds after resizing, diagram readability, and scroll resets. Existing
SSE, HTTP 429, map, drawer, and reduced-motion browser checks also passed with
synthetic providers and no JavaScript exceptions. No live search quota was used.
