"use strict";
const API_BASE = "https://smart-inventory-backend-q2ce.onrender.com";
const CURRENCY = "USD";
const money = (n) => new Intl.NumberFormat(undefined, { style: "currency", currency: CURRENCY }).format(n || 0);
const num = (n) => new Intl.NumberFormat().format(n || 0);
const fmtDate = (s) => (s ? new Date(s.replace(" ", "T") + "Z").toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
const isoDay = (d) => d.toISOString().slice(0, 10);

/* ---------- safe HTML templating: every interpolated value is escaped unless wrapped in raw() ---------- */
class Raw { constructor(s) { this.s = s; } }
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const part = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join("") : esc(v));
const html = (strings, ...vals) => new Raw(strings.reduce((out, s, i) => out + s + (i < vals.length ? part(vals[i]) : ""), ""));
const $ = (sel, el = document) => el.querySelector(sel);

/* ---------- session ---------- */
const LEVEL = { staff: 1, manager: 2, admin: 3 };
const load = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } };
const state = { token: localStorage.getItem("inv_token"), user: load("inv_user") };
const can = (role) => !!state.user && LEVEL[state.user.role] >= LEVEL[role];
function setSession(token, user) {
  state.token = token; state.user = user;
  if (token) { localStorage.setItem("inv_token", token); localStorage.setItem("inv_user", JSON.stringify(user)); }
  else { localStorage.removeItem("inv_token"); localStorage.removeItem("inv_user"); }
}

/* ---------- API ---------- */

  if (body) headers["Content-Type"] = "application/json";
    if (state.token) headers.Authorization = "Bearer " + state.token;

    const res = await fetch(API_BASE + "/api" + path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined
    });

    if (res.status === 401 && state.token && !path.startsWith("/auth/login")) {
        setSession(null, null);
        route();
        throw new Error("Your session has ended. Please sign in again.");
    }

    return res;


/* ---------- UI helpers ---------- */
function toast(message, type = "info") {
  const el = Object.assign(document.createElement("div"), { className: "toast " + type, textContent: message });
  $("#toasts").append(el); setTimeout(() => el.remove(), 4200);
}
const fail = (e) => toast(e.message || "Something went wrong", "error");
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function openDialog(content, { wide = false } = {}) {
  const dlg = document.createElement("dialog");
  if (wide) dlg.className = "wide";
  dlg.innerHTML = content.s;
  dlg.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) dlg.close(); });
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg); dlg.showModal();
  return dlg;
}

const fieldHtml = (f, v) => html`<label class="field"><span>${f.label}${f.required ? " *" : ""}</span>${
  f.type === "select"
    ? html`<select name="${f.name}">${f.options.map((o) => html`<option value="${o.value}" ${String(o.value) === String(v ?? "") ? "selected" : ""}>${o.label}</option>`)}</select>`
    : f.type === "textarea"
      ? html`<textarea name="${f.name}" rows="3">${v ?? ""}</textarea>`
      : html`<input name="${f.name}" type="${f.type || "text"}" value="${v ?? ""}" ${f.step ? raw(`step="${esc(f.step)}"`) : ""} ${f.min != null ? raw(`min="${esc(f.min)}"`) : ""} autocomplete="off">`
}<small class="err" data-err="${f.name}"></small></label>`;
const raw = (s) => new Raw(s);

/* Generic form dialog with server-side validation messages shown per field */
function formModal({ title, fields, values = {}, submitLabel = "Save", onSubmit }) {
  const dlg = openDialog(html`<form novalidate><h2>${title}</h2>${fields.map((f) => fieldHtml(f, values[f.name]))}
    <p class="form-error" role="alert"></p>
    <div class="actions"><button type="button" class="ghost" data-close>Cancel</button><button class="primary">${submitLabel}</button></div></form>`);
  const form = $("form", dlg);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const out = {};
    for (const f of fields) {
      const v = form.elements[f.name].value;
      out[f.name] = f.type === "number" || f.numeric ? (v === "" ? null : Number(v)) : v.trim();
    }
    dlg.querySelectorAll("[data-err]").forEach((el) => (el.textContent = ""));
    $(".form-error", dlg).textContent = "";
    const btn = $("button.primary", dlg); btn.disabled = true;
    try { await onSubmit(out); dlg.close(); }
    catch (err) {
      $(".form-error", dlg).textContent = err.message;
      for (const [k, msg] of Object.entries(err.details || {})) { const el = $(`[data-err="${k}"]`, dlg); if (el) el.textContent = msg; }
      btn.disabled = false;
    }
  });
  $("input, select, textarea", dlg)?.focus();
  return dlg;
}

const pager = (d) => {
  const pages = Math.max(1, Math.ceil(d.total / d.limit));
  return html`<div class="pager"><span>${num(d.total)} total</span>
    <button class="small" data-act="page" data-page="${d.page - 1}" ${d.page <= 1 ? "disabled" : ""}>Previous</button>
    <span>Page ${d.page} of ${pages}</span>
    <button class="small" data-act="page" data-page="${d.page + 1}" ${d.page >= pages ? "disabled" : ""}>Next</button></div>`;
};
const table = (headers, rows, emptyText) => rows.length
  ? html`<div class="table-wrap"><table><thead><tr>${headers.map((h) => html`<th class="${h.num ? "num" : ""}">${h.label ?? h}</th>`)}</tr></thead><tbody>${rows}</tbody></table></div>`
  : html`<div class="table-wrap"><p class="empty">${emptyText}</p></div>`;
const gauge = (p) => {
  const cls = p.stock_qty === 0 ? "out" : p.low_stock ? "low" : "";
  const pct = p.reorder_level === 0 ? (p.stock_qty > 0 ? 100 : 0) : Math.min(100, (p.stock_qty / (p.reorder_level * 3)) * 100);
  return html`<div class="gauge" title="${p.low_stock ? "At or below reorder level (" + p.reorder_level + ")" : "Healthy stock"}"><b>${num(p.stock_qty)}</b><span><i class="${cls}" style="width:${pct}%"></i></span></div>`;
};
const status = (s) => html`<span class="badge ${s}">${s}</span>`;

/* ---------- login / shell ---------- */
function showLogin() {
  $("#app").innerHTML = html`<div class="login"><form id="login" novalidate>
    <h1>Stockroom</h1><p>Sign in to manage stock, customers and orders.</p>
    <label class="field"><span>Email</span><input name="email" type="email" autocomplete="username" required></label>
    <label class="field"><span>Password</span><input name="password" type="password" autocomplete="current-password" required></label>
    <p class="form-error" role="alert"></p>
    <button class="primary" style="width:100%">Sign in</button>
</form></div>`.s;
  $("#login").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, btn = $("button", f); btn.disabled = true;
    try {
      const r = await api("/auth/login", { method: "POST", body: { email: f.email.value, password: f.password.value } });
      setSession(r.token, r.user); location.hash = "#/dashboard"; route();
    } catch (err) { $(".form-error", f).textContent = err.message; btn.disabled = false; }
  });
}

const NAV = [
  ["dashboard", "Dashboard", "staff"], ["products", "Products", "staff"], ["inventory", "Inventory", "staff"],
  ["customers", "Customers", "staff"], ["orders", "Orders", "staff"], ["reports", "Reports", "manager"], ["users", "Users", "admin"],
];
function shell(active) {
  if (!$("#main")) {
    $("#app").innerHTML = html`<div class="shell"><aside class="rail"><div class="brand">Stockroom</div><nav aria-label="Main"></nav>
      <div class="who"><small id="who"></small><button class="small" id="logout">Sign out</button></div></aside><main id="main"></main></div>`.s;
    $("#logout").addEventListener("click", async () => { try { await api("/auth/logout", { method: "POST" }); } catch {} setSession(null, null); route(); });
  }
  $("#who").textContent = `${state.user.name} (${state.user.role})`;
  $(".rail nav").innerHTML = NAV.filter(([, , r]) => can(r)).map(([p, label]) =>
    html`<a href="#/${p}" ${p === active ? raw('aria-current="page"') : ""}>${label}</a>`.s).join("");
  return $("#main");
}

/* ---------- pages ---------- */
const PAGES = {
  dashboard: { role: "staff", render: dashboardPage }, products: { role: "staff", render: productsPage },
  inventory: { role: "staff", render: inventoryPage }, customers: { role: "staff", render: customersPage },
  orders: { role: "staff", render: ordersPage }, "orders/new": { role: "staff", render: newOrderPage, nav: "orders" },
  reports: { role: "manager", render: reportsPage }, users: { role: "admin", render: usersPage },
};

async function route() {
  if (!state.token) return showLogin();
  const hash = location.hash.replace(/^#\/?/, "") || "dashboard";
  const page = PAGES[hash] || PAGES[hash.split("/")[0]];
  const main = shell(page?.nav || hash.split("/")[0]);
  if (!page || !can(page.role)) { main.innerHTML = html`<h1>Not available</h1><p class="empty">This page doesn't exist or your role can't open it.</p>`.s; return; }
  main.onclick = main.onkeydown = main.onchange = null;
  main.innerHTML = html`<p class="empty">Loading…</p>`.s;
  try { await page.render(main); } catch (e) { main.innerHTML = html`<h1>Something went wrong</h1><p class="empty">${e.message}</p>`.s; }
}

async function dashboardPage(main) {
  const d = await api("/dashboard");
  const max = Math.max(1, ...d.sales_last_7_days.map((x) => x.revenue));
  const bars = d.sales_last_7_days.map((x, i) => {
    const h = Math.round((x.revenue / max) * 70);
    const day = new Date(x.date + "T00:00:00").toLocaleDateString([], { weekday: "short" });
    return html`<g><title>${day}: ${money(x.revenue)}</title><rect x="${i * 40 + 8}" y="${78 - h}" width="24" height="${Math.max(h, 1)}" rx="2"/><text x="${i * 40 + 20}" y="92" text-anchor="middle">${day}</text></g>`;
  });
  main.innerHTML = html`<div class="page-head"><h1>Dashboard</h1><a href="#/orders/new"><button class="primary">New order</button></a></div>
    <dl class="ledger">
      <div><dt>Sales today</dt><dd>${money(d.sales_today)}</dd></div><div><dt>Sales this month</dt><dd>${money(d.sales_month)}</dd></div>
      <div><dt>Orders</dt><dd>${num(d.orders_total)}</dd></div><div><dt>Customers</dt><dd>${num(d.customers)}</dd></div>
      <div><dt>Products</dt><dd>${num(d.products)}</dd></div><div><dt>Units in stock</dt><dd>${num(d.units_in_stock)}</dd></div>
      <div><dt>Stock value</dt><dd>${money(d.stock_value)}</dd></div><div class="${d.low_stock_count ? "warn" : ""}"><dt>Low stock</dt><dd>${num(d.low_stock_count)}</dd></div></dl>
    <div class="grid-2">
      <section class="card"><h2>Sales, last 7 days</h2><svg class="chart" viewBox="0 0 280 96" role="img" aria-label="Daily sales for the last 7 days">${bars}</svg></section>
      <section class="card"><h2>Needs restocking</h2>${table(["Product", { label: "Stock", num: true }],
        d.low_stock.map((p) => html`<tr><td>${p.name}</td><td>${gauge(p)}</td></tr>`), "Everything is above its reorder level.")}</section>
    </div>
    <section class="card" style="margin-top:1.25rem"><h2>Recent orders</h2>${table(["Order", "Customer", "Date", { label: "Total", num: true }, "Status"],
      d.recent_orders.map((o) => html`<tr><td>#${o.id}</td><td>${o.customer_name}</td><td>${fmtDate(o.created_at)}</td><td class="num">${money(o.total)}</td><td>${status(o.status)}</td></tr>`),
      "No orders yet.")}</section>`.s;
}

async function productsPage(main) {
  const f = { q: "", low_stock: false, category_id: "", page: 1 };
  const cats = (await api("/categories")).items;
  const catOptions = [{ value: "", label: "No category" }, ...cats.map((c) => ({ value: c.id, label: c.name }))];
  let items = [];
  main.innerHTML = html`<div class="page-head"><h1>Products</h1>${can("manager") ? html`<button class="primary" data-act="add">Add product</button>` : ""}</div>
    <div class="toolbar"><input type="search" id="q" placeholder="Search name or SKU" aria-label="Search products" size="26">
      <select id="cat" aria-label="Category"><option value="">All categories</option>${cats.map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select>
      <label class="check"><input type="checkbox" id="low"> Low stock only</label></div><div id="list"></div>`.s;

  async function refresh() {
    const d = await api("/products?" + qs({ ...f, limit: 15 }));
    items = d.items;
    $("#list").innerHTML = html`${table(["SKU", "Name", "Category", { label: "Price", num: true }, "Stock", ""],
      items.map((p) => html`<tr><td>${p.sku}</td><td>${p.name}</td><td>${p.category || "—"}</td><td class="num">${money(p.price)}</td><td>${gauge(p)}</td>
        <td>${can("manager") ? html`<div class="row-actions"><button class="small" data-act="edit" data-id="${p.id}">Edit</button><button class="small danger" data-act="del" data-id="${p.id}">Delete</button></div>` : ""}</td></tr>`),
      "No products match your filters.")}${pager(d)}`.s;
  }
  const productForm = (p) => formModal({
    title: p ? "Edit product" : "Add product", values: p || { reorder_level: 10, stock_qty: 0 },
    fields: [{ name: "sku", label: "SKU", required: true }, { name: "name", label: "Name", required: true },
      { name: "category_id", label: "Category", type: "select", options: catOptions, numeric: true },
      { name: "price", label: "Price", type: "number", step: "0.01", min: 0, required: true },
      ...(p ? [] : [{ name: "stock_qty", label: "Opening stock", type: "number", min: 0 }]),
      { name: "reorder_level", label: "Reorder level", type: "number", min: 0 }],
    onSubmit: async (v) => { await api(p ? `/products/${p.id}` : "/products", { method: p ? "PUT" : "POST", body: v }); toast(p ? "Product saved" : "Product added"); refresh(); },
  });
  main.onclick = async (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const p = items.find((x) => x.id === Number(b.dataset.id));
    try {
      if (b.dataset.act === "page") { f.page = Number(b.dataset.page); await refresh(); }
      else if (b.dataset.act === "add") productForm();
      else if (b.dataset.act === "edit") productForm(p);
      else if (b.dataset.act === "del" && confirm(`Delete ${p.name}? Past orders keep their history.`)) { await api(`/products/${p.id}`, { method: "DELETE" }); toast("Product deleted"); await refresh(); }
    } catch (err) { fail(err); }
  };
  $("#q").addEventListener("input", debounce((e) => { f.q = e.target.value; f.page = 1; refresh().catch(fail); }));
  $("#cat").addEventListener("change", (e) => { f.category_id = e.target.value; f.page = 1; refresh().catch(fail); });
  $("#low").addEventListener("change", (e) => { f.low_stock = e.target.checked; f.page = 1; refresh().catch(fail); });
  await refresh();
}

async function inventoryPage(main) {
  const [all, low] = await Promise.all([api("/products?limit=200"), api("/inventory/low-stock")]);
  const opts = all.items.map((p) => ({ value: p.id, label: `${p.name} (${p.sku}) – ${p.stock_qty} in stock` }));
  const f = { type: "", page: 1 };
  main.innerHTML = html`<div class="page-head"><h1>Inventory</h1>${can("manager") ? html`<span><button class="primary" data-act="in">Stock in</button> <button data-act="out">Stock out</button></span>` : ""}</div>
    <div class="grid-2"><section class="card"><h2>Low-stock alerts (${low.total})</h2>${table(["Product", "Stock", { label: "Reorder at", num: true }],
      low.items.map((p) => html`<tr><td>${p.name}<br><small>${p.sku}</small></td><td>${gauge(p)}</td><td class="num">${p.reorder_level}</td></tr>`), "No alerts. Every product is above its reorder level.")}</section>
    <section class="card"><h2>Movement history</h2><div class="toolbar"><select id="mt" aria-label="Movement type"><option value="">All movements</option><option value="IN">Stock in</option><option value="OUT">Stock out</option></select></div><div id="moves"></div></section></div>`.s;
  async function refresh() {
    const d = await api("/inventory/movements?" + qs({ ...f, limit: 12 }));
    $("#moves").innerHTML = html`${table(["When", "Product", "Type", { label: "Qty", num: true }, "Reason"],
      d.items.map((m) => html`<tr><td>${fmtDate(m.created_at)}</td><td>${m.product}</td><td>${status(m.type)}</td><td class="num">${m.quantity}</td><td>${m.reason || ""}</td></tr>`), "No movements yet.")}${pager(d)}`.s;
  }
  const move = (kind) => formModal({
    title: kind === "in" ? "Receive stock" : "Remove stock", submitLabel: kind === "in" ? "Add to stock" : "Remove from stock",
    fields: [{ name: "product_id", label: "Product", type: "select", options: opts, numeric: true },
      { name: "quantity", label: "Quantity", type: "number", min: 1, required: true }, { name: "reason", label: "Reason (optional)" }],
    onSubmit: async (v) => { await api(`/inventory/stock-${kind}`, { method: "POST", body: v }); toast("Stock updated"); inventoryPage(main); },
  });
  main.onclick = (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    if (b.dataset.act === "page") { f.page = Number(b.dataset.page); refresh().catch(fail); } else move(b.dataset.act);
  };
  $("#mt").addEventListener("change", (e) => { f.type = e.target.value; f.page = 1; refresh().catch(fail); });
  await refresh();
}

async function customersPage(main) {
  const f = { q: "", page: 1 }; let items = [];
  main.innerHTML = html`<div class="page-head"><h1>Customers</h1><button class="primary" data-act="add">Add customer</button></div>
    <div class="toolbar"><input type="search" id="q" placeholder="Search name, email or phone" aria-label="Search customers" size="28"></div><div id="list"></div>`.s;
  async function refresh() {
    const d = await api("/customers?" + qs({ ...f, limit: 15 })); items = d.items;
    $("#list").innerHTML = html`${table(["Name", "Email", "Phone", "Address", ""], items.map((c) => html`<tr><td>${c.name}</td><td>${c.email || "—"}</td><td>${c.phone || "—"}</td><td>${c.address || "—"}</td>
      <td><div class="row-actions"><button class="small" data-act="edit" data-id="${c.id}">Edit</button>${can("manager") ? html`<button class="small danger" data-act="del" data-id="${c.id}">Delete</button>` : ""}</div></td></tr>`), "No customers yet. Add your first customer to start taking orders.")}${pager(d)}`.s;
  }
  const form = (c) => formModal({
    title: c ? "Edit customer" : "Add customer", values: c || {},
    fields: [{ name: "name", label: "Name", required: true }, { name: "email", label: "Email", type: "email" }, { name: "phone", label: "Phone" }, { name: "address", label: "Address", type: "textarea" }],
    onSubmit: async (v) => { await api(c ? `/customers/${c.id}` : "/customers", { method: c ? "PUT" : "POST", body: v }); toast("Customer saved"); refresh(); },
  });
  main.onclick = async (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const c = items.find((x) => x.id === Number(b.dataset.id));
    try {
      if (b.dataset.act === "page") { f.page = Number(b.dataset.page); await refresh(); }
      else if (b.dataset.act === "add") form(); else if (b.dataset.act === "edit") form(c);
      else if (b.dataset.act === "del" && confirm(`Delete ${c.name}?`)) { await api(`/customers/${c.id}`, { method: "DELETE" }); toast("Customer deleted"); await refresh(); }
    } catch (err) { fail(err); }
  };
  $("#q").addEventListener("input", debounce((e) => { f.q = e.target.value; f.page = 1; refresh().catch(fail); }));
  await refresh();
}

async function ordersPage(main) {
  const f = { status: "", page: 1 };
  main.innerHTML = html`<div class="page-head"><h1>Orders</h1><a href="#/orders/new"><button class="primary">New order</button></a></div>
    <div class="toolbar"><select id="st" aria-label="Status"><option value="">All statuses</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></div><div id="list"></div>`.s;
  async function refresh() {
    const d = await api("/orders?" + qs({ ...f, limit: 15 }));
    $("#list").innerHTML = html`${table(["Order", "Customer", "Date", { label: "Items", num: true }, { label: "Total", num: true }, "Status", "Taken by"],
      d.items.map((o) => html`<tr class="clickable" data-act="view" data-id="${o.id}" tabindex="0"><td>#${o.id}</td><td>${o.customer_name}</td><td>${fmtDate(o.created_at)}</td><td class="num">${o.item_count}</td><td class="num">${money(o.total)}</td><td>${status(o.status)}</td><td>${o.created_by_name}</td></tr>`),
      "No orders found.")}${pager(d)}`.s;
  }
  async function view(id) {
    const o = await api(`/orders/${id}`);
    const dlg = openDialog(html`<h2>Order #${o.id} ${status(o.status)}</h2>
      <p>${o.customer_name} · ${fmtDate(o.created_at)} · taken by ${o.created_by_name}</p>${o.notes ? html`<p>Note: ${o.notes}</p>` : ""}
      ${table(["Product", { label: "Qty", num: true }, { label: "Price", num: true }, { label: "Line total", num: true }],
        o.items.map((i) => html`<tr><td>${i.name}<br><small>${i.sku}</small></td><td class="num">${i.quantity}</td><td class="num">${money(i.unit_price)}</td><td class="num">${money(i.line_total)}</td></tr>`), "")}
      <p class="total">${money(o.total)}</p>
      <div class="actions">${can("manager") && o.status === "completed" ? html`<button class="danger" data-cancel>Cancel order</button>` : ""}<button class="primary" data-close>Close</button></div>`, { wide: true });
    $("[data-cancel]", dlg)?.addEventListener("click", async () => {
      if (!confirm("Cancel this order and return its items to stock?")) return;
      try { await api(`/orders/${id}/cancel`, { method: "POST" }); toast("Order cancelled, stock restored"); dlg.close(); refresh(); } catch (err) { fail(err); }
    });
  }
  main.onclick = (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    if (b.dataset.act === "page") { f.page = Number(b.dataset.page); refresh().catch(fail); } else view(b.dataset.id).catch(fail);
  };
  main.onkeydown = (e) => { if (e.key === "Enter" && e.target.matches("tr[data-id]")) e.target.click(); };
  $("#st").addEventListener("change", (e) => { f.status = e.target.value; f.page = 1; refresh().catch(fail); });
  await refresh();
}

async function newOrderPage(main) {
  const [custs, prods] = await Promise.all([api("/customers?limit=200"), api("/products?limit=200")]);
  let lines = [{ product_id: "", quantity: 1 }];
  const byId = (id) => prods.items.find((p) => p.id === Number(id));
  const total = () => lines.reduce((s, l) => s + (byId(l.product_id)?.price || 0) * (Number(l.quantity) || 0), 0);
  function draw() {
    $("#lines").innerHTML = lines.map((l, i) => {
      const p = byId(l.product_id);
      return html`<div class="line"><select data-i="${i}" data-k="product_id" aria-label="Product"><option value="">Choose a product</option>${prods.items.map((x) =>
        html`<option value="${x.id}" ${String(x.id) === String(l.product_id) ? "selected" : ""} ${x.stock_qty === 0 ? "disabled" : ""}>${x.name} (${x.stock_qty} left)</option>`)}</select>
        <input type="number" min="1" ${p ? raw(`max="${p.stock_qty}"`) : ""} value="${l.quantity}" data-i="${i}" data-k="quantity" aria-label="Quantity">
        <span class="sum">${p ? money(p.price * (Number(l.quantity) || 0)) : ""}</span><button type="button" class="ghost" data-rm="${i}" aria-label="Remove line">✕</button></div>`.s;
    }).join("");
    $("#total").textContent = money(total());
  }
  main.innerHTML = html`<div class="page-head"><h1>New order</h1><a href="#/orders">Back to orders</a></div>
    <form class="card" id="order" novalidate style="max-width:760px">
      <label class="field"><span>Customer *</span><select name="customer_id"><option value="">Choose a customer</option>${custs.items.map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select>
        <small class="err" data-err="customer_id"></small></label>
      <div id="lines" class="lines"></div><button type="button" id="add">Add another product</button>
      <label class="field" style="margin-top:1rem"><span>Note (optional)</span><input name="notes" maxlength="300"></label>
      <p class="total" id="total"></p><p class="form-error" role="alert"></p>
      <div class="actions"><button class="primary">Place order</button></div></form>`.s;
  draw();
  const form = $("#order");
  form.addEventListener("change", (e) => { const t = e.target; if (t.dataset.k === "product_id") { lines[t.dataset.i].product_id = t.value; draw(); } });
  form.addEventListener("input", (e) => {
    const t = e.target; if (t.dataset.k !== "quantity") return;
    const l = lines[t.dataset.i]; l.quantity = t.value;
    const p = byId(l.product_id); t.closest(".line").querySelector(".sum").textContent = p ? money(p.price * (Number(l.quantity) || 0)) : "";
    $("#total").textContent = money(total());
  });
  form.addEventListener("click", (e) => { const rm = e.target.closest("[data-rm]"); if (rm && lines.length > 1) { lines.splice(Number(rm.dataset.rm), 1); draw(); } });
  $("#add").addEventListener("click", () => { lines.push({ product_id: "", quantity: 1 }); draw(); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $(".form-error", form); err.textContent = "";
    const items = lines.filter((l) => l.product_id).map((l) => ({ product_id: Number(l.product_id), quantity: Number(l.quantity) }));
    if (!form.customer_id.value) { err.textContent = "Choose a customer."; return; }
    if (!items.length) { err.textContent = "Add at least one product."; return; }
    const btn = $("button.primary", form); btn.disabled = true;
    try {
      const o = await api("/orders", { method: "POST", body: { customer_id: Number(form.customer_id.value), items, notes: form.notes.value } });
      toast(`Order #${o.id} placed. Stock updated.`); location.hash = "#/orders";
    } catch (ex) { err.textContent = ex.message; btn.disabled = false; }
  });
}

async function reportsPage(main) {
  const today = new Date(), start = new Date(Date.now() - 29 * 864e5);
  const f = { from: isoDay(start), to: isoDay(today), group: "day" };
  main.innerHTML = html`<div class="page-head"><h1>Reports</h1></div>
    <div class="toolbar"><label class="check">From <input type="date" id="from" value="${f.from}"></label><label class="check">To <input type="date" id="to" value="${f.to}"></label>
      <select id="group" aria-label="Group by"><option value="day">By day</option><option value="month">By month</option></select>
      <button class="primary" id="run">Update</button></div><div id="out"></div>`.s;
  async function run() {
    const [sales, top, inv] = await Promise.all([api("/reports/sales?" + qs(f)), api("/reports/top-products?" + qs({ from: f.from, to: f.to })), api("/reports/inventory")]);
    $("#out").innerHTML = html`<dl class="ledger"><div><dt>Revenue</dt><dd>${money(sales.totals.revenue)}</dd></div><div><dt>Orders</dt><dd>${num(sales.totals.orders)}</dd></div>
        <div><dt>Average order</dt><dd>${money(sales.totals.average_order)}</dd></div><div><dt>Stock value</dt><dd>${money(inv.totals.stock_value)}</dd></div>
        <div class="${inv.totals.low_stock ? "warn" : ""}"><dt>Low-stock products</dt><dd>${inv.totals.low_stock}</dd></div></dl>
      <div class="grid-2"><section class="card"><div class="page-head"><h2>Sales</h2><button class="small" data-dl="sales">Download CSV</button></div>${table(["Period", { label: "Orders", num: true }, { label: "Revenue", num: true }],
        sales.rows.map((r) => html`<tr><td>${r.period}</td><td class="num">${r.orders}</td><td class="num">${money(r.revenue)}</td></tr>`), "No completed orders in this range.")}</section>
      <section class="card"><h2>Best sellers</h2>${table(["Product", { label: "Units", num: true }, { label: "Revenue", num: true }],
        top.items.map((r) => html`<tr><td>${r.name}</td><td class="num">${r.units_sold}</td><td class="num">${money(r.revenue)}</td></tr>`), "No sales in this range.")}</section></div>
      <section class="card" style="margin-top:1.25rem"><div class="page-head"><h2>Inventory</h2><button class="small" data-dl="inventory">Download CSV</button></div>${table(
        ["SKU", "Product", { label: "Stock", num: true }, { label: "Price", num: true }, { label: "Value", num: true }, "Status"],
        inv.items.map((p) => html`<tr><td>${p.sku}</td><td>${p.name}</td><td class="num">${p.stock_qty}</td><td class="num">${money(p.price)}</td><td class="num">${money(p.stock_value)}</td><td>${p.low_stock ? "Reorder" : "OK"}</td></tr>`), "No products.")}</section>`.s;
  }
  main.onclick = (e) => {
    const b = e.target.closest("[data-dl]"); if (!b) return;
    const path = b.dataset.dl === "sales" ? "/reports/sales?" + qs({ ...f, format: "csv" }) : "/reports/inventory?format=csv";
    download(path, b.dataset.dl + "-report.csv").catch(fail);
  };
  $("#run").addEventListener("click", () => {
    f.from = $("#from").value; f.to = $("#to").value; f.group = $("#group").value; run().catch(fail);
  });
  await run();
}

async function usersPage(main) {
  const d = await api("/users?limit=100");
  main.innerHTML = html`<div class="page-head"><h1>Users</h1><button class="primary" data-act="add">Add user</button></div>${table(["Name", "Email", "Role", "Status", ""],
    d.items.map((u) => html`<tr><td>${u.name}</td><td>${u.email}</td><td><select data-role="${u.id}" aria-label="Role for ${u.name}" ${u.id === state.user.id ? "disabled" : ""}>${["staff", "manager", "admin"].map((r) =>
      html`<option ${r === u.role ? "selected" : ""}>${r}</option>`)}</select></td><td>${u.active ? "Active" : "Disabled"}</td>
      <td>${u.id === state.user.id ? "" : html`<button class="small" data-act="toggle" data-id="${u.id}" data-active="${u.active}">${u.active ? "Disable" : "Enable"}</button>`}</td></tr>`), "No users.")}`.s;
  main.onclick = async (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    if (b.dataset.act === "add") {
      formModal({ title: "Add user", fields: [{ name: "name", label: "Name", required: true }, { name: "email", label: "Email", type: "email", required: true },
        { name: "password", label: "Temporary password (8+ characters)", type: "password", required: true },
        { name: "role", label: "Role", type: "select", options: ["staff", "manager", "admin"].map((r) => ({ value: r, label: r })) }],
        onSubmit: async (v) => { await api("/users", { method: "POST", body: v }); toast("User added"); usersPage(main); } });
    } else {
      try { await api(`/users/${b.dataset.id}`, { method: "PATCH", body: { active: b.dataset.active !== "1" } }); usersPage(main); } catch (err) { fail(err); }
    }
  };
  main.onchange = async (e) => {
    if (!e.target.dataset.role) return;
    try { await api(`/users/${e.target.dataset.role}`, { method: "PATCH", body: { role: e.target.value } }); toast("Role updated"); } catch (err) { fail(err); usersPage(main); }
  };
}

window.addEventListener("hashchange", route);
route();
