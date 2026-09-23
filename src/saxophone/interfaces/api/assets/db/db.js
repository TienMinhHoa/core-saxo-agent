const state = { offset: 0, limit: 25, total: 0 };

const collectionSelect = document.querySelector("#collection-select");
const queryInput = document.querySelector("#query-input");
const documentRefInput = document.querySelector("#document-ref-input");
const pageSize = document.querySelector("#page-size");
const records = document.querySelector("#records");
const status = document.querySelector("#status");
const previousButton = document.querySelector("#previous-button");
const nextButton = document.querySelector("#next-button");
const template = document.querySelector("#record-template");

async function loadCollections() {
  const response = await fetch("/db/api/collections", { headers: { Accept: "application/json" } });
  const payload = await readResponse(response);
  collectionSelect.replaceChildren();
  for (const collection of payload.collections) {
    const option = document.createElement("option");
    option.value = collection.name;
    option.textContent = `${collection.name} (${collection.count})`;
    collectionSelect.append(option);
  }
  if (!payload.collections.length) {
    throw new Error("Khong co collection nao trong ChromaDB.");
  }
}

async function loadRecords({ reset = false } = {}) {
  if (reset) state.offset = 0;
  state.limit = Number(pageSize.value);
  setBusy(true, "Dang doc du lieu...");
  const params = new URLSearchParams({ offset: String(state.offset), limit: String(state.limit) });
  if (queryInput.value.trim()) params.set("q", queryInput.value.trim());
  if (documentRefInput.value.trim()) params.set("document_ref", documentRefInput.value.trim());
  try {
    const path = `/db/api/collections/${encodeURIComponent(collectionSelect.value)}/records?${params}`;
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    const payload = await readResponse(response);
    state.total = payload.total_count;
    renderRecords(payload.records);
    document.querySelector("#summary-collection").textContent = payload.collection;
    document.querySelector("#summary-count").textContent = String(payload.total_count);
    document.querySelector("#summary-page").textContent = String(Math.floor(payload.offset / payload.limit) + 1);
    previousButton.disabled = payload.offset === 0;
    nextButton.disabled = !payload.has_more;
    status.textContent = payload.records.length
      ? `Dang hien thi ${payload.offset + 1}-${payload.offset + payload.records.length}.`
      : "Khong tim thay record phu hop.";
  } catch (error) {
    records.replaceChildren();
    status.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function renderRecords(items) {
  records.replaceChildren();
  for (const item of items) {
    const fragment = template.content.cloneNode(true);
    fragment.querySelector(".record-id").textContent = item.id;
    fragment.querySelector(".record-document").textContent = item.document || "(Khong co document text)";
    fragment.querySelector(".record-metadata").textContent = JSON.stringify(item.metadata, null, 2);
    fragment.querySelector(".copy-button").addEventListener("click", async (event) => {
      await navigator.clipboard.writeText(item.id);
      event.currentTarget.textContent = "Da copy";
      setTimeout(() => { event.currentTarget.textContent = "Copy ID"; }, 1200);
    });
    records.append(fragment);
  }
}

async function readResponse(response) {
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function setBusy(busy, message) {
  document.querySelector("#search-button").disabled = busy;
  if (busy && message) status.textContent = message;
}

document.querySelector("#search-button").addEventListener("click", () => loadRecords({ reset: true }));
collectionSelect.addEventListener("change", () => loadRecords({ reset: true }));
pageSize.addEventListener("change", () => loadRecords({ reset: true }));
previousButton.addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.limit);
  loadRecords();
});
nextButton.addEventListener("click", () => {
  state.offset += state.limit;
  loadRecords();
});

loadCollections()
  .then(() => loadRecords({ reset: true }))
  .catch((error) => { status.textContent = error.message; });
