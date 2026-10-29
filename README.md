# CultureFit

Find common ground through culture. CultureFit helps one person or two people
discover neighborhoods in Zurich and Almaty based on their favorite films,
artists, brands, food, and games. Qloo finds related places; CultureFit compares
neighborhoods and shows the venues behind each result.

**Author:** [architron-kak](https://github.com/architron-kak)

**Live demo:** [culturefit-yafy.onrender.com](https://culturefit-yafy.onrender.com)

**Source:** [main](https://github.com/architron-kak/CultureFit/tree/main)

**License:** [MIT](LICENSE)

The current source, night map interface, and published application all use `main`.
Gemini and OpenRouter are optional: rules and template explanations keep the app
usable without an LLM key.

## Quick start (Python 3.10+)

Clone the repository:

```bash
git clone https://github.com/architron-kak/CultureFit.git
cd CultureFit
```

From the repository root, where `requirements.txt` is located:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
# Set QLOO_API_KEY in .env before starting the server.
python -m uvicorn culturefit.main:app --reload
```

Open http://localhost:8000. The application's API documentation is available at
http://localhost:8000/docs.

Only the server reads API keys. `.env` is excluded from Git. For a standard Qloo
account, set the appropriate `QLOO_API_URL`; the hackathon key was tested with
https://hackathon.api.qloo.com.

## Using the app

1. Select a city and enter one to six favorites per person, separated by commas.
2. The second person is optional. Clear that field to explore on your own.
3. Click **Find our neighborhood**. Search steps appear as the workflow runs.
4. Refine the results with requests such as `quiet`, `no bars`, `no clubs`, or
   `avoid Altstadt`. Without an LLM, only a limited set of explicit phrases is
   supported. Constraints accumulate until you click **Reset** or change cities.
5. If a network request fails, the agent log displays the error. You can retry
   the search.

The text results remain usable if the map or its CDN is unavailable. The map
uses MapLibre and OpenStreetMap.

## How ranking works

- `/search?query=...` resolves each favorite to a Qloo entity ID. An exact name
  match among the first five results is preferred; otherwise, the first result
  is used. This is automatic matching, so review the resolved names in the log.
- `/v2/insights` requests 20 places around each neighborhood center separately
  for each person. Requests use `filter.type=urn:entity:place`, a WKT
  `POINT(lon lat)`, a radius in meters, `signal.interests.entities`, and
  `feature.explainability=true`.
- After filtering hotels, selected chain venues, and user exclusions, the app
  averages the affinity of the five strongest qualifying places. Missing or
  nonnumeric affinity values are not treated as zero.
- Each person's averages are converted to a 0–100 score relative to their best
  neighborhood: `100 * (1 - (best - raw) / max(spread, 0.08))`. Small differences
  are not stretched across the entire scale: affinities of 0.83 and 0.79 produce
  scores of 100 and 50. When all available averages are equal, every area scores
  100 and a small-differences notice appears.
- **Group fit** is the lowest personal score. **Gives up** is 100 minus a person's
  relative score.
- If an area lacks data for either person, its group score is `null` and the UI
  shows **insufficient data**. These areas appear last; they are not assigned
  an artificial score of 0 or 50.

Scores are relative to the compared neighborhoods, **not match percentages** or
official Qloo neighborhood ratings. This is a heuristic. Affinity depends on the
query context; comparing averages from separate geographic queries is not a
calibrated statistical model. Small differences should not be overinterpreted.

`MIN_SPREAD = LOW_SPREAD = 0.08` is a heuristic threshold for the API's 0–1
affinity scale, not a confidence interval. Once the spread reaches 0.08, the
lowest area can still score 0. That means the lowest relative score, not that
the area has no suitable places.

Zurich uses a 700 m radius; Almaty uses 1500 m. Search circles can still overlap,
and their centers are approximate. Official neighborhood boundaries are not used.

Payment methods, parking, accessibility, prices, delivery, Wi-Fi, and other
utility tags are removed from cards, evidence diagrams, and Gemini inputs.
The original `why` data is preserved: confirmed Qloo links are not replaced by
guessed connections.

The `quiet` constraint filters nightlife venue categories; it does not measure
actual street noise. Housing prices, safety, transportation, and apartment
availability are outside the app's scope.

## API and resilience

- `POST /api/rank`: one or two people with unique names and one to six favorites
  each. Invalid input returns HTTP 422 before streaming starts. The response
  streams SSE events: `step`, `result`, `explanation`, or `error`. Once the stream
  begins, the HTTP status is 200; upstream failures must be read from the
  `error` event.
- `POST /api/refine`: a city and a request of up to 300 characters.
- `GET /api/cities`: available cities and neighborhoods.

POST requests are limited per IP to **6 searches** (`/api/rank`) and
**20 refinements** (`/api/refine`) in a rolling hour. The first value of
`X-Forwarded-For` identifies the client behind Render's proxy; without it, the
socket address is used. An exhausted quota returns HTTP 429 with a short JSON
`message` and `Retry-After` header before any SSE stream or provider work starts.
The interface displays that message. Refining results also starts a search,
which counts toward the separate search quota.

All Gemini and OpenRouter generation attempts share a **150-call budget per
UTC day**, resetting at midnight UTC. Failed attempts and each fallback model
count; cached answers and missing credentials do not. When a new generation
is blocked, explanations use the existing template and refinements use rules.
SSE events and payloads remain the same.

These limits are in memory in a single process: restarting the server resets
them, and multiple workers or instances do not share them. The Render setup
uses one worker and one instance. Run the app behind the trusted proxy that
sets `X-Forwarded-For`.

Each server process limits Qloo traffic to four requests per second, retries a
429 response once, and respects `Retry-After` in seconds up to a 30-second cap.
The Qloo cache holds up to 512 responses for six hours. The LLM cache holds up to
256 responses for one hour. With multiple processes, the request limits add up;
that setup needs a shared rate limiter.

## Checks

Install the development dependencies and run the offline tests:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

The unit tests use a fake Qloo client and do not consume API requests. To test
against real Qloo using your `.env` key, run the live check (about 37 requests):

```bash
python scripts/live_check.py
```

Run the browser checks:

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/culturefit-browsers python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/tmp/culturefit-browsers python scripts/frontend_check.py
PLAYWRIGHT_BROWSERS_PATH=/tmp/culturefit-browsers python scripts/browser_check.py
```

The browser check uses synthetic Qloo responses to test the interface and real
MapLibre rendering when the CDN is available. Artifacts are saved in `artifacts/`,
which is excluded from Git.

`frontend_check.py` runs entirely offline. It covers the example search, personal
and shared picks, refinement comparisons, escaped API text, and evidence-number
formatting. Its intercepted API responses are test fixtures only; the app's
"Try an example" button always starts a normal real search with no saved fallback.

Further documentation:

- [Qloo notes and development ideas](docs/QLOO_NOTES.md)
- [Validation history](docs/VALIDATION.md)
- [Live Qloo validation of scores, radii, and tag filtering](docs/SCORING_VALIDATION.md)
- [Published demo validation](docs/PUBLIC_DEMO_VALIDATION.md)

## Project structure

```text
culturefit/           # application package
  main.py             # FastAPI and SSE
  qloo.py             # Qloo client
  llm.py              # LLM integration, rules, and explanations
  scoring.py          # neighborhood ranking
  districts.py        # neighborhood centers
  static/index.html   # night UI: HTML, CSS, and vanilla JS in one file
tests/                # automated tests
scripts/              # Qloo and browser checks
docs/                 # documentation and validation reports
.env.example          # configuration template
requirements.txt      # application dependencies
requirements-dev.txt  # testing tools
pyproject.toml        # pytest configuration
render.yaml           # Render deployment configuration
```

`.env`, `.venv/`, `venv/`, caches, and `artifacts/` remain local and are excluded
from Git. The original personal notes file, `only me.txt`, is outside the repository.

## Gemini

Add `GEMINI_API_KEY` to `.env` in the project root. Select the model with
`GEMINI_MODEL`. Do not insert the key into `culturefit/llm.py`: the server sends
it to Google through the `x-goog-api-key` header. Restart the server after
changing `.env`.

```bash
python scripts/gemini_check.py
# List available models without generating content:
python scripts/gemini_check.py --models
```

The check runs a short generation, parses a refinement, and generates an
explanation, verifying that the source is Gemini. Google errors 404, 429, and
503 are reported separately. A valid key alone does not guarantee that a
particular model is available. If the LLM is unavailable, the app continues
with rules and template explanations.

If you moved an existing virtual environment with the project folder, its
scripts may still contain old absolute paths. Create a new `.venv` using the
instructions above. Virtual environments should be created in place rather
than moved between directories.

## License

The source code is released under the [MIT License](LICENSE).
Copyright © 2026 architron-kak.

## Hackathon submission and hosting

The English project description and submission checklist are available in
[docs/SUBMISSION.md](docs/SUBMISSION.md).

The [live demo](https://culturefit-yafy.onrender.com) is published on Render's
free plan from `main`. On 27 October 2026, checks confirmed anonymous public
access, real searches in both cities, and refinement followed by reranking.
The GitHub repository is public and GitHub detects its MIT license. See the
[published demo validation report](docs/PUBLIC_DEMO_VALIDATION.md).

After an idle period, the free service may take about a minute to resume.
To reproduce the deployment, use [render.yaml](render.yaml) and the
[deployment instructions](docs/DEPLOYMENT.md).
