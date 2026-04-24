# AutoR — GitHub Pages site

Single-file static landing page for the AutoR repo. Drop this folder at the root of the repo (or push its contents to `gh-pages`) and enable GitHub Pages for it.

## Files

- `index.html` — the landing page. Self-contained: inlined CSS, Google Fonts imported, no build step.
- `assets/` — studio screenshots, example figures, paper page thumbnails. Copied from the design system's `assets/`.
- `_config.yml` — disables Jekyll's default theme so `index.html` renders as-is.
- `.nojekyll` — tells GitHub Pages to serve files verbatim (skip the Jekyll build).

## Enabling GitHub Pages

Two paths, pick one:

### Option A — serve from a folder on `main`

1. Commit this `site/` folder to your default branch.
2. On GitHub: **Settings → Pages**.
3. Source: **Deploy from a branch**, branch `main`, folder `/site`.
4. Save. It will be live at `https://jiangyi01.github.io/AutoR/` within a minute.

### Option B — serve from a `gh-pages` branch

1. `git subtree push --prefix site origin gh-pages`
2. Settings → Pages → Source: **Deploy from a branch**, branch `gh-pages`, folder `/ (root)`.

## Editing

The whole page is one HTML file. All CSS lives in `<style>` at the top; there is no JavaScript. Sections are commented with `<!-- ====== NAME -->` headers so they're easy to find.

## Local preview

Just `open site/index.html` — it works straight from the filesystem. Or serve it:

```
cd site && python3 -m http.server 8080
```
