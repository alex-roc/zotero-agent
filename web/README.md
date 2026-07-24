# zotero-agent documentation site

The documentation website for [`zotero-agent`](https://github.com/alex-roc/zotero-agent),
built with [Astro](https://astro.build) + [Starlight](https://starlight.astro.build)
and deployed to GitHub Pages at `https://alex-roc.github.io/zotero-agent`.

## Develop

Uses **pnpm** (via corepack). Do not use npm or yarn.

```bash
cd web
pnpm install
pnpm dev        # local dev server
pnpm build      # production build -> web/dist
pnpm preview     # preview the production build
```

## Structure

- `astro.config.mjs` — site config. `site` + `base` are set for the GitHub Pages
  project subpath (`/zotero-agent`); the sidebar lives here.
- `src/content.config.ts` — Starlight content collection.
- `src/content/docs/**` — all pages (Markdown/MDX). `index.mdx` is the splash
  landing page.
- Search is Starlight's built-in **Pagefind** (self-hosted, CSP-safe — no
  external service).

## Internal links

Because the site is served under the `/zotero-agent` base path, cross-page links
in content and the landing hero are written with the full base prefix
(`/zotero-agent/...`). Sidebar links in `astro.config.mjs` are written **without**
the base — Starlight prepends it automatically.

## Deploy

Pushing to `main` with changes under `web/**` triggers
`.github/workflows/pages.yml`, which builds with pnpm and deploys `web/dist` to
GitHub Pages. It can also be run manually via workflow dispatch. Enable Pages in
the repo settings with **Source: GitHub Actions**.

## Build status

`pnpm install` and `pnpm build` were run and verified to succeed during
scaffolding.
