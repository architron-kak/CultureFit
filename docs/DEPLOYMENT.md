# Public demo deployment

Author: [architron-kak](https://github.com/architron-kak).

A public demo must run the FastAPI server as well as the frontend. GitHub Pages
alone cannot run this Python backend. The repository includes a Render Blueprint
in `render.yaml`; it has not yet been deployed.

## Render

1. Sign in to https://dashboard.render.com and connect your GitHub account.
2. Choose **New → Blueprint** and select `architron-kak/CultureFit`.
3. Select the **design/night-taste-map** branch, which contains the night UI,
   current scoring fixes, and the deployment configuration.
4. Review the `culturefit` web service. The configuration explicitly selects the
   `free` plan. Review the provider's current account/plan conditions before creating it.
5. Enter `QLOO_API_KEY` and `GEMINI_API_KEY` in the secret fields prompted by
   `sync: false`. Copy them from your local configuration into Render's secret
   settings. Do not put their values in Git, `render.yaml`, or the submission text.
6. Deploy and wait for the service to become **Live**. Use the actual public HTTPS
   URL shown by Render; no demo URL has been assigned to this project yet.
7. Verify that the URL works in a private/incognito browser window without login.
8. Complete the end-to-end checks below. A successful health check alone does not
   prove that upstream API credentials and quotas work.
9. Add the verified URL to README, `docs/SUBMISSION.md`, the repository's About
   website field, and the hackathon application.

The app supports a no-LLM fallback. If Gemini is intentionally disabled, remove
its secret entry from the Blueprint before creating the service; the supplied
Blueprint assumes that both existing project keys will be configured.

## Equivalent manual service settings

| Setting | Value |
| --- | --- |
| Type | Public Web Service, not Static Site |
| Runtime | Python 3 |
| Python | 3.14.8 |
| Branch | design/night-taste-map |
| Root directory | Repository root; leave empty |
| Build | `python -m pip install -r requirements.txt` |
| Start | `python -m uvicorn culturefit.main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health check | `/api/cities` |
| Qloo URL | `https://hackathon.api.qloo.com` |
| Gemini model | `gemini-3.5-flash` |
| Required project secrets | QLOO_API_KEY, GEMINI_API_KEY for this configuration |

One worker keeps the in-memory cache and request pacing together. Keep one
service instance unless a shared rate limiter is added. Production does not use
`--reload`. Configuration comes from the hosting environment; `.env` remains local.

## End-to-end checks on the public URL

- `GET /` returns the night UI.
- `GET /api/cities` returns Zurich and Almaty.
- Search Zurich with the default favorites for both people. Receive neighborhood
  cards and the explanation without console errors.
- Search Almaty and verify that the map and results change.
- Apply `no bars` and verify active constraint chips and refreshed results.
- Open an area from a card or map marker. Verify the area → venues → tags graph.
- Verify the mobile taste/map/matches tabs.
- Check that `/.env` returns 404 and that no Qloo/Gemini key appears in page source
  or browser requests. Calls to those providers belong on the server.
- Confirm the server is serving a fresh result from Qloo, not a test fixture.

Free services may suspend while idle and need time to resume. Test the actual
public URL before submission, including the first visit after an idle period.
A local server, screenshot, private preview, or deploy configuration by itself
is not a published functional demo.

## Repository and license

The hackathon requires a public repository. Open
https://github.com/architron-kak/CultureFit/settings and use **Danger Zone → Change
repository visibility → Public** if the repository is still private. Then open
its URL while signed out to confirm that the source is visible.

The MIT `LICENSE` file is placed in the repository root, including the `main`
branch, so GitHub can detect it for the repository's license information. Verify
that **MIT license** appears on the repository page after pushing. Keep the
current submission branch link explicit if `main` still contains an older UI.

## Official references

- FastAPI on Render: https://render.com/docs/deploy-fastapi
- Blueprint configuration: https://render.com/docs/blueprint-spec
- Python runtime: https://render.com/docs/python-version
- Free service behavior: https://render.com/docs/free
- GitHub license detection: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository
