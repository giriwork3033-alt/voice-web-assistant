import { useState } from "react";
import { createRoot } from "react-dom/client";
import LiveAvatarPanel from "./components/LiveAvatarPanel";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function AvatarTestPage() {
  const [audioBase64, setAudioBase64] = useState(null);
  const [status, setStatus] = useState("");

  const fetchTestAudio = async () => {
    setStatus("Fetching test speech...");
    try {
      const res = await fetch(`${API}/ask-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "Hello, this is a test." }),
      });
      const data = await res.json();
      setAudioBase64(data.audio_base64);
      setStatus("Got test audio - now click Start LiveAvatar session below.");
    } catch (err) {
      setStatus(`Failed to fetch test audio: ${err}`);
    }
  };

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h2>LiveAvatar test page (temporary)</h2>
      <button onClick={fetchTestAudio}>Generate test speech</button>
      <p>{status}</p>
      <LiveAvatarPanel audioBase64={audioBase64} apiBaseUrl={API} />
    </div>
  );
}

createRoot(document.getElementById("root")).render(<AvatarTestPage />);
