# Dashboard

`index.html` is the source of the Market Briefing dashboard, published as a Claude Artifact
(type "Data"). The Artifact reads a copy of `../data/market-briefing-data.csv` that is attached
to it, and parses and computes everything in the page: no network calls.

## Refreshing

An Artifact page cannot fetch from GitHub, so it does not update on its own. After the weekday
Actions job commits new data, the attached CSV must be re-uploaded to the Artifact (say
"update report" in a Claude session). The page then redraws from the new file.

## Notes

- Six KPIs in the order the handoff specifies; every figure shows an as-of date, and deltas name
  the verified reference date.
- Rows tagged `unverified` or `estimate` carry a pill. Rows with revision or correction notes feed the
  corrections box automatically.
- Design spec was not available when this was built; layout follows `briefing_session_handoff.md`.
  Reconcile against `market-briefing-design-spec.md` when it is attached.
