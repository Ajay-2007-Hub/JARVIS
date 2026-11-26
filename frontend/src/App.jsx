import { useEffect, useRef, useState } from "react";

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return data;
}

export default function App() {
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [autoStartEnabled, setAutoStartEnabled] = useState(null);
  const [autoStartError, setAutoStartError] = useState("");
  const [autoStartLoading, setAutoStartLoading] = useState(true);
  const [autoStartRequesting, setAutoStartRequesting] = useState(false);
  const [autoStartApproval, setAutoStartApproval] = useState(null);
  const autoStartApprovalRef = useRef(null);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approvals, setApprovals] = useState([]);
  const [health, setHealth] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busyApproval, setBusyApproval] = useState("");

  async function refreshAutoStartStatus(isActive = () => true) {
    if (isActive()) setAutoStartLoading(true);
    try {
      const data = await fetchJson("/api/settings/autostart");
      if (!isActive()) return;
      if (typeof data.enabled !== "boolean") {
        setAutoStartEnabled(null);
        setAutoStartError(data.error || "Auto-start status is unavailable.");
      } else {
        setAutoStartEnabled(data.enabled);
        setAutoStartError("");
      }
    } catch (requestError) {
      if (isActive()) {
        setAutoStartEnabled(null);
        setAutoStartError(requestError.message);
      }
    } finally {
      if (isActive()) setAutoStartLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function refreshHealth() {
      try {
        const data = await fetchJson("/health");
        if (active) setHealth(data);
      } catch {
        if (active) setHealth(null);
      }
    }

    refreshHealth();
    const timer = window.setInterval(refreshHealth, 10000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let active = true;
    refreshAutoStartStatus(() => active);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!approvalOpen && !autoStartApproval) return undefined;
    let active = true;

    async function refreshApprovals() {
      try {
        const data = await fetchJson("/api/approvals");
        if (!active) return;
        setApprovals(data.pending);
        const trackedApproval = autoStartApprovalRef.current;
        if (
          trackedApproval &&
          !data.pending.some((approval) => approval.id === trackedApproval.id)
        ) {
          autoStartApprovalRef.current = null;
          await refreshAutoStartStatus();
          setAutoStartApproval(null);
          setNotice("Auto-start approval resolved.");
        }
      } catch (requestError) {
        if (active) setError(requestError.message);
      }
    }

    refreshApprovals();
    const timer = window.setInterval(refreshApprovals, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [approvalOpen, autoStartApproval]);

  async function sendMessage(event) {
    event.preventDefault();
    setError("");
    try {
      const response = await fetchJson("/api/chat", { method: "POST" });
      setReply(response.reply);
      setMessage("");
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function requestAutoStartChange(event) {
    if (autoStartApprovalRef.current || autoStartRequesting) return;
    const enabled = event.target.checked;
    setError("");
    setAutoStartError("");
    setNotice("");
    setAutoStartRequesting(true);
    try {
      const data = await fetchJson("/api/settings/autostart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const pendingApproval = { id: data.approval.id, enabled };
      autoStartApprovalRef.current = pendingApproval;
      setAutoStartApproval(pendingApproval);
      setNotice("Waiting for approval - open Review approvals");
      setApprovalOpen(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setAutoStartRequesting(false);
    }
  }

  async function decideApproval(approvalId, decision) {
    setBusyApproval(approvalId);
    setError("");
    try {
      const data = await fetchJson(
        `/api/approvals/${approvalId}/${decision}`,
        { method: "POST" },
      );
      setApprovals((current) =>
        current.filter((approval) => approval.id !== approvalId),
      );
      setNotice(
        decision === "approve"
          ? `${data.approval.action.replaceAll("_", " ")} approved.`
          : "Approval denied.",
      );
      const isAutoStartApproval =
        data.approval.action === "enable_autostart" ||
        data.approval.action === "disable_autostart";
      if (isAutoStartApproval) {
        if (decision === "approve") {
          setAutoStartEnabled(data.approval.action === "enable_autostart");
          setAutoStartError("");
        }
        if (autoStartApprovalRef.current?.id === approvalId) {
          autoStartApprovalRef.current = null;
          setAutoStartApproval(null);
        }
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusyApproval("");
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">LOCAL AI ASSISTANT</p>
          <h1>JARVIS</h1>
        </div>
        <div className="health-badges" aria-live="polite">
          <span className={`badge ${health ? "online" : "offline"}`}>
            Backend {health ? "online" : "offline"}
          </span>
          <span className={`badge ${health?.ollama_ok ? "online" : "offline"}`}>
            Ollama {health?.ollama_ok ? "online" : "offline"}
          </span>
          {health?.ollama_ok && (
            <span className={`badge ${health.model_loaded ? "online" : "offline"}`}>
              Model {health.model_loaded ? "loaded" : "not loaded"}
            </span>
          )}
        </div>
      </header>

      <section className="chat-panel">
        <section className="conversation" aria-live="polite">
          {reply ? <p className="reply">{reply}</p> : <p className="empty">Your conversation will appear here.</p>}
        </section>
        <form onSubmit={sendMessage}>
          <label className="visually-hidden" htmlFor="message">Message</label>
          <input
            id="message"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Ask JARVIS something..."
          />
          <button type="submit" disabled={!message.trim()}>Send</button>
        </form>
      </section>

      <section className="settings-panel" aria-labelledby="settings-title">
        <div>
          <p className="eyebrow">PREFERENCES</p>
          <h2 id="settings-title">Settings</h2>
          <label className="switch-row">
            <span>Start JARVIS when I sign in</span>
            <input
              type="checkbox"
              role="switch"
              checked={
                autoStartApproval
                  ? autoStartApproval.enabled
                  : Boolean(autoStartEnabled)
              }
              disabled={autoStartRequesting}
              onChange={requestAutoStartChange}
            />
          </label>
          {autoStartError && (
            <div className="autostart-error">
              <p className="error" role="alert">{autoStartError}</p>
              <button
                type="button"
                className="secondary-button"
                disabled={autoStartLoading}
                onClick={() => refreshAutoStartStatus()}
              >
                {autoStartLoading ? "Retrying..." : "Retry"}
              </button>
            </div>
          )}
        </div>
        <button className="secondary-button" onClick={() => setApprovalOpen(true)}>
          Review approvals
        </button>
      </section>

      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {approvalOpen && (
        <div className="dialog-backdrop">
          <section
            className="approval-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="approval-title"
          >
            <div className="dialog-heading">
              <div>
                <p className="eyebrow">ACTION REVIEW</p>
                <h2 id="approval-title">Pending approvals</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close approvals"
                onClick={() => setApprovalOpen(false)}
              >
                ×
              </button>
            </div>
            {autoStartApproval && (
              <p className="notice" role="status">
                Waiting for approval - open Review approvals
              </p>
            )}
            {approvals.length === 0 ? (
              <p className="empty">No pending approvals.</p>
            ) : (
              <ul className="approval-list">
                {approvals.map((approval) => (
                  <li key={approval.id}>
                    <p>{approval.description}</p>
                    <div className="approval-actions">
                      <button
                        disabled={busyApproval === approval.id}
                        onClick={() => decideApproval(approval.id, "approve")}
                      >
                        Approve
                      </button>
                      <button
                        className="secondary-button"
                        disabled={busyApproval === approval.id}
                        onClick={() => decideApproval(approval.id, "deny")}
                      >
                        Deny
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
