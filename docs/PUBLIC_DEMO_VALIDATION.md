# Published demo validation — 27 October 2026

- Public application: https://culturefit-yafy.onrender.com
- Public repository: https://github.com/architron-kak/CultureFit
- Current deployed source: `main` (the initial design branch was merged into it).
- Initial application commit: `bffdf228450d2f5b97ed85cba35076aa99412baf`.
- Host: Render Python Web Service, **free** plan, Frankfurt, one instance.
- Startup: Uvicorn with one worker; health check `/api/cities`.

The initial Render deployment reached **Live** at 16:39:52 UTC. Checks below used
the public HTTPS address without authentication. Requests reached the real
deployed backend and its configured Qloo/Gemini services; no routes, providers,
or responses were replaced with fixtures.

## HTTP and real workflow

| Check | Observed result |
| --- | --- |
| `GET /` | HTTP 200, night UI and author `architron-kak` |
| `GET /api/cities` | Zurich with seven areas; Almaty with four |
| `/.env`, `/.env.deploy`, `/.git/config` | HTTP 404 for each |
| Zurich, default two profiles | Seven areas, Altstadt first, group fit 100; Gemini explanation |
| Almaty, same profiles | Four areas, Center first, group fit 100; template explanation |
| Refine “quiet, no bars, avoid Altstadt” | Exclusions returned and applied; Altstadt omitted from the six-area reranking |
| Refined Zurich | Enge first, group fit 99; Gemini explanation |
| Group fit | Equals the minimum available personal score when both scores exist |
| Evidence tags | No tags matched the service's utility-tag filter |
| Radius | Zurich 700 m; Almaty 1500 m |

The first streamed step arrived in 0.15–0.31 seconds. Complete HTTP searches
took 19.76 seconds for Zurich, 11.47 seconds for Almaty, and 15.52 seconds for
refined Zurich. These are observations from these runs, not performance guarantees.
Defaults were Blade Runner, Radiohead, Studio Ghibli for You and Metallica,
Peaky Blinders, Guinness for Partner.

The source field reported `template` for the Almaty explanation. The deployed
workflow remained usable through its intended fallback. Subsequent browser
search of Zurich reported Gemini. This check does not establish why the earlier
Gemini call was unavailable.

## Real Chromium browser

A fresh browser context opened the public URL and performed the default Zurich
search. It loaded MapLibre GL 4.7.1 and actual OpenStreetMap raster tiles.
Seven result cards, seven polygons, and seven markers appeared. The explanation
source was Gemini. The small-differences notice was visible for both profiles.

Opening a result card displayed the SVG evidence graph; the observed `why`
records produced nine supported input links for the first profile. Switching
to Partner worked. Clicking a map marker also opened the drawer. Escape closed it.

At a 390 × 844 viewport, the map occupied the full screen and the taste, map,
matches, and evidence drawer views worked. Visible panels stayed inside the
viewport. The desktop viewport was 1440 × 1000. No JavaScript exceptions were
recorded. Screenshots and machine-readable reports remain in ignored `artifacts/`.

## Repository, configuration, and local checks

The unauthenticated GitHub API returned HTTP 200, `private: false`, and license
SPDX `MIT`. Author credit and the root MIT license are present on `main`.
The repository homepage README links to the demo and the current source branch.
The previously separate design branch was merged into `main`, preserving its
history. Render and the Blueprint now use `main` as the single current branch.

The page source did not contain configured keys. Local `.env` and `.env.deploy`
remain ignored by Git. Only application configuration and the Qloo/Gemini keys
were sent as Render environment settings; the Render account API key was not
included in the deployed app. Secret values are excluded from this report.

The existing local test suite passed: **35 passed**. One upstream Starlette
TestClient deprecation warning was emitted. Documentation updates after the
initial deployment do not change application behavior.

Free Render hosting can sleep after inactivity. Allow time for the first page
to resume and verify the public address again before submitting the hackathon form.
