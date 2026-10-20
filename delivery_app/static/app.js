// Delivery checklist UI (vanilla JS). Talks to the backend through window.API.
(function () {
  'use strict';

  const STATUS = {
    todo: 'À faire', running: 'En cours', paused: 'En pause', done: 'Validée', skipped: 'Non applicable',
  };
  const BUILTIN_VARS = [
    ['version', 'version saisie, ex. 2.4.0'],
    ['major / minor / patch', 'segments de la version (2 / 4 / 0)'],
    ['date', 'date de création de la livraison (AAAA-MM-JJ)'],
    ['name', 'nom de la livraison'],
    ['prev_version', 'version précédente (pré-remplie automatiquement)'],
  ];
  const ICONS = {
    play: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M4.5 2.8v10.4L13 8z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M4 3h3v10H4zM9 3h3v10H9z" fill="currentColor"/></svg>',
    check: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chev: '<svg viewBox="0 0 16 16" class="ic chev" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    more: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><circle cx="3.5" cy="8" r="1.4" fill="currentColor"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/><circle cx="12.5" cy="8" r="1.4" fill="currentColor"/></svg>',
    plus: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    list: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M6 4h7M6 8h7M6 12h7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="3" cy="4" r="1" fill="currentColor"/><circle cx="3" cy="8" r="1" fill="currentColor"/><circle cx="3" cy="12" r="1" fill="currentColor"/></svg>',
    file: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M4 1.8h5.2L12.5 5v9.2H4z M9 1.8V5.3h3.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
    up: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M4 10l4-4 4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    down: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  };

  const state = {
    deliveries: [],
    delivery: null,
    templateTasks: [],
    settings: { default_variables: {} },
    view: 'empty', // empty | delivery | template
    expanded: new Set(),  // finished tasks the user re-opened
    collapsed: new Set(), // unfinished tasks the user folded
    menuFor: null,
  };

  const app = document.getElementById('app');

  // ---------------------------------------------------------------- helpers

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  };

  function buildVariables(d) {
    const parts = d.version.split(/[.\-+]/);
    return {
      version: d.version,
      major: parts[0] ?? '', minor: parts[1] ?? '', patch: parts[2] ?? '',
      date: (d.created_at || new Date().toISOString()).slice(0, 10),
      name: d.name || '',
      ...(d.variables || {}),
    };
  }

  const PLACEHOLDER = /\{\{\s*([\w.-]+)\s*\}\}/g;

  function renderText(text, vars) {
    return (text || '').replace(PLACEHOLDER, (m, k) => (k in vars ? vars[k] : m));
  }

  function renderHtml(text, vars) {
    let out = '';
    let last = 0;
    for (const m of (text || '').matchAll(PLACEHOLDER)) {
      out += esc(text.slice(last, m.index));
      const k = m[1];
      out += k in vars && vars[k] !== ''
        ? `<span class="var" title="{{${esc(k)}}}">${esc(vars[k])}</span>`
        : `<span class="var missing" title="Variable non renseignée">${esc(m[0])}</span>`;
      last = m.index + m[0].length;
    }
    return out + esc((text || '').slice(last));
  }

  const LINK = /\[([^\]]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s|]+)/g;

  // Mirror of templating.parse_table: one row per line, cells split by "|", first line = headers.
  function parseCell(text) {
    const segs = [];
    let last = 0;
    for (const m of text.matchAll(LINK)) {
      if (m.index > last) segs.push({ text: text.slice(last, m.index) });
      segs.push(m[1] ? { text: m[1], url: m[2] } : { text: m[3], url: m[3] });
      last = m.index + m[0].length;
    }
    if (last < text.length) segs.push({ text: text.slice(last) });
    return segs;
  }

  function parseTable(spec, vars) {
    const rows = [];
    for (let line of renderText(spec, vars).split('\n')) {
      line = line.trim();
      if (!line || (/^[\s|:-]+$/.test(line) && line.includes('-'))) continue;
      if (line.startsWith('|')) line = line.slice(1);
      if (line.endsWith('|')) line = line.slice(0, -1);
      rows.push(line.split('|').map((c) => parseCell(c.trim())));
    }
    if (!rows.length) return null;
    const width = Math.max(...rows.map((r) => r.length));
    rows.forEach((r) => { while (r.length < width) r.push([]); });
    return { headers: rows[0], rows: rows.slice(1) };
  }

  const cellHtml = (segs, linkStyle = '') => segs.map((s) => (s.url
    ? `<a href="${esc(s.url)}" target="_blank" rel="noopener"${linkStyle}>${esc(s.text)}</a>` : esc(s.text))).join('');

  // Self-contained HTML with inline styles: Word keeps borders, shading and hyperlinks on paste.
  function tableHtmlForWord(table) {
    const td = 'border:1px solid #C8D1DA;padding:4px 8px;font-family:Calibri,Arial,sans-serif;font-size:10.5pt;vertical-align:top;';
    const th = `${td}background:#1F5F7A;color:#FFFFFF;font-weight:bold;text-align:left;`;
    return `<table style="border-collapse:collapse;width:100%;">
      <thead><tr>${table.headers.map((c) => `<th style="${th}">${cellHtml(c, ' style="color:#FFFFFF;"')}</th>`).join('')}</tr></thead>
      <tbody>${table.rows.map((r) => `<tr>${r.map((c) => `<td style="${td}">${cellHtml(c, ' style="color:#0563C1;"')}</td>`).join('')}</tr>`).join('')}</tbody>
    </table>`;
  }

  const tableText = (table) => [table.headers, ...table.rows]
    .map((r) => r.map((c) => c.map((s) => (s.url && s.url !== s.text ? `${s.text} (${s.url})` : s.text)).join('')).join('\t')).join('\n');

  function missingVars(text, vars) {
    const out = new Set();
    for (const m of (text || '').matchAll(PLACEHOLDER)) if (!vars[m[1]]) out.add(m[1]);
    return [...out];
  }

  // Every text of a task that may hold {{variables}}.
  const taskText = (t) => [t.description, ...t.commands.flatMap((c) => [c.label, c.text]),
    ...t.link_tables.flatMap((tb) => [tb.title, tb.spec])].join('\n');

  function placeholdersIn(tasks) {
    const out = new Set();
    for (const t of tasks) for (const m of taskText(t).matchAll(PLACEHOLDER)) out.add(m[1]);
    return [...out];
  }

  function elapsed(t) {
    let s = t.elapsed_seconds || 0;
    if (t.status === 'running' && t.running_since) s += Math.max(0, (Date.now() - Date.parse(t.running_since)) / 1000);
    return Math.floor(s);
  }

  function fmtClock(sec) {
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function fmtDur(sec) {
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
    if (h) return `${h} h ${String(m).padStart(2, '0')}`;
    return `${m} min`;
  }

  function fmtDate(iso, withTime) {
    if (!iso) return '—';
    const d = new Date(iso);
    const opts = withTime
      ? { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }
      : { day: '2-digit', month: 'short', year: 'numeric' };
    return d.toLocaleString('fr-FR', opts);
  }

  const parseVars = (text) => Object.fromEntries(text.split('\n')
    .map((l) => l.match(/^\s*([\w.-]+)\s*[=:]\s*(.*?)\s*$/)).filter(Boolean).map((m) => [m[1], m[2]]));
  const varsToText = (vars) => Object.entries(vars || {}).map(([k, v]) => `${k} = ${v}`).join('\n');

  const finished = (t) => t.status === 'done' || t.status === 'skipped';
  const isOpen = (t) => (finished(t) ? state.expanded.has(t.id) : !state.collapsed.has(t.id));

  function toast(msg, isErr) {
    let wrap = document.querySelector('.toast-wrap');
    if (!wrap) { wrap = document.createElement('div'); wrap.className = 'toast-wrap'; document.body.appendChild(wrap); }
    const el = document.createElement('div');
    el.className = `toast${isErr ? ' err' : ''}`;
    el.setAttribute('role', 'status');
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => el.remove(), isErr ? 5000 : 2400);
  }

  async function run(promise, okMsg) {
    try {
      const res = await promise;
      if (okMsg) toast(okMsg);
      return res;
    } catch (err) {
      toast(err.message || String(err), true);
      throw err;
    }
  }

  // ---------------------------------------------------------------- data

  async function refreshList() {
    state.deliveries = await API.listDeliveries();
  }

  async function setDelivery(d) {
    state.delivery = d;
    state.view = 'delivery';
    store.set('lastDelivery', String(d.id));
    await refreshList();
    render();
  }

  async function openDelivery(id) {
    const d = await run(API.getDelivery(id));
    state.expanded.clear();
    state.collapsed.clear();
    await setDelivery(d);
    document.querySelector('.main')?.scrollTo(0, 0);
  }

  async function openTemplate() {
    [state.templateTasks, state.settings] = await Promise.all([API.listTasks(), API.getSettings()]);
    state.view = 'template';
    render();
  }

  // ---------------------------------------------------------------- render

  function render() {
    const focusId = document.activeElement?.id;
    const scroll = document.querySelector('.main')?.scrollTop ?? 0;
    const drafts = {};
    document.querySelectorAll('textarea[data-draft]').forEach((t) => { if (t.value) drafts[t.id] = t.value; });

    app.innerHTML = renderSidebar() + `<main class="main"><div class="main-inner">${renderMain()}</div></main>`;

    for (const [id, v] of Object.entries(drafts)) { const t = document.getElementById(id); if (t) t.value = v; }
    document.querySelector('.main').scrollTop = scroll;
    if (focusId) document.getElementById(focusId)?.focus();
    tick();
  }

  function renderSidebar() {
    const items = state.deliveries.map((d) => `
      <button class="hist-item ${state.view === 'delivery' && state.delivery?.id === d.id ? 'active' : ''} ${d.status === 'done' ? 'closed' : ''}"
              data-act="open-delivery" data-id="${d.id}">
        <span class="hist-version">${esc(d.version)}</span>
        <span class="hist-pct num">${d.status === 'done' ? 'Clôturée' : `${d.progress} %`}</span>
        <span class="hist-meta">${esc(d.name || 'Sans nom')} · ${fmtDate(d.created_at)}</span>
        <span class="hist-bar"><span style="width:${d.progress}%"></span></span>
      </button>`).join('');
    return `
      <aside class="side">
        <div class="brand"><span class="brand-mark">${ICONS.check}</span>Checklist Livraison</div>
        ${API.demo ? '<span class="demo-flag">Démo · données d\'exemple</span>' : ''}
        <nav class="side-nav">
          <button class="btn primary block" data-act="new-delivery">${ICONS.plus}Nouvelle livraison</button>
          <button class="btn ghost block ${state.view === 'template' ? 'active' : ''}" data-act="template">${ICONS.list}Modèle de tâches</button>
        </nav>
        <div class="side-label">Historique des livraisons</div>
        <div class="history">${items || '<div class="side-empty">Aucune livraison pour le moment.</div>'}</div>
      </aside>`;
  }

  function renderMain() {
    if (state.view === 'template') return renderTemplate();
    if (state.view === 'delivery' && state.delivery) return renderDelivery();
    return `
      <div class="empty">
        <h2>Prêt pour la prochaine livraison</h2>
        <p>Créez une livraison à partir du modèle de tâches. Les commandes s'adaptent à la version saisie,
           et chaque livraison reste consultable dans l'historique.</p>
        <div class="add-row">
          <button class="btn primary" data-act="new-delivery">${ICONS.plus}Nouvelle livraison</button>
          <button class="btn" data-act="template">${ICONS.list}Voir le modèle</button>
        </div>
      </div>`;
  }

  function renderDelivery() {
    const d = state.delivery;
    const vars = buildVariables(d);
    const custom = Object.entries(d.variables || {});
    const active = d.tasks.filter((t) => t.status !== 'skipped');
    const totalW = active.reduce((a, t) => a + t.weight, 0);
    const doneW = d.tasks.filter((t) => t.status === 'done').reduce((a, t) => a + t.weight, 0);
    const doneN = d.tasks.filter(finished).length;

    const segs = d.tasks.map((t) => `<span class="seg ${t.status}" style="flex:${Math.max(t.weight, 0.2)}"
      title="${esc(t.title)} · poids ${t.weight} · ${STATUS[t.status]}"></span>`).join('');

    return `
      <div class="head">
        <div>
          <div class="eyebrow">Livraison n° ${d.id} · créée le ${fmtDate(d.created_at, true)}</div>
          <h1>Version <span class="v">${esc(d.version)}</span></h1>
          ${d.name ? `<div class="sub">${esc(d.name)}</div>` : ''}
        </div>
        <div class="head-actions">
          <button class="btn" data-act="export" data-fmt="pdf">${ICONS.file}Rapport PDF</button>
          <button class="btn" data-act="export" data-fmt="docx">${ICONS.file}Rapport Word</button>
          ${d.status === 'done'
            ? ''
            : `<button class="btn ok" data-act="close-delivery">${ICONS.check}Clôturer</button>`}
          <div class="task-actions">
            <button class="btn icon" data-act="menu" data-id="delivery" aria-label="Plus d'actions">${ICONS.more}</button>
            ${state.menuFor === 'delivery' ? `<div class="menu">
              <button data-act="edit-delivery">Modifier version et variables</button>
              <button class="danger" data-act="delete-delivery">Supprimer la livraison</button>
            </div>` : ''}
          </div>
        </div>
      </div>

      <div class="chips">
        <span class="chip">{{version}} = <b>${esc(d.version)}</b></span>
        ${custom.map(([k, v]) => `<span class="chip">{{${esc(k)}}} = <b>${v ? esc(v) : '<i>vide</i>'}</b></span>`).join('')}
        <button class="chip edit" data-act="edit-delivery">Modifier les variables</button>
      </div>

      ${d.status === 'done' ? `<div class="banner">
        <span>Livraison clôturée le ${fmtDate(d.completed_at, true)}.</span>
        <button class="btn" data-act="reopen-delivery">Rouvrir</button></div>` : ''}

      <section class="progress-card" aria-label="Progression">
        <div class="pct num">${d.progress}<small>%</small></div>
        <div class="segbar" role="progressbar" aria-valuenow="${d.progress}" aria-valuemin="0" aria-valuemax="100">${segs}</div>
        <div class="stats num">
          <span><b>${doneN}</b> / ${d.tasks.length} tâches</span>
          <span>Poids <b>${doneW}</b> / ${totalW}</span>
          <span>Passé <b data-total-spent>—</b></span>
          <span>Estimé <b>${fmtDur(active.reduce((a, t) => a + t.estimated_minutes * 60, 0))}</b></span>
          <span>Reste estimé <b>${fmtDur(active.filter((t) => !finished(t)).reduce((a, t) => a + t.estimated_minutes * 60, 0))}</b></span>
        </div>
      </section>

      <div class="tasks">${d.tasks.map((t, i) => renderTask(t, i, vars)).join('')}</div>

      <div class="add-row">
        <button class="btn" data-act="add-delivery-task">${ICONS.plus}Ajouter une tâche à cette livraison</button>
      </div>`;
  }

  // Thumbnails of one task. scope: 'task' (delivery task) or 'tpl' (template task).
  function thumbStrip(scope, ownerId, images, { canAdd = true, toTemplate = false, small = false, addLabel = 'Ajouter' } = {}) {
    return `<div class="thumbs${small ? ' small' : ''}">
      ${images.map((img) => `
        <div class="thumb" role="button" tabindex="0" data-act="lightbox" data-scope="${scope}" data-owner="${ownerId}" data-img="${img.id}" title="${esc(img.filename)}">
          <img src="${esc(img.url)}" alt="${esc(img.filename)}" loading="lazy">
          <button class="x" data-act="delete-image" data-scope="${scope}" data-id="${img.id}" aria-label="Supprimer l'image">✕</button>
          ${toTemplate ? `<button class="to-tpl" data-act="image-to-template" data-id="${img.id}" title="Ajouter au modèle : les prochaines livraisons la recevront">→ modèle</button>` : ''}
        </div>`).join('')}
      ${canAdd ? `<button class="thumb-add" data-act="add-image" data-scope="${scope}" data-id="${ownerId}">${ICONS.plus}<span>${esc(addLabel)}</span></button>
      <input type="file" accept="image/*" multiple hidden data-upload="${scope}:${ownerId}">` : ''}
    </div>`;
  }

  function imagesOf(scope, ownerId) {
    const list = scope === 'tpl' ? state.templateTasks : state.delivery.tasks;
    return list.find((t) => t.id === ownerId)?.images || [];
  }

  function renderTask(t, i, vars) {
    const open = isOpen(t);
    const est = t.estimated_minutes;
    const primary = {
      todo: `<button class="btn run" data-act="task" data-action="start" data-id="${t.id}">${ICONS.play}Démarrer</button>`,
      paused: `<button class="btn run" data-act="task" data-action="start" data-id="${t.id}">${ICONS.play}Reprendre</button>`,
      running: `<button class="btn run" data-act="task" data-action="pause" data-id="${t.id}">${ICONS.pause}Pause</button>`,
    }[t.status] || '';
    const validate = finished(t) ? '' :
      `<button class="btn ok" data-act="task" data-action="done" data-id="${t.id}">${ICONS.check}Valider</button>`;

    const refImages = t.images.filter((img) => img.reference);
    const ownImages = t.images.filter((img) => !img.reference);
    const missing = missingVars(t.commands.map((c) => `${c.label}\n${c.text}`).join('\n'), vars);
    const tables = t.link_tables.map((tb) => ({ title: renderText(tb.title, vars), table: parseTable(tb.spec, vars) }))
      .filter((tb) => tb.table);
    const missingTbl = missingVars(t.link_tables.map((tb) => `${tb.title}\n${tb.spec}`).join('\n'), vars);
    const warn = (names, fix) => (names.length ? `<div class="warn-vars">Variable non renseignée : ${names.map((m) => `{{${esc(m)}}}`).join(', ')}${fix
      ? ' — <a href="#" data-act="edit-delivery">la définir</a>' : ''}</div>` : '');
    const body = !open ? '' : `
      <div class="task-body">
        ${t.description ? `<div class="desc">${renderHtml(t.description, vars).replace(/<span class="var[^"]*"[^>]*>/g, '<b>').replace(/<\/span>/g, '</b>')}</div>` : ''}
        ${t.commands.length ? `<div class="stack">
          <div class="section-label">${t.commands.length > 1 ? `Lignes de commande (${t.commands.length})` : 'Ligne de commande'}</div>
          ${t.commands.map((c, i) => `<div class="cmd-block">
            ${c.label ? `<div class="cmd-label">${renderHtml(c.label, vars)}</div>` : ''}
            <div class="cmd"><pre>${renderHtml(c.text, vars)}</pre>
              <button class="copy" data-act="copy" data-id="${t.id}" data-idx="${i}">Copier</button></div>
          </div>`).join('')}
          ${warn(missing, true)}
        </div>` : ''}
        ${tables.length ? `<div class="stack">
          <div class="section-label">${tables.length > 1 ? `Tableaux pour Word (${tables.length})` : 'Tableau pour Word'}</div>
          ${tables.map(({ title, table }, i) => `<div class="table-block">
            ${title ? `<div class="table-title">${esc(title)}</div>` : ''}
            <div class="doc-table-wrap"><table class="doc-table">
              <thead><tr>${table.headers.map((c) => `<th>${cellHtml(c)}</th>`).join('')}</tr></thead>
              <tbody>${table.rows.map((r) => `<tr>${r.map((c) => `<td>${cellHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody>
            </table></div>
            <div class="add-row table-actions">
              <button class="btn" data-act="copy-table" data-id="${t.id}" data-idx="${i}">Copier pour Word</button>
              <button class="btn ghost" data-act="table-docx" data-id="${t.id}" data-idx="${i}">Télécharger en .docx</button>
            </div>
          </div>`).join('')}
          ${tables.length > 1 ? `<div class="add-row table-actions all">
            <button class="btn" data-act="copy-table" data-id="${t.id}">Copier tous les tableaux</button>
            <button class="btn ghost" data-act="table-docx" data-id="${t.id}">Tous en .docx</button>
          </div>` : ''}
          ${warn(missingTbl, true)}
        </div>` : ''}
        ${refImages.length ? `<div>
          <div class="section-label">Captures de référence du modèle (${refImages.length})</div>
          ${thumbStrip('task', t.id, refImages, { canAdd: false })}
        </div>` : ''}
        <div>
          <div class="section-label">Captures (${ownImages.length})</div>
          ${thumbStrip('task', t.id, ownImages, { toTemplate: Boolean(t.template_task_id) })}
        </div>
        <div>
          <div class="section-label">Commentaires (${t.comments.length})</div>
          <div class="comments">
            ${t.comments.map((c) => `<div class="comment">
              <time>${fmtDate(c.created_at, true)}</time>
              <button class="del" data-act="delete-comment" data-id="${c.id}" aria-label="Supprimer le commentaire">Supprimer</button>
              <p>${esc(c.body)}</p></div>`).join('')}
            <div class="comment-form">
              <textarea id="c-${t.id}" data-draft rows="1" placeholder="Ajouter un commentaire… (Ctrl+Entrée pour publier, Ctrl+V pour coller une capture)" data-comment="${t.id}"></textarea>
              <button class="btn" data-act="comment" data-id="${t.id}">Publier</button>
            </div>
          </div>
        </div>
      </div>`;

    return `
      <article class="task ${t.status} ${finished(t) ? 'finished' : ''} ${open ? 'open' : ''}" data-task-id="${t.id}">
        <div class="task-head">
          <button class="status-btn" data-act="task" data-action="${finished(t) ? 'reopen' : 'done'}" data-id="${t.id}"
                  aria-label="${finished(t) ? 'Rouvrir la tâche' : 'Valider la tâche'}">${t.status === 'skipped' ? '–' : ICONS.check}</button>
          <div class="task-title" data-act="toggle" data-id="${t.id}">
            <strong>${i + 1}. ${esc(t.title)}</strong>
            <span class="task-meta">
              ${t.status !== 'todo' ? `<span class="pill ${t.status}">${STATUS[t.status]}</span>` : ''}
              <span class="badge">Poids ${t.weight}</span>
              <span class="badge">Estimé ${est ? fmtDur(est * 60) : '—'}</span>
              ${t.comments.length ? `<span class="badge">${t.comments.length} commentaire${t.comments.length > 1 ? 's' : ''}</span>` : ''}
              ${t.images.length ? `<span class="badge">${t.images.length} capture${t.images.length > 1 ? 's' : ''}</span>` : ''}
              ${t.link_tables.length ? `<span class="badge">${t.link_tables.length > 1 ? `${t.link_tables.length} tableaux Word` : 'Tableau Word'}</span>` : ''}
            </span>
          </div>
          <span class="timer" data-timer="${t.id}" title="Temps passé / estimé"></span>
          <div class="task-actions">
            ${primary}${validate}
            <button class="btn icon ghost" data-act="menu" data-id="${t.id}" aria-label="Plus d'actions">${ICONS.more}</button>
            <button class="btn icon ghost" data-act="toggle" data-id="${t.id}" aria-label="${open ? 'Replier' : 'Déplier'}">${ICONS.chev}</button>
            ${state.menuFor === t.id ? `<div class="menu">
              <button data-act="edit-task" data-id="${t.id}">Modifier la tâche</button>
              ${finished(t) ? '' : `<button data-act="task" data-action="skip" data-id="${t.id}">Marquer non applicable</button>`}
              <button data-act="move-task" data-dir="-1" data-id="${t.id}">Monter</button>
              <button data-act="move-task" data-dir="1" data-id="${t.id}">Descendre</button>
              <button data-act="task" data-action="reset" data-id="${t.id}">Remettre à zéro (statut et chrono)</button>
              <button class="danger" data-act="delete-task" data-id="${t.id}">Retirer de cette livraison</button>
            </div>` : ''}
          </div>
        </div>
        ${body}
      </article>`;
  }

  function renderTemplate() {
    const tasks = state.templateTasks;
    const totalW = tasks.reduce((a, t) => a + t.weight, 0);
    const totalE = tasks.reduce((a, t) => a + t.estimated_minutes, 0);
    const rows = tasks.map((t, i) => `
      <div class="tpl-row" data-tpl-id="${t.id}" tabindex="-1">
        <span class="tpl-idx">${i + 1}</span>
        <div class="tpl-main">
          <strong>${esc(t.title)}</strong>
          <div class="tpl-cmd">${t.commands.length ? esc(t.commands[0].text.split('\n')[0]) : '<i>pas de commande</i>'}${t.commands.length > 1 ? ` <span class="tpl-tag">+${t.commands.length - 1} commande${t.commands.length > 2 ? 's' : ''}</span>` : ''}${t.link_tables.length ? ` · <span class="tpl-tag">${t.link_tables.length} tableau${t.link_tables.length > 1 ? 'x' : ''} Word</span>` : ''}</div>
          <div class="tpl-images">${thumbStrip('tpl', t.id, t.images, { small: true, addLabel: 'Capture de référence' })}</div>
        </div>
        <div class="tpl-nums num"><span>Poids ${t.weight}</span><span>${t.estimated_minutes ? fmtDur(t.estimated_minutes * 60) : '—'}</span></div>
        <div class="tpl-btns">
          <button class="btn icon ghost" data-act="tpl-move" data-dir="-1" data-id="${t.id}" aria-label="Monter" ${i === 0 ? 'disabled' : ''}>${ICONS.up}</button>
          <button class="btn icon ghost" data-act="tpl-move" data-dir="1" data-id="${t.id}" aria-label="Descendre" ${i === tasks.length - 1 ? 'disabled' : ''}>${ICONS.down}</button>
          <button class="btn ghost" data-act="tpl-edit" data-id="${t.id}">Modifier</button>
          <button class="btn ghost danger" data-act="tpl-delete" data-id="${t.id}">Supprimer</button>
        </div>
      </div>`).join('');

    return `
      <div class="head">
        <div>
          <div class="eyebrow">${tasks.length} tâches · poids total ${totalW} · ${fmtDur(totalE * 60)} estimées</div>
          <h1>Modèle de tâches</h1>
          <div class="sub">Copié dans chaque nouvelle livraison. Les livraisons existantes ne sont pas modifiées.</div>
        </div>
        <div class="head-actions"><button class="btn primary" data-act="tpl-add">${ICONS.plus}Ajouter une tâche</button></div>
      </div>
      <div class="tpl-list">${rows || '<div class="tpl-row"><span></span><span class="tpl-main">Aucune tâche. Ajoutez la première.</span></div>'}</div>
      <div class="grid2">
        <section class="panel">
          <h3>Variables disponibles dans les commandes</h3>
          <p>Écrivez <code>{{version}}</code> dans une commande ou une description : la valeur de la livraison est substituée.</p>
          <div class="help-vars">${BUILTIN_VARS.map(([k, v]) => `<code>{{${k}}}</code><span>${v}</span>`).join('')}</div>
        </section>
        <section class="panel">
          <h3>Variables par défaut</h3>
          <p>Pré-remplies à chaque nouvelle livraison (une par ligne, <code>clé = valeur</code>). Utile pour un serveur, un dépôt, un environnement…</p>
          <textarea id="default-vars" class="mono" rows="5" placeholder="env = recette&#10;registry = registry.local">${esc(varsToText(state.settings.default_variables))}</textarea>
          <div><button class="btn" data-act="save-defaults">Enregistrer</button></div>
        </section>
      </div>`;
  }

  // ---------------------------------------------------------------- live timers

  function tick() {
    const d = state.delivery;
    if (state.view !== 'delivery' || !d) return;
    let total = 0;
    for (const t of d.tasks) {
      const sec = elapsed(t);
      total += sec;
      const el = document.querySelector(`[data-timer="${t.id}"]`);
      if (!el) continue;
      const est = t.estimated_minutes * 60;
      el.classList.toggle('over', est > 0 && sec > est);
      el.innerHTML = t.status === 'todo' && !sec ? '' : `<b>${fmtClock(sec)}</b>${est ? ` / ${fmtDur(est)}` : ''}`;
    }
    const tot = document.querySelector('[data-total-spent]');
    if (tot) tot.textContent = fmtDur(total);
  }
  setInterval(tick, 1000);

  // ---------------------------------------------------------------- modals

  function modal({ title, body, submit = 'Enregistrer', onSubmit, onInput, danger }) {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.innerHTML = `
      <form class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <header><h2>${esc(title)}</h2></header>
        <div class="content">${body}<div class="error" hidden></div></div>
        <footer>
          <button type="button" class="btn" data-close>Annuler</button>
          <button type="submit" class="btn ${danger ? 'danger' : 'primary'}">${esc(submit)}</button>
        </footer>
      </form>`;
    const form = overlay.querySelector('form');
    const close = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
    overlay.querySelector('[data-close]').onclick = close;
    if (onInput) form.addEventListener('input', () => onInput(form));
    if (form.querySelector('[data-list]')) repEditor(form);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const errEl = form.querySelector('.error');
      try {
        await onSubmit(form);
        close();
      } catch (err) {
        errEl.textContent = err.message || String(err);
        errEl.hidden = false;
      }
    });
    document.body.appendChild(overlay);
    if (onInput) onInput(form);
    form.querySelector('input:not([type=checkbox]), textarea')?.focus();
    return form;
  }

  function confirmBox(message, okLabel = 'Supprimer') {
    return new Promise((resolve) => {
      let ok = false;
      const form = modal({
        title: 'Confirmation', body: `<p style="margin:0">${esc(message)}</p>`, submit: okLabel, danger: true,
        onSubmit: () => { ok = true; },
      });
      new MutationObserver((_, obs) => {
        if (!document.body.contains(form)) { obs.disconnect(); resolve(ok); }
      }).observe(document.body, { childList: true });
    });
  }

  function taskFormBody(t = {}, extra = '') {
    return `
      <div class="field"><label for="f-title">Titre</label>
        <input type="text" id="f-title" name="title" required value="${esc(t.title)}"></div>
      <div class="field"><label for="f-desc">Description</label>
        <textarea id="f-desc" name="description" rows="3">${esc(t.description)}</textarea></div>
      <div class="field"><label>Lignes de commande</label>
        <div class="rep-list" data-list="commands">${(t.commands?.length ? t.commands : [{}]).map((c) => repRow('commands', c)).join('')}</div>
        <div><button type="button" class="btn ghost" data-rep-add="commands">${ICONS.plus}Ajouter une commande</button></div>
        <span class="hint">Chaque bloc a son bouton Copier. Variables : {{version}}, {{major}}, {{minor}}, {{patch}}, {{prev_version}}, {{date}} et vos variables personnalisées.</span></div>
      <div class="field"><label>Tableaux pour Word (optionnels)</label>
        <div class="rep-list" data-list="link_tables">${(t.link_tables || []).map((tb) => repRow('link_tables', tb)).join('')}</div>
        <div><button type="button" class="btn ghost" data-rep-add="link_tables">${ICONS.plus}Ajouter un tableau Word</button></div>
        <span class="hint">Une ligne par rangée, cellules séparées par <code>|</code>, la 1re ligne donne les en-têtes. Liens : <code>[texte](https://…)</code> ou URL brute. Variables acceptées.</span></div>
      <div class="row2">
        <div class="field"><label for="f-weight">Poids (progression)</label>
          <input type="number" id="f-weight" name="weight" min="0" step="1" value="${t.weight ?? 1}"></div>
        <div class="field"><label for="f-est">Temps estimé (minutes)</label>
          <input type="number" id="f-est" name="estimated_minutes" min="0" step="1" value="${t.estimated_minutes ?? 10}"></div>
      </div>${extra}`;
  }

  // One editable entry of a repeated list (a command block or a Word table) in the task form.
  function repRow(kind, item = {}) {
    const isCmd = kind === 'commands';
    return `<div class="rep-item" data-item>
      <div class="rep-head">
        <input type="text" data-k="${isCmd ? 'label' : 'title'}" value="${esc(isCmd ? item.label : item.title)}"
               placeholder="${isCmd ? 'Libellé (optionnel) : Linux, Build, Rollback…' : 'Titre du tableau (optionnel) : Liens, Livrables…'}"
               aria-label="${isCmd ? 'Libellé de la commande' : 'Titre du tableau'}">
        <button type="button" class="btn icon ghost" data-rep-move="-1" aria-label="Monter">${ICONS.up}</button>
        <button type="button" class="btn icon ghost" data-rep-move="1" aria-label="Descendre">${ICONS.down}</button>
        <button type="button" class="btn ghost danger" data-rep-remove>Retirer</button>
      </div>
      <textarea data-k="${isCmd ? 'text' : 'spec'}" class="mono" rows="${isCmd ? 3 : 4}" aria-label="${isCmd ? 'Commande' : 'Contenu du tableau'}"
        placeholder="${isCmd ? 'git tag -a v{{version}} -m &quot;Release {{version}}&quot;'
          : 'Élément | Lien&#10;Notes de version | [Wiki {{version}}](https://wiki.example.com/releases/{{version}})&#10;Ticket | https://jira.example.com/browse/REL-{{version}}'}">${esc(isCmd ? item.text : item.spec)}</textarea>
    </div>`;
  }

  function repEditor(form) {
    form.addEventListener('click', (e) => {
      const add = e.target.closest('[data-rep-add]');
      const item = e.target.closest('[data-item]');
      if (add) {
        const list = form.querySelector(`[data-list="${add.dataset.repAdd}"]`);
        list.insertAdjacentHTML('beforeend', repRow(add.dataset.repAdd));
        list.lastElementChild.querySelector('textarea').focus();
      } else if (item && e.target.closest('[data-rep-remove]')) {
        item.remove();
      } else if (item && e.target.closest('[data-rep-move]')) {
        const dir = Number(e.target.closest('[data-rep-move]').dataset.repMove);
        const other = dir < 0 ? item.previousElementSibling : item.nextElementSibling;
        if (other) (dir < 0 ? other.before(item) : other.after(item));
      }
    });
  }

  const listData = (form, kind, [k1, k2]) => [...form.querySelectorAll(`[data-list="${kind}"] [data-item]`)]
    .map((row) => ({ [k1]: row.querySelector(`[data-k="${k1}"]`).value.trim(), [k2]: row.querySelector(`[data-k="${k2}"]`).value }))
    .filter((x) => x[k2].trim());

  const taskFormData = (form) => ({
    title: form.title.value.trim(),
    description: form.description.value,
    commands: listData(form, 'commands', ['label', 'text']),
    link_tables: listData(form, 'link_tables', ['title', 'spec']),
    weight: Number(form.weight.value) || 0,
    estimated_minutes: Number(form.estimated_minutes.value) || 0,
  });

  async function deliveryModal(existing) {
    const tasks = existing ? existing.tasks : await API.listTasks();
    const settings = await API.getSettings();
    let vars = existing ? { ...existing.variables } : { ...settings.default_variables };
    if (!existing) {
      const prev = state.deliveries[0];
      if (prev && !vars.prev_version) vars.prev_version = prev.version;
    }
    const used = placeholdersIn(tasks);
    modal({
      title: existing ? 'Modifier la livraison' : 'Nouvelle livraison',
      submit: existing ? 'Enregistrer' : 'Créer la livraison',
      body: `
        <div class="row2">
          <div class="field"><label for="d-version">Version</label>
            <input type="text" id="d-version" name="version" class="mono" required placeholder="ex. 2.5.0" value="${esc(existing?.version)}"></div>
          <div class="field"><label for="d-name">Nom (optionnel)</label>
            <input type="text" id="d-name" name="name" placeholder="Release d'automne" value="${esc(existing?.name)}"></div>
        </div>
        <div class="field"><label for="d-vars">Variables personnalisées</label>
          <textarea id="d-vars" name="vars" class="mono" rows="4" placeholder="prev_version = 2.3.1&#10;env = recette">${esc(varsToText(vars))}</textarea>
          <span class="hint">Une par ligne, <code>clé = valeur</code>. Utilisables dans les commandes sous la forme {{clé}}.</span></div>
        <div class="field"><label>Variables utilisées par les tâches</label><div class="var-preview" data-preview></div></div>`,
      onInput(form) {
        const draft = { version: form.version.value.trim() || '?', name: form.name.value, created_at: existing?.created_at, variables: parseVars(form.vars.value) };
        const v = buildVariables(draft);
        form.querySelector('[data-preview]').innerHTML = used.length
          ? used.map((k) => `<span class="chip ${v[k] ? '' : 'missing'}">{{${esc(k)}}} = <b>${v[k] ? esc(v[k]) : 'non renseignée'}</b></span>`).join('')
          : '<span>Aucune variable dans les commandes.</span>';
      },
      async onSubmit(form) {
        const data = { version: form.version.value.trim(), name: form.name.value.trim(), variables: parseVars(form.vars.value) };
        const d = existing ? await API.updateDelivery(existing.id, data) : await API.createDelivery(data);
        if (!existing) { state.expanded.clear(); state.collapsed.clear(); }
        await setDelivery(d);
        toast(existing ? 'Livraison mise à jour' : `Livraison ${d.version} créée`);
      },
    });
  }

  // ---------------------------------------------------------------- lightbox

  function lightbox(images, imgId) {
    const task = { images };
    let idx = task.images.findIndex((i) => i.id === imgId);
    const el = document.createElement('div');
    el.className = 'lightbox';
    el.setAttribute('role', 'dialog');
    const show = () => {
      const img = task.images[idx];
      el.innerHTML = `
        <button class="close" aria-label="Fermer">✕</button>
        ${task.images.length > 1 ? '<button class="nav prev" aria-label="Précédente">‹</button><button class="nav next" aria-label="Suivante">›</button>' : ''}
        <img src="${esc(img.url)}" alt="${esc(img.filename)}">
        <div class="cap">${esc(img.filename)} · ${idx + 1} / ${task.images.length}</div>`;
    };
    const step = (n) => { idx = (idx + n + task.images.length) % task.images.length; show(); };
    const close = () => { el.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = (e) => {
      if (e.key === 'Escape') close();
      if (e.key === 'ArrowRight') step(1);
      if (e.key === 'ArrowLeft') step(-1);
    };
    el.addEventListener('click', (e) => {
      if (e.target.closest('.prev')) step(-1);
      else if (e.target.closest('.next')) step(1);
      else if (e.target.tagName !== 'IMG') close();
    });
    document.addEventListener('keydown', onKey);
    show();
    document.body.appendChild(el);
  }

  // ---------------------------------------------------------------- actions

  // Reports embed PNG/JPEG only: other formats (GIF, WebP, BMP…) are converted to PNG in the browser.
  async function toPngOrJpeg(file) {
    if (file.type === 'image/png' || file.type === 'image/jpeg') return file;
    const url = URL.createObjectURL(file);
    try {
      const img = await new Promise((resolve, reject) => {
        const i = new Image();
        i.onload = () => resolve(i);
        i.onerror = () => reject(new Error(`Image illisible : ${file.name}`));
        i.src = url;
      });
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
      const name = (file.name || 'capture').replace(/\.[^.]+$/, '') + '.png';
      return new File([blob], name, { type: 'image/png' });
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function uploadFiles(scope, ownerId, files) {
    const images = [...files].filter((f) => f.type.startsWith('image/'));
    if (!images.length) return;
    const upload = scope === 'tpl' ? API.uploadTemplateImage : API.uploadImage;
    let res;
    for (const f of images) res = await run(toPngOrJpeg(f).then((png) => upload(ownerId, png)));
    if (scope === 'tpl') {
      state.templateTasks = res;
      render();
    } else {
      await setDelivery(res);
    }
    toast(images.length > 1 ? `${images.length} images ajoutées` : 'Image ajoutée');
  }

  async function copyCommand(btn, taskId, idx) {
    const t = state.delivery.tasks.find((x) => x.id === taskId);
    const text = renderText(t.commands[idx].text, buildVariables(state.delivery));
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(btn.parentElement.querySelector('pre'));
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      toast('Copie automatique refusée : texte sélectionné, faites Ctrl+C');
      return;
    }
    btn.textContent = 'Copié ✓';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copier'; btn.classList.remove('copied'); }, 1500);
  }

  // idx = one table; null = all of them, each preceded by its title.
  async function copyTable(btn, taskId, idx) {
    const t = state.delivery.tasks.find((x) => x.id === taskId);
    const vars = buildVariables(state.delivery);
    let tables = t.link_tables.map((tb) => ({ title: renderText(tb.title, vars), table: parseTable(tb.spec, vars) }))
      .filter((tb) => tb.table);
    if (idx !== null) tables = [tables[idx]];
    const withTitles = tables.length > 1;
    const titleStyle = 'font-family:Calibri,Arial,sans-serif;font-size:11pt;font-weight:bold;margin:12pt 0 4pt;';
    const html = tables.map(({ title, table }) => (withTitles && title ? `<p style="${titleStyle}">${esc(title)}</p>` : '')
      + tableHtmlForWord(table)).join('<p></p>');
    const text = tables.map(({ title, table }) => (withTitles && title ? `${title}\n` : '') + tableText(table)).join('\n\n');
    const label = btn.textContent;
    let ok = false;
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([text], { type: 'text/plain' }),
      })]);
      ok = true;
    } catch {
      // Fallback: select a rendered copy so the browser puts rich HTML on the clipboard.
      const holder = document.createElement('div');
      holder.style.cssText = 'position:fixed;left:-10000px;top:0;background:#fff;color:#000;';
      holder.innerHTML = html;
      document.body.appendChild(holder);
      const range = document.createRange();
      range.selectNodeContents(holder);
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      try { ok = document.execCommand('copy'); } catch { ok = false; }
      getSelection().removeAllRanges();
      holder.remove();
    }
    if (!ok) { toast('Copie refusée par le navigateur : utilisez « Télécharger en .docx ».', true); return; }
    btn.textContent = 'Copié ✓ — collez dans Word';
    setTimeout(() => { btn.textContent = label; }, 2200);
  }

  async function postComment(taskId) {
    const ta = document.getElementById(`c-${taskId}`);
    if (!ta.value.trim()) return;
    const d = await run(API.addComment(taskId, ta.value));
    ta.value = '';
    await setDelivery(d);
  }

  const handlers = {
    'open-delivery': (el) => openDelivery(Number(el.dataset.id)),
    'new-delivery': () => deliveryModal(null),
    'edit-delivery': () => deliveryModal(state.delivery),
    template: () => openTemplate(),
    menu: (el) => {
      const id = el.dataset.id === 'delivery' ? 'delivery' : Number(el.dataset.id);
      state.menuFor = state.menuFor === id ? null : id;
      render();
    },
    toggle: (el) => {
      const t = state.delivery.tasks.find((x) => x.id === Number(el.dataset.id));
      const set = finished(t) ? state.expanded : state.collapsed;
      set.has(t.id) ? set.delete(t.id) : set.add(t.id);
      render();
    },
    async task(el) {
      const id = Number(el.dataset.id);
      const action = el.dataset.action;
      const d = await run(API.taskAction(id, action));
      if (action === 'reopen') state.expanded.delete(id);
      if (action === 'done' || action === 'skip') state.expanded.delete(id);
      await setDelivery(d);
    },
    copy: (el) => copyCommand(el, Number(el.dataset.id), Number(el.dataset.idx)),
    'copy-table': (el) => copyTable(el, Number(el.dataset.id), el.dataset.idx === undefined ? null : Number(el.dataset.idx)),
    'table-docx': (el) => run(API.exportTaskTable(Number(el.dataset.id),
      el.dataset.idx === undefined ? null : Number(el.dataset.idx))),
    comment: (el) => postComment(Number(el.dataset.id)),
    async 'delete-comment'(el) {
      if (!(await confirmBox('Supprimer ce commentaire ?'))) return;
      await setDelivery(await run(API.deleteComment(Number(el.dataset.id))));
    },
    'add-image': (el) => document.querySelector(`[data-upload="${el.dataset.scope}:${el.dataset.id}"]`).click(),
    lightbox: (el) => lightbox(imagesOf(el.dataset.scope, Number(el.dataset.owner)), Number(el.dataset.img)),
    async 'delete-image'(el) {
      if (el.dataset.scope === 'tpl') {
        if (!(await confirmBox("Supprimer cette capture du modèle ? Les livraisons existantes gardent leur copie."))) return;
        state.templateTasks = await run(API.deleteTemplateImage(Number(el.dataset.id)));
        render();
        return;
      }
      if (!(await confirmBox("Supprimer cette image ?"))) return;
      await setDelivery(await run(API.deleteImage(Number(el.dataset.id))));
    },
    async 'image-to-template'(el) {
      await setDelivery(await run(API.imageToTemplate(Number(el.dataset.id)),
        'Capture ajoutée au modèle : les prochaines livraisons la recevront'));
    },
    'edit-task': (el) => {
      const t = state.delivery.tasks.find((x) => x.id === Number(el.dataset.id));
      modal({
        title: 'Modifier la tâche',
        body: taskFormBody(t, t.template_task_id ? `
          <label class="check"><input type="checkbox" name="sync"> Répercuter aussi dans le modèle (prochaines livraisons)</label>` : ''),
        async onSubmit(form) {
          const data = taskFormData(form);
          const d = await API.updateDeliveryTask(t.id, data);
          if (form.sync?.checked) await API.updateTask(t.template_task_id, data);
          await setDelivery(d);
          toast('Tâche mise à jour');
        },
      });
    },
    'add-delivery-task': () => modal({
      title: 'Ajouter une tâche',
      submit: 'Ajouter',
      body: taskFormBody({}, '<label class="check"><input type="checkbox" name="tpl" checked> Ajouter aussi au modèle pour les prochaines livraisons</label>'),
      async onSubmit(form) {
        const d = await API.addDeliveryTask(state.delivery.id, { ...taskFormData(form), add_to_template: form.tpl.checked });
        await setDelivery(d);
        toast('Tâche ajoutée');
      },
    }),
    async 'move-task'(el) {
      const ids = state.delivery.tasks.map((t) => t.id);
      const i = ids.indexOf(Number(el.dataset.id));
      const j = i + Number(el.dataset.dir);
      if (j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      await setDelivery(await run(API.reorderDeliveryTasks(state.delivery.id, ids)));
    },
    async 'delete-task'(el) {
      if (!(await confirmBox('Retirer cette tâche de la livraison ? Le modèle n\'est pas modifié.', 'Retirer'))) return;
      await setDelivery(await run(API.deleteDeliveryTask(Number(el.dataset.id))));
    },
    async 'close-delivery'() {
      const open = state.delivery.tasks.filter((t) => !finished(t)).length;
      if (open && !(await confirmBox(`${open} tâche(s) ne sont pas validées. Clôturer quand même ?`, 'Clôturer'))) return;
      await setDelivery(await run(API.updateDelivery(state.delivery.id, { status: 'done' }), 'Livraison clôturée'));
    },
    async 'reopen-delivery'() {
      await setDelivery(await run(API.updateDelivery(state.delivery.id, { status: 'in_progress' })));
    },
    async 'delete-delivery'() {
      if (!(await confirmBox(`Supprimer définitivement la livraison ${state.delivery.version} et son historique ?`))) return;
      await run(API.deleteDelivery(state.delivery.id), 'Livraison supprimée');
      state.delivery = null;
      state.view = 'empty';
      await refreshList();
      render();
    },
    export: (el) => run(API.exportReport(state.delivery.id, el.dataset.fmt)),
    'tpl-add': () => modal({
      title: 'Nouvelle tâche du modèle', submit: 'Ajouter', body: taskFormBody(),
      async onSubmit(form) {
        await API.createTask(taskFormData(form));
        await openTemplate();
        toast('Tâche ajoutée au modèle');
      },
    }),
    'tpl-edit': (el) => {
      const t = state.templateTasks.find((x) => x.id === Number(el.dataset.id));
      modal({
        title: 'Modifier la tâche du modèle', body: taskFormBody(t),
        async onSubmit(form) {
          await API.updateTask(t.id, taskFormData(form));
          await openTemplate();
          toast('Modèle mis à jour');
        },
      });
    },
    async 'tpl-delete'(el) {
      if (!(await confirmBox('Supprimer cette tâche du modèle ? Les livraisons existantes la conservent.'))) return;
      await run(API.deleteTask(Number(el.dataset.id)));
      await openTemplate();
    },
    async 'tpl-move'(el) {
      const ids = state.templateTasks.map((t) => t.id);
      const i = ids.indexOf(Number(el.dataset.id));
      const j = i + Number(el.dataset.dir);
      [ids[i], ids[j]] = [ids[j], ids[i]];
      state.templateTasks = await run(API.reorderTasks(ids));
      render();
    },
    async 'save-defaults'() {
      state.settings = await run(API.saveSettings({ default_variables: parseVars(document.getElementById('default-vars').value) }),
        'Variables par défaut enregistrées');
      render();
    },
  };

  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    if (state.menuFor !== null && !e.target.closest('.menu') && el?.dataset.act !== 'menu') {
      state.menuFor = null;
      if (!el) { render(); return; }
    }
    if (!el) return;
    e.preventDefault();
    if (el.dataset.act !== 'menu') state.menuFor = null;
    e.stopPropagation();
    Promise.resolve(handlers[el.dataset.act]?.(el)).catch(() => {});
  });

  document.addEventListener('keydown', (e) => {
    const thumb = e.target.closest?.('.thumb');
    if (thumb && (e.key === 'Enter' || e.key === ' ') && e.target === thumb) {
      e.preventDefault();
      lightbox(imagesOf(thumb.dataset.scope, Number(thumb.dataset.owner)), Number(thumb.dataset.img));
    }
    if (e.target.dataset?.comment && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      postComment(Number(e.target.dataset.comment)).catch(() => {});
    }
  });

  document.addEventListener('input', (e) => {
    if (e.target.dataset?.comment) {
      e.target.style.height = 'auto';
      e.target.style.height = `${e.target.scrollHeight + 2}px`;
    }
  });

  document.addEventListener('change', (e) => {
    const target = e.target.dataset?.upload;
    if (target) {
      const [scope, id] = target.split(':');
      uploadFiles(scope, Number(id), e.target.files).catch(() => {});
    }
  });

  // Paste a screenshot while focused inside a task (delivery or template) to attach it.
  document.addEventListener('paste', (e) => {
    const card = e.target.closest?.('[data-task-id], [data-tpl-id]');
    const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
    if (!card || !files.length) return;
    e.preventDefault();
    const tpl = card.dataset.tplId;
    uploadFiles(tpl ? 'tpl' : 'task', Number(tpl || card.dataset.taskId), files).catch(() => {});
  });

  // ---------------------------------------------------------------- boot

  (async function boot() {
    try {
      await refreshList();
      const last = Number(store.get('lastDelivery'));
      const pick = state.deliveries.find((d) => d.id === last)
        || state.deliveries.find((d) => d.status === 'in_progress') || state.deliveries[0];
      if (pick) await openDelivery(pick.id);
      else render();
    } catch (err) {
      app.innerHTML = `<div class="empty"><h2>Serveur injoignable</h2><p>${esc(err.message)}</p></div>`;
    }
  })();
})();
