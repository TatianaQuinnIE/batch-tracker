// Feedback page: only talks to the feedback service. Product names and expiry dates
// come from the batches service through feedback (server side, across the seam);
// when batches is down, feedback still answers and says so in `notice`.
const formNotice = document.getElementById("form-notice");
const notice = document.getElementById("notice");
const alerts = document.getElementById("alerts");
const list = document.getElementById("summaries");
const form = document.getElementById("report");

function stars(average) {
  const full = Math.round(average);
  return h("span", { class: "mini", "aria-label": `Average ${average} out of 5` },
    [1, 2, 3, 4, 5].map((n) => h("span", { class: n <= full ? "" : "off" }, "★")));
}

function batchLine(batch, batchesAnswered) {
  // batch is null when the code is not registered, or when batches did not answer.
  if (!batch) return h("small", {}, batchesAnswered ? "Not a registered batch" : "Product details unavailable");
  const when = { ok: "in date until", expiring_soon: "expires", expired: "expired" }[batch.status];
  return h("small", {}, h("b", {}, batch.product), ` · ${when} ${niceDate(batch.expires_on)}`);
}

function renderAlerts(summaries) {
  const flagged = summaries.filter((s) => s.flagged);
  if (flagged.length === 0) {
    alerts.replaceChildren(summaries.length
      ? h("p", { class: "clear" }, "All clear. No batch is causing concern right now.")
      : "");
    return;
  }
  alerts.replaceChildren(h("div", { class: "alerts" }, flagged.map((s) =>
    h("div", { class: "alert" },
      h("span", { class: "tag" }, s.batch_code),
      s.batch ? h("span", { class: "product" }, s.batch.product) : null,
      h("b", {}, `${Math.round(s.reaction_rate * 100)}%`),
      h("p", {}, h("strong", {}, "reported a reaction"),
        ` · ${s.reactions} of ${s.reports} customers · avg ${s.average_rating}/5. Consider withdrawing this batch.`)))));
}

function renderList(summaries, batchesAnswered) {
  if (summaries.length === 0) {
    list.replaceChildren(h("p", { class: "empty" }, "No feedback yet."));
    return;
  }
  list.replaceChildren(...summaries.map((s) => {
    const pct = Math.round(s.reaction_rate * 100);
    const plural = (n, word) => `${word}${n === 1 ? "" : "s"}`;
    return h("div", { class: "item" },
      h("span", { class: "who" }, h("span", { class: "tag" }, s.batch_code), batchLine(s.batch, batchesAnswered)),
      h("span", { class: "reports" },
        h("b", {}, s.reports), ` ${plural(s.reports, "report")}, `,
        h("b", {}, s.reactions), ` ${plural(s.reactions, "reaction")}`),
      h("span", { class: `meter ${s.flagged ? "bad" : ""}` },
        h("i", {}, h("b", { style: `width: ${pct}%` })), h("em", {}, `${pct}%`)),
      stars(s.average_rating),
      h("span", { class: `pill ${s.flagged ? "flagged" : "ok"}` }, s.flagged ? "Flagged" : "OK"));
  }));
}

async function load() {
  try {
    const body = await read("feedback", "/feedback", waitingIn(notice, "feedback"));
    // Partial failure, designed: feedback answered, batches did not.
    if (body.batches_service === "unavailable") showNotice(notice, "warn", body.notice);
    else if (notice.classList.contains("warn")) hideNotice(notice);
    renderAlerts(body.summaries);
    renderList(body.summaries, body.batches_service === "ok");
  } catch (err) {
    alerts.replaceChildren();
    list.replaceChildren(h("p", { class: "empty" }, "Feedback could not be loaded."));
    showNotice(notice, "error", describeError(err, "feedback"), () => { hideNotice(notice); load(); });
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  const data = new FormData(form);
  button.disabled = true;
  try {
    const summary = await write("feedback", "/feedback", {
      batch_code: data.get("batch_code"),
      rating: Number(data.get("rating")),
      had_reaction: data.get("had_reaction") === "on",   // a real JSON boolean
      comment: data.get("comment"),
    });
    form.reset();
    const product = summary.batch ? ` (${summary.batch.product})` : "";
    showNotice(formNotice, "ok", `Thank you. Your report for ${summary.batch_code}${product} was recorded.`);
    load();
  } catch (err) {
    showNotice(formNotice, "error", describeError(err, "feedback"));
  } finally {
    button.disabled = false;
  }
});

load();
