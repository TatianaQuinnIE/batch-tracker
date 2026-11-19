// Batches page: only talks to the batches service.
const notice = document.getElementById("notice");
const ledger = document.getElementById("ledger");
const form = document.getElementById("new-batch");

function renderLedger(batches) {
  const count = (status) => batches.filter((b) => b.status === status).length;
  document.getElementById("n-expired").textContent = count("expired");
  document.getElementById("n-soon").textContent = count("expiring_soon");
  document.getElementById("n-ok").textContent = count("ok");

  if (batches.length === 0) {
    ledger.replaceChildren(h("p", { class: "empty" }, "The shelf is empty. Register your first batch above."));
    return;
  }
  ledger.replaceChildren(...batches.map((b) =>
    h("div", { class: `row ${b.status}` },
      h("div", { class: "mono", "aria-hidden": "true" }, b.product.slice(0, 1).toUpperCase()),
      h("div", { class: "what" },
        h("strong", {}, b.product),
        h("small", {}, h("span", { class: "tag" }, b.batch_code), `${b.quantity} units`)),
      h("div", { class: "when" },
        h("span", {}, `Made ${niceDate(b.produced_on)}`),
        h("span", { class: "arrow" }, "→"),
        h("b", {}, niceDate(b.expires_on))),
      h("span", { class: `pill ${b.status}` }, STATUS_LABELS[b.status]))));
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

load();
