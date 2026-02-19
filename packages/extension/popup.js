/**
 * SWE-Agent Copilot — Popup Script
 *
 * Handles:
 *  1. Backend health check
 *  2. Detecting current GitHub page type (Issue / PR)
 *  3. Triggering analysis via content script
 *  4. Receiving SSE events and rendering results
 *  5. Dark/Light theme toggle
 */

const BACKEND_URL = "http://localhost:8000";

// ── State ─────────────────────────────────────────────────────────────────────
let currentTab = null;
let currentPageType = null; // 'issue' | 'pr' | null
let currentResult = null;
let isDark = true;

// ── DOM Refs ──────────────────────────────────────────────────────────────────
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const pageInfo = document.getElementById("page-info");
const pageTypeBadge = document.getElementById("page-type-badge");
const pageRepo = document.getElementById("page-repo");
const noPage = document.getElementById("no-page");
const analyzePanel = document.getElementById("analyze-panel");
const analyzeBtn = document.getElementById("analyze-btn");
const analyzeBtnText = document.getElementById("analyze-btn-text");
const resultsSection = document.getElementById("results-section");
const liveLog = document.getElementById("live-log");
const liveLogBody = document.getElementById("live-log-body");
const tokenStatus = document.getElementById("token-status");
const themeToggle = document.getElementById("theme-toggle");

// ── Theme ─────────────────────────────────────────────────────────────────────
themeToggle.addEventListener("click", () => {
    isDark = !isDark;
    document.body.classList.toggle("swe-light", !isDark);
    themeToggle.textContent = isDark ? "🌙" : "☀️";
});

// ── Backend Health ────────────────────────────────────────────────────────────
async function checkBackendHealth() {
    statusDot.className = "status-dot checking";
    statusText.textContent = "Connecting to backend...";

    try {
        const resp = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(3000) });
        if (resp.ok) {
            statusDot.className = "status-dot online";
            statusText.textContent = "Backend online — SWE-Agent ready";
        } else {
            throw new Error(`HTTP ${resp.status}`);
        }
    } catch {
        statusDot.className = "status-dot offline";
        statusText.textContent = "Backend offline — start with: uvicorn main:app";
    }
}

// ── Token Status ──────────────────────────────────────────────────────────────
function checkTokenStatus() {
    chrome.runtime.sendMessage({ type: "GET_TOKEN_STATUS" }, (resp) => {
        if (resp?.hasToken) {
            const expiresIn = Math.round((resp.expiresAt - Date.now()) / 60000);
            tokenStatus.textContent = `🔑 Auth valid (${expiresIn}m)`;
        } else {
            tokenStatus.textContent = "🔑 Not authenticated";
        }
    });
}

// ── Page Detection ────────────────────────────────────────────────────────────
async function detectCurrentPage() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTab = tab;

    if (!tab?.url) {
        showNoPage();
        return;
    }

    const issueMatch = tab.url.match(/github\.com\/([^/]+)\/([^/]+)\/issues\/(\d+)/);
    const prMatch = tab.url.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/);

    if (issueMatch) {
        currentPageType = "issue";
        showAnalyzePanel("issue", issueMatch[1], issueMatch[2], parseInt(issueMatch[3]));
    } else if (prMatch) {
        currentPageType = "pr";
        showAnalyzePanel("pr", prMatch[1], prMatch[2], parseInt(prMatch[3]));
    } else {
        showNoPage();
    }
}

function showNoPage() {
    noPage.style.display = "block";
    analyzePanel.style.display = "none";
    pageInfo.style.display = "none";
}

function showAnalyzePanel(type, owner, repo, number) {
    noPage.style.display = "none";
    analyzePanel.style.display = "flex";
    pageInfo.style.display = "flex";

    pageTypeBadge.textContent = type === "pr" ? "Pull Request" : "Issue";
    pageTypeBadge.className = `page-type-badge ${type === "pr" ? "badge-pr" : "badge-issue"}`;
    pageRepo.textContent = `${owner}/${repo} #${number}`;
}

// ── Pipeline Step Updates ─────────────────────────────────────────────────────
const stepMap = {
    sentry: "step-sentry",
    strategist: "step-strategist",
    architect: "step-architect",
    developer: "step-developer",
    validator: "step-validator",
};

function setStepStatus(step, status) {
    const el = document.getElementById(`${stepMap[step]}-status`);
    if (el) el.className = `step-status ${status}`;
}

function resetSteps() {
    Object.values(stepMap).forEach((id) => {
        const el = document.getElementById(`${id}-status`);
        if (el) el.className = "step-status";
    });
}

function addLog(message) {
    liveLog.style.display = "block";
    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    liveLogBody.appendChild(entry);
    liveLogBody.scrollTop = liveLogBody.scrollHeight;
}

// ── Analyze Button ────────────────────────────────────────────────────────────
analyzeBtn.addEventListener("click", () => {
    if (!currentTab) return;

    analyzeBtn.disabled = true;
    analyzeBtnText.textContent = "Analyzing...";
    resultsSection.style.display = "none";
    resetSteps();
    liveLogBody.innerHTML = "";

    addLog("🚀 Starting SWE-Agent pipeline...");

    // Trigger analysis via content script
    chrome.tabs.sendMessage(currentTab.id, { type: "TRIGGER_ANALYZE" }, (resp) => {
        if (chrome.runtime.lastError) {
            // Content script might not be ready — inject it
            addLog("⚠️ Injecting content script...");
            chrome.scripting.executeScript({
                target: { tabId: currentTab.id },
                files: ["content.js"],
            }).then(() => {
                chrome.scripting.insertCSS({
                    target: { tabId: currentTab.id },
                    files: ["content.css"],
                });
                setTimeout(() => {
                    chrome.tabs.sendMessage(currentTab.id, { type: "TRIGGER_ANALYZE" });
                }, 500);
            });
        }
    });
});

// ── Listen for SSE Events from Content Script ─────────────────────────────────
chrome.runtime.onMessage.addListener((message) => {
    if (message.type !== "SWE_AGENT_EVENT") return;

    const { event, data } = message;

    switch (event) {
        case "start":
            addLog(`🚀 Pipeline started — Run ID: ${data.run_id}`);
            break;

        case "sentry":
            if (data.status === "running") {
                setStepStatus("sentry", "running");
                addLog("🔍 Sentry scanning...");
            } else {
                setStepStatus("sentry", "done");
                addLog(`✅ Sentry done — ${data.issue_title || ""}`);
            }
            break;

        case "strategist":
            if (data.status === "running") {
                setStepStatus("strategist", "running");
                addLog("🧠 Strategist classifying...");
            } else {
                setStepStatus("strategist", "done");
                addLog(`✅ Strategist: ${data.issue_type} | ${data.severity}`);
            }
            break;

        case "architect":
            if (data.status === "running") {
                setStepStatus("architect", "running");
                addLog("📐 Architect planning...");
            } else {
                setStepStatus("architect", "done");
                addLog(`✅ Architect: ${data.steps} steps planned`);
            }
            break;

        case "developer":
            if (data.status === "running") {
                setStepStatus("developer", "running");
                addLog("💻 Developer generating patch...");
            } else {
                setStepStatus("developer", "done");
                addLog(`✅ Developer: ${data.files_changed} files changed`);
            }
            break;

        case "validator":
            if (data.status === "running") {
                setStepStatus("validator", "running");
                addLog("✅ Validator verifying...");
            } else {
                setStepStatus("validator", "done");
                addLog(`✅ Validator: ${data.tests_passed}/${data.tests_total} tests passed`);
            }
            break;

        case "complete":
            currentResult = data;
            renderResults(data);
            analyzeBtn.disabled = false;
            analyzeBtnText.textContent = "Re-Analyze";
            addLog("🎯 Analysis complete!");
            break;

        case "error":
            analyzeBtn.disabled = false;
            analyzeBtnText.textContent = "Retry Analysis";
            addLog(`❌ Error: ${data.message}`);
            Object.keys(stepMap).forEach((step) => {
                const el = document.getElementById(`${stepMap[step]}-status`);
                if (el?.classList.contains("running")) el.className = "step-status error";
            });
            break;
    }
});

// ── Render Results ────────────────────────────────────────────────────────────
function renderResults(data) {
    resultsSection.style.display = "flex";

    // Classification badge
    const classEl = document.getElementById("result-classification");
    const cls = (data.classification || "unknown").toLowerCase().replace(/\s+/g, "-");
    classEl.textContent = data.classification || "Unknown";
    classEl.className = `result-value badge badge-${cls}`;

    // Severity
    document.getElementById("result-severity").textContent =
        `${data.severity || "?"} | Priority: ${data.priority || "?"}`;

    // Confidence
    const confPct = Math.round((data.confidence || 0) * 100);
    document.getElementById("confidence-pct").textContent = `${confPct}%`;
    setTimeout(() => {
        document.getElementById("confidence-fill").style.width = `${confPct}%`;
    }, 100);

    // Root cause
    document.getElementById("root-cause-text").textContent = data.root_cause || "No root cause identified.";

    // Wire up action buttons
    document.getElementById("popup-copy-patch").onclick = () => {
        navigator.clipboard.writeText(data.patch_diff || "").then(() => {
            document.getElementById("popup-copy-patch").textContent = "✅ Copied!";
            setTimeout(() => {
                document.getElementById("popup-copy-patch").textContent = "📋 Copy Patch";
            }, 2000);
        });
    };

    document.getElementById("popup-download-patch").onclick = () => {
        const blob = new Blob([data.patch_diff || ""], { type: "text/plain" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `swe-agent-fix-${data.issue_number || data.pr_number}.patch`;
        a.click();
    };

    document.getElementById("popup-open-panel").onclick = () => {
        // Tell content script to open/show the side panel
        chrome.tabs.sendMessage(currentTab.id, { type: "SHOW_PANEL" });
        window.close();
    };
}

// Note: Single init block is at the bottom of the file (after Knowledge Base section).


// ═══════════════════════════════════════════════════════════════════════════════
// PR-Agent Tools — /review, /improve, /test
// ═══════════════════════════════════════════════════════════════════════════════

const prAgentPanel = document.getElementById("pr-agent-panel");
const toolLoading = document.getElementById("tool-loading");
const toolLoadingText = document.getElementById("tool-loading-text");
const toolResults = document.getElementById("tool-results");

let currentPRInfo = null; // { owner, repo, number }

function initPRAgentTools() {
    // Only show PR-Agent tools on PR pages
    const tab = currentTab;
    if (!tab?.url) return;

    const prMatch = tab.url.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/);
    if (!prMatch) return;

    currentPRInfo = {
        owner: prMatch[1],
        repo: prMatch[2],
        number: parseInt(prMatch[3]),
    };

    prAgentPanel.style.display = "block";

    // Wire up tool buttons
    document.getElementById("tool-review-btn").addEventListener("click", () => runTool("/review"));
    document.getElementById("tool-suggest-btn").addEventListener("click", () => runTool("/improve"));
    document.getElementById("tool-test-btn").addEventListener("click", () => runTool("/test"));

    // Wire up tab navigation
    document.querySelectorAll(".result-tab").forEach((tab) => {
        tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    });

    // Copy tests button
    document.getElementById("copy-tests-btn").addEventListener("click", copyAllTests);

    // Show and init PR Chat
    initPRChat();
}

// ── Tab Switching ────────────────────────────────────────────────────────────
function switchTab(tabId) {
    document.querySelectorAll(".result-tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

    document.querySelector(`[data-tab="${tabId}"]`).classList.add("active");
    document.getElementById(tabId).classList.add("active");
}

// ── Run Tool ─────────────────────────────────────────────────────────────────
async function runTool(command) {
    if (!currentPRInfo) return;

    // Get token
    const token = await getStoredToken();

    // Show loading
    const toolBtns = document.querySelectorAll(".tool-btn");
    toolBtns.forEach((b) => (b.disabled = true));
    toolLoading.style.display = "flex";
    toolLoadingText.textContent = `Running ${command}...`;

    // Map command to endpoint and tab
    const commandConfig = {
        "/review": { endpoint: "/review-pr", tab: "review-tab" },
        "/improve": { endpoint: "/suggest-fixes", tab: "suggest-tab" },
        "/test": { endpoint: "/generate-tests", tab: "test-tab" },
    };

    const config = commandConfig[command];
    if (!config) {
        toolLoadingText.textContent = `Unknown command: ${command}`;
        toolBtns.forEach((b) => (b.disabled = false));
        return;
    }

    try {
        const resp = await fetch(`${BACKEND_URL}${config.endpoint}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
                repo_owner: currentPRInfo.owner,
                repo_name: currentPRInfo.repo,
                pr_number: currentPRInfo.number,
            }),
        });

        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        }

        const data = await resp.json();

        // Show results
        toolLoading.style.display = "none";
        toolResults.style.display = "block";

        // Render based on command
        switch (command) {
            case "/review":
                renderReviewResults(data);
                break;
            case "/improve":
                renderSuggestionResults(data);
                break;
            case "/test":
                renderTestResults(data);
                break;
        }

        // Switch to the relevant tab
        switchTab(config.tab);

    } catch (err) {
        toolLoadingText.textContent = `❌ ${command} failed: ${err.message}`;
        setTimeout(() => {
            toolLoading.style.display = "none";
        }, 3000);
    } finally {
        toolBtns.forEach((b) => (b.disabled = false));
    }
}

// ── Get Stored Token ─────────────────────────────────────────────────────────
function getStoredToken() {
    return new Promise((resolve) => {
        chrome.runtime.sendMessage({ type: "GET_TOKEN_STATUS" }, (resp) => {
            resolve(resp?.token || null);
        });
    });
}

// ── Render Review Results ────────────────────────────────────────────────────
function renderReviewResults(data) {
    // Score
    const scoreEl = document.getElementById("review-score");
    const score = data.score || 0;
    scoreEl.textContent = score;
    scoreEl.className = `score-value ${score >= 80 ? "score-high" : score >= 50 ? "score-medium" : "score-low"}`;

    // Effort
    const effortEl = document.getElementById("review-effort");
    effortEl.textContent = data.estimated_effort || "—";

    // Tests
    const testsEl = document.getElementById("review-tests-badge");
    const hasTests = (data.relevant_tests || "No").toLowerCase().includes("yes");
    testsEl.textContent = hasTests ? "✓" : "✗";
    testsEl.className = `score-value ${hasTests ? "score-high" : "score-low"}`;

    // Summary
    document.getElementById("review-summary").textContent = data.summary || "No summary available.";

    // Key Issues
    const issuesList = document.getElementById("issues-list");
    issuesList.innerHTML = "";

    const issues = data.key_issues || [];
    if (issues.length === 0) {
        issuesList.innerHTML = '<div class="issue-card"><div class="issue-content">✅ No major issues found</div></div>';
    } else {
        issues.forEach((issue) => {
            const severity = (issue.severity || "minor").toLowerCase();
            const card = document.createElement("div");
            card.className = `issue-card severity-${severity}`;
            card.innerHTML = `
                <div class="issue-header-row">
                    <span class="issue-title">${escapeHtml(issue.issue_header || "Issue")}</span>
                    <span class="severity-badge ${severity}">${severity}</span>
                </div>
                <div class="issue-content">${escapeHtml(issue.issue_content || "")}</div>
                ${issue.relevant_file ? `<div class="issue-file">${escapeHtml(issue.relevant_file)} (L${issue.start_line || "?"}–L${issue.end_line || "?"})</div>` : ""}
            `;
            issuesList.appendChild(card);
        });
    }

    // Security
    const securitySection = document.getElementById("review-security");
    const securityContent = document.getElementById("security-content");
    const securityText = data.security_concerns || "No";
    if (securityText.toLowerCase() === "no") {
        securitySection.style.display = "none";
    } else {
        securitySection.style.display = "block";
        securityContent.textContent = securityText;
    }
}

// ── Render Suggestion Results ────────────────────────────────────────────────
function renderSuggestionResults(data) {
    const suggestions = data.suggestions || [];
    document.getElementById("suggestions-count").textContent =
        `${suggestions.length} suggestion${suggestions.length !== 1 ? "s" : ""} found`;

    const list = document.getElementById("suggestions-list");
    list.innerHTML = "";

    if (suggestions.length === 0) {
        list.innerHTML = '<div class="suggestion-card"><div class="suggestion-summary">✅ No suggestions — code looks great!</div></div>';
        return;
    }

    suggestions.forEach((s) => {
        const labelClass = (s.label || "enhancement").toLowerCase().replace(/\s+/g, "-");
        const card = document.createElement("div");
        card.className = "suggestion-card";
        card.innerHTML = `
            <div class="suggestion-header">
                <span class="suggestion-label label-${labelClass}">${escapeHtml(s.label || "enhancement")}</span>
                <span class="suggestion-score">Score: ${s.score || "?"}/10</span>
            </div>
            <div class="suggestion-summary">${escapeHtml(s.one_sentence_summary || s.suggestion_content || "")}</div>
            ${s.existing_code || s.improved_code ? `
                <div class="suggestion-code">
                    ${s.existing_code ? `<div class="code-block code-before">- ${escapeHtml(s.existing_code)}</div>` : ""}
                    ${s.improved_code ? `<div class="code-block code-after">+ ${escapeHtml(s.improved_code)}</div>` : ""}
                </div>
            ` : ""}
            ${s.relevant_file ? `<div class="suggestion-file">📁 ${escapeHtml(s.relevant_file)}</div>` : ""}
        `;
        list.appendChild(card);
    });
}

// ── Render Test Results ──────────────────────────────────────────────────────
let allTestCode = "";

function renderTestResults(data) {
    const suites = data.test_suites || [];
    const totalTests = data.total_tests || 0;

    document.getElementById("tests-summary").textContent =
        `🧪 Generated ${totalTests} test${totalTests !== 1 ? "s" : ""} in ${suites.length} suite${suites.length !== 1 ? "s" : ""}`;

    const container = document.getElementById("tests-code");
    container.innerHTML = "";
    allTestCode = "";

    suites.forEach((suite) => {
        // Accumulate all test code
        const fullCode = [
            suite.setup_code || "",
            ...(suite.test_cases || []).map((tc) => tc.test_code || ""),
            suite.teardown_code || "",
        ]
            .filter(Boolean)
            .join("\n\n");
        allTestCode += `# === ${suite.test_file_name || "tests.py"} ===\n${fullCode}\n\n`;

        // Render individual test cases
        (suite.test_cases || []).forEach((tc) => {
            const typeClass = (tc.test_type || "unit").toLowerCase().replace(/\s+/g, "_");
            const card = document.createElement("div");
            card.className = "test-case-card";
            card.innerHTML = `
                <div class="test-case-header">
                    <span class="test-case-name">${escapeHtml(tc.test_name || "test_unnamed")}</span>
                    <span class="test-type-badge type-${typeClass}">${escapeHtml(tc.test_type || "unit")}</span>
                </div>
                <div class="test-case-desc">${escapeHtml(tc.test_description || "")}</div>
                <div class="test-case-code">${escapeHtml(tc.test_code || "# No test code generated")}</div>
            `;
            container.appendChild(card);
        });
    });

    // Show copy button
    const copyBtn = document.getElementById("copy-tests-btn");
    if (totalTests > 0) {
        copyBtn.style.display = "block";
    }
}

function copyAllTests() {
    const btn = document.getElementById("copy-tests-btn");
    navigator.clipboard.writeText(allTestCode).then(() => {
        btn.textContent = "✅ Copied!";
        setTimeout(() => {
            btn.textContent = "📋 Copy All Tests";
        }, 2000);
    });
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
    await Promise.all([checkBackendHealth(), detectCurrentPage()]);
    // Ensure token is ready before loading knowledge base docs
    await ensureToken();
    checkTokenStatus();
    initPRAgentTools();
    initKnowledgeBase();
})();

/**
 * Wait for the background script to have a valid token.
 * Retries a few times with a small delay since the background service worker
 * might still be exchanging the API key for a JWT.
 */
function ensureToken() {
    return new Promise((resolve) => {
        let attempts = 0;
        const maxAttempts = 5;

        function tryGetToken() {
            chrome.runtime.sendMessage({ type: "GET_TOKEN_STATUS" }, (resp) => {
                if (resp?.hasToken && resp.token) {
                    resolve(resp.token);
                } else if (++attempts < maxAttempts) {
                    setTimeout(tryGetToken, 400);
                } else {
                    resolve(null); // give up, let individual calls handle 401
                }
            });
        }

        tryGetToken();
    });
}


// ═══════════════════════════════════════════════════════════════════════════════
// Knowledge Base — File Upload & Documentation
// ═══════════════════════════════════════════════════════════════════════════════

const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const docsListKB = document.getElementById("docs-list-kb");
const uploadStatus = document.getElementById("upload-status");
const uploadStatusText = document.getElementById("upload-status-text");

function initKnowledgeBase() {
    // 1. Load initial docs
    refreshDocs();

    // 2. Refresh button
    document.getElementById("refresh-docs").addEventListener("click", refreshDocs);

    // 3. Drag & Drop events
    dropZone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) handleFileUpload(e.target.files[0]);
    });

    ["dragenter", "dragover", "dragleave", "drop"].forEach(name => {
        dropZone.addEventListener(name, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ["dragenter", "dragover"].forEach(name => {
        dropZone.addEventListener(name, () => dropZone.classList.add("drag-over"));
    });

    ["dragleave", "drop"].forEach(name => {
        dropZone.addEventListener(name, () => dropZone.classList.remove("drag-over"));
    });

    dropZone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        if (file) handleFileUpload(file);
    });

    // 4. URL ingestion
    document.getElementById("ingest-url-btn").addEventListener("click", handleUrlIngest);
    document.getElementById("url-input").addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleUrlIngest();
    });
}

async function handleUrlIngest() {
    const urlInput = document.getElementById("url-input");
    const url = urlInput.value.trim();
    if (!url) return;

    if (!url.startsWith("http")) {
        alert("Please enter a valid URL starting with http:// or https://");
        return;
    }

    const token = await getStoredToken();
    uploadStatus.style.display = "flex";
    uploadStatusText.textContent = `Scraping ${url}...`;

    try {
        const resp = await fetch(`${BACKEND_URL}/ingest-url`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ url }),
        });

        if (!resp.ok) {
            const errData = await resp.json();
            throw new Error(errData.detail || "URL ingestion failed");
        }

        uploadStatusText.textContent = "✅ URL Ingested!";
        urlInput.value = "";
        setTimeout(() => {
            uploadStatus.style.display = "none";
        }, 2000);

        refreshDocs();
    } catch (err) {
        uploadStatusText.textContent = `❌ ${err.message}`;
        setTimeout(() => {
            uploadStatus.style.display = "none";
        }, 4000);
    }
}

async function refreshDocs() {
    let token = await getStoredToken();

    // If no token yet, wait and retry once
    if (!token) {
        token = await ensureToken();
    }

    if (!token) {
        console.warn("[SWE-Agent] No auth token available — skipping doc list.");
        return;
    }

    try {
        const resp = await fetch(`${BACKEND_URL}/list-docs`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (resp.status === 401) {
            // Token expired — clear it so the next call re-fetches
            chrome.storage.local.remove(["jwt_token", "jwt_expires_at"]);
            return;
        }
        if (!resp.ok) return;
        const data = await resp.json();
        renderDocsList(data.documents || []);
    } catch (err) {
        console.error("Failed to fetch docs:", err);
    }
}

function renderDocsList(docs) {
    if (docs.length === 0) {
        docsListKB.innerHTML = '<div class="empty-docs">No documents uploaded yet.</div>';
        return;
    }

    docsListKB.innerHTML = "";
    docs.forEach(doc => {
        const date = new Date(doc.uploaded_at).toLocaleDateString();
        const icon = doc.filename.endsWith(".pdf") ? "📕" : "📄";
        const item = document.createElement("div");
        item.className = "doc-item";
        item.innerHTML = `
            <div class="doc-icon">${icon}</div>
            <div class="doc-info">
                <div class="doc-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</div>
                <div class="doc-date">Uploaded on ${date}</div>
            </div>
        `;
        docsListKB.appendChild(item);
    });
}

async function handleFileUpload(file) {
    const validTypes = [".pdf", ".md", ".txt"];
    const extension = "." + file.name.split(".").pop().toLowerCase();

    if (!validTypes.includes(extension)) {
        alert("Invalid file type. Please upload PDF, MD, or TXT.");
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        alert("File too large. Max 10MB.");
        return;
    }

    const token = await getStoredToken();
    uploadStatus.style.display = "flex";
    uploadStatusText.textContent = `Uploading ${file.name}...`;

    const formData = new FormData();
    formData.append("file", file);

    try {
        const resp = await fetch(`${BACKEND_URL}/upload-doc`, {
            method: "POST",
            headers: (token ? { Authorization: `Bearer ${token}` } : {}),
            body: formData,
        });

        if (!resp.ok) {
            const errData = await resp.json();
            throw new Error(errData.detail || "Upload failed");
        }

        uploadStatusText.textContent = "✅ Success!";
        setTimeout(() => {
            uploadStatus.style.display = "none";
        }, 2000);

        refreshDocs();
    } catch (err) {
        uploadStatusText.textContent = `❌ ${err.message}`;
        setTimeout(() => {
            uploadStatus.style.display = "none";
        }, 4000);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PR Chat — Conversational Q&A about PR code
// ═══════════════════════════════════════════════════════════════════════════════

let chatHistory = []; // { role: 'user'|'assistant', content: string }

function initPRChat() {
    if (!currentPRInfo) return;

    const chatPanel = document.getElementById("pr-chat-panel");
    const chatInput = document.getElementById("chat-input");
    const chatSendBtn = document.getElementById("chat-send-btn");
    const chatSuggestions = document.getElementById("chat-suggestions");

    chatPanel.style.display = "block";

    // Send button
    chatSendBtn.addEventListener("click", () => sendChatMessage());

    // Enter key
    chatInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // Quick action chips
    chatSuggestions.querySelectorAll(".chat-chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            chatInput.value = chip.dataset.msg;
            sendChatMessage();
        });
    });
}

async function sendChatMessage() {
    const chatInput = document.getElementById("chat-input");
    const message = chatInput.value.trim();
    if (!message || !currentPRInfo) return;

    const chatMessages = document.getElementById("chat-messages");
    const chatTyping = document.getElementById("chat-typing");
    const chatSendBtn = document.getElementById("chat-send-btn");
    const chatSuggestions = document.getElementById("chat-suggestions");

    // Clear welcome message on first send
    const welcome = chatMessages.querySelector(".chat-welcome");
    if (welcome) welcome.remove();

    // Hide suggestion chips after first message
    chatSuggestions.style.display = "none";

    // Add user message bubble
    appendChatMsg("user", message);
    chatHistory.push({ role: "user", content: message });

    // Clear input & disable
    chatInput.value = "";
    chatInput.disabled = true;
    chatSendBtn.disabled = true;

    // Show typing indicator
    chatTyping.style.display = "flex";
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Get token
    const token = await getStoredToken();

    try {
        const resp = await fetch(`${BACKEND_URL}/chat-pr`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
                repo_owner: currentPRInfo.owner,
                repo_name: currentPRInfo.repo,
                pr_number: currentPRInfo.number,
                message: message,
                history: chatHistory.slice(0, -1), // exclude current msg (sent separately)
            }),
        });

        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        }

        const data = await resp.json();
        const reply = data.reply || "Sorry, I couldn't generate a response.";

        // Add AI response bubble
        appendChatMsg("assistant", reply);
        chatHistory.push({ role: "assistant", content: reply });

    } catch (err) {
        appendChatMsg("assistant", `❌ Error: ${err.message}. Make sure the backend is running.`);
    } finally {
        chatTyping.style.display = "none";
        chatInput.disabled = false;
        chatSendBtn.disabled = false;
        chatInput.focus();
    }
}

function appendChatMsg(role, content) {
    const chatMessages = document.getElementById("chat-messages");
    const msg = document.createElement("div");
    msg.className = `chat-msg ${role}`;

    const avatar = role === "user" ? "👤" : "🤖";
    const formattedContent = role === "assistant" ? renderMarkdownLight(content) : escapeHtml(content);

    msg.innerHTML = `
        <div class="chat-avatar">${avatar}</div>
        <div class="chat-bubble">${formattedContent}</div>
    `;

    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Lightweight markdown renderer for chat responses.
 * Handles: code blocks, inline code, bold, italic, lists.
 */
function renderMarkdownLight(text) {
    let html = escapeHtml(text);

    // Code blocks: ```lang\n...\n```
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Inline code: `...`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold: **...**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic: *...*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Bullet lists: lines starting with - or *
    html = html.replace(/^[\-\*] (.+)$/gm, '• $1');

    return html;
}

// ── Utility ──────────────────────────────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
