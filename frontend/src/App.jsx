import { useState } from "react";

export default function App() {
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");

  async function sendMessage(event) {
    event.preventDefault();
    const response = await fetch("/api/chat", { method: "POST" });
    const data = await response.json();
    setReply(data.reply);
    setMessage("");
  }

  return (
    <main className="chat">
      <header>
        <p className="eyebrow">LOCAL AI ASSISTANT</p>
        <h1>JARVIS</h1>
      </header>
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
    </main>
  );
}
