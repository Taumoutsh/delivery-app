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
    trash: '<svg viewBox="0 0 16 16" class="ic" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5M7 7v4M9 7v4" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
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
    editor: null, // open task editor ({ blocks, open })
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
  const taskText = (t) => [t.description, ...(t.blocks || []).flatMap((b) => Blocks.get(b.type)?.texts(b) || [])].join('\n');

  // Progress weight of a task = its estimated time (a task without estimate counts as 1 minute).
  const weightOf = (t) => Math.max(1, t.estimated_minutes || 0);

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
    const doneN = d.tasks.filter(finished).length;
    const doneMin = d.tasks.filter((t) => t.status === 'done').reduce((a, t) => a + t.estimated_minutes, 0);
    const totalMin = active.reduce((a, t) => a + t.estimated_minutes, 0);

    const segs = d.tasks.map((t) => `<span class="seg ${t.status}" style="flex:${weightOf(t)}"
      title="${esc(t.title)} · ${t.estimated_minutes ? fmtDur(t.estimated_minutes * 60) : 'sans estimation'} · ${STATUS[t.status]}"></span>`).join('');

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
          <span>Validé <b>${fmtDur(doneMin * 60)}</b> / ${fmtDur(totalMin * 60)} estimées</span>
          <span>Passé <b data-total-spent>—</b></span>
          <span>Reste estimé <b>${fmtDur(active.filter((t) => !finished(t)).reduce((a, t) => a + t.estimated_minutes * 60, 0))}</b></span>
        </div>
      </section>

      <div class="tasks">${d.tasks.map((t, i) => renderTask(t, i, vars)).join('')}</div>

      <div class="add-row">
        <button class="btn" data-act="add-delivery-task">${ICONS.plus}Ajouter une tâche à cette livraison</button>
      </div>`;
  }

  // Thumbnails of media files ({id, filename, mime, url}). Inside a block, thumbs open the viewer;
  // editable strips (task editor) also offer add/remove.
  function mediaStrip(files, { editable = false } = {}) {
    return `<div class="thumbs media">
      ${files.map((f) => `
        <div class="thumb${isVideo(f) ? ' video' : ''}" role="button" tabindex="0" data-act="media-open" data-file="${esc(f.id)}" title="${esc(f.filename)}">
          ${isVideo(f) ? `<video src="${esc(f.url)}" muted preload="metadata"></video><span class="play">${Blocks.ICON.play}</span>`
            : `<img src="${esc(f.url)}" alt="${esc(f.filename)}" loading="lazy">`}
          ${editable ? `<button type="button" class="x" data-ed="media-remove" data-file="${esc(f.id)}" aria-label="Retirer le fichier">✕</button>` : ''}
        </div>`).join('')}
      ${editable ? `<button type="button" class="thumb-add" data-ed="media-add">${ICONS.plus}<span>Ajouter</span></button>
        <input type="file" accept="image/*,video/*" multiple hidden data-ed-upload>` : ''}
    </div>`;
  }

  const isVideo = (f) => String(f.mime || '').startsWith('video/');

  // Helpers handed to block types (blocks.js).
  const H = { esc, renderHtml, renderText, parseTable, cellHtml, mediaStrip };

  function blockBadges(blocks) {
    const counts = {};
    for (const b of blocks || []) counts[b.type] = (counts[b.type] || 0) + 1;
    return Blocks.ORDER.filter((k) => counts[k]).map((k) => `<span class="badge blk-badge" title="${esc(Blocks.get(k).label)}">${Blocks.get(k).icon}${counts[k]}</span>`).join('');
  }

  function renderBlocks(t, vars) {
    const tables = t.blocks.filter((b) => b.type === 'table');
    // The type heading is shown once per run of consecutive blocks of the same type.
    return t.blocks.map((b, i) => {
      const type = Blocks.get(b.type);
      if (!type) return '';
      const html = type.view(b, { vars, h: H });
      const heading = t.blocks[i - 1]?.type !== b.type ? `<div class="blk-type">${type.icon}${type.label}</div>` : '';
      return html ? `<div class="blk blk-${b.type}${heading ? '' : ' cont'}" data-block="${esc(b.id)}" data-task="${t.id}">
        ${heading}${html}</div>` : '';
    }).join('') + (tables.length > 1 ? `<div class="add-row table-actions all">
        <button class="btn" data-act="copy-all-tables" data-task="${t.id}">Copier tous les tableaux Word</button>
        <button class="btn ghost" data-act="all-tables-docx" data-task="${t.id}">Tous en .docx</button></div>` : '');
  }

  // Screenshots taken during a delivery (scope 'task').
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

  const imagesOf = (scope, ownerId) => state.delivery.tasks.find((t) => t.id === ownerId)?.images || [];

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

    const missing = missingVars(taskText(t), vars);
    const body = !open ? '' : `
      <div class="task-body">
        ${t.description ? `<div class="desc">${renderHtml(t.description, vars).replace(/<span class="var[^"]*"[^>]*>/g, '<b>').replace(/<\/span>/g, '</b>')}</div>` : ''}
        ${t.blocks.length ? `<div class="blocks">${renderBlocks(t, vars)}</div>` : ''}
        ${missing.length ? `<div class="warn-vars">Variable non renseignée : ${missing.map((m) => `{{${esc(m)}}}`).join(', ')} —
          <a href="#" data-act="edit-delivery">la définir</a></div>` : ''}
        <div>
          <div class="section-label">Captures de la livraison (${t.images.length})</div>
          ${thumbStrip('task', t.id, t.images, { toTemplate: Boolean(t.template_task_id) })}
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
              <span class="badge">Estimé ${est ? fmtDur(est * 60) : '—'}</span>
              ${blockBadges(t.blocks)}
              ${t.comments.length ? `<span class="badge">${t.comments.length} commentaire${t.comments.length > 1 ? 's' : ''}</span>` : ''}
              ${t.images.length ? `<span class="badge">${t.images.length} capture${t.images.length > 1 ? 's' : ''}</span>` : ''}
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
    const totalE = tasks.reduce((a, t) => a + t.estimated_minutes, 0);
    const rows = tasks.map((t, i) => `
      <div class="tpl-row" data-tpl-id="${t.id}">
        <span class="tpl-idx">${i + 1}</span>
        <div class="tpl-main">
          <strong>${esc(t.title)}</strong>
          <div class="tpl-blocks">${t.blocks.length ? t.blocks.map((b) => `<span class="tpl-blk" title="${esc(Blocks.get(b.type).label)}">${Blocks.get(b.type).icon}<span>${esc(Blocks.get(b.type).summary(b))}</span></span>`).join('')
            : '<i class="muted">Aucun élément</i>'}</div>
        </div>
        <div class="tpl-nums num"><span>${t.estimated_minutes ? fmtDur(t.estimated_minutes * 60) : '—'}</span></div>
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
          <div class="eyebrow">${tasks.length} tâches · ${fmtDur(totalE * 60)} estimées</div>
          <h1>Modèle de tâches</h1>
          <div class="sub">Copié dans chaque nouvelle livraison. Les livraisons existantes ne sont pas modifiées.</div>
        </div>
        <div class="head-actions"><button class="btn primary" data-act="tpl-add">${ICONS.plus}Ajouter une tâche</button></div>
      </div>
      <div class="tpl-list">${rows || '<div class="tpl-row"><span></span><span class="tpl-main">Aucune tâche. Ajoutez la première.</span></div>'}</div>
      <div class="grid2">
        <section class="panel">
          <h3>Variables disponibles</h3>
          <p>Écrivez <code>{{version}}</code> dans une commande, un lien, un programme, un tableau ou une description : la valeur de la livraison est substituée.</p>
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

  function modal({ title, subtitle, body, submit = 'Enregistrer', onSubmit, onInput, onClose, danger, wide }) {
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.innerHTML = `
      <form class="modal${wide ? ' wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <header><h2>${esc(title)}</h2>${subtitle ? `<p class="modal-sub">${esc(subtitle)}</p>` : ''}</header>
        <div class="content">${body}<div class="error" hidden></div></div>
        <footer>
          <button type="button" class="btn" data-close>Annuler</button>
          <button type="submit" class="btn ${danger ? 'danger' : 'primary'}">${esc(submit)}</button>
        </footer>
      </form>`;
    const form = overlay.querySelector('form');
    const close = () => {
      overlay.remove();
      document.removeEventListener('keydown', onKey);
      if (!document.querySelector('.overlay')) document.documentElement.classList.remove('modal-open');
      onClose?.();
    };
    const onKey = (e) => { if (e.key === 'Escape' && !document.querySelector('.lightbox')) close(); };
    document.addEventListener('keydown', onKey);
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
    overlay.querySelector('[data-close]').onclick = close;
    if (onInput) form.addEventListener('input', () => onInput(form));
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
    document.documentElement.classList.add('modal-open'); // lock the page behind the dialog
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

  // ---------------------------------------------------------------- task editor
  //
  // One editor for template tasks and delivery tasks: general fields, then the ordered list of
  // content blocks (see blocks.js). Blocks live in `ed.blocks`; the DOM is read back into it before
  // any re-render or save.

  function taskEditor(t, { title, subtitle, submit = 'Enregistrer', extra = '', onSave }) {
    const ed = {
      blocks: (t.blocks || []).map((b) => ({ ...b, files: b.files ? [...b.files] : b.files })),
      open: new Set(),
    };
    if (ed.blocks.length <= 3) ed.blocks.forEach((b) => ed.open.add(b.id));
    state.editor = ed;

    const cardHtml = (b) => {
      const type = Blocks.get(b.type);
      const isOpen = ed.open.has(b.id);
      return `<div class="ed-card${isOpen ? ' open' : ''}" data-card="${esc(b.id)}" data-type="${b.type}">
        <div class="ed-card-head">
          <span class="grip" data-ed="grip" title="Glisser pour déplacer" aria-hidden="true">⠿</span>
          <button type="button" class="ed-toggle" data-ed="fold" aria-expanded="${isOpen}">
            <span class="ed-type">${type.icon}${type.label}</span>
            <span class="ed-sum">${esc(type.summary(b) || 'vide')}</span>
          </button>
          <button type="button" class="btn icon ghost" data-ed="up" aria-label="Monter">${ICONS.up}</button>
          <button type="button" class="btn icon ghost" data-ed="down" aria-label="Descendre">${ICONS.down}</button>
          <button type="button" class="btn icon ghost danger" data-ed="remove" aria-label="Supprimer l'élément" title="Supprimer l'élément">${ICONS.trash}</button>
        </div>
        <div class="ed-card-body">${type.editor(b, H)}</div>
      </div>`;
    };

    const body = `
      <section class="ed-section">
        <h3>Général</h3>
        <div class="ed-grid">
          <label class="bf wide2"><span class="bf-label">Titre</span>
            <input type="text" id="f-title" name="title" required value="${esc(t.title)}" placeholder="Déployer en recette"></label>
          <label class="bf"><span class="bf-label">Temps estimé (minutes)</span>
            <input type="number" id="f-est" name="estimated_minutes" min="0" step="1" value="${t.estimated_minutes ?? 10}">
            <span class="hint">Sert aussi à la progression.</span></label>
          <label class="bf wide3"><span class="bf-label">Description</span>
            <textarea id="f-desc" name="description" rows="2" placeholder="Ce qu'il faut faire et vérifier.">${esc(t.description)}</textarea></label>
        </div>
      </section>
      <section class="ed-section">
        <div class="ed-section-head"><h3>Contenu</h3><span class="muted" data-ed-count></span></div>
        <div class="ed-blocks" data-ed-list>${ed.blocks.map(cardHtml).join('')}</div>
        <div class="ed-empty" data-ed-empty ${ed.blocks.length ? 'hidden' : ''}>Aucun élément : ajoutez une commande, un lien, un programme…</div>
        <div class="ed-add">
          <span class="bf-label">Ajouter</span>
          <div class="ed-add-types">${Blocks.ORDER.map((k) => `<button type="button" class="ed-add-btn" data-ed="add" data-type="${k}" title="${esc(Blocks.get(k).hint)}">${Blocks.get(k).icon}${Blocks.get(k).label}</button>`).join('')}</div>
        </div>
        <details class="ed-help"><summary>Variables utilisables dans les éléments</summary>
          <div class="help-vars">${BUILTIN_VARS.map(([k, v]) => `<code>{{${k}}}</code><span>${v}</span>`).join('')}
            <code>{{…}}</code><span>et vos variables personnalisées (env, serveur…)</span></div></details>
      </section>${extra}`;

    const form = modal({
      title, subtitle, submit, body, wide: true,
      onClose: () => { if (state.editor === ed) state.editor = null; },
      async onSubmit(f) {
        sync(f);
        const blocks = ed.blocks.filter((b) => !Blocks.get(b.type).isEmpty(b));
        await onSave({
          title: f.title.value.trim(),
          description: f.description.value,
          estimated_minutes: Number(f.estimated_minutes.value) || 0,
          blocks,
        }, f);
      },
    });
    const list = form.querySelector('[data-ed-list]');

    function sync(f = form) {
      const byId = Object.fromEntries(ed.blocks.map((b) => [b.id, b]));
      ed.blocks = [...f.querySelectorAll('[data-card]')].map((card) => {
        const b = byId[card.dataset.card];
        return Object.assign(b, Blocks.get(b.type).read(card, b));
      });
    }
    // Re-render the cards from ed.blocks (callers sync() first when the DOM holds unsaved input).
    function refresh() {
      list.innerHTML = ed.blocks.map(cardHtml).join('');
      counts();
    }
    function counts() {
      form.querySelector('[data-ed-count]').textContent = ed.blocks.length
        ? `${ed.blocks.length} élément${ed.blocks.length > 1 ? 's' : ''} · glisser ⠿ pour réordonner` : '';
      form.querySelector('[data-ed-empty]').hidden = ed.blocks.length > 0;
    }
    counts();

    async function addFiles(card, files) {
      sync();
      const b = ed.blocks.find((x) => x.id === card.dataset.card);
      for (const file of files) {
        if (!/^(image|video)\//.test(file.type)) continue;
        const prepared = file.type.startsWith('image/') ? await toPngOrJpeg(file) : file;
        b.files.push(await run(API.uploadMedia(prepared)));
      }
      refresh();
    }

    form.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-ed]');
      if (!btn) return;
      const card = btn.closest('[data-card]');
      const action = btn.dataset.ed;
      if (action === 'add') {
        sync();
        const b = Blocks.create(btn.dataset.type);
        ed.blocks.push(b);
        ed.open.add(b.id);
        refresh();
        list.lastElementChild.querySelector('input, textarea')?.focus();
        list.lastElementChild.scrollIntoView({ block: 'nearest' });
      } else if (action === 'fold') {
        sync();
        ed.open.has(card.dataset.card) ? ed.open.delete(card.dataset.card) : ed.open.add(card.dataset.card);
        refresh();
      } else if (action === 'up' || action === 'down') {
        const other = action === 'up' ? card.previousElementSibling : card.nextElementSibling;
        if (other) (action === 'up' ? other.before(card) : other.after(card));
        sync();
      } else if (action === 'remove') {
        card.remove();
        sync();
        counts();
      } else if (action === 'media-add') {
        card.querySelector('[data-ed-upload]').click();
      } else if (action === 'media-remove') {
        sync();
        const b = ed.blocks.find((x) => x.id === card.dataset.card);
        b.files = b.files.filter((f) => String(f.id) !== btn.dataset.file);
        refresh();
      }
    });
    form.addEventListener('change', (e) => {
      if (e.target.matches('[data-ed-upload]')) addFiles(e.target.closest('[data-card]'), [...e.target.files]).catch(() => {});
    });
    form.addEventListener('input', (e) => {
      const card = e.target.closest('[data-card]');
      if (!card) return;
      const b = ed.blocks.find((x) => x.id === card.dataset.card);
      card.querySelector('.ed-sum').textContent = Blocks.get(b.type).summary(Blocks.get(b.type).read(card, b)) || 'vide';
    });
    form.addEventListener('paste', (e) => {
      const card = e.target.closest('[data-card][data-type="media"]');
      const files = [...(e.clipboardData?.files || [])];
      if (card && files.length) { e.preventDefault(); e.stopPropagation(); addFiles(card, files).catch(() => {}); }
    });

    // Drag and drop: by the grip to reorder cards; files dropped on a media card are added to it.
    let dragged = null;
    list.addEventListener('mousedown', (e) => {
      const grip = e.target.closest('[data-ed="grip"]');
      if (grip) grip.closest('[data-card]').draggable = true;
    });
    list.addEventListener('dragstart', (e) => {
      dragged = e.target.closest('[data-card]');
      if (!dragged?.draggable) { dragged = null; return; }
      dragged.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    list.addEventListener('dragover', (e) => {
      const target = e.target.closest('[data-card]');
      if (dragged && target && target !== dragged) {
        e.preventDefault();
        const box = target.getBoundingClientRect();
        e.clientY < box.top + box.height / 2 ? target.before(dragged) : target.after(dragged);
      } else if (!dragged && target?.dataset.type === 'media' && e.dataTransfer.types.includes('Files')) {
        e.preventDefault();
        target.classList.add('drop');
      }
    });
    list.addEventListener('dragleave', (e) => e.target.closest('[data-card]')?.classList.remove('drop'));
    list.addEventListener('drop', (e) => {
      const target = e.target.closest('[data-card][data-type="media"]');
      if (!dragged && target && e.dataTransfer.files.length) {
        e.preventDefault();
        target.classList.remove('drop');
        addFiles(target, [...e.dataTransfer.files]).catch(() => {});
      }
    });
    list.addEventListener('dragend', () => {
      if (!dragged) return;
      dragged.classList.remove('dragging');
      dragged.draggable = false;
      dragged = null;
      sync();
    });
    return form;
  }

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

  // items: [{id, url, filename, mime?}] — images and videos.
  function lightbox(images, imgId) {
    const task = { images };
    let idx = task.images.findIndex((i) => String(i.id) === String(imgId));
    const el = document.createElement('div');
    el.className = 'lightbox';
    el.setAttribute('role', 'dialog');
    const show = () => {
      const img = task.images[idx];
      el.innerHTML = `
        <button class="close" aria-label="Fermer">✕</button>
        ${task.images.length > 1 ? '<button class="nav prev" aria-label="Précédente">‹</button><button class="nav next" aria-label="Suivante">›</button>' : ''}
        ${isVideo(img) ? `<video src="${esc(img.url)}" controls autoplay></video>` : `<img src="${esc(img.url)}" alt="${esc(img.filename)}">`}
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
      else if (!['IMG', 'VIDEO'].includes(e.target.tagName)) close();
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
    let res;
    for (const f of images) res = await run(toPngOrJpeg(f).then((png) => API.uploadImage(ownerId, png)));
    await setDelivery(res);
    toast(images.length > 1 ? `${images.length} images ajoutées` : 'Image ajoutée');
  }

  // Block of a delivery task, from an element inside its rendering.
  function blockOf(el) {
    const host = el.closest('[data-block]');
    const task = state.delivery.tasks.find((t) => t.id === Number(host.dataset.task));
    return { task, block: task.blocks.find((b) => b.id === host.dataset.block) };
  }

  // Any block currently shown (open editor, delivery or template), by id.
  function findBlock(id) {
    const pools = [state.editor?.blocks || [], ...(state.delivery?.tasks || []).map((t) => t.blocks),
      ...state.templateTasks.map((t) => t.blocks)];
    for (const blocks of pools) {
      const b = blocks.find((x) => x.id === id);
      if (b) return b;
    }
    return null;
  }

  async function copyText(btn, text, selectEl) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      if (selectEl) {
        const range = document.createRange();
        range.selectNodeContents(selectEl);
        getSelection().removeAllRanges();
        getSelection().addRange(range);
      }
      toast(`Copie automatique refusée. Texte : ${text}`);
      return;
    }
    const label = btn.textContent;
    btn.textContent = 'Copié ✓';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = label; btn.classList.remove('copied'); }, 1500);
  }

  // blockId = one table block; null = every table of the task, each preceded by its title.
  async function copyTable(btn, task, blockId) {
    const vars = buildVariables(state.delivery);
    const tables = task.blocks.filter((b) => b.type === 'table' && (blockId === null || b.id === blockId))
      .map((b) => ({ title: renderText(b.title, vars), table: parseTable(b.spec, vars) }))
      .filter((tb) => tb.table);
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
    'blk-copy': (el) => {
      const { block } = blockOf(el);
      const vars = buildVariables(state.delivery);
      const text = renderText(block.type === 'link' ? block.url : block.text, vars);
      return copyText(el, text, el.closest('[data-block]').querySelector('pre, .link-url'));
    },
    'blk-launch': async (el) => {
      const { task, block } = blockOf(el);
      const res = await run(API.launchProgram(task.id, block.id));
      toast(res.message || `${block.name || 'Programme'} lancé`);
    },
    'blk-copy-table': (el) => { const { task, block } = blockOf(el); return copyTable(el, task, block.id); },
    'blk-table-docx': (el) => { const { task, block } = blockOf(el); return run(API.exportTaskTable(task.id, block.id)); },
    'copy-all-tables': (el) => copyTable(el, state.delivery.tasks.find((t) => t.id === Number(el.dataset.task)), null),
    'all-tables-docx': (el) => run(API.exportTaskTable(Number(el.dataset.task), null)),
    'media-open': (el) => {
      const host = el.closest('[data-block], [data-card]');
      const block = findBlock(host.dataset.block || host.dataset.card);
      lightbox(block.files, el.dataset.file);
    },
    comment: (el) => postComment(Number(el.dataset.id)),
    async 'delete-comment'(el) {
      if (!(await confirmBox('Supprimer ce commentaire ?'))) return;
      await setDelivery(await run(API.deleteComment(Number(el.dataset.id))));
    },
    'add-image': (el) => document.querySelector(`[data-upload="${el.dataset.scope}:${el.dataset.id}"]`).click(),
    lightbox: (el) => lightbox(imagesOf(el.dataset.scope, Number(el.dataset.owner)), Number(el.dataset.img)),
    async 'delete-image'(el) {
      if (!(await confirmBox("Supprimer cette image ?"))) return;
      await setDelivery(await run(API.deleteImage(Number(el.dataset.id))));
    },
    async 'image-to-template'(el) {
      await setDelivery(await run(API.imageToTemplate(Number(el.dataset.id)),
        'Capture ajoutée au modèle : les prochaines livraisons la recevront'));
    },
    'edit-task': (el) => {
      const t = state.delivery.tasks.find((x) => x.id === Number(el.dataset.id));
      taskEditor(t, {
        title: 'Modifier la tâche',
        subtitle: `Livraison ${state.delivery.version} uniquement, sauf si vous cochez la case en bas.`,
        extra: t.template_task_id ? `<label class="check ed-sync"><input type="checkbox" name="sync"> Appliquer aussi au modèle (prochaines livraisons)</label>` : '',
        async onSave(data, form) {
          const d = await API.updateDeliveryTask(t.id, data);
          if (form.sync?.checked) await API.updateTask(t.template_task_id, data);
          await setDelivery(d);
          toast('Tâche mise à jour');
        },
      });
    },
    'add-delivery-task': () => taskEditor({ blocks: [Blocks.create('command')] }, {
      title: 'Ajouter une tâche',
      subtitle: `À la livraison ${state.delivery.version}.`,
      submit: 'Ajouter',
      extra: '<label class="check ed-sync"><input type="checkbox" name="tpl" checked> Ajouter aussi au modèle pour les prochaines livraisons</label>',
      async onSave(data, form) {
        const d = await API.addDeliveryTask(state.delivery.id, { ...data, add_to_template: form.tpl.checked });
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
    'tpl-add': () => taskEditor({ blocks: [Blocks.create('command')] }, {
      title: 'Nouvelle tâche du modèle',
      subtitle: 'Elle sera copiée dans chaque nouvelle livraison.',
      submit: 'Ajouter',
      async onSave(data) {
        await API.createTask(data);
        await openTemplate();
        toast('Tâche ajoutée au modèle');
      },
    }),
    'tpl-edit': (el) => {
      const t = state.templateTasks.find((x) => x.id === Number(el.dataset.id));
      taskEditor(t, {
        title: 'Modifier la tâche du modèle',
        subtitle: 'Les modifications s\'appliquent aux prochaines livraisons ; les livraisons existantes ne changent pas.',
        async onSave(data) {
          await API.updateTask(t.id, data);
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
      thumb.click();
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
    const card = e.target.closest?.('[data-task-id]');
    const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
    if (!card || !files.length || e.target.closest('.modal')) return;
    e.preventDefault();
    uploadFiles('task', Number(card.dataset.taskId), files).catch(() => {});
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
