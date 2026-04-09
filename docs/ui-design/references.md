# Reference Audit

These references were used to shape the initial UI direction.

## 1. VS Code

**Source**

- https://code.visualstudio.com/docs/getstarted/userinterface

**Why it matters**

- strong file-and-folder mental model
- permanent side bar and utility panel grammar
- flexible split editor layout
- comfortable density for expert users

**Takeaways for AutoR**

- keep a permanent left navigation rail
- allow multiple panes without modal churn
- use a bottom utility panel for logs, compile output, and raw trace
- keep file tree behavior conventional

## 2. Overleaf

**Sources**

- https://docs.overleaf.com/navigating-in-the-editor/working-with-the-pdf-viewer
- https://docs.overleaf.com/navigating-in-the-editor/working-with-the-pdf-viewer/moving-between-the-editor-and-pdf
- https://docs.overleaf.com/writing-and-editing/history-and-versioning

**Why it matters**

- proven source-and-PDF split workflow
- jump between source and rendered output
- practical version history and restore model

**Takeaways for AutoR**

- writing must get a dedicated source-plus-preview studio
- compile state should always be visible
- version history needs labels, compare, and restore
- manuscript iteration should be one click away from viewing the PDF

## 3. Linear

**Sources**

- https://linear.app/features
- https://linear.app/docs/projects

**Why it matters**

- clean project overview patterns
- strong status communication without visual overload
- powerful custom views over structured work items

**Takeaways for AutoR**

- the top-level object should be a project, not just a run directory
- users need list, board, and timeline views for research work
- progress, ownership, and block states should be visible on every project card

## 4. Cursor

**Source**

- https://docs.cursor.com/background-agents

**Why it matters**

- clear mental model for asynchronous agents
- users can inspect status, follow up, or take over

**Takeaways for AutoR**

- Human and AutoR modes should be explicit
- async agent work should stay inspectable
- “take over” and “send follow-up” are better metaphors than burying everything inside one chat

## 5. NotebookLM And Gemini Notebooks

**Sources**

- https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-discover-sources/
- https://blog.google/innovation-and-ai/products/gemini-app/notebooks-gemini-notebooklm/
- https://blog.google/innovation-and-ai/models-and-research/google-labs/video-overviews-nano-banana/

**Why it matters**

- source-grounded workflows
- notebook container for long-running projects
- multi-format outputs, including multimedia explainers

**Takeaways for AutoR**

- a project should feel like a durable notebook with files, context, and instructions
- source panels and evidence panels should be first-class
- prototype generation can use Gemini image workflows without drifting into generic “AI art”

## Reference Summary

The combined lesson is straightforward:

- use VS Code for file, pane, and panel grammar
- use Overleaf for writing and restore flows
- use Linear for project-level clarity
- use Cursor for agent mode control
- use NotebookLM for source-grounded project organization

AutoR should not imitate any one of these products directly. It should combine their strongest interaction patterns around AutoR's actual run-and-artifact model.
