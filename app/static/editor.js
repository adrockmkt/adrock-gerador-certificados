import * as pdfjsLib from "./vendor/pdfjs/pdf.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL("./vendor/pdfjs/pdf.worker.mjs", import.meta.url).href;

const root = document.getElementById("editor");
const pageElement = document.getElementById("pdf-page");
const canvas = document.getElementById("pdf-canvas");
const layer = document.getElementById("field-layer");
const status = document.getElementById("editor-status");
const pageWidth = Number(root.dataset.pageWidth);
const pageHeight = Number(root.dataset.pageHeight);
const fields = JSON.parse(root.dataset.fields);
for (const field of fields) {
  field.height_pt ??= field.font_size_pt * 2.5;
  field.max_lines ??= 1;
}
let selectedId = fields[0]?.id ?? null;
let scale = 1;
let page = null;
let renderQueue = Promise.resolve();

const sample = { nome: "Maria", sobrenome: "Silva", nome_completo: "Maria Silva" };
const labels = { nome: "Nome", sobrenome: "Sobrenome", nome_completo: "Nome completo" };

async function loadPdf() {
  try {
    const document = await pdfjsLib.getDocument({ url: root.dataset.pdfUrl }).promise;
    page = await document.getPage(1);
    await renderPage();
  } catch (error) {
    console.error("Falha ao carregar o template PDF no editor:", error);
    status.textContent = "Não foi possível abrir o PDF. Atualize a página e tente novamente.";
  }
}

function renderPage() {
  renderQueue = renderQueue.catch(() => {}).then(renderPageNow);
  return renderQueue;
}

async function renderPageNow() {
  if (!page) return;
  const available = Math.max(320, pageElement.parentElement.clientWidth - 32);
  scale = Math.min(1.6, available / pageWidth);
  const viewport = page.getViewport({ scale });
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.ceil(viewport.width * dpr);
  canvas.height = Math.ceil(viewport.height * dpr);
  canvas.style.width = `${viewport.width}px`;
  canvas.style.height = `${viewport.height}px`;
  pageElement.style.width = `${viewport.width}px`;
  pageElement.style.height = `${viewport.height}px`;
  layer.style.width = `${viewport.width}px`;
  layer.style.height = `${viewport.height}px`;
  const context = canvas.getContext("2d");
  await page.render({ canvasContext: context, viewport, transform: [dpr, 0, 0, dpr, 0, 0] }).promise;
  renderFields();
}

function renderFields() {
  layer.replaceChildren();
  for (const field of fields) {
    const box = document.createElement("button");
    box.type = "button";
    box.className = `pdf-field ${field.id === selectedId ? "selected" : ""}`;
    const label = document.createElement("span");
    label.textContent = sample[field.key];
    box.append(label);
    box.style.left = `${field.x_pt * scale}px`;
    box.style.top = `${(pageHeight - field.y_pt - field.height_pt / 2) * scale}px`;
    box.style.width = `${field.width_pt * scale}px`;
    box.style.height = `${field.height_pt * scale}px`;
    box.style.fontSize = `${field.font_size_pt * scale}px`;
    box.style.color = field.color;
    label.style.textAlign = field.align;
    box.style.fontFamily = field.font_family === "Helvetica" ? "Helvetica, Arial, sans-serif" : `"${field.font_family}", sans-serif`;
    box.style.fontWeight = field.font_weight === "semibold" ? "600" : "400";
    box.addEventListener("click", () => selectField(field.id));
    box.addEventListener("pointerdown", (event) => beginDrag(event, field, box));
    layer.append(box);
  }
  renderList();
  renderProperties();
}

function beginDrag(event, field, box) {
  event.preventDefault();
  selectedId = field.id;
  layer.querySelectorAll(".pdf-field").forEach((item) => item.classList.remove("selected"));
  box.classList.add("selected");
  renderList();
  renderProperties();
  const startX = event.clientX;
  const startY = event.clientY;
  const oldX = field.x_pt;
  const oldY = field.y_pt;
  box.setPointerCapture(event.pointerId);
  const move = (next) => {
    field.x_pt = Math.max(0, Math.min(pageWidth - field.width_pt, oldX + (next.clientX - startX) / scale));
    field.y_pt = Math.max(field.height_pt / 2, Math.min(pageHeight - field.height_pt / 2, oldY - (next.clientY - startY) / scale));
    box.style.left = `${field.x_pt * scale}px`;
    box.style.top = `${(pageHeight - field.y_pt - field.height_pt / 2) * scale}px`;
    renderProperties();
  };
  const end = () => {
    box.removeEventListener("pointermove", move);
    box.removeEventListener("pointerup", end);
    box.removeEventListener("pointercancel", end);
    renderFields();
  };
  box.addEventListener("pointermove", move);
  box.addEventListener("pointerup", end);
  box.addEventListener("pointercancel", end);
}

function selectField(id) {
  selectedId = id;
  renderFields();
}

function renderList() {
  const list = document.getElementById("field-list");
  list.replaceChildren();
  for (const field of fields) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `field-item ${field.id === selectedId ? "selected" : ""}`;
    button.textContent = labels[field.key];
    button.addEventListener("click", () => selectField(field.id));
    list.append(button);
  }
}

function renderProperties() {
  const field = fields.find((item) => item.id === selectedId);
  document.getElementById("field-properties").hidden = !field;
  if (!field) return;
  document.getElementById("field-x").value = field.x_pt.toFixed(1);
  document.getElementById("field-y").value = field.y_pt.toFixed(1);
  document.getElementById("field-width").value = field.width_pt.toFixed(1);
  document.getElementById("field-height").value = field.height_pt.toFixed(1);
  document.getElementById("field-lines").value = String(field.max_lines);
  document.getElementById("field-font").value = field.font_family;
  document.getElementById("field-weight").value = field.font_weight;
  document.getElementById("field-weight").disabled = field.font_family === "Helvetica";
  document.getElementById("field-size").value = field.font_size_pt;
  document.getElementById("field-min-size").value = field.min_font_size_pt;
  document.getElementById("field-color").value = field.color;
  document.getElementById("field-align").value = field.align;
}

for (const [control, property] of Object.entries({
  "field-x": "x_pt", "field-y": "y_pt", "field-width": "width_pt", "field-height": "height_pt",
  "field-size": "font_size_pt", "field-min-size": "min_font_size_pt",
})) {
  document.getElementById(control).addEventListener("change", (event) => {
    const field = fields.find((item) => item.id === selectedId);
    if (!field) return;
    field[property] = Number(event.target.value);
    if (property === "height_pt") {
      field.height_pt = Math.min(pageHeight, Math.max(1, field.height_pt));
      field.y_pt = Math.max(field.height_pt / 2, Math.min(pageHeight - field.height_pt / 2, field.y_pt));
    }
    renderFields();
  });
}
document.getElementById("field-lines").addEventListener("change", (event) => {
  const field = fields.find((item) => item.id === selectedId);
  if (field) { field.max_lines = Number(event.target.value); renderFields(); }
});
document.getElementById("field-color").addEventListener("change", (event) => {
  const field = fields.find((item) => item.id === selectedId);
  if (field) { field.color = event.target.value; renderFields(); }
});
document.getElementById("field-align").addEventListener("change", (event) => {
  const field = fields.find((item) => item.id === selectedId);
  if (field) { field.align = event.target.value; renderFields(); }
});
document.getElementById("field-font").addEventListener("change", (event) => {
  const field = fields.find((item) => item.id === selectedId);
  if (field) {
    field.font_family = event.target.value;
    if (field.font_family === "Helvetica") field.font_weight = "regular";
    renderFields();
  }
});
document.getElementById("field-weight").addEventListener("change", (event) => {
  const field = fields.find((item) => item.id === selectedId);
  if (field) { field.font_weight = event.target.value; renderFields(); }
});
document.getElementById("add-field").addEventListener("click", () => {
  if (fields.length >= 20) { status.textContent = "Limite de 20 campos atingido."; return; }
  const key = document.getElementById("new-field-key").value;
  const width = Math.min(400, pageWidth - 20);
  const field = {
    id: crypto.randomUUID(), key, x_pt: (pageWidth - width) / 2, y_pt: pageHeight / 2,
    width_pt: width, height_pt: 80, max_lines: 2,
    font_family: "Helvetica", font_weight: "regular",
    font_size_pt: 28, min_font_size_pt: 18, color: "#333333", align: "center",
  };
  fields.push(field);
  selectField(field.id);
});
document.getElementById("remove-field").addEventListener("click", () => {
  const index = fields.findIndex((item) => item.id === selectedId);
  if (index >= 0) fields.splice(index, 1);
  selectedId = fields[0]?.id ?? null;
  renderFields();
});
document.getElementById("save-fields").addEventListener("click", async () => {
  try {
    const response = await fetch(root.dataset.saveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf },
      body: JSON.stringify({ fields }),
    });
    if (!response.ok) throw new Error("save failed");
    const result = await response.json();
    status.textContent = `Configuração salva como versão ${result.version}.`;
  } catch {
    status.textContent = "Não foi possível salvar. Confira se os campos estão dentro da página e tente novamente.";
  }
});
new ResizeObserver(() => renderPage()).observe(pageElement.parentElement);
loadPdf();
