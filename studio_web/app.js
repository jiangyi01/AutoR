const PAGE_IDS = ["overview", "review", "files", "paper"];

const state = {
  page: readHashPage(),
  projects: [],
  runIds: [],
  selectedProjectId: null,
  selectedRunId: null,
  selectedStageSlug: null,
  selectedFilePath: null,
  runSummary: null,
  artifactIndex: null,
  fileTree: null,
  stageDocument: "",
  filePreview: null,
  paperPreview: null,
  iterationPlan: null,
};

const elements = {
  connectionStatus: document.getElementById("connection-status"),
  reloadButton: document.getElementById("reload-button"),
  pageButtons: [...document.querySelectorAll(".page-link")],
  pages: Object.fromEntries(PAGE_IDS.map((page) => [page, document.getElementById(`page-${page}`)])),
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
  runTitle: document.getElementById("run-title"),
  runGoal: document.getElementById("run-goal"),
  runStatus: document.getElementById("run-status"),
  projectMeta: document.getElementById("project-meta"),
  projectBrief: document.getElementById("project-brief"),
  stageCount: document.getElementById("stage-count"),
  stageRail: document.getElementById("stage-rail"),
  overviewStageTitle: document.getElementById("overview-stage-title"),
  overviewStageMeta: document.getElementById("overview-stage-meta"),
  overviewStageSummary: document.getElementById("overview-stage-summary"),
  runSummary: document.getElementById("run-summary"),
  artifactTotal: document.getElementById("artifact-total"),
  artifactSummary: document.getElementById("artifact-summary"),
  reviewStageLabel: document.getElementById("review-stage-label"),
  documentTitle: document.getElementById("document-title"),
  documentMeta: document.getElementById("document-meta"),
  stageDocument: document.getElementById("stage-document"),
  iterationForm: document.getElementById("iteration-form"),
  iterationMode: document.getElementById("iteration-mode"),
  iterationStage: document.getElementById("iteration-stage"),
  iterationScopeType: document.getElementById("iteration-scope-type"),
  iterationScopeValue: document.getElementById("iteration-scope-value"),
  iterationFeedback: document.getElementById("iteration-feedback"),
  reviewerActions: document.getElementById("reviewer-actions"),
  iterationPlan: document.getElementById("iteration-plan"),
  fileTree: document.getElementById("file-tree"),
  filePreviewTitle: document.getElementById("file-preview-title"),
  filePreviewMeta: document.getElementById("file-preview-meta"),
  filePreview: document.getElementById("file-preview"),
  paperStatus: document.getElementById("paper-status"),
  paperFrameContainer: document.getElementById("paper-frame-container"),
  paperMeta: document.getElementById("paper-meta"),
  paperSummary: document.getElementById("paper-summary"),
  paperSections: document.getElementById("paper-sections"),
  paperTexPreview: document.getElementById("paper-tex-preview"),
  paperBuildLog: document.getElementById("paper-build-log"),
};

elements.reloadButton.addEventListener("click", () => {
  void safeAction(bootstrap());
});

elements.projectForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void safeAction(createProject());
});

elements.attachRunButton.addEventListener("click", () => {
  void safeAction(attachSelectedRun());
});

elements.iterationForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void safeAction(planIteration());
});

for (const button of elements.pageButtons) {
  button.addEventListener("click", () => {
    setPage(button.dataset.page);
  });
}

window.addEventListener("hashchange", () => {
  const page = readHashPage();
  if (page !== state.page) {
    state.page = page;
    renderPageNav();
  }
});

renderPageNav();
void safeAction(bootstrap());

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
  } else {
    clearRunState();
    renderWorkspaceSkeleton("No runs found under the configured runs directory.");
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
    renderIterationPlaceholder("Select both a project and a run before attaching.");
    return;
  }
  await api(`/api/projects/${state.selectedProjectId}/runs`, {
    method: "POST",
    body: { run_id: state.selectedRunId, make_active: true },
  });
  await bootstrap();
}

async function loadRun(runId) {
  const runChanged = runId !== state.selectedRunId;
  state.selectedRunId = runId;
  if (runChanged) {
    state.selectedFilePath = null;
    state.filePreview = null;
    state.iterationPlan = null;
  }

  const [summary, artifacts, fileTree, paperPreview] = await Promise.all([
    api(`/api/runs/${runId}`),
    api(`/api/runs/${runId}/artifacts`),
    api(`/api/runs/${runId}/files/tree?root=workspace&depth=4`),
    api(`/api/runs/${runId}/paper`),
  ]);
  state.runSummary = summary;
  state.artifactIndex = artifacts;
  state.fileTree = fileTree;
  state.paperPreview = paperPreview;

  const matchingProject = state.projects.find(
    (project) => project.project_id === state.selectedProjectId || project.run_ids.includes(runId)
  );
  if (matchingProject) {
    state.selectedProjectId = matchingProject.project_id;
  }

  if (!state.selectedStageSlug || !summary.stages.some((stage) => stage.slug === state.selectedStageSlug)) {
    state.selectedStageSlug = summary.current_stage_slug || summary.stages.at(-1)?.slug || null;
  }

  renderProjects();
  renderRuns();
  renderHeader();
  renderProjectBrief();
  renderSummary();
  renderArtifacts();
  renderStages();
  renderFileTree();
  renderPaperPreview();
  renderIterationForm();

  if (state.selectedStageSlug) {
    await loadStageDocument(state.selectedStageSlug);
  } else {
    renderStagePanels();
  }
}

async function loadStageDocument(stageSlug) {
  if (!state.selectedRunId) {
    return;
  }
  state.selectedStageSlug = stageSlug;
  const payload = await api(`/api/runs/${state.selectedRunId}/stages/${stageSlug}`);
  state.stageDocument = payload.markdown || "";
  renderStages();
  renderStagePanels();
  renderIterationForm();
}

async function loadFileContent(relativePath) {
  if (!state.selectedRunId) {
    return;
  }
  state.selectedFilePath = relativePath;
  state.filePreview = await api(
    `/api/runs/${state.selectedRunId}/files/content?path=${encodeURIComponent(relativePath)}`
  );
  renderFileTree();
  renderFilePreview();
  setPage("files");
}

async function planIteration() {
  if (!state.selectedRunId) {
    renderIterationPlaceholder("Select a run before generating an execution brief.");
    return;
  }
  const payload = {
    base_stage_slug: elements.iterationStage.value,
    scope_type: elements.iterationScopeType.value,
    scope_value: elements.iterationScopeValue.value.trim() || elements.iterationStage.value,
    mode: elements.iterationMode.value,
    user_feedback: elements.iterationFeedback.value.trim(),
  };
  state.iterationPlan = await api(`/api/runs/${state.selectedRunId}/iterations/plan`, {
    method: "POST",
    body: payload,
  });
  renderIterationPlan();
  setPage("review");
}

function renderHeader() {
  const project = getSelectedProject();
  const summary = state.runSummary;

  elements.activeProjectLabel.textContent = project ? project.title : "No project selected";
  elements.runTitle.textContent = summary ? summary.run_id : "No run selected";
  elements.runGoal.textContent = summary?.goal || "Select a run to inspect stage output, files, and manuscript artifacts.";
  elements.runStatus.textContent = summary?.run_status || "Idle";
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
      renderProjectBrief();
      const nextRunId = project.active_run_id || project.run_ids.at(-1) || null;
      if (nextRunId) {
        void safeAction(loadRun(nextRunId));
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
    const linkedProject = state.projects.find((project) => project.run_ids.includes(runId));
    card.innerHTML = `
      <div class="run-card-title">${escapeHtml(runId)}</div>
      <div class="run-card-meta">${escapeHtml(linkedProject?.title || "Unassigned project")}</div>
    `;
    card.addEventListener("click", () => {
      void safeAction(loadRun(runId));
    });
    elements.runsList.appendChild(card);
  }
}

function renderProjectBrief() {
  const project = getSelectedProject();
  if (!project) {
    elements.projectMeta.textContent = "No project";
    renderEmpty(elements.projectBrief, "Project context appears here after you select a project.");
    return;
  }
  elements.projectMeta.textContent = `${project.default_mode} mode · ${project.run_ids.length} run(s)`;
  elements.projectBrief.classList.remove("empty-state");
  elements.projectBrief.innerHTML = `
    <p><strong>Thesis.</strong> ${escapeHtml(project.thesis)}</p>
    <p><strong>Active run.</strong> ${escapeHtml(project.active_run_id || "None attached yet.")}</p>
    <p><strong>Latest checkpoint.</strong> ${escapeHtml(project.latest_completed_stage_slug || "No approved stages yet.")}</p>
  `;
}

function renderSummary() {
  const summary = state.runSummary;
  elements.runSummary.innerHTML = "";
  if (!summary) {
    return;
  }
  renderDefinitionList(elements.runSummary, [
    ["Model", summary.model],
    ["Venue", summary.venue],
    ["Status", summary.run_status],
    ["Updated", summary.updated_at],
    ["Current", summary.current_stage_slug || "none"],
  ]);
}

function renderArtifacts() {
  const counts = state.artifactIndex?.counts_by_category || {};
  const total = state.artifactIndex?.artifact_count || 0;
  elements.artifactTotal.textContent = `${total} artifacts`;
  elements.artifactSummary.innerHTML = "";

  const entries = Object.entries(counts);
  if (!entries.length) {
    const item = document.createElement("li");
    item.textContent = "No indexed artifacts yet.";
    elements.artifactSummary.appendChild(item);
    return;
  }

  for (const [label, count] of entries) {
    const item = document.createElement("li");
    item.textContent = `${label}: ${count}`;
    elements.artifactSummary.appendChild(item);
  }
}

function renderStages() {
  elements.stageCount.textContent = String(state.runSummary?.stages?.length || 0);
  elements.stageRail.innerHTML = "";
  for (const stage of state.runSummary?.stages || []) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `stage-item${stage.slug === state.selectedStageSlug ? " is-active" : ""}`;
    item.innerHTML = `
      <div class="stage-title">${escapeHtml(stage.title)}</div>
      <div class="stage-meta">updated ${escapeHtml(stage.updated_at || "unknown")}</div>
      <span class="stage-status status-${escapeHtml(stage.status)}">${escapeHtml(stage.status)}</span>
    `;
    item.addEventListener("click", () => {
      void safeAction(loadStageDocument(stage.slug));
    });
    elements.stageRail.appendChild(item);
  }
}

function renderStagePanels() {
  const stage = getSelectedStage();
  if (!stage || !state.stageDocument) {
    elements.overviewStageTitle.textContent = "Stage snapshot";
    elements.overviewStageMeta.textContent = "";
    renderEmpty(elements.overviewStageSummary, "Select a stage to inspect the current summary.");
    elements.reviewStageLabel.textContent = "Human Review";
    elements.documentTitle.textContent = "Stage document";
    elements.documentMeta.textContent = "";
    renderEmpty(elements.stageDocument, "Select a stage to inspect the human-readable summary.");
    return;
  }

  elements.overviewStageTitle.textContent = stage.title;
  elements.overviewStageMeta.textContent = `${stage.status} · attempts ${stage.attempt_count || 0}`;
  renderMarkdown(elements.overviewStageSummary, markdownExcerpt(state.stageDocument, 22));

  elements.reviewStageLabel.textContent = `Human Review · ${stage.slug}`;
  elements.documentTitle.textContent = stage.title;
  elements.documentMeta.textContent = `${stage.status} · attempts ${stage.attempt_count || 0}`;
  renderMarkdown(elements.stageDocument, state.stageDocument);
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
  renderIterationPlan();
}

function renderIterationPlan() {
  if (!state.iterationPlan) {
    renderIterationPlaceholder("No iteration brief generated yet.");
    elements.reviewerActions.innerHTML = `
      <li>Pick a run and stage.</li>
      <li>Review the stage summary and artifacts.</li>
      <li>Generate an execution brief for the next iteration.</li>
    `;
    return;
  }

  const plan = state.iterationPlan;
  elements.iterationPlan.classList.remove("empty-state");
  elements.iterationPlan.innerHTML = `
    <p class="plan-summary">${escapeHtml(plan.summary)}</p>
    <div class="plan-grid">
      <div>Preserved</div>
      <strong>${escapeHtml(plan.preserved_stages.join(", ") || "none")}</strong>
      <div>Affected</div>
      <strong>${escapeHtml(plan.affected_stages.join(", ") || "none")}</strong>
      <div>Stale</div>
      <strong>${escapeHtml(plan.stale_stages.join(", ") || "none")}</strong>
      <div>Branch run</div>
      <strong>${escapeHtml(plan.branch_run_id || "current run")}</strong>
    </div>
    <pre class="brief-block">${escapeHtml(plan.operator_brief)}</pre>
  `;
  elements.reviewerActions.innerHTML = plan.reviewer_actions
    .map((action) => `<li>${escapeHtml(action)}</li>`)
    .join("");
}

function renderFileTree() {
  elements.fileTree.innerHTML = "";
  if (!state.fileTree) {
    return;
  }
  elements.fileTree.appendChild(renderTreeNode(state.fileTree));
  renderFilePreview();
}

function renderTreeNode(node) {
  const wrapper = document.createElement("div");
  wrapper.className = "tree-node";

  const label = document.createElement("button");
  label.type = "button";
  label.className = `tree-label${node.rel_path === state.selectedFilePath ? " is-active" : ""}`;
  label.textContent = `${node.node_type === "directory" ? "▾" : "•"} ${node.name}`;
  if (node.node_type === "file") {
    label.addEventListener("click", () => {
      void safeAction(loadFileContent(node.rel_path));
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

function renderFilePreview() {
  const preview = state.filePreview;
  if (!preview) {
    elements.filePreviewTitle.textContent = "File preview";
    elements.filePreviewMeta.textContent = "";
    renderEmpty(elements.filePreview, "Select a file from the workspace tree to preview it here.");
    return;
  }

  elements.filePreviewTitle.textContent = preview.relative_path;
  elements.filePreviewMeta.textContent = `${preview.encoding} · ${preview.size_bytes} bytes`;

  if (preview.encoding === "binary") {
    renderEmpty(elements.filePreview, "Binary file preview is unavailable in the browser.");
    return;
  }

  if (preview.relative_path.endsWith(".md")) {
    renderMarkdown(elements.filePreview, preview.content);
    return;
  }

  if (preview.relative_path.endsWith(".json")) {
    const pretty = tryPrettyJson(preview.content);
    renderCode(elements.filePreview, pretty);
    return;
  }

  renderCode(elements.filePreview, preview.content);
}

function renderPaperPreview() {
  const preview = state.paperPreview;
  elements.paperSummary.innerHTML = "";
  elements.paperSections.innerHTML = "";

  if (!preview) {
    elements.paperStatus.textContent = "No PDF yet";
    elements.paperMeta.textContent = "";
    renderEmpty(elements.paperFrameContainer, "Select a run with writing artifacts to preview the paper.");
    renderEmpty(elements.paperTexPreview, "No manuscript source found.");
    renderEmpty(elements.paperBuildLog, "No build log found.");
    return;
  }

  elements.paperStatus.textContent = preview.pdf_available ? "PDF ready" : "TeX only";
  elements.paperMeta.textContent = preview.pdf_relative_path || preview.tex_relative_path || "No manuscript files";
  renderDefinitionList(elements.paperSummary, [
    ["Main TeX", preview.tex_relative_path || "missing"],
    ["Compiled PDF", preview.pdf_relative_path || "missing"],
    ["Sections", String(preview.section_paths.length)],
    ["Build log", preview.build_log_relative_path || "missing"],
  ]);

  if (preview.section_paths.length) {
    elements.paperSections.innerHTML = preview.section_paths
      .map((path) => `<li>${escapeHtml(path)}</li>`)
      .join("");
  } else {
    elements.paperSections.innerHTML = "<li>No section files found.</li>";
  }

  if (preview.pdf_available && state.selectedRunId) {
    elements.paperFrameContainer.classList.remove("empty-state");
    elements.paperFrameContainer.innerHTML = `
      <iframe
        class="paper-frame"
        src="/api/runs/${encodeURIComponent(state.selectedRunId)}/paper/pdf"
        title="Compiled paper preview"
      ></iframe>
    `;
  } else {
    renderEmpty(elements.paperFrameContainer, "No compiled PDF found yet. Main TeX and build logs can still be reviewed here.");
  }

  if (preview.tex_content) {
    renderCode(elements.paperTexPreview, preview.tex_content);
  } else {
    renderEmpty(elements.paperTexPreview, "No manuscript source found.");
  }

  if (preview.build_log_content) {
    renderCode(elements.paperBuildLog, preview.build_log_content);
  } else {
    renderEmpty(elements.paperBuildLog, "No build log found.");
  }
}

function renderWorkspaceSkeleton(message) {
  renderHeader();
  renderProjectBrief();
  renderEmpty(elements.overviewStageSummary, message);
  renderEmpty(elements.stageDocument, message);
  renderEmpty(elements.filePreview, "Select a file from the workspace tree to preview it here.");
  renderEmpty(elements.paperFrameContainer, "Select a run with writing artifacts to preview the paper.");
  renderEmpty(elements.paperTexPreview, "No manuscript source found.");
  renderEmpty(elements.paperBuildLog, "No build log found.");
  elements.runSummary.innerHTML = "";
  elements.artifactSummary.innerHTML = "";
  elements.stageRail.innerHTML = "";
  elements.fileTree.innerHTML = "";
  renderIterationPlaceholder("No iteration brief generated yet.");
}

function clearRunState() {
  state.selectedRunId = null;
  state.selectedStageSlug = null;
  state.selectedFilePath = null;
  state.runSummary = null;
  state.artifactIndex = null;
  state.fileTree = null;
  state.stageDocument = "";
  state.filePreview = null;
  state.paperPreview = null;
  state.iterationPlan = null;
}

function renderIterationPlaceholder(message) {
  renderEmpty(elements.iterationPlan, message);
}

function renderDefinitionList(target, rows) {
  target.innerHTML = "";
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    target.append(dt, dd);
  }
}

function renderMarkdown(element, markdown) {
  if (!markdown?.trim()) {
    renderEmpty(element, "Nothing to preview yet.");
    return;
  }
  element.classList.remove("empty-state");
  element.classList.add("markdown-body");
  element.innerHTML = markdownToHtml(markdown);
}

function renderCode(element, content) {
  if (!content?.length) {
    renderEmpty(element, "Nothing to preview yet.");
    return;
  }
  element.classList.remove("empty-state");
  element.classList.remove("markdown-body");
  element.innerHTML = `<pre>${escapeHtml(content)}</pre>`;
}

function renderEmpty(element, message) {
  element.classList.remove("markdown-body");
  element.classList.add("empty-state");
  element.textContent = message;
}

function markdownToHtml(markdown) {
  const lines = markdown.replaceAll("\r", "").split("\n");
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let listKind = null;
  let codeFence = null;
  let codeLines = [];

  const flushParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    blocks.push(`<p>${formatInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length || !listKind) {
      return;
    }
    blocks.push(`<${listKind}>${listItems.map((item) => `<li>${formatInline(item)}</li>`).join("")}</${listKind}>`);
    listItems = [];
    listKind = null;
  };

  const flushCode = () => {
    if (codeFence === null) {
      return;
    }
    blocks.push(`<pre>${escapeHtml(codeLines.join("\n"))}</pre>`);
    codeFence = null;
    codeLines = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();

    if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      if (codeFence === null) {
        codeFence = line.slice(3).trim();
      } else {
        flushCode();
      }
      continue;
    }

    if (codeFence !== null) {
      codeLines.push(rawLine);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      blocks.push(`<h${level}>${formatInline(headingMatch[2])}</h${level}>`);
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listKind && listKind !== "ol") {
        flushList();
      }
      listKind = "ol";
      listItems.push(orderedMatch[1]);
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.*)$/);
    if (bulletMatch) {
      flushParagraph();
      if (listKind && listKind !== "ul") {
        flushList();
      }
      listKind = "ul";
      listItems.push(bulletMatch[1]);
      continue;
    }

    const quoteMatch = line.match(/^>\s?(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${formatInline(quoteMatch[1])}</blockquote>`);
      continue;
    }

    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  flushCode();
  return blocks.join("");
}

function formatInline(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function markdownExcerpt(markdown, maxLines) {
  const lines = markdown.replaceAll("\r", "").split("\n").filter((line) => line.trim());
  if (lines.length <= maxLines) {
    return markdown;
  }
  return `${lines.slice(0, maxLines).join("\n")}\n\n...`;
}

function tryPrettyJson(content) {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

function setPage(page) {
  if (!PAGE_IDS.includes(page)) {
    return;
  }
  state.page = page;
  if (window.location.hash !== `#${page}`) {
    window.location.hash = page;
  }
  renderPageNav();
}

function renderPageNav() {
  for (const button of elements.pageButtons) {
    const isActive = button.dataset.page === state.page;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  }
  for (const [page, element] of Object.entries(elements.pages)) {
    element.classList.toggle("is-active", page === state.page);
  }
}

function getSelectedProject() {
  return state.projects.find((project) => project.project_id === state.selectedProjectId) || null;
}

function getSelectedStage() {
  return state.runSummary?.stages.find((stage) => stage.slug === state.selectedStageSlug) || null;
}

function readHashPage() {
  const page = window.location.hash.replace(/^#/, "");
  return PAGE_IDS.includes(page) ? page : "overview";
}

function setConnection(text) {
  elements.connectionStatus.textContent = text;
}

async function safeAction(promise) {
  try {
    await promise;
  } catch (error) {
    console.error(error);
    setConnection("Error");
    renderWorkspaceSkeleton(error.message || "Unexpected studio error.");
  }
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
