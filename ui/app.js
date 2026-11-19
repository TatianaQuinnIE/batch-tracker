// Shared code for the three pages: calling the two services, and small DOM helpers.
// The base URLs come from config.js (local compose ports, or the Container Apps URLs
// written by the pipeline). No framework and no build step: the files are served as-is.

const SERVICES = {
  batches: window.APP_CONFIG.BATCHES_URL,
  feedback: window.APP_CONFIG.FEEDBACK_URL,
};

// On Azure both services scale to zero and their databases pause. The first request
// can wait ~30 s and then get a 503 from Container Apps, or a 503 from the service
// while its database resumes (up to about a minute). Reads retry a few times while
// showing a "starting up" message; writes never retry on their own, so a report is
// never sent twice, and the form keeps what the user typed.
const ATTEMPT_TIMEOUT_MS = 35000;
const READ_RETRIES = 4;
const RETRY_WAIT_MS = 5000;

class ServiceError extends Error {
  // kind: "starting" (503, timeout or no answer) or "rejected" (4xx with a message)
  constructor(kind, message, status) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

async function callOnce(service, path, options = {}) {
  let response;
  try {
    response = await fetch(SERVICES[service] + path, {
      ...options,
      // Content-Type only when there is a body: on a GET it would add a CORS preflight.
      headers: options.body ? { "Content-Type": "application/json" } : {},
      signal: AbortSignal.timeout(ATTEMPT_TIMEOUT_MS),
    });
  } catch {
    // Timeout, connection refused, or a CORS failure: the browser cannot tell them apart.
    throw new ServiceError("starting", `The ${service} service did not answer.`, 0);
  }
  let body = null;
  try { body = await response.json(); } catch { /* e.g. an HTML 503 page from Azure */ }
  if (response.ok) return body;
  if (response.status >= 500) {
    throw new ServiceError("starting", `The ${service} service is not ready (${response.status}).`, response.status);
  }
  throw new ServiceError("rejected", (body && body.error) || `Request failed (${response.status}).`, response.status);
}

// GET with retries. onWaiting(attempt) is called before each retry so the page can
// show "starting up"; it is called with null once the data arrives.
async function read(service, path, onWaiting) {
  for (let attempt = 1; ; attempt++) {
    try {
      const body = await callOnce(service, path);
      if (onWaiting) onWaiting(null);
      return body;
    } catch (err) {
      if (err.kind !== "starting" || attempt > READ_RETRIES) throw err;
      if (onWaiting) onWaiting(attempt);
      await new Promise((resolve) => setTimeout(resolve, RETRY_WAIT_MS));
    }
  }
}

// POST once, no retry.
function write(service, path, data) {
  return callOnce(service, path, { method: "POST", body: JSON.stringify(data) });
}

// ---- DOM helpers --------------------------------------------------------------

// h("p", {class: "x"}, "text", child) builds elements with textContent only, so text
// typed by users (product names, codes) can never be read as HTML.
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (key === "class") el.className = value;
    else if (key === "style") el.style.cssText = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

// One notice element per page, reused for ok / error / "starting up" messages.
function showNotice(el, kind, text, onRetry) {
  el.className = `notice ${kind}`;
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.replaceChildren(h("span", {}, text));
  if (onRetry) {
    const again = h("button", { class: "again", type: "button" }, "Try again");
    again.addEventListener("click", onRetry);
    el.append(again);
  }
  el.hidden = false;
}

function hideNotice(el) {
  el.hidden = true;
}

function startingText(service) {
  return `The ${service} service is starting up (it sleeps when nobody is using it). ` +
    "This can take up to a minute.";
}

// The onWaiting callback for read(): shows "starting up, retrying" in the notice, and
// clears it once the data arrives (leaving any other message, e.g. "batch added").
function waitingIn(noticeEl, service) {
  return (attempt) => {
    if (attempt) showNotice(noticeEl, "warn", `${startingText(service)} Retrying (${attempt} of ${READ_RETRIES})…`);
    else if (noticeEl.classList.contains("warn")) hideNotice(noticeEl);
  };
}

// Explains a failed call in words the user can act on.
function describeError(err, service) {
  if (err instanceof ServiceError && err.kind === "rejected") return err.message;
  return `${startingText(service)} Please try again in a moment.`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function niceDate(iso) {
  const [y, m, d] = iso.split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
}

const STATUS_LABELS = { ok: "In date", expiring_soon: "Expiring soon", expired: "Expired" };

// Footer: each service's own /health, so it is visible which side is down.
function renderStatusFooter() {
  const footer = document.querySelector("footer");
  if (!footer) return;
  for (const service of Object.keys(SERVICES)) {
    const dot = h("span", { class: "dot" });
    const label = h("span", {}, dot, `${service}: checking…`);
    footer.append(label);
    callOnce(service, "/health")
      .then((health) => {
        dot.className = "dot ok";
        label.lastChild.textContent = `${service}: ok (${health.version})`;
      })
      .catch(() => {
        dot.className = "dot down";
        label.lastChild.textContent = `${service}: not answering`;
      });
  }
}

document.addEventListener("DOMContentLoaded", renderStatusFooter);
