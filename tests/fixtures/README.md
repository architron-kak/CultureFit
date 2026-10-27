# Browser-test fixtures

`qloo_places.json` is synthetic test data. Its venue names, tags, and stand-in
input ID are used only by `scripts/browser_check.py`, which replaces the Qloo
client in that standalone test process. The `signal.interests.entities`
explainability structure matches the live Qloo shape inspected during development.

The normal application imports `culturefit.qloo.Qloo` and requests real data.
It does not import these fixtures or the browser-check script.
