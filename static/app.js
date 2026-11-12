// BrightPath Learn help desk: the ask box, the document list and the page's small animations.

const $ = (id) => document.getElementById(id);
const form = $("ask-form");
const questionBox = $("question");
const askButton = $("ask-button");

// ---------- Asking ----------

async function ask(question) {
  askButton.disabled = true;
  askButton.textContent = "Reading…";
  $("error").hidden = true;
  $("result").hidden = true;
  const started = performance.now();

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "The request failed.");
    showAnswer(data, (performance.now() - started) / 1000);
  } catch (err) {
    // The web server itself is down, or the question was rejected (empty, too long).
    showError(err instanceof TypeError ? "Can't reach the help desk server. Is it running?" : err.message);
  } finally {
    askButton.disabled = false;
    askButton.textContent = "Ask";
  }
}

function showAnswer(data, seconds) {
  highlightSources(data.sources);
  if (data.error) {                       // the language model failed: red banner
    showError(data.answer);
    return;
  }

  $("answer").textContent = data.answer;

  // "From Getting started · 2.1 s", with each source linking to its document below.
  const meta = $("meta");
  meta.replaceChildren();
  if (data.found) {
    meta.append("From ");
    data.sources.forEach((s, i) => {
      if (i > 0) meta.append(" and ");
      const link = document.createElement("a");
      link.href = `#doc-${s.id}`;
      link.textContent = s.title;
      meta.append(link);
    });
  } else {
    meta.append("Not in the documents");
  }
  meta.append(` · ${seconds.toFixed(1)} s`);
  if (data.mode === "mock") meta.append(" · Mock mode: a canned answer, no model was used");

  $("result").hidden = false;
  bringIntoView($("result"));
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
  bringIntoView($("error"));
}

// On a short screen the answer can land below the fold: scroll just enough to show it.
function bringIntoView(el) {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
}

// Turn the source document(s) blue in the "What it knows" list.
function highlightSources(sources) {
  document.querySelectorAll(".doc-group").forEach((g) => g.classList.remove("is-source"));
  for (const s of sources) $(`doc-${s.id}`)?.classList.add("is-source");
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (askButton.disabled) return;          // already waiting for an answer: ignore repeat Enter
  const question = questionBox.value.trim();
  if (question) ask(question);
});

// Enter asks; Shift+Enter adds a new line.
questionBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

// The example questions fill the box and ask straight away.
document.querySelectorAll(".example").forEach((button) => {
  button.addEventListener("click", () => {
    questionBox.value = button.textContent;
    form.requestSubmit();
  });
});

// ---------- The documents, from GET /documents ----------

async function loadDocuments() {
  const table = $("doc-table");
  try {
    const docs = await (await fetch("/documents")).json();
    table.replaceChildren(...docs.map(docGroup));
  } catch {
    table.textContent = "The documents could not be loaded.";
  }
}

// One group per document: its title on the first row, then one row per sentence.
function docGroup(doc) {
  const group = document.createElement("div");
  group.className = "doc-group";
  group.id = `doc-${doc.id}`;

  const sentences = doc.text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("Platform:")); // same line in every doc

  sentences.forEach((sentence, i) => {
    const row = document.createElement("p");
    row.className = "doc-row";
    const title = document.createElement("span");
    title.className = "doc-title";
    title.textContent = i === 0 ? doc.title : "";
    const text = document.createElement("span");
    text.textContent = sentence;
    row.append(title, text);
    group.append(row);
  });
  return group;
}

// ---------- The diagram: scattered squares, a ribbon, then neat rows ----------

function drawDiagram() {
  const svg = $("diagram");
  const ns = "http://www.w3.org/2000/svg";
  let seed = 7;
  const random = () => (seed = (seed * 16807) % 2147483647) / 2147483647; // repeatable

  const squares = [];
  for (let i = 0; i < 50; i++) {            // left third: loose scatter, two greys
    squares.push([10 + random() * 270, 20 + random() * 160, random() < 0.5 ? "#5c5c5c" : "#8f8f8f"]);
  }
  for (let c = 0; c < 18; c++) {            // middle third: a ribbon three squares high
    for (let r = 0; r < 3; r++) squares.push([318 + c * 14, 79 + r * 14, "#bdbdbd"]);
  }
  for (let r = 0; r < 5; r++) {             // right third: ordered rows in red
    for (let c = 0; c < 12; c++) squares.push([630 + c * 22, 46 + r * 24, "#ff3b1f"]);
  }

  for (const [x, y, fill] of squares) {
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", x.toFixed(1));
    rect.setAttribute("y", y.toFixed(1));
    rect.setAttribute("width", 11);
    rect.setAttribute("height", 11);
    rect.setAttribute("fill", fill);
    rect.style.transitionDelay = `${Math.round(x * 0.7)}ms`; // fills in from left to right
    svg.append(rect);
  }
}

// ---------- Entrances: each part of a section rises in as it scrolls into view ----------

function watchReveals() {
  const targets = document.querySelectorAll(".reveal, .diagram");
  if (!("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("in"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add("in");
      observer.unobserve(entry.target);
    }
  }, { threshold: 0.15 });

  targets.forEach((el) => {
    // Stagger the parts of one section by 80ms each.
    const siblings = [...el.closest("section, footer").querySelectorAll(".reveal")];
    el.style.transitionDelay = `${Math.max(0, siblings.indexOf(el)) * 80}ms`;
    observer.observe(el);
  });
}

drawDiagram();
watchReveals();
loadDocuments();
requestAnimationFrame(() => document.documentElement.classList.add("loaded"));
