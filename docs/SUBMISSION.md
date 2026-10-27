# CultureFit — Find common ground through culture

**Author:** [architron-kak](https://github.com/architron-kak)

**Source:** https://github.com/architron-kak/CultureFit/tree/design/night-taste-map

**License:** [MIT](../LICENSE)

**Live demo:** [culturefit-yafy.onrender.com](https://culturefit-yafy.onrender.com)

**Public repository:** [architron-kak/CultureFit](https://github.com/architron-kak/CultureFit)

## Project description

CultureFit is a Qloo-powered neighborhood discovery workflow for one person or
two people with different tastes. Enter favorite films, artists, brands, food,
or games, choose Zurich or Almaty, and explore neighborhoods through real venue
evidence. The goal is to find common ground without hiding either person's
trade-offs.

The workflow resolves favorites through Qloo's Search API, then requests place
recommendations around curated neighborhood centers using `/v2/insights`,
`signal.interests.entities`, geographic filters, and explainability. The app
compares the strongest qualifying venues for each person and ranks neighborhoods
by the weaker person's relative score. A minimum spread prevents small affinity
differences from becoming an exaggerated 0–100 contrast.

Judges can follow live search steps, inspect venues and cleaned cultural tags,
compare both profiles, and open an interactive evidence graph. Returned Qloo
input-entity IDs and contribution weights are shown when available; favorite
names are not inferred from unidentified IDs.

Gemini parses natural-language refinements and explains the leading results
using the returned evidence. Refinements such as “no bars” or “avoid Altstadt”
update constraints and rerun the workflow. Rules and template explanations keep
the application usable if an LLM is unavailable.

Qloo provides the cultural connections, venues, tags, affinities, and
explainability. CultureFit supplies the neighborhood comparison and compromise
logic. Scores are relative to compared neighborhoods, not match percentages or
objective ratings of residential quality.

## Key features

- One-person and two-person taste profiles, up to six favorites per person.
- Seven Zurich areas and four Almaty areas.
- A full-screen dark OpenStreetMap with glowing neighborhood circles.
- Separate teal/coral profile scores, compromise information, and venue evidence.
- Natural-language refinement with visible removable constraint chips.
- A live agent log and an SVG area → venue → tag explanation drawer.
- Explicit low-confidence, missing-data, loading, and error states.
- Mobile bottom sheets and reduced-motion support.

## Suggested judging walkthrough

1. Open the public demo without signing in.
2. Select Zurich and run the prefilled two-person example.
3. Compare the scores and the actual venues supporting the top areas.
4. Click an area to open its evidence graph and switch between people.
5. Apply “no bars” and inspect the active constraints and updated results.
6. Try Almaty and the mobile layout.

## Scope and limitations

Neighborhoods use approximate centers and circular search areas. Zurich uses
700 m and Almaty 1500 m; some overlap remains. Utility tags are filtered from
explanations. A “quiet” refinement filters nightlife evidence and does not
measure street noise. The app does not analyze rent, housing availability,
safety, or commuting. API availability and coverage affect the results.

## Submission readiness — 27 October 2026

| Required item | Current status |
| --- | --- |
| Functional end-to-end demo URL | Published and tested anonymously at the live demo link above |
| Public source repository | Public; unauthenticated GitHub API confirms `private: false` |
| Text description | Provided above |
| Fully published external hosting | Render Python Web Service, free plan, Frankfurt; deployment is Live |
| Open-source license visible in repository | Root LICENSE in main and the submission branch; GitHub detects MIT |

A demo video is not required by the supplied rules. The published service uses
the `design/night-taste-map` branch linked above. The repository's default `main`
branch retains an earlier UI and links to the current submission branch.
See [public demo validation](PUBLIC_DEMO_VALIDATION.md) for the actual checks.
The free hosting service can take about a minute to resume after an idle period.
