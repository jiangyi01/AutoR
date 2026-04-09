# Development Plan

## 1. Objective

This document turns the UI design into an implementation plan.

It answers three questions:

1. How should frontend and backend be developed in waves?
2. What should be built first versus deferred?
3. How can the product support iterative updates from any step without creating state chaos?

## 2. Development Principle

Build the UI as a thin, useful layer over the existing AutoR workflow before attempting large internal refactors.

That means:

- do not rebuild the research engine first
- do not invent new hidden workflow state
- expose existing run data to the UI quickly
- only add new metadata where the current repo model is missing an obvious concept

## 3. Delivery Waves

## Wave 0: Service Adapter Layer

### Goal

Make the current Python workflow readable and controllable from a web UI.

### Backend work

- create FastAPI app
- add run summary endpoint
- add file tree endpoint
- add artifact index endpoint
- add trace stream endpoint
- add create, resume, redo, and rollback endpoints

### Frontend work

- basic app shell
- project list placeholder
- run workspace placeholder
- API client
- event stream client

### Acceptance bar

- UI can open an existing run
- UI can show stages, files, and artifacts
- UI can resume or rollback a run

## Wave 1: Project Hub And Run Workspace

### Goal

Make AutoR usable as a real multi-project dashboard.

### Backend work

- add project index storage
- map projects to runs
- expose waiting-for-approval queries
- expose active-run summaries

### Frontend work

- build Project Hub
- build run overview
- build stage rail
- build inspector panel
- build active and waiting filters

### Acceptance bar

- user can manage multiple projects
- user can find the latest run quickly
- user can see which stage needs attention

## Wave 2: Stage Actions And Trace

### Goal

Make the human-in-the-loop control loop practical from the UI.

### Backend work

- approve endpoint
- refine endpoint with free-form feedback
- normalized trace event schema
- live status updates

### Frontend work

- approval actions
- refinement composer
- trace timeline
- event filtering
- stage diff previews

### Acceptance bar

- user can approve, refine, or rollback from UI
- user can watch live execution state without opening terminal logs

## Wave 3: Writing Studio

### Goal

Deliver the highest-value manuscript workflow.

### Backend work

- compile endpoint
- build status endpoint
- build log endpoint
- PDF preview endpoint
- citation verification and package metadata endpoints

### Frontend work

- file tree for writing folder
- Monaco editor
- PDF preview with PDF.js
- compile button and build status
- build log and citation panels

### Acceptance bar

- user can edit LaTeX, compile, inspect PDF, and see failures in one place

## Wave 4: Versions And Iteration

### Goal

Support safe experimentation from any step.

### Backend work

- named milestone storage
- branch point creation
- version diff endpoint
- restore endpoint
- scoped iteration endpoint

### Frontend work

- version list
- compare view
- restore actions
- scoped iteration modal
- branch lineage display

### Acceptance bar

- user can save milestones
- user can branch safely
- user can rerun from a specific stage without losing context accidentally

## Wave 5: Polish And Reliability

### Goal

Make the product feel robust for daily use.

### Backend work

- worker supervision
- retry policies
- better event compaction
- performance tuning for large run folders

### Frontend work

- keyboard shortcuts
- better empty states
- better loading states
- accessibility pass
- small quality-of-life touches

## 4. Frontend And Backend Ownership Split

### Frontend should own

- navigation
- layout state
- selected project and run
- pane state
- editor state
- optimistic interaction state

### Backend should own

- run lifecycle
- stage transitions
- filesystem reads and writes
- trace normalization
- compile execution
- version persistence

### Shared contracts

- status enums
- stage identifiers
- event payloads
- version metadata schema

## 5. Recommended Implementation Order Inside Each Wave

The order should always be:

1. backend schema
2. backend endpoint
3. frontend read view
4. frontend action
5. event handling
6. reload and recovery validation

This prevents flashy screens with weak runtime behavior.

## 6. The Core Iteration Model

The product needs one clean mental model for “iterate from here”.

### Iteration object

Every iteration request should declare:

- target run
- target step
- target scope
- iteration mode
- freeze rules
- output destination

### Suggested request shape

```json
{
  "run_id": "20260406_101245",
  "base_stage_slug": "07_writing",
  "scope_type": "file",
  "scope_value": "workspace/writing/sections/method.tex",
  "mode": "branch",
  "freeze_upstream": true,
  "invalidate_downstream": false,
  "user_feedback": "Tighten the method narrative and clarify the operator loop."
}
```

## 7. Iteration Modes

### Mode 1: Refine current stage

Use when:

- the stage is already active
- the user wants another attempt

Effects:

- same run
- same stage
- increment attempt count

### Mode 2: Redo from selected stage

Use when:

- the user wants to rerun from stage N
- downstream state should no longer be trusted

Effects:

- same run
- target stage becomes dirty
- downstream stages become stale

### Mode 3: Branch from selected stage

Use when:

- the user wants an alternative path
- the approved baseline must remain intact

Effects:

- new run or sub-run lineage
- upstream context copied or linked
- downstream recomputed in branch only

### Mode 4: Scoped writing iteration

Use when:

- the user wants to update only a manuscript section or a figure explanation

Effects:

- branch point or scoped patch workflow
- unchanged sections remain frozen
- rebuild writing outputs

## 8. Decision Logic For “Start From Step X”

The UI should ask one clarifying question only:

**Do you want to update the current run, or create a new branch?**

After that, the logic is deterministic.

### If update current run

- if target is current stage, continue in place
- if target is earlier stage, rollback and redo
- mark downstream stale

### If create new branch

- save a checkpoint
- record branch lineage
- continue from target stage in the new branch

## 9. Safe Iteration Rules

Before starting any iteration job, the backend should:

1. create an auto checkpoint
2. validate the target scope exists
3. calculate what becomes stale
4. show the user a summary of affected files and stages
5. record the iteration request in metadata

Without these steps, the UI will feel unpredictable.

## 10. Partial Iteration Rules By Scope

| Scope | Example | Frozen | Recomputed |
| --- | --- | --- | --- |
| stage | `06_analysis` | stages 01-05 | 06 onward |
| file | `sections/method.tex` | upstream stage state | selected file plus dependent writing build |
| subtree | `workspace/figures/` | run context | selected subtree and manifests |
| manuscript | `07_writing` | 01-06 | writing and dissemination |

## 11. Reload And Recovery Requirements

Every wave must support hard refresh recovery.

### Required tests

- refresh during active run
- refresh during compile
- refresh during waiting-for-approval state
- refresh after rollback
- refresh after branch creation

If the screen cannot reconstruct cleanly after reload, the wave is incomplete.

## 12. Suggested Milestones

### Milestone A

Read-only product shell.

Includes:

- projects
- runs
- stage rail
- files
- artifact browser

### Milestone B

Interactive run control.

Includes:

- approve
- refine
- rollback
- live trace

### Milestone C

Writing-first workflow.

Includes:

- source editor
- PDF preview
- compile log
- packaging

### Milestone D

Versioning and branching.

Includes:

- checkpoints
- named milestones
- compare
- restore
- branch from stage

## 13. Suggested Team Split

If two people are building this in parallel:

### Track 1

- backend service layer
- run orchestration endpoints
- event streaming
- version metadata

### Track 2

- app shell
- project hub
- run workspace
- writing studio

They can converge on shared schemas and event contracts.

## 14. Minimum Test Matrix

### Backend

- create run
- resume run
- rollback from stage
- approve stage
- refine stage
- compile writing
- create version
- restore version
- branch from stage

### Frontend

- open project
- open run
- switch tabs
- receive live event
- reload during active state
- open PDF preview
- compare versions

## 15. Recommended First Build Target

If only one thin but useful slice is built first, it should be:

**Project Hub + Run Workspace + Stage actions**

Reason:

- it exposes the core AutoR value immediately
- it uses the current repository model directly
- it avoids getting blocked on the full writing studio too early

After that, the writing studio becomes the next highest-value slice.
