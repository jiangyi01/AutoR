# Gemini Prototype Prompts

These prompts are designed to generate concept screenshots for the UI direction above.

## Usage Notes

- generate these as static product mockups, not marketing posters
- prefer realistic software screenshots
- avoid fantasy glassmorphism, neon gradients, floating holograms, or sci-fi control rooms
- keep the visual language serious, calm, and research-oriented
- favor readability over stylistic novelty

## Global Style Prefix

Use this prefix before each prompt:

```text
Create a realistic desktop product UI mockup for a research operating system called "AutoR Studio". The product is for serious AI-assisted research and paper writing. Style: calm, premium, practical, understated, warm paper background, cool gray panels, crisp typography, no purple bias, no dark mode, no flashy gradients, no empty marketing whitespace. Use IBM Plex Sans or similar for UI labels, Source Serif style for reading panes, JetBrains Mono style for code surfaces. Make it look like a polished shipping product screenshot, not a wireframe and not a landing page.
```

## Prompt 1: Project Hub

```text
Create a realistic desktop product UI mockup for a research operating system called "AutoR Studio". The product is for serious AI-assisted research and paper writing. Style: calm, premium, practical, understated, warm paper background, cool gray panels, crisp typography, no purple bias, no dark mode, no flashy gradients, no empty marketing whitespace. Use IBM Plex Sans or similar for UI labels, Source Serif style for reading panes, JetBrains Mono style for code surfaces. Make it look like a polished shipping product screenshot, not a wireframe and not a landing page.

Screen: multi-project dashboard.

Show a left sidebar with Projects, Inbox, Active Runs, Files, Versions, Settings.
Show a top bar with project search, new project button, waiting approvals count, active runs count, and user avatar.
In the main area, show a clean hero strip summarizing 3 urgent research items, then a grid of project cards.
Each project card should display:
- project title
- one-line thesis
- mode badge: Human or AutoR
- latest run id
- latest completed stage
- small badges for PDF, figures, results, blocked
- last updated timestamp

The overall feeling should combine Linear's calm project clarity with a research workspace. Use muted teal accents, brass warning badges, and light paper tones. Include tiny charts or status bars sparingly. Make the screen information-dense but elegant. Desktop web app screenshot, 16:10 ratio.
```

## Prompt 2: Run Workspace

```text
Create a realistic desktop product UI mockup for a research operating system called "AutoR Studio". The product is for serious AI-assisted research and paper writing. Style: calm, premium, practical, understated, warm paper background, cool gray panels, crisp typography, no purple bias, no dark mode, no flashy gradients, no empty marketing whitespace. Use IBM Plex Sans or similar for UI labels, Source Serif style for reading panes, JetBrains Mono style for code surfaces. Make it look like a polished shipping product screenshot, not a wireframe and not a landing page.

Screen: single run workspace.

Show a permanent vertical stage rail on the left with stages 01 through 08, using clear states like approved, running, needs review, pending, stale. The center should show a detailed stage summary and artifact viewer. Add a secondary pane showing trace events, tool calls, and recent logs. Add a right inspector with status, metadata, run config, session ids, refinement actions, and save version button.

The top bar should show project name, run id, current mode switch between Human and AutoR, pause, save version, and share buttons.

This should feel like VS Code meets a research control room, but much calmer and more editorial. Include subtle file references, evidence cards, small charts, and approval controls. Prioritize readability and professional density. Desktop app screenshot, 16:10 ratio.
```

## Prompt 3: Writing Studio

```text
Create a realistic desktop product UI mockup for a research operating system called "AutoR Studio". The product is for serious AI-assisted research and paper writing. Style: calm, premium, practical, understated, warm paper background, cool gray panels, crisp typography, no purple bias, no dark mode, no flashy gradients, no empty marketing whitespace. Use IBM Plex Sans or similar for UI labels, Source Serif style for reading panes, JetBrains Mono style for code surfaces. Make it look like a polished shipping product screenshot, not a wireframe and not a landing page.

Screen: manuscript writing studio inspired by Overleaf and VS Code.

Use a three-column layout:
- left file tree with main.tex, references.bib, sections, tables, figures
- center LaTeX source editor with tabs for method.tex and results.tex
- right compiled PDF preview

At the bottom, show build log, citation verification, and packaging tabs.
In the top bar, show Recompile, Save Milestone, Build Passed, and Export Bundle actions.

The PDF preview should feel real, with a visible academic paper page. The source editor should show LaTeX. The build panel should show a clean compile log. Add small status badges for citation check and self-review. Make the layout practical and balanced, not flashy. Desktop web app screenshot, 16:10 ratio.
```

## Prompt 4: Versions And Trace

```text
Create a realistic desktop product UI mockup for a research operating system called "AutoR Studio". The product is for serious AI-assisted research and paper writing. Style: calm, premium, practical, understated, warm paper background, cool gray panels, crisp typography, no purple bias, no dark mode, no flashy gradients, no empty marketing whitespace. Use IBM Plex Sans or similar for UI labels, Source Serif style for reading panes, JetBrains Mono style for code surfaces. Make it look like a polished shipping product screenshot, not a wireframe and not a landing page.

Screen: version history and execution trace review.

Show a left column with saved versions, named milestones, branch points, and auto checkpoints. Show a central diff viewer with changed files, changed stage summary text, and changed artifacts. Show a right column with a vertical trace timeline containing stage started, validation failed, repair applied, approved, build passed events.

The screen should make restore, compare, and branch actions obvious without looking scary. Use compact cards, timestamp rows, and tasteful status colors. Think of Overleaf history plus Linear timeline plus IDE diff view. Desktop product screenshot, 16:10 ratio.
```

## Negative Prompt Guidance

When using an image model that supports negative guidance, avoid:

```text
dark mode, purple neon, fantasy HUD, cyberpunk, 3D floating holograms, mobile app UI, landing page hero image, huge empty whitespace, oversized illustrations, cartoon mascot, unrealistic depth blur, glossy enterprise dashboard, gaming interface
```

## Current Suggested Models

Validated locally on April 9, 2026:

- `models/gemini-3.1-flash-image-preview`
- `models/gemini-2.5-flash-image`
- `models/imagen-4.0-fast-generate-001`

## Suggested Generation Order

1. Project Hub
2. Run Workspace
3. Writing Studio
4. Versions And Trace

That sequence is useful because it establishes the broad product language before generating deeper workflow screens.
