# Screen Specs

## Screen 1: Project Hub

### Purpose

A calm command center for many research efforts.

### Layout

```text
+--------------------------------------------------------------------------------------+
| AutoR Studio | Search | New Project | Import Run | Waiting: 3 | Running: 2 | Me      |
+-----------+--------------------------------------------------------------------------+
| Sidebar   | Hero strip: Active work, waiting approvals, latest manuscript, alerts    |
| Projects  +--------------------------------------------------------------------------+
| Inbox     | Project grid / list                                                      |
| Active    | [Card] Sparse MoE Study                                                  |
| Files     | mode: Human | latest run: 20260406_101245 | stage 07 | PDF ready         |
| Versions  | [Card] Agent Recovery Benchmark                                          |
| Settings  | mode: AutoR | stage 05 running | results ready | 2 blockers              |
+-----------+--------------------------------------------------------------------------+
```

### Key components

- project cards
- approval inbox
- quick resume buttons
- run health filters
- recents rail

### Design notes

- use list and board toggles
- keep cards compact and readable
- show manuscript and figure readiness without opening the run

## Screen 2: Run Workspace

### Purpose

The main working environment for steering a single run.

### Layout

```text
+------------------------------------------------------------------------------------------------+
| Project: Sparse MoE Study | Run 20260406_101245 | Human Mode | Save Version | Pause | Share    |
+-------------+------------------------------------------+---------------------+------------------+
| Stage rail  | Main pane                                | Inspector           |                  |
| 01 approved | Stage summary / editor / trace content   | status              |                  |
| 02 approved |                                          | metadata            |                  |
| 03 approved |                                          | artifact links      |                  |
| 04 approved |                                          | refinement actions  |                  |
| 05 approved |                                          | run config          |                  |
| 06 approved |                                          | session ids         |                  |
| 07 review   |                                          |                     |                  |
| 08 pending  |                                          |                     |                  |
+-------------+------------------------------------------+---------------------+------------------+
| Bottom panel: trace | raw logs | compile | notifications | terminal                                |
+------------------------------------------------------------------------------------------------+
```

### Core actions

- approve and continue
- request refinement
- run from this stage
- rollback to this stage
- save version
- open artifacts produced by this stage

### Main tabs

- Summary
- Files
- Artifacts
- Trace
- Writing

## Screen 3: Writing Studio

### Purpose

A manuscript-focused environment combining Overleaf and IDE patterns.

### Layout

```text
+--------------------------------------------------------------------------------------------------+
| Writing Studio | main.tex | method.tex | results.tex | main.pdf | Recompile | Save Milestone     |
+------------------+--------------------------------------+---------------------------------------+
| File tree         | LaTeX source editor                  | PDF preview                           |
| main.tex          |                                      |                                       |
| references.bib    |                                      |                                       |
| sections/         |                                      |                                       |
| tables/           |                                      |                                       |
+------------------+--------------------------------------+---------------------------------------+
| Build log         | Citation verification                | Packaging / submission bundle         |
+--------------------------------------------------------------------------------------------------+
```

### Required interactions

- split source and PDF by default
- jump from PDF to source and back
- compile status badge
- stale preview warning
- build log panel
- citation verification panel
- packaging panel for submission bundle

### Why this matters

The current repo already has:

- `workspace/writing/main.tex`
- `workspace/writing/main.pdf`
- `workspace/artifacts/build_log.txt`
- `workspace/artifacts/citation_verification.json`
- `workspace/artifacts/self_review.json`

The UI should turn those into first-class manuscript workflow objects.

## Screen 4: Version And Trace Review

### Purpose

Help the user understand what changed and recover safely.

### Layout

```text
+-----------------------------------------------------------------------------------------------+
| Versions | Auto checkpoints | Named milestones | Branch points | Compare                      |
+----------------------+--------------------------------+---------------------------------------+
| Version list         | Diff viewer                    | Trace timeline                         |
| Stage 07 approved    | changed files                  | stage started                          |
| Build succeeded      | changed summary text           | tool events                            |
| Saved by human       | changed artifacts              | validation repaired                    |
| Branched from Stage6 | restore actions                | approved                               |
+----------------------+--------------------------------+---------------------------------------+
```

### Key interactions

- label current state
- compare two versions
- restore one version
- branch from one version
- filter trace by stage, file, event type, or actor

## Interaction Flows

## Flow A: Start a new project

1. User clicks `New Project`.
2. User enters title, thesis, and resources.
3. User chooses default mode:
   - Human
   - AutoR
4. App creates a project container and starts the first run.
5. User lands in run workspace.

## Flow B: Resume waiting stage

1. User opens `Waiting For Approval`.
2. User sees stage summary and linked artifacts.
3. User opens the relevant figure, results JSON, and stage trace.
4. User chooses:
   - approve
   - request refinement
   - rollback

## Flow C: Iterate only the manuscript method section

1. User opens `Writing Studio`.
2. User selects `sections/method.tex`.
3. User clicks `Iterate This Section`.
4. Modal shows frozen context:
   - prior approved analysis
   - current figures
   - unchanged sections
5. User confirms.
6. App creates a branch point and runs scoped iteration.

## Flow D: Recover from compile failure

1. Build badge turns red.
2. Writing Studio automatically opens `Build`.
3. The failing file and line are highlighted.
4. User can:
   - ask AutoR to fix
   - edit manually
   - restore previous successful build

## Flow E: Restart from Stage 05 in place

1. User opens the stage rail menu on `05_experimentation`.
2. User clicks `Redo From Here`.
3. The UI shows the exact impact:
   - Stage 05 becomes dirty
   - downstream stages become stale
   - the current run id stays the same
4. User confirms.
5. The backend rolls back state and resumes from Stage 05.

## Flow F: Branch from Stage 06 and explore an alternative story

1. User opens the stage rail menu on `06_analysis`.
2. User clicks `Branch From Here`.
3. The UI shows:
   - preserved upstream stages
   - new branch name
   - new output destination
4. User optionally adds guidance.
5. The backend creates a branch point and starts a new lineage from Stage 06.

## Future Features Worth Planning For

- compare two runs side by side at stage and artifact level
- reusable project templates for benchmarks, reproduction, ablation, and paper polishing
- annotations pinned to stage summaries, figures, or PDF spans
- collaborator review mode with approval ownership
- dataset and experiment registry across projects
- paper submission checklist with venue-specific readiness gates
- prompt library for recurring refinement styles
- “explain this run” executive summary generated from manifest and trace
- shareable public run report with hidden raw internals

## Components That Need Strong Design Early

- stage rail
- version cards
- artifact preview card
- trace event row
- compile status badge
- mode switch
- scoped iteration modal

If these components are coherent, the rest of the interface can evolve without visual drift.
