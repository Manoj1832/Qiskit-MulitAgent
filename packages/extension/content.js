/**
 * SWE-Agent Copilot — Content Script
 *
 * Injected into:
 *   - https://github.com/{owner}/{repo}/issues/{number}   (Issue pages)
 *   - https://github.com/{owner}/{repo}/pull/{number}     (PR pages)
 *   - https://github.com/{owner}/{repo}/pull/{number}/files (PR diff pages)
 *
 * Responsibilities:
 *  1. Detect page type (Issue vs PR)
 *  2. Extract all relevant data from the GitHub DOM
 *  3. Inject the "🤖 Analyze with SWE-Agent" floating button
 *  4. Send analysis request to background service worker
 *  5. Render real-time SSE events in an injected side panel
 */

(function () {
  "use strict";

  // Prevent double injection
  if (window.__sweAgentInjected) return;
  window.__sweAgentInjected = true;

  // ── Page Detection ──────────────────────────────────────────────────────────

  const url = window.location.href;
  const issueMatch = url.match(/github\.com\/([^/]+)\/([^/]+)\/issues\/(\d+)/);
  const prMatch = url.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/);

  if (!issueMatch && !prMatch) return;

  const match = issueMatch || prMatch;
  const pageType = issueMatch ? "issue" : "pr";
  const repoOwner = match[1];
  const repoName = match[2];
  const number = parseInt(match[3], 10);

  console.log(`[SWE-Agent] Detected ${pageType} page: ${repoOwner}/${repoName}#${number}`);

  // ── Data Extraction ─────────────────────────────────────────────────────────

  function extractIssueData() {
    const title = document.querySelector(".js-issue-title, [data-testid='issue-title'], h1.gh-header-title .markdown-title")?.textContent?.trim() || document.title;
    const body = document.querySelector(".comment-body, .js-comment-body")?.innerText?.trim() || "";

    const commentElements = document.querySelectorAll(".timeline-comment .comment-body, .js-comment-body");
    const comments = Array.from(commentElements)
      .slice(1) // Skip first (issue body)
      .map((el) => el.innerText?.trim())
      .filter(Boolean)
      .slice(0, 20); // Max 20 comments

    const labels = Array.from(document.querySelectorAll(".js-issue-labels .IssueLabel, [data-testid='issue-label']"))
      .map((el) => el.textContent?.trim())
      .filter(Boolean);

    return {
      repo_owner: repoOwner,
      repo_name: repoName,
      issue_number: number,
      issue_title: title,
      issue_body: body,
      comments,
      labels,
    };
  }

  function extractPRData() {
    const title = document.querySelector(".js-issue-title, [data-testid='issue-title'], h1.gh-header-title .markdown-title")?.textContent?.trim() || document.title;
    const body = document.querySelector(".comment-body, .js-comment-body")?.innerText?.trim() || "";

    // Extract changed files list
    const changedFiles = Array.from(document.querySelectorAll(".file-info .link-gray-dark, [data-testid='file-name']"))
      .map((el) => el.textContent?.trim())
      .filter(Boolean);

    // Extract review comments
    const reviewComments = Array.from(document.querySelectorAll(".review-comment .comment-body"))
      .map((el) => el.innerText?.trim())
      .filter(Boolean)
      .slice(0, 15);

    // Extract inline diff (first 5000 chars)
    const diffContent = Array.from(document.querySelectorAll(".blob-code"))
      .map((el) => el.textContent)
      .join("\n")
      .slice(0, 5000);

    return {
      repo_owner: repoOwner,
      repo_name: repoName,
      pr_number: number,
      pr_title: title,
      pr_body: body,
      changed_files: changedFiles,
      review_comments: reviewComments,
      diff_content: diffContent,
    };
  }

  // ── Side Panel UI ───────────────────────────────────────────────────────────

  function createSidePanel() {
    const existing = document.getElementById("swe-agent-panel");
    if (existing) {
      existing.style.display = "flex";
      return existing;
    }

    const panel = document.createElement("div");
    panel.id = "swe-agent-panel";
    panel.innerHTML = `
      <div class="swe-panel-header">
        <div class="swe-panel-title">
          <span class="swe-logo">🤖</span>
          <span>SWE-Agent Copilot</span>
        </div>
        <div class="swe-panel-controls">
          <button id="swe-theme-toggle" title="Toggle theme">🌙</button>
          <button id="swe-panel-close" title="Close">✕</button>
        </div>
      </div>

      <div class="swe-panel-body" id="swe-panel-body">
        <div class="swe-welcome">
          <div class="swe-welcome-icon">🤖</div>
          <h3>SWE-Agent Copilot</h3>
          <p>Click <strong>Analyze</strong> to start the multi-agent pipeline</p>
          <div class="swe-agents-list">
            <span class="swe-agent-badge">🔍 Sentry</span>
            <span class="swe-agent-badge">🧠 Strategist</span>
            <span class="swe-agent-badge">📐 Architect</span>
            <span class="swe-agent-badge">💻 Developer</span>
            <span class="swe-agent-badge">✅ Validator</span>
          </div>
        </div>
      </div>

      <div class="swe-panel-footer" id="swe-panel-footer" style="display:none;">
        <button id="swe-copy-patch" class="swe-btn swe-btn-secondary">📋 Copy Patch</button>
        <button id="swe-download-patch" class="swe-btn swe-btn-secondary">⬇️ Download</button>
        <button id="swe-create-pr" class="swe-btn swe-btn-primary">🔀 Create PR</button>
      </div>
    `;

    document.body.appendChild(panel);

    // Close button
    document.getElementById("swe-panel-close").addEventListener("click", () => {
      panel.style.display = "none";
    });

    // Theme toggle
    let isDark = true;
    document.getElementById("swe-theme-toggle").addEventListener("click", () => {
      isDark = !isDark;
      panel.classList.toggle("swe-light", !isDark);
      document.getElementById("swe-theme-toggle").textContent = isDark ? "🌙" : "☀️";
    });

    return panel;
  }

  function showPhaseCard(phaseId, icon, title, content, status = "running") {
    const body = document.getElementById("swe-panel-body");
    let card = document.getElementById(`swe-phase-${phaseId}`);

    if (!card) {
      card = document.createElement("div");
      card.id = `swe-phase-${phaseId}`;
      card.className = "swe-phase-card";
      body.appendChild(card);
    }

    const statusClass = status === "done" ? "swe-status-done" : status === "error" ? "swe-status-error" : "swe-status-running";
    const statusIcon = status === "done" ? "✅" : status === "error" ? "❌" : "⏳";

    card.innerHTML = `
      <div class="swe-phase-header">
        <span class="swe-phase-icon">${icon}</span>
        <span class="swe-phase-title">${title}</span>
        <span class="swe-phase-status ${statusClass}">${statusIcon}</span>
      </div>
      <div class="swe-phase-content">${content}</div>
    `;
  }

  function renderPhaseContent(event, data) {
    const phases = {
      start: { icon: "🚀", title: "Pipeline Started" },
      sentry: { icon: "🔍", title: "Sentry — Reconnaissance" },
      strategist: { icon: "🧠", title: "Strategist — Classification" },
      architect: { icon: "📐", title: "Architect — Planning" },
      developer: { icon: "💻", title: "Developer — Patch Generation" },
      validator: { icon: "✅", title: "Validator — Verification" },
    };

    const phase = phases[event] || { icon: "⚙️", title: event };

    if (data.status === "running") {
      showPhaseCard(event, phase.icon, phase.title, `<div class="swe-spinner-row"><div class="swe-spinner"></div><span>${data.message || "Processing..."}</span></div>`, "running");
      return;
    }

    let content = "";

    switch (event) {
      case "start":
        content = `<p class="swe-info">Repo: <strong>${data.repo}</strong> | #${data.issue_number || data.pr_number}</p>`;
        break;

      case "sentry":
        content = `
          <p><strong>Issue:</strong> ${escHtml(data.issue_title || "")}</p>
          ${data.related_issues?.length ? `<p><strong>Related:</strong> #${data.related_issues.join(", #")}</p>` : ""}
          ${data.recent_commits_summary ? `<p class="swe-muted">${escHtml(data.recent_commits_summary.slice(0, 200))}</p>` : ""}
        `;
        break;

      case "strategist":
        content = `
          <div class="swe-tags">
            <span class="swe-tag swe-tag-type">${escHtml(data.issue_type || "")}</span>
            <span class="swe-tag swe-tag-severity">${escHtml(data.severity || "")}</span>
            <span class="swe-tag swe-tag-priority">${escHtml(data.priority || "")}</span>
            <span class="swe-tag swe-tag-confidence">Confidence: ${escHtml(data.confidence || "")}</span>
          </div>
          <p class="swe-summary">${escHtml(data.summary || "")}</p>
          ${data.suspected_components?.length ? `<p class="swe-muted">Components: ${data.suspected_components.map(escHtml).join(", ")}</p>` : ""}
        `;
        break;

      case "architect":
        content = `
          <p>${escHtml(data.plan_summary || "")}</p>
          <p class="swe-muted">Complexity: ${escHtml(data.complexity || "")} | Steps: ${data.steps || 0}</p>
          ${data.localized_files?.length ? `
            <div class="swe-files-list">
              ${data.localized_files.slice(0, 5).map((f) => `
                <div class="swe-file-item">
                  <span class="swe-file-icon">📄</span>
                  <span class="swe-file-path">${escHtml(f.file)}</span>
                  <span class="swe-file-reason">${escHtml(f.reason?.slice(0, 60) || "")}</span>
                </div>
              `).join("")}
            </div>
          ` : ""}
        `;
        break;

      case "developer":
        content = `
          <p>${escHtml(data.explanation || "")}</p>
          <p class="swe-muted">Files changed: ${data.files_changed || 0} | Confidence: ${escHtml(data.confidence || "")}</p>
          ${data.patch_preview ? `<pre class="swe-patch-preview">${escHtml(data.patch_preview)}</pre>` : ""}
        `;
        break;

      case "validator":
        const passRate = data.tests_total > 0 ? Math.round((data.tests_passed / data.tests_total) * 100) : 0;
        content = `
          <div class="swe-test-bar">
            <div class="swe-test-bar-fill ${data.all_passed ? "swe-bar-green" : "swe-bar-red"}" style="width:${passRate}%"></div>
          </div>
          <p>${data.tests_passed}/${data.tests_total} tests passed ${data.regression ? "⚠️ REGRESSION DETECTED" : ""}</p>
          ${data.feedback ? `<p class="swe-muted">${escHtml(data.feedback.slice(0, 200))}</p>` : ""}
        `;
        break;
    }

    showPhaseCard(event, phase.icon, phase.title, content, "done");
  }

  function renderFinalResult(data) {
    window.__sweAgentResult = data;

    const body = document.getElementById("swe-panel-body");

    // Confidence bar
    const confPct = Math.round((data.confidence || 0) * 100);
    const confColor = confPct >= 75 ? "#22c55e" : confPct >= 50 ? "#f59e0b" : "#ef4444";

    const resultCard = document.createElement("div");
    resultCard.className = "swe-result-card";
    resultCard.innerHTML = `
      <div class="swe-result-header">
        <h3>🎯 Analysis Complete</h3>
        <span class="swe-run-id">Run: ${escHtml(data.run_id || "")}</span>
      </div>

      <div class="swe-confidence-section">
        <div class="swe-confidence-label">
          <span>Confidence Score</span>
          <strong>${confPct}%</strong>
        </div>
        <div class="swe-confidence-bar">
          <div class="swe-confidence-fill" style="width:0%;background:${confColor}" data-target="${confPct}"></div>
        </div>
      </div>

      <div class="swe-root-cause">
        <h4>🔍 Root Cause</h4>
        <p>${escHtml(data.root_cause || "")}</p>
      </div>

      ${data.affected_files?.length ? `
        <div class="swe-affected-files">
          <h4>📁 Affected Files</h4>
          ${data.affected_files.map((f) => `<div class="swe-file-chip">📄 ${escHtml(f)}</div>`).join("")}
        </div>
      ` : ""}

      ${data.patch_diff ? `
        <div class="swe-diff-section">
          <h4>🔧 Generated Patch</h4>
          <div class="swe-diff-viewer">${renderDiff(data.patch_diff)}</div>
        </div>
      ` : "<p class='swe-muted'>No patch generated.</p>"}
    `;

    body.appendChild(resultCard);

    // Animate confidence bar
    setTimeout(() => {
      const fill = resultCard.querySelector(".swe-confidence-fill");
      if (fill) fill.style.width = fill.dataset.target + "%";
    }, 100);

    // Show footer actions
    const footer = document.getElementById("swe-panel-footer");
    if (footer) footer.style.display = "flex";

    // Wire up footer buttons
    document.getElementById("swe-copy-patch")?.addEventListener("click", () => {
      navigator.clipboard.writeText(data.patch_diff || "").then(() => {
        showToast("Patch copied to clipboard!");
      });
    });

    document.getElementById("swe-download-patch")?.addEventListener("click", () => {
      const blob = new Blob([data.patch_diff || ""], { type: "text/plain" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `swe-agent-fix-${data.issue_number || data.pr_number}.patch`;
      a.click();
    });

    document.getElementById("swe-create-pr")?.addEventListener("click", async () => {
      const btn = document.getElementById("swe-create-pr");
      btn.textContent = "⏳ Creating PR...";
      btn.disabled = true;

      chrome.runtime.sendMessage({
        type: "CREATE_PR",
        payload: {
          repo_owner: repoOwner,
          repo_name: repoName,
          issue_number: data.issue_number || number,
          patch_diff: data.patch_diff,
        },
      }, (resp) => {
        if (resp?.success) {
          showToast(`PR created: ${resp.data.pr_url}`);
          btn.textContent = "✅ PR Created";
          window.open(resp.data.pr_url, "_blank");
        } else {
          showToast(`PR creation failed: ${resp?.error || "Unknown error"}`, "error");
          btn.textContent = "🔀 Create PR";
          btn.disabled = false;
        }
      });
    });
  }

  function renderDiff(patch) {
    if (!patch) return "<em>No patch generated</em>";
    return patch
      .split("\n")
      .map((line) => {
        const escaped = escHtml(line);
        if (line.startsWith("+++") || line.startsWith("---")) {
          return `<div class="diff-file">${escaped}</div>`;
        } else if (line.startsWith("+")) {
          return `<div class="diff-add">${escaped}</div>`;
        } else if (line.startsWith("-")) {
          return `<div class="diff-del">${escaped}</div>`;
        } else if (line.startsWith("@@")) {
          return `<div class="diff-hunk">${escaped}</div>`;
        }
        return `<div class="diff-ctx">${escaped}</div>`;
      })
      .join("");
  }

  function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `swe-toast swe-toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add("swe-toast-show"), 10);
    setTimeout(() => {
      toast.classList.remove("swe-toast-show");
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── Inject Button ───────────────────────────────────────────────────────────

  function injectButton() {
    if (document.getElementById("swe-agent-btn")) return;

    const btn = document.createElement("button");
    btn.id = "swe-agent-btn";
    btn.className = "swe-analyze-btn";
    btn.innerHTML = `<span class="swe-btn-icon">🤖</span><span class="swe-btn-label">Analyze with SWE-Agent</span>`;
    btn.title = `Analyze this ${pageType === "pr" ? "Pull Request" : "Issue"} with the SWE-Agent multi-agent pipeline`;

    btn.addEventListener("click", () => {
      const panel = createSidePanel();
      panel.style.display = "flex";

      const body = document.getElementById("swe-panel-body");
      body.innerHTML = `
        <div class="swe-loading-state">
          <div class="swe-pulse-ring"></div>
          <p>🚀 Initializing SWE-Agent pipeline...</p>
          <p class="swe-muted">5 agents will analyze this ${pageType === "pr" ? "PR" : "issue"}</p>
        </div>
      `;

      const footer = document.getElementById("swe-panel-footer");
      if (footer) footer.style.display = "none";

      // Extract data and send to background
      if (pageType === "issue") {
        const payload = extractIssueData();
        chrome.runtime.sendMessage({ type: "ANALYZE_ISSUE", payload });
      } else {
        const payload = extractPRData();
        chrome.runtime.sendMessage({ type: "ANALYZE_PR", payload });
      }
    });

    // Try multiple injection points for robustness
    const targets = [
      ".gh-header-actions",
      ".gh-header-meta",
      ".discussion-timeline-actions",
      ".js-issue-header",
      ".pull-request-tab-content",
      "#partial-discussion-header",
    ];

    let injected = false;
    for (const selector of targets) {
      const target = document.querySelector(selector);
      if (target) {
        target.prepend(btn);
        injected = true;
        break;
      }
    }

    if (!injected) {
      // Fallback: floating button
      btn.classList.add("swe-floating-btn");
      document.body.appendChild(btn);
    }

    console.log(`[SWE-Agent] Button injected on ${pageType} page`);
  }

  // ── Event Listener ──────────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((message) => {
    // Popup → content: trigger analysis programmatically
    if (message.type === "TRIGGER_ANALYZE") {
      const btn = document.getElementById("swe-agent-btn");
      if (btn) btn.click();
      else {
        injectButton();
        setTimeout(() => document.getElementById("swe-agent-btn")?.click(), 200);
      }
      return;
    }

    // Popup → content: show the side panel
    if (message.type === "SHOW_PANEL") {
      const panel = document.getElementById("swe-agent-panel");
      if (panel) panel.style.display = "flex";
      else createSidePanel();
      return;
    }

    if (message.type !== "SWE_AGENT_EVENT") return;

    const { event, data } = message;

    if (event === "error") {
      const body = document.getElementById("swe-panel-body");
      if (body) {
        body.innerHTML += `
          <div class="swe-error-card">
            <span>❌</span>
            <p>${escHtml(data.message || "Unknown error")}</p>
          </div>
        `;
      }
      return;
    }

    if (event === "complete") {
      renderFinalResult(data);
      return;
    }

    renderPhaseContent(event, data);
  });

  // ── Init ────────────────────────────────────────────────────────────────────

  // Inject button immediately or wait for DOM
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectButton);
  } else {
    injectButton();
  }

  // Re-inject on GitHub's SPA navigation (pjax)
  const observer = new MutationObserver(() => {
    if (!document.getElementById("swe-agent-btn")) {
      injectButton();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

})();
