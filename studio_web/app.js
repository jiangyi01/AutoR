const state = {
  projects: [],
  runIds: [],
  selectedProjectId: null,
  selectedRunId: null,
  selectedStageSlug: null,
  runSummary: null,
  artifactIndex: null,
  fileTree: null,
  contentMode: "empty",
};

const elements = {
  connectionStatus: document.getElementById("connection-status"),
  reloadButton: document.getElementById("reload-button"),
  projectCount: document.getElementById("project-count"),
  runCount: document.getElementById("run-count"),
  projectForm: document.getElementById("project-form"),
  projectTitle: document.getElementById("project-title"),
  projectThesis: document.getElementById("project-thesis"),
  projectMode: document.getElementById("project-mode"),
  projectsList: document.getElementById("projects-list"),
  runsList: document.getElementById("runs-list"),
  attachRunButton: document.getElementById("attach-run-button"),
  activeProjectLabel: document.getElementById("active-project-label"),
  stageRail: document.getElementById("stage-rail"),
  runStatus: document.getElementById("run-status"),
  runTitle: document.getElementById("run-title"),
  documentTitle: document.getElementById("document-title"),
  documentMeta: document.getElementById("document-meta"),
  stageDocument: document.getElementById("stage-document"),
  artifactTotal: document.getElementById("artifact-total"),
  runSummary: document.getElementById("run-summary"),
  artifactSummary: document.getElementById("artifact-summary"),
  fileTree: document.getElementById("file-tree"),
  iterationForm: document.getElementById("iteration-form"),
  iterationMode: document.getElementById("iteration-mode"),
  iterationStage: document.getElementById("iteration-stage"),
  iterationScopeType: document.getElementById("iteration-scope-type"),
  iterationScopeValue: document.getElementById("iteration-scope-value"),
  iterationPlan: document.getElementById("iteration-plan"),
};

elements.reloadButton.addEventListener("click", () => {
  void bootstrap();
});

elements.projectForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void createProject();
});

elements.attachRunButton.addEventListener("click", () => {
  void attachSelectedRun();
});

elements.iterationForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void planIteration();
});

void bootstrap();

async function bootstrap() {
  setConnection("Loading");
  const [projectsPayload, runsPayload] = await Promise.all([
    api("/api/projects/overview"),
    api("/api/runs"),
  ]);
  state.projects = projectsPayload.projects || [];
  state.runIds = runsPayload.run_ids || [];

  if (!state.selectedProjectId && state.projects.length) {
    state.selectedProjectId = state.projects[0].project_id;
  }
  if (state.selectedProjectId && !state.projects.some((project) => project.project_id === state.selectedProjectId)) {
    state.selectedProjectId = state.projects[0]?.project_id || null;
  }

  const preferredRunId =
    state.projects.find((project) => project.project_id === state.selectedProjectId)?.active_run_id ||
    state.selectedRunId ||
    state.runIds.at(-1) ||
    null;

  renderProjects();
  renderRuns();

  if (preferredRunId) {
    await loadRun(preferredRunId);
    renderProjects();
    renderRuns();
  } else {
    renderEmptyWorkspace("No runs found under the configured runs directory.");
  }

  setConnection("Connected");
}

async function createProject() {
  const payload = {
    title: elements.projectTitle.value.trim(),
    thesis: elements.projectThesis.value.trim(),
    default_mode: elements.projectMode.value,
  };
  if (!payload.title || !payload.thesis) {
    return;
  }
  const created = await api("/api/projects", { method: "POST", body: payload });
  state.selectedProjectId = created.project_id;
  elements.projectForm.reset();
  elements.projectMode.value = "human";
  await bootstrap();
}

async function attachSelectedRun() {
  if (!state.selectedProjectId || !state.selectedRunId) {
    elements.iterationPlan.textContent = "Select both a project and a run before attaching.";
    elements.iterationPlan.classList.remove("empty-state");
    return;
  }
  await api(`/api/projects/${state.selectedProjectId}/runs`, {
    method: "POST",
    body: { run_id: state.selectedRunId, make_active: true },
  });
  await bootstrap();
}

async function loadRun(runId) {
  state.selectedRunId = runId;
  const [summary, artifacts, fileTree] = await Promise.all([
    api(`/api/runs/${runId}`),
    api(`/api/runs/${runId}/artifacts`),
    api(`/api/runs/${runId}/files/tree?root=workspace&depth=3`),
  ]);
  state.runSummary = summary;
  state.artifactIndex = artifacts;
  state.fileTree = fileTree;

  if (!state.selectedStageSlug || !summary.stages.some((stage) => stage.slug === state.selectedStageSlug)) {
    state.selectedStageSlug = summary.current_stage_slug || summary.stages.at(-1)?.slug || null;
  }

  renderSummary();
  renderStages();
  renderArtifacts();
  renderFileTree();
  renderIterationForm();

  if (state.selectedStageSlug) {
    await loadStageDocument(state.selectedStageSlug);
  }
}

async function loadStageDocument(stageSlug) {
  if (!state.selectedRunId) {
    return;
  }
  state.selectedStageSlug = stageSlug;
  state.contentMode = "stage";
  renderStages();
  const payload = await api(`/api/runs/${state.selectedRunId}/stages/${stageSlug}`);
  const stage = state.runSummary.stages.find((item) => item.slug === stageSlug);
  elements.documentTitle.textContent = stage ? stage.title : stageSlug;
  elements.documentMeta.textContent = `${stage?.status || "unknown"} · attempts ${stage?.attempt_count || 0}`;
  elements.stageDocument.textContent = payload.markdown;
  elements.stageDocument.classList.remove("empty-state");
}

async function loadFileContent(relativePath) {
  if (!state.selectedRunId) {
    return;
  }
  state.contentMode = "file";
  const payload = await api(
    `/api/runs/${state.selectedRunId}/files/content?path=${encodeURIComponent(relativePath)}`
  );
  elements.documentTitle.textContent = payload.relative_path;
  elements.documentMeta.textContent = `${payload.encoding} · ${payload.size_bytes} bytes`;
  elements.stageDocument.textContent = payload.content || "(binary file preview unavailable)";
  elements.stageDocument.classList.toggle("empty-state", !payload.content);
}

async function planIteration() {
  if (!state.selectedRunId) {
    elements.iterationPlan.textContent = "Select a run before planning an iteration.";
    elements.iterationPlan.classList.remove("empty-state");
    return;
  }
  const payload = {
    base_stage_slug: elements.iterationStage.value,
    scope_type: elements.iterationScopeType.value,
    scope_value: elements.iterationScopeValue.value.trim() || elements.iterationStage.value,
    mode: elements.iterationMode.value,
  };
  const plan = await api(`/api/runs/${state.selectedRunId}/iterations/plan`, {
    method: "POST",
    body: payload,
  });
  elements.iterationPlan.textContent = [
    plan.summary,
    "",
    `Preserved: ${plan.preserved_stages.join(", ") || "none"}`,
    `Affected: ${plan.affected_stages.join(", ") || "none"}`,
    `Stale: ${plan.stale_stages.join(", ") || "none"}`,
    `Branch run: ${plan.branch_run_id || "current run"}`,
  ].join("\n");
  elements.iterationPlan.classList.remove("empty-state");
}

function renderProjects() {
  elements.projectCount.textContent = String(state.projects.length);
  elements.projectsList.innerHTML = "";
  for (const project of state.projects) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `project-card${project.project_id === state.selectedProjectId ? " is-active" : ""}`;
    card.innerHTML = `
      <div class="project-card-header">
        <span class="project-card-title">${escapeHtml(project.title)}</span>
        <span class="mode-chip">${escapeHtml(project.default_mode)}</span>
      </div>
      <div class="project-card-thesis">${escapeHtml(project.thesis)}</div>
      <div class="run-card-meta">active run: ${escapeHtml(project.active_run_id || "none")}</div>
      <div class="run-card-meta">status: ${escapeHtml(project.latest_run_status || "unknown")}</div>
      <div class="run-card-meta">latest stage: ${escapeHtml(project.latest_completed_stage_slug || "none")}</div>
      <div class="tag-row">${project.tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
    `;
    card.addEventListener("click", () => {
      state.selectedProjectId = project.project_id;
      renderProjects();
      if (project.active_run_id) {
        void loadRun(project.active_run_id);
      }
    });
    elements.projectsList.appendChild(card);
  }
}

function renderRuns() {
  elements.runCount.textContent = String(state.runIds.length);
  elements.runsList.innerHTML = "";
  for (const runId of state.runIds) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `run-card${runId === state.selectedRunId ? " is-active" : ""}`;
    card.innerHTML = `
      <div class="run-card-title">${escapeHtml(runId)}</div>
      <div class="run-card-meta">Open run workspace</div>
    `;
    card.addEventListener("click", () => {
      void loadRun(runId);
    });
    elements.runsList.appendChild(card);
  }
}

function renderSummary() {
  const summary = state.runSummary;
  if (!summary) {
    return;
  }
  const project = state.projects.find((item) => item.project_id === state.selectedProjectId);
  elements.activeProjectLabel.textContent = project ? project.title : "No project selected";
  elements.runTitle.textContent = summary.run_id;
  elements.runStatus.textContent = summary.run_status;
  elements.runSummary.innerHTML = "";
  const rows = [
    ["Model", summary.model],
    ["Venue", summary.venue],
    ["Status", summary.run_status],
    ["Updated", summary.updated_at],
    ["Current", summary.current_stage_slug || "none"],
  ];
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    elements.runSummary.append(dt, dd);
  }
}

function renderStages() {
  elements.stageRail.innerHTML = "";
  const stages = state.runSummary?.stages || [];
  for (const stage of stages) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `stage-item${stage.slug === state.selectedStageSlug && state.contentMode === "stage" ? " is-active" : ""}`;
    item.innerHTML = `
      <div class="stage-title">${escapeHtml(stage.title)}</div>
      <div class="stage-meta">updated ${escapeHtml(stage.updated_at || "unknown")}</div>
      <span class="stage-status status-${escapeHtml(stage.status)}">${escapeHtml(stage.status)}</span>
    `;
    item.addEventListener("click", () => {
      void loadStageDocument(stage.slug);
    });
    elements.stageRail.appendChild(item);
  }
}

function renderArtifacts() {
  const counts = state.artifactIndex?.counts_by_category || {};
  const total = state.artifactIndex?.artifact_count || 0;
  elements.artifactTotal.textContent = `${total} artifacts`;
  elements.artifactSummary.innerHTML = "";
  for (const [label, count] of Object.entries(counts)) {
    const item = document.createElement("li");
    item.textContent = `${label}: ${count}`;
    elements.artifactSummary.appendChild(item);
  }
}

function renderFileTree() {
  elements.fileTree.innerHTML = "";
  if (!state.fileTree) {
    return;
  }
  elements.fileTree.appendChild(renderTreeNode(state.fileTree));
}

function renderTreeNode(node) {
  const wrapper = document.createElement("div");
  wrapper.className = "tree-node";
  const label = document.createElement("button");
  label.type = "button";
  label.className = "tree-label";
  label.textContent = `${node.node_type === "directory" ? "▾" : "•"} ${node.name}`;
  if (node.node_type === "file") {
    label.addEventListener("click", () => {
      void loadFileContent(node.rel_path);
    });
  } else {
    label.disabled = true;
  }
  wrapper.appendChild(label);
  if (node.children?.length) {
    const children = document.createElement("div");
    children.className = "tree-children";
    for (const child of node.children) {
      children.appendChild(renderTreeNode(child));
    }
    wrapper.appendChild(children);
  }
  return wrapper;
}

function renderIterationForm() {
  elements.iterationStage.innerHTML = "";
  for (const stage of state.runSummary?.stages || []) {
    const option = document.createElement("option");
    option.value = stage.slug;
    option.textContent = stage.title;
    if (stage.slug === state.selectedStageSlug) {
      option.selected = true;
    }
    elements.iterationStage.appendChild(option);
  }
  elements.iterationScopeValue.value = state.selectedStageSlug || "";
}

function renderEmptyWorkspace(message) {
  elements.activeProjectLabel.textContent = "No project selected";
  elements.runTitle.textContent = "No run selected";
  elements.documentTitle.textContent = "Workspace Preview";
  elements.documentMeta.textContent = "";
  elements.stageDocument.textContent = message;
  elements.stageDocument.classList.add("empty-state");
  elements.stageRail.innerHTML = "";
  elements.runSummary.innerHTML = "";
  elements.artifactSummary.innerHTML = "";
  elements.fileTree.innerHTML = "";
}

function setConnection(text) {
  elements.connectionStatus.textContent = text;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
