"""Offline browser regressions for frontend logic; no real provider calls."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/tmp/culturefit-browsers")


def check(page):
    requests = []
    result = {"areas": [], "low_confidence_for": [], "radius": 700}
    state = {"fail": False}

    def route_app(route):
        path = route.request.url.split("culturefit.test", 1)[1]
        if path == "/":
            route.fulfill(content_type="text/html", body=(ROOT / "culturefit/static/index.html").read_text())
        elif path == "/api/cities":
            route.fulfill(json={"Zurich": ["Altstadt"], "Almaty": ["Center"]})
        elif path == "/api/rank":
            requests.append(json.loads(route.request.post_data))
            if state["fail"]:
                route.fulfill(status=429, json={"message": "Example search limit reached"})
            else:
                route.fulfill(content_type="text/event-stream", body="event: result\ndata: " + json.dumps(result) + "\n\n")
        else:
            route.abort()

    page.route("**/*", lambda route: route.abort())
    page.route("http://culturefit.test/**", route_app)
    page.goto("http://culturefit.test/")
    page.wait_for_function("!busy && document.querySelector('#city').options.length === 2")
    page.locator("#city").select_option("Almaty")
    page.locator("#f1").fill("Different favorites")
    page.locator("#f2").fill("")
    page.evaluate("constraints = {exclude: ['bar'], avoid_areas: ['Altstadt']}; renderConstraints()")
    page.locator("#example-button").click()
    page.wait_for_function("!busy")
    assert requests == [{
        "city": "Zurich",
        "people": [
            {"name": "You", "favorites": ["Blade Runner", "Radiohead", "Studio Ghibli"]},
            {"name": "Partner", "favorites": ["Metallica", "Peaky Blinders", "Guinness"]},
        ],
        "exclude": [], "avoid_areas": [],
    }]
    assert page.locator("#count1").inner_text() == "3 / 6"
    assert page.locator("#count2").inner_text() == "3 / 6"
    page.evaluate("setBusy(true); tryExample()")
    assert len(requests) == 1
    assert page.locator("#example-button").is_disabled()
    page.evaluate("setBusy(false)")
    state["fail"] = True
    page.locator("#example-button").click()
    page.wait_for_function("!busy")
    assert len(requests) == 2
    assert "Example search limit reached" in page.locator("#field-message").inner_text()
    assert page.evaluate("lastResult") is None  # No saved fallback after a failed search.
    print("PASS: example uses normal search, correct profiles/city, resets constraints, busy guard, HTTP errors without fallback")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1366, "height": 768}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        check(page)
        assert not errors, errors
        browser.close()
