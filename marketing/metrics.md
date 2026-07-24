# Metrics — what to track and how (free tools only)

Wire up the ones that need setup *before* launch (traffic Action, GoatCounter),
so you don't lose the launch-day data. The rest you can read on demand.

## GitHub stars

- **Tool:** star-history.com — free, generates a stars-over-time chart from the
  repo name; embeddable in the README.
- **How:** just visit https://star-history.com/#alex-roc/zotero-agent&Date. No
  setup. Optionally embed the SVG in the README.
- **Watch for:** the launch-day spike and, more tellingly, whether stars keep
  trickling in afterward (sustained interest vs. one-day blip).

## Repo traffic (views / clones / referrers)

- **Tool:** GitHub's built-in **Insights → Traffic** — but native data **expires
  after 14 days** and isn't retained. Launch traffic will be gone before you can
  analyze it.
- **Fix (set up before launch):** a scheduled **GitHub Action** that hits the
  traffic API (`/repos/{owner}/{repo}/traffic/views` and `/clones`) daily and
  commits the JSON/CSV to a `metrics/` branch or a stats repo, so history
  persists. Search for the community action `sangonzal/repository-traffic-action`
  (or equivalent) as a starting point; it needs a token with repo scope.
- **Watch for:** top referrers — tells you which channel (HN, Reddit, a specific
  awesome-list) actually drove people.

## PyPI downloads

- **Tools:** pepy.tech (https://pepy.tech/project/zotero-agent — total + chart)
  and pypistats (`pipx run pypistats recent zotero-agent`, or pypistats.org).
- **How:** no setup; both read PyPI's public download stats (BigQuery-backed).
  Data lags ~a day or two.
- **Watch for:** installs are the truer adoption signal than stars — someone who
  `uv tool install`s actually tried it.

## XPI (plugin) installs

- **Tool:** GitHub **Release asset `download_count`** — every release asset
  exposes a download count via the API
  (`/repos/alex-roc/zotero-agent/releases` → each asset's `download_count`).
- **Key setup:** ship the `.xpi` as a **Release asset** and have `updates.json`
  point `update_link` at the Releases download URL (it already does — see
  `updates.json`). That way both fresh installs and auto-updates pull from
  Releases, so the download count is a real proxy for plugin installs + updates.
- **How to read:** `gh api repos/alex-roc/zotero-agent/releases --jq '.[].assets[] | {name, download_count}'`.
- **Caveat:** counts include re-downloads and auto-update checks; treat as a
  trend, not an exact user count.

## Site / docs traffic

- **Tool:** **GoatCounter** (https://goatcounter.com) — free for
  non-commercial/open-source, **cookieless** (no consent banner needed), and it's
  a single `<script>` tag.
- **How:** create a GoatCounter site, drop the one script tag into the Astro
  Starlight site's `<head>` (or a layout partial). Done.
- **Watch for:** which docs pages people land on and where they come from —
  install page vs. security page tells you what the audience cares about.

## MCP directory usage

- **Where:** each directory has its own counters — Glama, Smithery, PulseMCP show
  views / installs / rank on the listing page.
- **How:** no automation; check each listing periodically (fold into the monthly
  review). PulseMCP and Glama trend charts are the most useful.

---

## Monthly review

Once a month, pull the above into a short note (a dated section in a running file
is enough) and answer three questions:

1. **Which channel is still sending people?** (traffic referrers + directory rank)
2. **Are installs/plugin-downloads growing, flat, or spiking-then-dying?**
3. **What did people ask for / complain about?** (issues, comments, forum replies)
   — feed that back into the roadmap and, per the compound-engineering habit,
   into the skill/docs.

Keep it lightweight — the point is direction, not a dashboard.
