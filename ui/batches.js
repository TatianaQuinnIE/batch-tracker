// Batches page: only talks to the batches service.
const notice = document.getElementById("notice");
const ledger = document.getElementById("ledger");
const form = document.getElementById("new-batch");
const recallForm = document.getElementById("recall-batch");

// recalled_on is missing (not just null) from a batches revision older than migration 002.
const isRecalled = (b) => Boolean(b.recalled_on);

function renderLedger(batches) {
  // The counts are about what is still on sale, so recalled batches are left out.
  const onSale = batches.filter((b) => !isRecalled(b));
  const count = (status) => onSale.filter((b) => b.status === status).length;
  document.getElementById("n-expired").textContent = count("expired");
  document.getElementById("n-soon").textContent = count("expiring_soon");
  document.getElementById("n-ok").textContent = count("ok");

  const select = recallForm.elements.batch_code;
  select.replaceChildren(select.options[0],
    ...onSale.map((b) => h("option", { value: b.batch_code }, `${b.batch_code} · ${b.product}`)));

  if (batches.length === 0) {
    ledger.replaceChildren(h("p", { class: "empty" }, "The shelf is empty. Register your first batch above."));
    return;
  }
  ledger.replaceChildren(...batches.map((b) => {
    const state = isRecalled(b) ? "recalled" : b.status;
    return h("div", { class: `row ${state}` },
      h("div", { class: "mono", "aria-hidden": "true" }, b.product.slice(0, 1).toUpperCase()),
      h("div", { class: "what" },
        h("strong", {}, b.product),
        h("small", {}, h("span", { class: "tag" }, b.batch_code),
          isRecalled(b) ? `Recalled: ${b.recall_reason}` : `${b.quantity} units`)),
      h("div", { class: "when" },
        h("span", {}, `Made ${niceDate(b.produced_on)}`),
        h("span", { class: "arrow" }, "→"),
        h("b", {}, niceDate(b.expires_on))),
      h("span", { class: `pill ${state}` },
        isRecalled(b) ? `Recalled ${niceDate(b.recalled_on)}` : STATUS_LABELS[b.status]));
  }));
}

async function load() {
  try {
    const batches = await read("batches", "/batches", waitingIn(notice, "batches"));
    renderLedger(batches);
  } catch (err) {
    ledger.replaceChildren(h("p", { class: "empty" }, "The ledger could not be loaded."));
    showNotice(notice, "error", describeError(err, "batches"), () => { hideNotice(notice); load(); });
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  const data = Object.fromEntries(new FormData(form));
  button.disabled = true;
  try {
    const created = await write("batches", "/batches", data);
    form.reset();
    showNotice(notice, "ok", `Batch ${created.batch_code} added to the ledger.`);
    load();
  } catch (err) {
    // The form keeps what was typed, so the user can fix it or send it again.
    showNotice(notice, "error", describeError(err, "batches"));
  } finally {
    button.disabled = false;
  }
});

recallForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = recallForm.querySelector("button");
  const { batch_code: code, reason } = Object.fromEntries(new FormData(recallForm));
  button.disabled = true;
  try {
    const recalled = await write("batches", `/batches/${encodeURIComponent(code)}/recall`, { reason });
    recallForm.reset();
    showNotice(notice, "ok", `Batch ${recalled.batch_code} recalled. It stays in the ledger, marked as recalled.`);
    load();
  } catch (err) {
    showNotice(notice, "error", describeError(err, "batches"));
  } finally {
    button.disabled = false;
  }
});

load();
