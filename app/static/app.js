const api = {
  async getAccounts() {
    const r = await fetch('/api/accounts');
    return r.json();
  },
  async createAccount(name, industry) {
    const r = await fetch('/api/accounts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, industry: industry || null})
    });
    return r.json();
  },
  async accountDetail(accountId) {
    const r = await fetch(`/api/accounts/${accountId}`);
    return r.json();
  },
  async createInteraction(accountId, raw_text, source) {
    const r = await fetch(`/api/accounts/${accountId}/interactions`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({raw_text, source})
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async extractFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/extract", { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
  },
  async analyze(interactionId) {
    const r = await fetch(`/api/interactions/${interactionId}/analyze`, {method: 'POST'});
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async completeTask(taskId) {
    const r = await fetch(`/api/tasks/${taskId}/complete`, {method: 'POST'});
    return r.json();
  },
  taskIcsUrl(taskId) {
    return `/api/tasks/${taskId}/ics`;
  },
  async ask(accountId, question, mode) {
    const r = await fetch(`/api/ask`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({account_id: accountId, question, mode})
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
};

let state = {
  accounts: [],
  selectedAccountId: null,
  lastInteractionId: null,
  busyMode: false
};

// Elements
const accountForm = document.getElementById('accountForm');
const accountName = document.getElementById('accountName');
const accountIndustry = document.getElementById('accountIndustry');
const accountSelect = document.getElementById('accountSelect');
const refreshBtn = document.getElementById('refreshBtn');
const accountMeta = document.getElementById('accountMeta');

const fileUpload = document.getElementById('fileUpload');
const extractBtn = document.getElementById('extractBtn');
const fileStatus = document.getElementById('fileStatus');

const notes = document.getElementById('notes');
const saveInteractionBtn = document.getElementById('saveInteractionBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const interactionStatus = document.getElementById('interactionStatus');
const clearNotesBtn = document.getElementById('clearNotesBtn');

const results = document.getElementById('results');

const contrastBtn = document.getElementById('contrastBtn');
const dyslexiaBtn = document.getElementById('dyslexiaBtn');
const busyBtn = document.getElementById('busyBtn');

const dictateBtn = document.getElementById('dictateBtn');
const stopDictateBtn = document.getElementById('stopDictateBtn');
const dictationStatus = document.getElementById('dictationStatus');

const askBtn = document.getElementById('askBtn');
const questionEl = document.getElementById('question');
const askMode = document.getElementById('askMode');
const askAnswer = document.getElementById('askAnswer');

// Accessibility toggles
contrastBtn.addEventListener('click', () => {
  document.body.classList.toggle('high-contrast');
  const pressed = document.body.classList.contains('high-contrast');
  contrastBtn.setAttribute('aria-pressed', String(pressed));
});

dyslexiaBtn.addEventListener('click', () => {
  document.body.classList.toggle('dyslexia');
  const pressed = document.body.classList.contains('dyslexia');
  dyslexiaBtn.setAttribute('aria-pressed', String(pressed));
});

busyBtn.addEventListener('click', () => {
  state.busyMode = !state.busyMode;
  busyBtn.setAttribute('aria-pressed', String(state.busyMode));
  busyBtn.textContent = state.busyMode ? 'Busy mode: ON' : 'Busy mode';
});

// Load accounts
async function loadAccounts() {
  state.accounts = await api.getAccounts();
  renderAccounts();
}

function renderAccounts() {
  accountSelect.innerHTML = '';
  if (state.accounts.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No accounts yet';
    accountSelect.appendChild(opt);
    state.selectedAccountId = null;
    return;
  }

  state.accounts.forEach(a => {
    const opt = document.createElement('option');
    opt.value = a.id;
    opt.textContent = a.name;
    accountSelect.appendChild(opt);
  });

  if (!state.selectedAccountId) state.selectedAccountId = state.accounts[0].id;
  accountSelect.value = String(state.selectedAccountId);
  renderAccountMeta();
}

async function renderAccountMeta() {
  if (!state.selectedAccountId) return;
  const data = await api.accountDetail(state.selectedAccountId);
  const a = data.account;
  const tasksOpen = (data.tasks || []).filter(t => t.status === 'Open').length;
  accountMeta.textContent = `Selected: ${a.name} • Open tasks: ${tasksOpen}`;
}

accountSelect.addEventListener('change', async (e) => {
  state.selectedAccountId = Number(e.target.value);
  state.lastInteractionId = null;
  interactionStatus.textContent = '';
  results.innerHTML = '<p class="small">Run Analyze to generate results.</p>';
  await renderAccountMeta();
});

refreshBtn.addEventListener('click', async () => {
  await loadAccounts();
  await renderAccountMeta();
});

// Create account
accountForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const created = await api.createAccount(accountName.value.trim(), accountIndustry.value.trim());
  accountName.value = '';
  accountIndustry.value = '';
  await loadAccounts();
  state.selectedAccountId = created.id;
  accountSelect.value = String(created.id);
  await renderAccountMeta();
});

// Save interaction
saveInteractionBtn.addEventListener('click', async () => {
  interactionStatus.textContent = '';
  if (!state.selectedAccountId) {
    interactionStatus.textContent = 'Create/select an account first.';
    return;
  }
  const text = notes.value.trim();
  if (!text) {
    interactionStatus.textContent = 'Please paste notes or dictate first.';
    return;
  }
  const source = isDictated(text) ? 'voice' : 'notes';
  const inter = await api.createInteraction(state.selectedAccountId, text, source);
  state.lastInteractionId = inter.id;
  interactionStatus.textContent = `Saved interaction #${inter.id}.`;

  // notes.value = '';
  // dictationStatus.textContent = 'Ready for new notes.';
});

function isDictated(text) {
  return dictationStatus.textContent.includes('dictation') && text.length > 0;
}

extractBtn?.addEventListener('click', async () => {
  fileStatus.textContent = '';
  const f = fileUpload?.files?.[0];
  if (!f) {
    fileStatus.textContent = 'Choose a file first.';
    return;
  }

  try {
    fileStatus.textContent = 'Extracting…';
    const resp = await api.extractFile(f);

    notes.value = resp.text || '';
    interactionStatus.textContent = `Loaded notes from ${resp.filename}${resp.truncated ? ' (truncated)' : ''}.`;
    fileStatus.textContent = `Loaded ${resp.chars} characters.`;
    notes.focus();
  } catch (e) {
    fileStatus.textContent = 'Error extracting file.';
    interactionStatus.textContent = `Error: ${e.message || e}`;
  }
});

clearNotesBtn?.addEventListener('click', () => {
  notes.value = '';
  if (fileUpload) fileUpload.value = '';
  interactionStatus.textContent = '';
  dictationStatus.textContent = 'Cleared.';
  state.lastInteractionId = null;
  notes.focus();
});

// Analyze
analyzeBtn.addEventListener('click', async () => {
  interactionStatus.textContent = '';
  if (!state.lastInteractionId) {
    interactionStatus.textContent = 'Save an interaction first, then Analyze.';
    return;
  }
  try {
    interactionStatus.textContent = 'Analyzing…';
    const out = await api.analyze(state.lastInteractionId);
    interactionStatus.textContent = 'Done.';
    renderResults(out);
    await renderAccountMeta();
  } catch (err) {
    interactionStatus.textContent = `Error: ${err.message || err}`;
  }
});

function esc(s) {
  return (s || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

function renderResults(out) {
  const busyBullets = out.busy_bullets || [];
  const nextActions = out.next_actions || [];
  const summary = out.summary || '';
  const tasks = out.tasks || [];
  const email = out.email_draft || {};
  const risk = out.risk || {};

  const showBusy = state.busyMode;

  const busyHtml = `
    <div class="kv">
      <h3>Explain like I'm busy (5 bullets)</h3>
      <ul class="list">
        ${busyBullets.map(b => `<li>${esc(b)}</li>`).join('')}
      </ul>
    </div>
  `;

  const summaryHtml = `
    <div class="kv">
      <h3>Summary</h3>
      <p class="small">${esc(summary)}</p>
    </div>
  `;

  const nextHtml = `
    <div class="kv">
      <h3>Next actions</h3>
      <ul class="list">
        ${nextActions.map(a => `<li>${esc(a)}</li>`).join('')}
      </ul>
    </div>
  `;

  const tasksHtml = `
    <div class="kv">
      <h3>Tasks</h3>
      <ul class="list">
        ${tasks.map(t => {
          const due = t.due_date ? ` • due ${t.due_date}` : '';
          const ics = t.due_date ? `<a class="small" href="${api.taskIcsUrl(t.id)}">Download .ics</a>` : `<span class="small">(no date)</span>`;
          return `
            <li>
              <strong>${esc(t.title)}</strong>
              <span class="small"> • ${esc(t.priority)}${due}</span>
              <div class="row">
                <button class="btn" data-complete="${t.id}" type="button">Mark done</button>
                ${ics}
              </div>
              <div class="small">${esc(t.rationale || '')}</div>
            </li>
          `;
        }).join('')}
      </ul>
    </div>
  `;

  const riskHtml = `
    <div class="kv">
      <h3>Risk score</h3>
      <p class="small"><strong>${esc(String(risk.score ?? '—'))}/100</strong></p>
      <ul class="list">
        ${(risk.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}
      </ul>
    </div>
  `;

  const emailHtml = `
    <div class="kv">
      <h3>Follow-up email draft</h3>
      <p class="small"><strong>Subject:</strong> ${esc(email.subject || '')}</p>

      <div class="row">
        <button class="btn" type="button" data-copy="email">Copy email</button>
        <button class="btn" type="button" data-copy="simple">Copy simplified email</button>
      </div>

      <pre class="pre" id="emailBody">${esc(email.body || '')}</pre>

      <h3>Dyslexia-friendly version</h3>
      <pre class="pre" id="emailSimple">${esc(email.simplified_body || '')}</pre>
    </div>
  `;

  results.innerHTML = [
    showBusy ? busyHtml : '',
    summaryHtml,
    nextHtml,
    tasksHtml,
    riskHtml,
    emailHtml
  ].join('');

  // Bind buttons
  results.querySelectorAll('[data-complete]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = Number(btn.getAttribute('data-complete'));
      await api.completeTask(id);
      btn.textContent = 'Done ✓';
      btn.disabled = true;
      await renderAccountMeta();
    });
  });

  results.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const which = btn.getAttribute('data-copy');
      const text = which === 'simple'
        ? document.getElementById('emailSimple').textContent
        : document.getElementById('emailBody').textContent;
      await navigator.clipboard.writeText(text);
      btn.textContent = 'Copied ✓';
      setTimeout(() => btn.textContent = which === 'simple' ? 'Copy simplified email' : 'Copy email', 1400);
    });
  });
}

// Ask
askBtn.addEventListener('click', async () => {
  askAnswer.textContent = '';
  if (!state.selectedAccountId) {
    askAnswer.textContent = 'Select an account first.';
    return;
  }
  const q = questionEl.value.trim();
  if (!q) {
    askAnswer.textContent = 'Type a question.';
    return;
  }
  askAnswer.textContent = 'Thinking…';
  try {
    const resp = await api.ask(state.selectedAccountId, q, askMode.value);
    askAnswer.textContent = resp.answer || '';
  } catch (e) {
    askAnswer.textContent = `Error: ${e.message || e}`;
  }
});

// Voice dictation: Web Speech API (client-side)
let recognition = null;
function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    dictateBtn.disabled = true;
    stopDictateBtn.disabled = true;
    dictationStatus.textContent = 'Dictation not supported in this browser.';
    return;
  }
  recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  let baseText = '';
  let finalText = '';

  recognition.onstart = () => {
    dictationStatus.textContent = 'Dictation running… speak now.';
    dictateBtn.disabled = true;
    stopDictateBtn.disabled = false;
  };

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += transcript + ' ';
      else interim += transcript;
    }
    const spoken = (finalText + interim).trim();
    notes.value = (finalText + interim).trim();
  };

  recognition.onerror = (e) => {
    dictationStatus.textContent = 'Dictation error: ' + e.error;
  };

  recognition.onend = () => {
    dictateBtn.disabled = false;
    stopDictateBtn.disabled = true;
    dictationStatus.textContent = 'Dictation stopped.';
  };

  dictateBtn.addEventListener('click', () => {
  // ✅ keep whatever is already in the notes (PDF extraction / typed text)
  baseText = notes.value.trim();
  finalText = ''; // reset only the new dictation buffer
  recognition.start();
});

  stopDictateBtn.addEventListener('click', () => recognition.stop());
}

setupSpeech();
loadAccounts();
