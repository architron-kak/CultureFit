"""Offline browser regressions for frontend logic; no real provider calls."""
import copy
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/tmp/culturefit-browsers")


def check(page):
    requests = []
    result = {"areas": [], "low_confidence_for": [], "radius": 700}
    state = {"fail": False, "result": result, "refine_fail": False,
             "constraints": {"exclude": ["bar"], "avoid_areas": ["Shared"]}}

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
                route.fulfill(content_type="text/event-stream", body="event: result\ndata: " + json.dumps(state["result"]) + "\n\n")
        elif path == "/api/refine":
            if state["refine_fail"]:
                route.fulfill(status=429, json={"message": "Refine limit"})
            else:
                route.fulfill(json={**state["constraints"], "message": "Constraints applied", "source": "rules"})
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

    def area(name, you, partner, group):
        return {"area": name, "scores": {"You": you, "Partner": partner},
                "group_fit": group, "evidence": {"You": [{"name": "Cafe " + name}], "Partner": []}}

    areas = [area("Solo favorite", 100, 20, 20), area("Partner favorite", 30, 100, 30),
             area("Shared", 85, 90, 85), area("Better tie", 100, 40, 40)]
    data = {**result, "areas": areas}
    before = json.dumps(data)
    picks = page.evaluate("data => computePicks(data)", data)
    assert [pick["area"]["area"] for pick in picks] == ["Better tie", "Partner favorite", "Shared"]
    assert json.dumps(data) == before
    page.evaluate("data => show(data)", data)
    assert page.locator("#picks .pick").count() == 3
    assert "Cafe Better tie" in page.locator("#picks").inner_text()
    assert "You: 85 / 100" in page.locator("#picks .shared-pick").inner_text()
    assert "Partner: 90 / 100" in page.locator("#picks .shared-pick").inner_text()
    assert "Best of the compared areas" in page.locator("#picks").inner_text()
    # Group ties keep response order. Zero is a valid score; null is missing.
    assert page.evaluate("data => bestArea(data).area", [areas[2], area("Tie", 85, 90, 85)]) == "Shared"
    assert page.evaluate("data => bestArea(data, 'You').area", [area("Missing", None, None, None), area("Zero", 0, 0, 0)]) == "Zero"
    assert page.evaluate("data => bestArea(data, 'You')", [area("Missing", None, None, None)]) is None
    malicious = '<img src=x onerror="window.xss=1">'
    page.evaluate("data => show(data)", {**result, "areas": [area(malicious, 100, 100, 100)]})
    assert page.locator("#picks .pick").count() == 1
    assert "One area wins for everyone" in page.locator("#picks").inner_text()
    assert malicious in page.locator("#picks").inner_text()
    assert page.locator("#picks img,#picks script").count() == 0
    assert page.evaluate("window.xss") is None
    solo = {"area": "Solo", "scores": {"You": 80}, "group_fit": 80, "evidence": {}}
    page.evaluate("data => show(data)", {**result, "areas": [solo]})
    assert page.locator("#picks .pick").count() == 1
    assert "Best for both" not in page.locator("#picks").inner_text()
    page.evaluate("data => show(data)", result)
    assert page.locator("#picks").is_hidden()
    print("PASS: personal/group picks, tie breaks, null/zero scores, shared winner, solo/empty results, evidence and escaped API strings")

    previous = data
    current = {**result, "areas": [area("Better tie", 90, 80, 80), area("Partner favorite", 40, 100, 40)]}
    diff = page.evaluate("([a,b]) => refinementComparison(a,b)", [previous, current])
    assert diff["previousTop"] == "Shared" and diff["newTop"] == "Better tie"
    assert diff["changes"][0]["afterPresent"] is False
    assert diff["changes"][0]["metrics"][0]["delta"] is None
    assert diff["changes"][1]["metrics"] == [
        {"label": "Group fit", "before": 40, "after": 80, "delta": 40},
        {"label": "You", "before": 100, "after": 90, "delta": -10},
        {"label": "Partner", "before": 40, "after": 80, "delta": 40},
    ]
    same = {**previous, "trace": ["Different log, same result"]}
    assert page.evaluate("([a,b]) => refinementComparison(a,b).unchanged", [previous, same])
    changed_evidence = copy.deepcopy(previous)
    changed_evidence["areas"][0]["evidence"]["You"][0]["name"] = "Different cafe"
    assert not page.evaluate("([a,b]) => refinementComparison(a,b).unchanged", [previous, changed_evidence])
    # End-to-end browser state: capture the previous result before clearResults().
    state.update(fail=False, result=previous)
    page.locator("#example-button").click()
    page.wait_for_function("!busy")
    state["result"] = current

    def refine():
        page.locator("#ref").fill("no bars, avoid Shared")
        page.locator("#refine-form button").click()
        page.wait_for_function("!busy")

    refine()
    text = page.locator("#refinement-diff").inner_text()
    assert "Previous top: Shared" in text and "New top: Better tie" in text
    assert "Excluded words: bar" in text and "Skipped areas: Shared" in text
    assert "not compared" in text and "(-10 points)" in text and "(+40 points)" in text
    assert requests[-1]["exclude"] == ["bar"] and requests[-1]["avoid_areas"] == ["Shared"]
    refine()
    assert "Nothing changed" in page.locator("#refinement-diff").inner_text()
    assert "Previous top: Better tie" in page.locator("#refinement-diff").inner_text()
    # A normal search clears the diff, as do a changed profile/city and failed rank.
    page.locator("#search-button").click()
    page.wait_for_function("!busy")
    assert page.locator("#refinement-diff").is_hidden()
    page.locator("#f1").fill("New taste")
    refine()
    assert page.locator("#refinement-diff").is_hidden()
    state["fail"] = True
    refine()
    assert page.locator("#refinement-diff").is_hidden()
    state["fail"] = False
    page.locator("#city").select_option("Almaty")
    refine()
    assert page.locator("#refinement-diff").is_hidden()
    state["refine_fail"] = True
    calls = len(requests)
    refine()
    assert len(requests) == calls
    # API-derived area names, person names and constraint words stay literal text.
    page.evaluate("([a,b,c]) => renderRefinementDiff(a,b,c)", [
        previous, {**result, "areas": [area(malicious, 90, 90, 90)]},
        {"exclude": [malicious], "avoid_areas": [malicious]},
    ])
    assert malicious in page.locator("#refinement-diff").inner_text()
    assert page.locator("#refinement-diff img,#refinement-diff script").count() == 0
    assert page.evaluate("window.xss") is None
    assert page.evaluate("([a,b]) => refinementComparison(a,b).newTop", [previous, result]) is None
    print("PASS: refinement diff, top changes/removals, signed score changes, no change, evidence-only change, repeated refine, reset/errors/profile isolation, escaped constraints")

    assert "Your favorites → Qloo place signals → venues → area scores" in page.locator(".qloo-contribution").inner_text()
    assert "Gemini writes the text; scores are computed by our algorithm from Qloo data." in page.locator(".qloo-contribution").inner_text()
    assert page.evaluate("[evidenceNumber(0.123456), evidenceNumber(0.98765), evidenceNumber(1), evidenceNumber(null)]") == ["0.12", "0.99", "1.00", "—"]
    why = {"signal.interests.entities": [
        {"entity_id": "real-id-123", "score": 0.123456789},
        {"entity_id": malicious, "score": 0.987654321},
        {"entity_id": "invalid-string-score", "score": "0.8"},
        {"entity_id": "invalid-null-score", "score": None},
    ]}
    graph_area = area("Evidence", 80, 80, 80)
    graph_area["evidence"]["You"] = [
        {"name": "Real venue", "tags": ["Music"], "affinity": 0.87654321, "why": why},
        {"name": "Second venue", "tags": [], "why": {"signal.interests.entities": [{"entity_id": "real-id-123", "score": 0.54321987}]}},
    ]
    page.evaluate("data => show(data)", {**result, "areas": [graph_area]})
    page.locator(".card-button").first.click()
    assert page.locator(".why-diagram path[stroke-dasharray]").count() == 3
    assert page.locator(".why-diagram text[aria-label]").first.get_attribute("aria-label") == "Reported weights: 0.12, 0.54"
    assert "real-id-123" in page.locator("#why-records").inner_text()
    assert "Reported contribution: 0.12." in page.locator("#why-records").inner_text()
    assert "Venue affinity: 0.88." in page.locator("#why-records").inner_text()
    assert "0.123456789" not in page.locator("#diagram-scroll").inner_text()
    assert "0.123456789" in page.locator(".raw-why pre").first.text_content()
    assert "Blade Runner" not in page.locator("#diagram-scroll").inner_text()
    assert "Radiohead" not in page.locator("#diagram-scroll").inner_text()
    assert page.locator("#diagram-scroll img,#why-records img,#why-records script").count() == 0
    assert page.evaluate("window.xss") is None
    # Unsupported shapes and invalid values cannot create contribution links.
    assert page.evaluate("whyLinks({'favorites': [{'entity_id': 'invented', 'score': 1}]})") == []
    assert page.evaluate("whyLinks({'signal.interests.entities': [{entity_id: 'bad', score: Infinity}]})") == []
    page.keyboard.press("Escape")
    print("PASS: Qloo attribution, rounded graph/record numbers, intact raw evidence, only real links, literal entity IDs")


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1366, "height": 768}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        check(page)
        assert not errors, errors
        browser.close()
