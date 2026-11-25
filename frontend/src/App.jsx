import { useEffect, useState } from "react";

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
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approvals, setApprovals] = useState([]);
  const [health, setHealth] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busyApproval, setBusyApproval] = useState("");

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
    fetchJson("/api/settings/autostart")
      .then((data) => {
        if (active) setAutoStartEnabled(data.enabled);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!approvalOpen) return undefined;
    let active = true;

    async function refreshApprovals() {
      try {
        const data = await fetchJson("/api/approvals");
        if (active) setApprovals(data.pending);
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
  }, [approvalOpen]);

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
    const enabled = event.target.checked;
    setError("");
    setNotice("");
    try {
      await fetchJson("/api/settings/autostart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      setNotice("Approval requested. Approve the change to apply it.");
      setApprovalOpen(true);
    } catch (requestError) {
      setError(requestError.message);
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
      if (data.approval.action === "enable_autostart" && decision === "approve") {
        setAutoStartEnabled(true);
      }
      if (data.approval.action === "disable_autostart" && decision === "approve") {
        setAutoStartEnabled(false);
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
              checked={Boolean(autoStartEnabled)}
              disabled={autoStartEnabled === null}
              onChange={requestAutoStartChange}
            />
          </label>
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
