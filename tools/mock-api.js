// In-memory stand-in for api.js, used only by the standalone demo (tools/build_demo.py).
// Mirrors the backend rules on example data.
(function () {
  const iso = (d) => d.toISOString().replace(/\.\d{3}Z$/, 'Z');
  const ago = (min) => iso(new Date(Date.now() - min * 60000));
  const daysAgo = (days, h = 10) => { const d = new Date(); d.setDate(d.getDate() - days); d.setHours(h, 0, 0, 0); return iso(d); };
  let seq = 100;
  const nextId = () => ++seq;
  const clone = (x) => JSON.parse(JSON.stringify(x));

  function screenshot(lines, color) {
    const c = document.createElement('canvas');
    c.width = 640; c.height = 360;
    const g = c.getContext('2d');
    g.fillStyle = '#0f1a23'; g.fillRect(0, 0, 640, 360);
    g.fillStyle = '#1d2b36'; g.fillRect(0, 0, 640, 28);
    ['#ff5f57', '#febc2e', '#28c840'].forEach((col, i) => { g.fillStyle = col; g.beginPath(); g.arc(18 + i * 18, 14, 5, 0, 7); g.fill(); });
    g.font = '15px monospace';
    lines.forEach((l, i) => { g.fillStyle = i === lines.length - 1 ? color : '#c9d6df'; g.fillText(l, 18, 62 + i * 24); });
    return c.toDataURL('image/png');
  }
  // Demo storage figures (the real ones come from the database).
  let storageCleaned = false;
  let storageBackups = [{ name: 'delivery.db.v4-20261020-101500.bak', bytes: 41_200_000, modified: '2026-10-20T10:15:00Z' }];
  const demoStorage = () => ({
    file_bytes: storageCleaned ? 8_300_000 : 55_400_000,
    journal_bytes: storageCleaned ? 0 : 23_100_000,
    media_folder_bytes: storageCleaned ? 88_100_000 : 131_900_000,
    content: [
      { label: 'Images des tâches', count: 6, bytes: 640_000 },
      { label: 'Vidéos (dossier media)', count: storageCleaned ? 3 : 6, bytes: storageCleaned ? 88_100_000 : 131_900_000 },
      { label: 'Captures des livraisons', count: 14, bytes: 7_600_000 },
      { label: 'Livraisons (3) : tâches et commentaires', count: 31, bytes: 182_000 },
      { label: 'Modèle de tâches', count: 7, bytes: 9_400 },
    ],
    reclaimable: storageCleaned
      ? { unused_media: { count: 0, bytes: 0 }, orphans: { count: 0, bytes: 0 }, free_bytes: 0, journal_bytes: 0 }
      : { unused_media: { count: 3, bytes: 43_800_000 }, orphans: { count: 0, bytes: 0 }, free_bytes: 47_200_000, journal_bytes: 23_100_000 },
    backups: storageBackups,
  });

  const media = (filename, url, mime = 'image/png') => ({ id: `m${nextId()}`, filename, mime, url });

  const settings = {
    default_variables: { prev_version: '', registry: 'registry.local', env: 'recette' },
    app_title: 'Checklist Livraison', auto_timer: true, logo: null, app_version: 'démo', schema_version: 5,
  };
  // Mirror of Database._start_next: chain the timers unless one is already running.
  const startNext = (d, after, now) => {
    if (!settings.auto_timer || d.tasks.some((x) => x.status === 'running')) return;
    const idx = after ? d.tasks.indexOf(after) : -1;
    const pending = d.tasks.filter((x) => x.status === 'todo' || x.status === 'paused');
    const next = pending.find((x) => d.tasks.indexOf(x) > idx) || pending[0];
    if (next) Object.assign(next, { status: 'running', running_since: now, started_at: next.started_at || now });
  };

  // Block helpers (same shapes as blocks.js).
  const B = {
    command: (label, text) => ({ type: 'command', label, text }),
    link: (label, url) => ({ type: 'link', label, url }),
    program: (name, path, args = '', cwd = '') => ({ type: 'program', name, path, args, cwd }),
    table: (title, spec) => ({ type: 'table', title, spec }),
    media: (title, files) => ({ type: 'media', title, files }),
    note: (text) => ({ type: 'note', text }),
  };

  // [title, description, estimated minutes, blocks]
  const template = [
    ['Mettre à jour le numéro de version', 'Mettre à jour le fichier VERSION et le changelog avant de créer la branche.', 10, [
      B.command('', 'git checkout develop && git pull\necho "{{version}}" > VERSION\ngit commit -am "chore: bump version to {{version}}"'),
      B.link('Changelog à compléter', 'https://git.example.com/app/-/blob/develop/CHANGELOG.md'),
    ]],
    ['Créer la branche de release', 'La branche part de develop à jour.', 5, [
      B.command('', 'git checkout -b release/{{version}}\ngit push -u origin release/{{version}}'),
    ]],
    ['Lancer la suite de tests', 'Tous les tests doivent passer. Joindre une capture du rapport.', 30, [
      B.command('Tests', 'make test'),
      B.command('Qualité', 'make lint'),
      B.link('Pipeline de la branche', 'https://ci.example.com/app/-/pipelines?ref=release/{{version}}'),
    ]],
    ['Construire les artefacts', "Build de l'image Docker et du paquet pour la version {{version}}.", 20, [
      B.command('Image Docker', 'docker build -t {{registry}}/app:{{version}} .\ndocker push {{registry}}/app:{{version}}'),
      B.command('Paquet', 'make package VERSION={{version}}'),
    ]],
    ['Tagger la version', 'Tag annoté, comparé à la version précédente {{prev_version}}.', 5, [
      B.command('Créer le tag', 'git tag -a v{{version}} -m "Release {{version}}"\ngit push origin v{{version}}'),
      B.command('Changements depuis {{prev_version}}', 'git log --oneline v{{prev_version}}..v{{version}}'),
    ]],
    ['Déployer en recette', 'Déployer puis vérifier que la recette répond avec la bonne version.', 25, [
      B.note("Prévenir l'équipe support sur le canal #recette avant de lancer le déploiement de {{version}}."),
      B.program('Console de déploiement', 'C:\\Outils\\Deploy\\deploy-console.exe', '--env {{env}} --version {{version}}', 'C:\\Outils\\Deploy'),
      B.command('Linux', './deploy.sh --env {{env}} --version {{version}}'),
      B.command('Windows', '.\\deploy.ps1 -Env {{env}} -Version {{version}}'),
      B.link('Santé de la recette', 'https://{{env}}.example.com/health'),
      B.media('Écran attendu', [media('recette-attendue.png', screenshot(['$ curl -s https://recette.example.com/health', '{', '  "status": "UP",',
        '  "version": "x.y.z",', '  "db": "UP", "cache": "UP"', '}', '', 'Attendu : status UP et la version livrée'], '#7ee2a8'))]),
    ]],
    ['Rédiger les notes de version', "Résumé des changements depuis {{prev_version}}, à envoyer à l'équipe.", 20, [
      B.table('Liens de la livraison', 'Élément | Lien\nNotes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})\nTag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})\nComparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})'),
      B.table('Livrables', 'Livrable | Emplacement\nImage Docker | [{{registry}}/app:{{version}}](https://{{registry}}/harbor/projects/app/tags/{{version}})\nPaquet | [app-{{version}}.tar.gz](https://artifacts.example.com/app/{{version}}/app-{{version}}.tar.gz)'),
      B.program('Modèle de notes (Word)', 'C:\\Modeles\\notes-de-version.dotx'),
    ]],
  ].map(([title, description, estimated_minutes, blocks], i) => ({
    id: i + 1, position: i, title, description, estimated_minutes,
    blocks: blocks.map((b) => ({ id: `b${nextId()}`, ...b })),
    enabled: true,
    alarm: [3, 5].includes(i), // waiting tasks: build and deployment
  }));

  // Copies, not links: a delivery keeps its own blocks and media.
  const fromTemplate = (t, extra) => ({
    id: nextId(), template_task_id: t.id, title: t.title, description: t.description,
    estimated_minutes: t.estimated_minutes, blocks: clone(t.blocks || []), alarm: Boolean(t.alarm), status: 'todo', elapsed_seconds: 0,
    running_since: null, started_at: null, completed_at: null, comments: [], images: [], ...extra,
  });

  const readDataUrl = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Lecture du fichier impossible.'));
    reader.readAsDataURL(file);
  });

  const deliveries = [];

  function seed() {
    const older = {
      id: 1, version: '2.3.1', name: 'Correctif paiement', status: 'done',
      variables: { prev_version: '2.3.0', registry: 'registry.local', env: 'recette' },
      created_at: daysAgo(21, 9), completed_at: daysAgo(21, 12),
    };
    older.tasks = template.map((t, i) => fromTemplate(t, {
      status: i === 6 ? 'skipped' : 'done',
      elapsed_seconds: [480, 300, 2460, 1500, 240, 1680, 0][i],
      started_at: daysAgo(21, 9), completed_at: daysAgo(21, 11),
    }));
    older.tasks[2].comments.push({ id: nextId(), body: '1 test instable relancé (test_refund_timeout), OK au 2e passage.', created_at: daysAgo(21, 10) });

    const current = {
      id: 2, version: '2.4.0', name: "Release d'automne", status: 'in_progress',
      variables: { prev_version: '2.3.1', registry: 'registry.local', env: 'recette' },
      created_at: ago(95), completed_at: null,
    };
    current.tasks = template.map((t) => fromTemplate(t));
    Object.assign(current.tasks[0], { status: 'done', elapsed_seconds: 540, started_at: ago(90), completed_at: ago(81) });
    Object.assign(current.tasks[1], { status: 'done', elapsed_seconds: 210, started_at: ago(80), completed_at: ago(76) });
    Object.assign(current.tasks[2], { status: 'done', elapsed_seconds: 2280, started_at: ago(75), completed_at: ago(37) });
    current.tasks[2].comments.push({ id: nextId(), body: '212 tests OK, couverture 84 %. Rapport joint.', created_at: ago(37) });
    current.tasks[2].images.push({
      id: nextId(), filename: 'rapport-tests.png',
      url: screenshot(['$ make test', '============ test session starts ============', 'collected 212 items', '', 'tests/api ........................ [ 41%]', 'tests/core ....................... [ 88%]', 'tests/ui ......                    [100%]', '', '=========== 212 passed in 61.42s ==========='], '#7ee2a8'),
    });
    Object.assign(current.tasks[3], { status: 'running', elapsed_seconds: 600, running_since: ago(14), started_at: ago(36) });
    current.tasks[3].comments.push({ id: nextId(), body: 'Premier build en échec (cache npm), relancé avec --no-cache.', created_at: ago(20) });
    current.tasks[3].images.push({
      id: nextId(), filename: 'build-echec.png',
      url: screenshot(['$ docker build -t registry.local/app:2.4.0 .', 'Step 7/14 : RUN npm ci', 'npm ERR! code EINTEGRITY', 'npm ERR! sha512 integrity checksum failed', '', 'ERROR: failed to solve: process "npm ci"', 'did not complete successfully: exit code 1'], '#ff9d8a'),
    });
    deliveries.push(older, current);
  }
  seed();

  // Progress weighted by estimated time; a task without estimate weighs 1 minute.
  const weight = (t) => Math.max(1, t.estimated_minutes || 0);
  function progress(tasks) {
    const total = tasks.filter((t) => t.status !== 'skipped').reduce((a, t) => a + weight(t), 0);
    const done = tasks.filter((t) => t.status === 'done').reduce((a, t) => a + weight(t), 0);
    return total ? Math.round((100 * done) / total) : 0;
  }
  function elapsedNow(t) {
    let s = t.elapsed_seconds;
    if (t.status === 'running' && t.running_since) s += Math.floor((Date.now() - Date.parse(t.running_since)) / 1000);
    return s;
  }
  const full = (d) => clone({ ...d, progress: progress(d.tasks) });
  const findD = (id) => { const d = deliveries.find((x) => x.id === id); if (!d) throw new Error('Livraison introuvable.'); return d; };
  // A closed delivery is read-only until reopened (same rule as the server).
  const ensureOpen = (d) => { if (d.status === 'done') throw new Error('Livraison clôturée : rouvrez-la pour la modifier.'); };
  const findT = (id) => {
    for (const d of deliveries) { const t = d.tasks.find((x) => x.id === id); if (t) return [d, t]; }
    throw new Error('Tâche introuvable.');
  };
  const fields = (data) => {
    if (!String(data.title || '').trim()) throw new Error('Le titre est obligatoire.');
    return {
      title: data.title.trim(), description: data.description || '',
      estimated_minutes: Math.max(0, Number(data.estimated_minutes) || 0),
      blocks: clone(data.blocks || []),
      enabled: data.enabled !== false,
      alarm: Boolean(data.alarm),
    };
  };
  const ok = (v) => new Promise((r) => setTimeout(() => r(v), 60));

  const api = {
    getSettings: () => ok(clone(settings)),
    setLogo: async (file) => { settings.logo = await readDataUrl(file); return ok(clone(settings)); },
    deleteLogo: () => { settings.logo = null; return ok(clone(settings)); },
    getStorage: () => ok(demoStorage()),
    cleanupStorage: (deleteBackups) => {
      const before = demoStorage();
      storageCleaned = true;
      if (deleteBackups) storageBackups = [];
      const after = demoStorage();
      const saved = before.file_bytes + before.journal_bytes - after.file_bytes - after.journal_bytes
        + (deleteBackups ? before.backups.reduce((a, b) => a + b.bytes, 0) : 0);
      return ok({ ...after, result: { media: 3, rows: 0, backups: deleteBackups ? before.backups.length : 0, saved_bytes: saved } });
    },
    saveSettings: (data) => {
      if (data.default_variables) settings.default_variables = { ...data.default_variables };
      if (data.auto_timer !== undefined) settings.auto_timer = !!data.auto_timer;
      if (data.app_title !== undefined) settings.app_title = String(data.app_title).trim().slice(0, 60) || 'Checklist Livraison';
      return ok(clone(settings));
    },

    listTasks: () => ok(clone(template)),
    createTask: (data) => { const t = { id: nextId(), position: template.length, ...fields(data) }; template.push(t); return ok(clone(t)); },
    updateTask: (id, data) => { const t = template.find((x) => x.id === id); Object.assign(t, fields({ ...t, ...data })); return ok(clone(t)); },
    deleteTask: (id) => { template.splice(template.findIndex((x) => x.id === id), 1); return ok({ ok: true }); },
    reorderTasks: (ids) => { template.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id)); return ok(clone(template)); },
    uploadMedia: async (file) => media(file.name || 'fichier', await readDataUrl(file), file.type),

    listDeliveries: () => ok([...deliveries].sort((a, b) => b.created_at.localeCompare(a.created_at)).map((d) => ({
      id: d.id, version: d.version, name: d.name, status: d.status, created_at: d.created_at,
      completed_at: d.completed_at, variables: clone(d.variables), progress: progress(d.tasks),
      task_count: d.tasks.length, done_count: d.tasks.filter((t) => t.status === 'done' || t.status === 'skipped').length,
    }))),
    createDelivery: (data) => {
      if (!String(data.version || '').trim()) return Promise.reject(new Error('La version est obligatoire.'));
      const d = {
        id: nextId(), version: data.version.trim(), name: data.name || '', status: 'in_progress',
        variables: { ...data.variables }, created_at: iso(new Date()), completed_at: null,
      };
      d.tasks = template.filter((t) => t.enabled !== false).map((t) => fromTemplate(t));
      startNext(d, null, d.created_at);
      deliveries.push(d);
      return ok(full(d));
    },
    getDelivery: (id) => ok(full(findD(id))),
    updateDelivery: (id, data) => {
      const d = findD(id);
      if (d.status === 'done') {
        if (data.status !== 'in_progress') return Promise.reject(new Error('Livraison clôturée : rouvrez-la pour la modifier.'));
        data = { status: 'in_progress' };
      }
      if (data.status === 'done') {
        for (const t of d.tasks) if (t.status === 'running') Object.assign(t, { status: 'paused', elapsed_seconds: elapsedNow(t), running_since: null });
      }
      if (data.version !== undefined) d.version = data.version.trim() || d.version;
      if (data.name !== undefined) d.name = data.name;
      if (data.variables) d.variables = { ...data.variables };
      if (data.status && data.status !== d.status) { d.status = data.status; d.completed_at = data.status === 'done' ? iso(new Date()) : null; }
      return ok(full(d));
    },
    deleteDelivery: (id) => { ensureOpen(findD(id)); deliveries.splice(deliveries.indexOf(findD(id)), 1); return ok({ ok: true }); },
    addDeliveryTask: (id, data) => {
      const d = findD(id);
      ensureOpen(d);
      let tplId = null;
      if (data.add_to_template) { const t = { id: nextId(), position: template.length, ...fields(data) }; template.push(t); tplId = t.id; }
      d.tasks.push(fromTemplate({ ...fields(data), id: tplId }));
      return ok(full(d));
    },
    reorderDeliveryTasks: (id, ids) => { const d = findD(id); ensureOpen(d); d.tasks.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id)); return ok(full(d)); },

    updateDeliveryTask: (id, data) => { const [d, t] = findT(id); ensureOpen(d); Object.assign(t, fields({ ...t, ...data })); return ok(full(d)); },
    deleteDeliveryTask: (id) => { const [d, t] = findT(id); ensureOpen(d); d.tasks.splice(d.tasks.indexOf(t), 1); return ok(full(d)); },
    taskAction: (id, action) => {
      const [d, t] = findT(id);
      ensureOpen(d);
      const now = iso(new Date());
      const el = elapsedNow(t);
      if (action === 'start' && !['running', 'done', 'skipped'].includes(t.status)) Object.assign(t, { status: 'running', running_since: now, started_at: t.started_at || now });
      else if (action === 'pause' && t.status === 'running') Object.assign(t, { status: 'paused', running_since: null, elapsed_seconds: el });
      else if (action === 'done' || action === 'skip') Object.assign(t, { status: action === 'done' ? 'done' : 'skipped', running_since: null, elapsed_seconds: el, completed_at: now });
      else if (action === 'reopen' && ['done', 'skipped'].includes(t.status)) Object.assign(t, { status: t.elapsed_seconds ? 'paused' : 'todo', completed_at: null });
      else if (action === 'reset') Object.assign(t, { status: 'todo', running_since: null, elapsed_seconds: 0, started_at: null, completed_at: null });
      if (action === 'done' || action === 'skip') startNext(d, t, now);
      return ok(full(d));
    },
    addComment: (id, body) => {
      if (!String(body || '').trim()) return Promise.reject(new Error('Le commentaire est vide.'));
      const [d, t] = findT(id);
      ensureOpen(d);
      t.comments.push({ id: nextId(), body: body.trim(), created_at: iso(new Date()) });
      return ok(full(d));
    },
    deleteComment: (id) => {
      for (const d of deliveries) for (const t of d.tasks) {
        const i = t.comments.findIndex((c) => c.id === id);
        if (i >= 0) { t.comments.splice(i, 1); return ok(full(d)); }
      }
      return Promise.reject(new Error('Commentaire introuvable.'));
    },
    deleteImage: (id) => {
      for (const d of deliveries) for (const t of d.tasks) {
        const i = t.images.findIndex((c) => c.id === id);
        if (i >= 0) { t.images.splice(i, 1); return ok(full(d)); }
      }
      return Promise.reject(new Error('Image introuvable.'));
    },
    uploadImage: async (taskId, file) => {
      const [d, t] = findT(taskId);
      ensureOpen(d);
      t.images.push({ id: nextId(), filename: file.name || 'capture.png', url: await readDataUrl(file) });
      return full(d);
    },
    // A delivery screenshot joins the "Images et vidéos" element of its template task (created if needed).
    imageToTemplate: (id) => {
      for (const d of deliveries) for (const t of d.tasks) {
        const img = t.images.find((x) => x.id === id);
        if (!img) continue;
        const tpl = template.find((x) => x.id === t.template_task_id);
        if (!tpl) return Promise.reject(new Error('Cette tâche ne provient pas du modèle.'));
        let block = tpl.blocks.find((b) => b.type === 'media');
        if (!block) { block = { id: `b${nextId()}`, ...B.media('Captures de référence', []) }; tpl.blocks.push(block); }
        block.files.push(media(img.filename, img.url));
        return ok(full(d));
      }
      return Promise.reject(new Error('Image introuvable.'));
    },
    launchProgram: (taskId, blockId) => {
      const [d, t] = findT(taskId);
      const b = t.blocks.find((x) => x.id === blockId);
      return ok({ message: `Démo : dans l'application locale, « ${b.name || b.path} » serait lancé sur votre poste.` });
    },
    exportTaskTable: () => Promise.reject(new Error(
      "Démo : le .docx est généré par le serveur Python de l'app locale. « Copier pour Word » fonctionne ici.")),
    exportReport: (id, fmt) => Promise.reject(new Error(
      `Démo : l'export ${fmt === 'pdf' ? 'PDF' : 'Word'} est généré par le serveur Python de l'app locale.`)),
  };

  // Every call returns a promise, errors included (like the real HTTP client).
  window.API = { demo: true };
  for (const [name, fn] of Object.entries(api)) {
    window.API[name] = (...args) => {
      try { return Promise.resolve(fn(...args)); } catch (err) { return Promise.reject(err); }
    };
  }
})();
