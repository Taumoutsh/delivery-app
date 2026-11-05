// Registry of task content blocks. A task holds an ordered list of blocks:
//   { id, type, ...fields }
// Each type declares, in one place, how it is edited, displayed and summarised. Adding a new kind of
// element = adding one entry here (+ its report rendering on the server, see SPECS.md).
//
// Type contract:
//   label, icon, hint            shown in the "add an element" picker and on editor cards
//   blank()                      fields of a new block
//   editor(b, h)                 HTML of the editor fields (inputs carry data-f="<field>")
//   read(card, b)                fields read back from the editor card (b = previous value)
//   isEmpty(b)                   empty blocks are dropped on save
//   summary(b)                   one-line summary (collapsed card, template list)
//   texts(b)                     strings that may contain {{variables}}
//   view(b, ctx)                 HTML in a delivery task; ctx = { vars, h } (helpers)
(function () {
  'use strict';

  const I = (d) => `<svg viewBox="0 0 16 16" class="ic" aria-hidden="true">${d}</svg>`;
  const ICON = {
    command: I('<path d="M2.5 3.5h11v9h-11z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4.5 6.5l2 1.5-2 1.5M8 10h3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>'),
    link: I('<path d="M6.5 9.5l3-3M7 4.5l1-1a2.5 2.5 0 013.5 3.5l-1 1M9 11.5l-1 1a2.5 2.5 0 01-3.5-3.5l1-1" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>'),
    program: I('<rect x="2.5" y="2.5" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M6.5 5.5v5l4-2.5z" fill="currentColor"/>'),
    table: I('<rect x="2.5" y="3" width="11" height="10" rx="1" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M2.5 6.5h11M2.5 9.8h11M7 3v10" stroke="currentColor" stroke-width="1.1"/>'),
    media: I('<rect x="2" y="3" width="12" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="5.8" cy="6.3" r="1.2" fill="currentColor"/><path d="M3 12l3.5-3.5 2.5 2.5 2-2 2.5 2.5" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>'),
    note: I('<path d="M3 2.5h10v8l-3 3H3z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5.5 6h5M5.5 8.5h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>'),
    external: I('<path d="M9 2.5h4.5V7M13.5 2.5L7.5 8.5M11.5 9.5v4h-9v-9h4" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'),
    play: I('<path d="M5 3v10l8-5z" fill="currentColor"/>'),
    copy: I('<rect x="5.5" y="5.5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M10.5 3.5v-.5A1.5 1.5 0 009 1.5H4A1.5 1.5 0 002.5 3v5A1.5 1.5 0 004 9.5h.5" fill="none" stroke="currentColor" stroke-width="1.3"/>'),
  };

  // Note formatting buttons: [format, label, shortcut, glyph].
  const FORMATS = [
    ['b', 'Gras', 'B', '<b>G</b>'], ['i', 'Italique', 'I', '<i>I</i>'], ['u', 'Souligné', 'U', '<u>S</u>'],
    ['s', 'Barré', '', '<s>B</s>'],
    ['ul', 'Liste à puces', '', I('<circle cx="3" cy="4.5" r="1.1" fill="currentColor"/><circle cx="3" cy="8" r="1.1" fill="currentColor"/><circle cx="3" cy="11.5" r="1.1" fill="currentColor"/><path d="M6 4.5h8M6 8h8M6 11.5h8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>')],
    ['ol', 'Liste numérotée', '', I('<text x="1" y="6.3" font-size="5" font-family="sans-serif" fill="currentColor">1</text><text x="1" y="13" font-size="5" font-family="sans-serif" fill="currentColor">2</text><path d="M6 4.5h8M6 11.5h8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>')],
  ];

  const field = (label, inner, hint = '', wide = true) => `
    <label class="bf${wide ? ' wide' : ''}"><span class="bf-label">${label}</span>${inner}${hint ? `<span class="hint">${hint}</span>` : ''}</label>`;
  const val = (card, f) => card.querySelector(`[data-f="${f}"]`)?.value ?? '';
  const oneLine = (s) => String(s || '').split('\n')[0];

  const TYPES = {
    command: {
      label: 'Ligne de commande',
      hint: 'Une ou plusieurs lignes à copier, adaptées à la version.',
      icon: ICON.command,
      blank: () => ({ label: '', text: '' }),
      editor: (b, h) => field('Libellé', `<input type="text" data-f="label" value="${h.esc(b.label)}" placeholder="Linux, Build, Rollback…">`, '', false)
        + field('Commande', `<textarea data-f="text" class="mono" rows="3" placeholder="git tag -a v{{version}} -m &quot;Release {{version}}&quot;">${h.esc(b.text)}</textarea>`),
      read: (card) => ({ label: val(card, 'label').trim(), text: val(card, 'text') }),
      isEmpty: (b) => !b.text.trim(),
      summary: (b) => b.label || oneLine(b.text),
      texts: (b) => [b.label, b.text],
      view: (b, { vars, h }) => `
        ${b.label ? `<div class="blk-label">${h.renderHtml(b.label, vars)}</div>` : ''}
        <div class="cmd"><pre>${h.renderHtml(b.text, vars)}</pre>
          <button class="copy" data-act="blk-copy">Copier</button></div>`,
    },

    link: {
      label: 'Liens',
      hint: 'Une ou plusieurs adresses web ou réseau, affichées côte à côte ; elles peuvent contenir des variables.',
      icon: ICON.link,
      blank: () => ({ links: [{ label: '', url: '' }] }),
      editor: (b, h) => `<div class="bf wide"><span class="bf-label">Liens <span class="muted">(affichés sur une même ligne)</span></span>
          <div class="link-rows" data-link-rows>${(b.links && b.links.length ? b.links : [{ label: '', url: '' }]).map((l, i) => `
            <div class="link-edit" data-link-row>
              <input type="text" data-l="label" value="${h.esc(l.label)}" placeholder="Libellé (ex. Pipeline)" aria-label="Libellé du lien ${i + 1}">
              <input type="text" data-l="url" class="mono" value="${h.esc(l.url)}" placeholder="https://ci.example.com/app/{{version}}" aria-label="Adresse du lien ${i + 1}">
              <button type="button" class="btn icon ghost" data-ed="link-remove" data-index="${i}" aria-label="Retirer ce lien" title="Retirer ce lien">×</button>
            </div>`).join('')}</div>
          <div><button type="button" class="btn ghost sm" data-ed="link-add">+ Ajouter un lien</button></div></div>`,
      read: (card) => ({
        links: [...card.querySelectorAll('[data-link-row]')].map((row) => ({
          label: row.querySelector('[data-l="label"]').value.trim(),
          url: row.querySelector('[data-l="url"]').value.trim(),
        })),
      }),
      isEmpty: (b) => !(b.links || []).some((l) => l.url),
      summary: (b) => (b.links || []).filter((l) => l.url).map((l) => l.label || l.url).join(' · '),
      texts: (b) => (b.links || []).flatMap((l) => [l.label, l.url]),
      view: (b, { vars, h }) => `<div class="link-row">${(b.links || []).filter((l) => l.url).map((l, i) => {
        const url = h.renderText(l.url, vars);
        return `<span class="link-item">
            <a class="link-chip" href="${h.esc(url)}" title="${h.esc(url)}" target="_blank" rel="noopener">${ICON.external}<span>${h.esc(h.renderText(l.label, vars) || url)}</span></a>
            <button class="btn icon ghost link-copy" data-act="blk-copy" data-index="${i}" title="Copier le lien" aria-label="Copier le lien ${h.esc(h.renderText(l.label, vars) || url)}">${ICON.copy}</button>
          </span>`;
      }).join('')}</div>`,
    },

    program: {
      label: 'Programme',
      hint: 'Lance un programme de cette machine (outil, script, document…).',
      icon: ICON.program,
      blank: () => ({ name: '', path: '', args: '', cwd: '' }),
      editor: (b, h) => field('Nom affiché', `<input type="text" data-f="name" value="${h.esc(b.name)}" placeholder="Console d'administration">`, '', false)
        + field('Programme', `<input type="text" data-f="path" class="mono" value="${h.esc(b.path)}" placeholder="C:\\Outils\\admin.exe  ou  /opt/outils/admin">`,
          'Chemin complet de l\'exécutable, d\'un script ou d\'un document.')
        + field('Arguments', `<input type="text" data-f="args" class="mono" value="${h.esc(b.args)}" placeholder="--env {{env}} --version {{version}}">`, '', false)
        + field('Dossier de travail', `<input type="text" data-f="cwd" class="mono" value="${h.esc(b.cwd)}" placeholder="(dossier du programme)">`, '', false),
      read: (card) => ({ name: val(card, 'name').trim(), path: val(card, 'path').trim(), args: val(card, 'args').trim(), cwd: val(card, 'cwd').trim() }),
      isEmpty: (b) => !b.path,
      summary: (b) => b.name || b.path,
      texts: (b) => [b.name, b.path, b.args, b.cwd],
      view: (b, { vars, h }) => {
        const cmd = [b.path, b.args].filter(Boolean).map((x) => h.renderText(x, vars)).join(' ');
        return `<div class="program-row">
          <button class="btn run" data-act="blk-launch" title="${h.esc(cmd)}">${ICON.play}Lancer ${h.esc(h.renderText(b.name, vars) || 'le programme')}</button>
        </div>`;
      },
    },

    table: {
      label: 'Tableau pour Word',
      hint: 'Tableau avec liens, à coller dans un document Word.',
      icon: ICON.table,
      blank: () => ({ title: '', spec: '' }),
      editor: (b, h) => field('Titre', `<input type="text" data-f="title" value="${h.esc(b.title)}" placeholder="Liens de la livraison">`, '', false)
        + field('Contenu', `<textarea data-f="spec" class="mono" rows="4" placeholder="Élément | Lien&#10;Notes de version | [Wiki {{version}}](https://wiki.example.com/releases/{{version}})">${h.esc(b.spec)}</textarea>`,
          'Une ligne par rangée, cellules séparées par <code>|</code>, 1re ligne = en-têtes. Liens : <code>[texte](https://…)</code> ou URL brute.'),
      read: (card) => ({ title: val(card, 'title').trim(), spec: val(card, 'spec') }),
      isEmpty: (b) => !b.spec.trim(),
      summary: (b) => b.title || oneLine(b.spec),
      texts: (b) => [b.title, b.spec],
      view: (b, { vars, h }) => {
        const table = h.parseTable(b.spec, vars);
        if (!table) return '';
        return `${b.title ? `<div class="blk-label">${h.renderHtml(b.title, vars)}</div>` : ''}
          <div class="doc-table-wrap"><table class="doc-table">
            <thead><tr>${table.headers.map((c) => `<th>${h.cellHtml(c)}</th>`).join('')}</tr></thead>
            <tbody>${table.rows.map((r) => `<tr>${r.map((c) => `<td>${h.cellHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody>
          </table></div>
          <div class="add-row table-actions">
            <button class="btn" data-act="blk-copy-table">Copier pour Word</button>
            <button class="btn ghost" data-act="blk-table-docx">Télécharger en .docx</button>
          </div>`;
      },
    },

    media: {
      label: 'Images et vidéos',
      hint: 'Captures de référence, schémas, démonstrations vidéo.',
      icon: ICON.media,
      blank: () => ({ title: '', files: [] }),
      editor: (b, h) => field('Titre', `<input type="text" data-f="title" value="${h.esc(b.title)}" placeholder="Écran attendu après déploiement">`, '', false)
        + `<div class="bf wide"><span class="bf-label">Fichiers</span>${h.mediaStrip(b.files, { editable: true })}
            <span class="hint">Images ou vidéos (MP4, WebM, MOV, AVI, MKV… 2 Go max) : bouton, glisser-déposer, ou Ctrl+V dans cet élément.</span></div>`,
      read: (card, b) => ({ title: val(card, 'title').trim(), files: b.files || [] }),
      isEmpty: (b) => !b.files.length,
      summary: (b) => `${b.title ? `${b.title} · ` : ''}${b.files.length} fichier${b.files.length > 1 ? 's' : ''}`,
      texts: (b) => [b.title],
      view: (b, { vars, h }) => `${b.title ? `<div class="blk-label">${h.renderHtml(b.title, vars)}</div>` : ''}${h.mediaStrip(b.files)}`,
    },

    note: {
      label: 'Note',
      hint: 'Consigne, avertissement ou commentaire permanent.',
      icon: ICON.note,
      blank: () => ({ text: '' }),
      editor: (b, h) => `<div class="bf wide"><span class="bf-label">Texte</span>
          <div class="rich-bar" role="toolbar" aria-label="Mise en forme">
            ${FORMATS.map(([fmt, label, key, glyph]) => `<button type="button" class="btn ghost sm fmt-${fmt}" data-ed="fmt" data-fmt="${fmt}"
              title="${label}${key ? ` (Ctrl+${key})` : ''}" aria-label="${label}">${glyph}</button>`).join('')}
          </div>
          <textarea data-f="text" data-rich rows="4" placeholder="Prévenir l'équipe support avant de déployer {{version}}.">${h.esc(b.text)}</textarea>
          <span class="hint"><code>**gras**</code> <code>*italique*</code> <code>__souligné__</code> <code>~~barré~~</code>,
            lignes <code>- </code> pour une liste à puces, <code>1. </code> pour une liste numérotée ;
            Tab / Maj+Tab sur une ligne de liste pour changer de niveau.</span></div>`,
      read: (card) => ({ text: val(card, 'text') }),
      isEmpty: (b) => !b.text.trim(),
      summary: (b) => oneLine(b.text).replace(/^\s*([-*•]|\d+[.)])\s+/, '').replace(/\*\*|__|~~|(?<!\\)\*/g, ''),
      texts: (b) => [b.text],
      view: (b, { vars, h }) => `<div class="note-box rich">${h.richHtml(b.text, vars)}</div>`,
    },
  };

  // Order of the "add an element" picker.
  const ORDER = ['command', 'link', 'program', 'table', 'media', 'note'];

  let seq = 0;
  const newId = () => `b${Date.now().toString(36)}${(seq++).toString(36)}`;

  window.Blocks = {
    TYPES,
    ORDER,
    ICON,
    get: (type) => TYPES[type],
    create: (type) => ({ id: newId(), type, ...TYPES[type].blank() }),
    newId,
  };
})();
