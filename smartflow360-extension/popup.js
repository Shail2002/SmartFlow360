const API_BASE = "http://127.0.0.1:8000";

const apiBaseText = document.getElementById("apiBaseText");
apiBaseText.textContent = API_BASE;

const notes = document.getElementById("notes");
const voiceAddon = document.getElementById("voiceAddon");
const fileEl = document.getElementById("file");

const extractBtn = document.getElementById("extractBtn");
const analyzeBtn = document.getElementById("analyzeBtn");
const clearBtn = document.getElementById("clearBtn");

const startDictate = document.getElementById("startDictate");
const stopDictate = document.getElementById("stopDictate");
const dictationStatus = document.getElementById("dictationStatus");

const emailInput = document.getElementById("email");
const emailBtn = document.getElementById("emailBtn");

const statusEl = document.getElementById("status");
const outEl = document.getElementById("out");

let lastResult = null;

// ---------- helpers ----------
function setStatus(msg) {
  statusEl.textContent = msg || "";
}
function setOutput(obj) {
  outEl.textContent = obj ? JSON.stringify(obj, null, 2) : "";
}
function mergedText() {
  const base = (notes.value || "").trim();
  const extra = (voiceAddon.value || "").trim();
  return [base, extra].filter(Boolean).join("\n\n--- Voice add-on ---\n");
}

// ---------- dictation ----------
// ---------- Dictation (robust) ----------
let recognition = null;
let isDictating = false;

async function ensureMicPermission() {
  // This forces Chrome to ask permission if not granted
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  // We only need permission; stop immediately to avoid keeping mic open
  stream.getTracks().forEach(t => t.stop());
}

function setupDictation() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SR) {
    startDictate.disabled = true;
    stopDictate.disabled = true;
    dictationStatus.textContent = "SpeechRecognition not supported in this browser.";
    return;
  }

  recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  let finalText = "";

  recognition.onstart = () => {
    isDictating = true;
    dictationStatus.textContent = "Dictation running… speak now.";
    startDictate.disabled = true;
    stopDictate.disabled = false;
  };

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += t + " ";
      else interim += t;
    }
    voiceAddon.value = (finalText + interim).trim();
  };

  recognition.onerror = (e) => {
    // Common errors: not-allowed, service-not-allowed, no-speech, audio-capture
    dictationStatus.textContent = `Dictation error: ${e.error}. (Allow microphone access)`;
    isDictating = false;
    startDictate.disabled = false;
    stopDictate.disabled = true;
  };

  recognition.onend = () => {
    // If it ends immediately, you will see it here.
    isDictating = false;
    startDictate.disabled = false;
    stopDictate.disabled = true;

    // If it ended instantly with no text, guide the user
    if (!voiceAddon.value.trim()) {
      dictationStatus.textContent = "Dictation stopped (mic blocked or popup lost focus). Try again after allowing mic.";
    } else {
      dictationStatus.textContent = "Dictation stopped.";
    }
  };

  startDictate.addEventListener("click", async () => {
    try {
      dictationStatus.textContent = "Requesting microphone permission…";
      await ensureMicPermission();

      finalText = "";
      voiceAddon.value = "";

      // Start recognition AFTER mic permission
      recognition.start();
    } catch (err) {
      dictationStatus.textContent = "Microphone permission denied. Enable mic for Chrome and try again.";
    }
  });

  stopDictate.addEventListener("click", () => {
    try { recognition.stop(); } catch {}
  });
}

setupDictation();

// ---------- extract file ----------
extractBtn.addEventListener("click", async () => {
  setStatus("");
  const f = fileEl.files?.[0];
  if (!f) return setStatus("Choose a file first.");

  const fd = new FormData();
  fd.append("file", f);

  setStatus("Extracting…");
  try {
    const r = await fetch(`${API_BASE}/api/extract`, {
      method: "POST",
      body: fd
    });

    const text = await r.text();
    if (!r.ok) {
      // show backend message
      return setStatus(text);
    }
    const data = JSON.parse(text);

    notes.value = data.text || "";
    setStatus(`Loaded ${data.filename} (${data.chars} chars)${data.truncated ? " (truncated)" : ""}`);
  } catch (e) {
    setStatus("Extract failed: " + (e.message || e));
  }
});

// ---------- analyze ----------
analyzeBtn.addEventListener("click", async () => {
  setStatus("");
  const text = mergedText();
  if (!text) return setStatus("Add notes or dictation first.");

  setStatus("Analyzing…");
  try {
    const r = await fetch(`${API_BASE}/api/ext/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, title: "Chrome Extension" })
    });

    const raw = await r.text();
    if (!r.ok) return setStatus(raw);

    lastResult = JSON.parse(raw);
    setOutput(lastResult);
    setStatus("Done ✅");
    emailBtn.disabled = false;
  } catch (e) {
    setStatus("Analyze failed: " + (e.message || e));
  }
});

// ---------- email PDF report ----------
emailBtn.addEventListener("click", async () => {
  setStatus("");
  const to = (emailInput.value || "").trim();
  if (!to) return setStatus("Enter your email first.");
  if (!lastResult) return setStatus("Run Analyze first.");

  setStatus("Sending email…");
  try {
    const payload = {
      to_email: to,
      subject: "SmartFlow360 - Analysis Report",
      summary: lastResult.summary || "",
      full_json: lastResult
    };

    const r = await fetch(`${API_BASE}/api/ext/email-report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const raw = await r.text();
    if (!r.ok) return setStatus(raw);

    setStatus("Email sent ✅ (check inbox/spam)");
  } catch (e) {
    setStatus("Email failed: " + (e.message || e));
  }
});

// ---------- clear ----------
clearBtn.addEventListener("click", () => {
  notes.value = "";
  voiceAddon.value = "";
  fileEl.value = "";
  setOutput(null);
  setStatus("Cleared.");
  lastResult = null;
  emailBtn.disabled = true;
});