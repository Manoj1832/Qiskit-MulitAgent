/**
 * SWE-Agent Copilot — Background Service Worker
 *
 * Responsibilities:
 *  1. Authenticate with the backend (exchange API key for JWT)
 *  2. Handle ANALYZE_ISSUE / ANALYZE_PR messages from content.js
 *  3. Open SSE connection to the backend and relay events to the popup
 *  4. Manage token lifecycle (auto-refresh before expiry)
 */

const BACKEND_URL = "http://localhost:8000";
const EXTENSION_API_KEY = "swe-agent-dev-key-change-in-prod";

// ── Token Management ──────────────────────────────────────────────────────────

async function getToken() {
    const stored = await chrome.storage.local.get(["jwt_token", "jwt_expires_at"]);
    const now = Date.now();

    // Return cached token if still valid (with 60s buffer)
    if (stored.jwt_token && stored.jwt_expires_at && stored.jwt_expires_at - now > 60000) {
        return stored.jwt_token;
    }

    // Fetch new token
    try {
        const resp = await fetch(`${BACKEND_URL}/token`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: EXTENSION_API_KEY }),
        });

        if (!resp.ok) {
            throw new Error(`Token fetch failed: ${resp.status}`);
        }

        const data = await resp.json();
        const expiresAt = now + data.expires_in * 1000;

        await chrome.storage.local.set({
            jwt_token: data.access_token,
            jwt_expires_at: expiresAt,
        });

        console.log("[SWE-Agent] JWT token refreshed");
        return data.access_token;
    } catch (err) {
        console.error("[SWE-Agent] Token fetch error:", err);
        throw err;
    }
}

// ── SSE Streaming ─────────────────────────────────────────────────────────────

async function streamAnalysis(endpoint, payload, tabId) {
    let token;
    try {
        token = await getToken();
    } catch (err) {
        sendToTab(tabId, { event: "error", data: { message: "Backend authentication failed. Is the backend running?" } });
        return;
    }

    try {
        const resp = await fetch(`${BACKEND_URL}${endpoint}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`,
                "Accept": "text/event-stream",
            },
            body: JSON.stringify(payload),
        });

        if (!resp.ok) {
            const errText = await resp.text();
            sendToTab(tabId, { event: "error", data: { message: `Backend error ${resp.status}: ${errText}` } });
            return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // Keep incomplete line in buffer

            let currentEvent = "message";
            let currentData = "";

            for (const line of lines) {
                if (line.startsWith("event:")) {
                    currentEvent = line.slice(6).trim();
                } else if (line.startsWith("data:")) {
                    currentData = line.slice(5).trim();
                } else if (line === "") {
                    // Empty line = end of event
                    if (currentData) {
                        try {
                            const parsed = JSON.parse(currentData);
                            sendToTab(tabId, { event: currentEvent, data: parsed });
                        } catch (e) {
                            sendToTab(tabId, { event: currentEvent, data: { raw: currentData } });
                        }
                        currentEvent = "message";
                        currentData = "";
                    }
                }
            }
        }
    } catch (err) {
        console.error("[SWE-Agent] Stream error:", err);
        sendToTab(tabId, {
            event: "error",
            data: { message: `Connection error: ${err.message}. Make sure the backend is running on ${BACKEND_URL}` },
        });
    }
}

function sendToTab(tabId, message) {
    chrome.tabs.sendMessage(tabId, { type: "SWE_AGENT_EVENT", ...message }).catch(() => {
        // Tab might be closed — also broadcast to popup
        chrome.runtime.sendMessage({ type: "SWE_AGENT_EVENT", ...message }).catch(() => { });
    });
}

// ── Message Handler ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const tabId = sender.tab?.id;

    if (message.type === "ANALYZE_ISSUE") {
        console.log("[SWE-Agent] Analyzing issue:", message.payload);
        streamAnalysis("/analyze-issue", message.payload, tabId);
        sendResponse({ status: "started" });
        return true;
    }

    if (message.type === "ANALYZE_PR") {
        console.log("[SWE-Agent] Analyzing PR:", message.payload);
        streamAnalysis("/analyze-pr", message.payload, tabId);
        sendResponse({ status: "started" });
        return true;
    }

    if (message.type === "CREATE_PR") {
        (async () => {
            try {
                const token = await getToken();
                const params = new URLSearchParams({
                    repo_owner: message.payload.repo_owner,
                    repo_name: message.payload.repo_name,
                    issue_number: message.payload.issue_number,
                    patch_diff: message.payload.patch_diff,
                });
                const resp = await fetch(`${BACKEND_URL}/create-pr?${params}`, {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${token}` },
                });
                const data = await resp.json();
                sendResponse({ success: resp.ok, data });
            } catch (err) {
                sendResponse({ success: false, error: err.message });
            }
        })();
        return true;
    }

    if (message.type === "GET_TOKEN_STATUS") {
        getToken().then((token) => {
            chrome.storage.local.get(["jwt_expires_at"]).then((stored) => {
                sendResponse({
                    hasToken: !!token,
                    expiresAt: stored.jwt_expires_at,
                    token: token,
                });
            });
        }).catch((err) => {
            sendResponse({ hasToken: false, error: err.message });
        });
        return true;
    }
});

// ── Install Handler ───────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
    console.log("[SWE-Agent] Extension installed. Pre-fetching auth token...");
    try {
        await getToken();
        console.log("[SWE-Agent] Auth token ready.");
    } catch (err) {
        console.warn("[SWE-Agent] Could not pre-fetch token (backend may not be running yet):", err.message);
    }
});
