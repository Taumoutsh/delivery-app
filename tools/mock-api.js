// In-memory stand-in for api.js, used only by the standalone demo (tools/build_demo.py).
// Mirrors the backend rules in delivery_app/db.py on example data.
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

  const settings = { default_variables: { prev_version: '', registry: 'registry.local' } };

  // [title, description, [[label, command]], weight, minutes, [[table title, table spec]]]
  const template = [
    ['Mettre à jour le numéro de version', 'Mettre à jour le fichier VERSION et le changelog avant de créer la branche.',
      [['', 'git checkout develop && git pull\necho "{{version}}" > VERSION\ngit commit -am "chore: bump version to {{version}}"']], 2, 10],
    ['Créer la branche de release', 'La branche part de develop à jour.',
      [['', 'git checkout -b release/{{version}}\ngit push -u origin release/{{version}}']], 1, 5],
    ['Lancer la suite de tests', 'Tous les tests doivent passer. Joindre une capture du rapport.',
      [['Tests', 'make test'], ['Qualité', 'make lint']], 3, 30],
    ['Construire les artefacts', "Build de l'image Docker et du paquet pour la version {{version}}.",
      [['Image Docker', 'docker build -t {{registry}}/app:{{version}} .\ndocker push {{registry}}/app:{{version}}'],
        ['Paquet', 'make package VERSION={{version}}']], 3, 20],
    ['Tagger la version', 'Tag annoté, comparé à la version précédente {{prev_version}}.',
      [['Créer le tag', 'git tag -a v{{version}} -m "Release {{version}}"\ngit push origin v{{version}}'],
        ['Changements depuis {{prev_version}}', 'git log --oneline v{{prev_version}}..v{{version}}']], 1, 5],
    ['Déployer en recette', 'Vérifier les logs après déploiement.',
      [['Linux', './deploy.sh --env {{env}} --version {{version}}'], ['Windows', '.\\deploy.ps1 -Env {{env}} -Version {{version}}']], 3, 25],
    ['Rédiger les notes de version', "Résumé des changements depuis {{prev_version}}, à envoyer à l'équipe. Les tableaux se collent directement dans le document de livraison.",
      [], 2, 20, [
        ['Liens de la livraison', 'Élément | Lien\nNotes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})\nTag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})\nComparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})'],
        ['Livrables', 'Livrable | Emplacement\nImage Docker | [{{registry}}/app:{{version}}](https://{{registry}}/harbor/projects/app/tags/{{version}})\nPaquet | [app-{{version}}.tar.gz](https://artifacts.example.com/app/{{version}}/app-{{version}}.tar.gz)'],
      ]],
  ].map(([title, description, commands, weight, estimated_minutes, tables = []], i) => ({
    id: i + 1, position: i, title, description, weight, estimated_minutes,
    commands: commands.map(([label, text]) => ({ label, text })),
    link_tables: tables.map(([t, spec]) => ({ title: t, spec })),
  }));

  template.forEach((t) => { t.images = []; });
  template[5].images.push({
    id: nextId(), filename: 'recette-attendue.png',
    url: screenshot(['$ curl -s https://recette.example.com/health', '{', '  "status": "UP",', '  "version": "x.y.z",',
      '  "db": "UP", "cache": "UP"', '}', '', 'Attendu : status UP et la version livrée'], '#7ee2a8'),
  });

  // Template screenshots are copied as "reference" captures, like the backend does.
  const fromTemplate = (t, extra) => ({
    id: nextId(), template_task_id: t.id, title: t.title, description: t.description,
    commands: clone(t.commands || []), link_tables: clone(t.link_tables || []),
    weight: t.weight, estimated_minutes: t.estimated_minutes, status: 'todo', elapsed_seconds: 0,
    running_since: null, started_at: null, completed_at: null, comments: [],
    images: (t.images || []).map((img) => ({ ...img, id: nextId(), reference: true })), ...extra,
  });

  const readDataUrl = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Lecture de l'image impossible."));
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

  function elapsedNow(t) {
    let s = t.elapsed_seconds;
    if (t.status === 'running' && t.running_since) s += Math.floor((Date.now() - Date.parse(t.running_since)) / 1000);
    return s;
  }
  function progress(tasks) {
    const total = tasks.filter((t) => t.status !== 'skipped').reduce((a, t) => a + t.weight, 0);
    const done = tasks.filter((t) => t.status === 'done').reduce((a, t) => a + t.weight, 0);
    return total ? Math.round((100 * done) / total) : 0;
  }
  const full = (d) => clone({ ...d, progress: progress(d.tasks) });
  const findD = (id) => { const d = deliveries.find((x) => x.id === id); if (!d) throw new Error('Livraison introuvable.'); return d; };
  const findT = (id) => {
    for (const d of deliveries) { const t = d.tasks.find((x) => x.id === id); if (t) return [d, t]; }
    throw new Error('Tâche introuvable.');
  };
  const fields = (data) => {
    if (!String(data.title || '').trim()) throw new Error('Le titre est obligatoire.');
    return {
      title: data.title.trim(), description: data.description || '',
      commands: (data.commands || []).filter((c) => String(c.text || '').trim())
        .map((c) => ({ label: String(c.label || '').trim(), text: String(c.text) })),
      link_tables: (data.link_tables || []).filter((tb) => String(tb.spec || '').trim())
        .map((tb) => ({ title: String(tb.title || '').trim(), spec: String(tb.spec) })),
      weight: Math.max(0, Number(data.weight) || 0), estimated_minutes: Math.max(0, Number(data.estimated_minutes) || 0),
    };
  };
  const ok = (v) => new Promise((r) => setTimeout(() => r(v), 60));

  window.API = {
    demo: true,
    getSettings: () => ok(clone(settings)),
    saveSettings: (data) => { settings.default_variables = { ...data.default_variables }; return ok(clone(settings)); },

    listTasks: () => ok(clone(template)),
    createTask: (data) => { const t = { id: nextId(), position: template.length, images: [], ...fields(data) }; template.push(t); return ok(clone(t)); },
    uploadTemplateImage: async (taskId, file) => {
      const t = template.find((x) => x.id === taskId);
      t.images.push({ id: nextId(), filename: file.name || 'capture.png', url: await readDataUrl(file) });
      return clone(template);
    },
    deleteTemplateImage: (id) => {
      for (const t of template) t.images = t.images.filter((img) => img.id !== id);
      return ok(clone(template));
    },
    imageToTemplate: (id) => {
      for (const d of deliveries) for (const t of d.tasks) {
        const img = t.images.find((x) => x.id === id);
        const tpl = img && template.find((x) => x.id === t.template_task_id);
        if (!img) continue;
        if (!tpl) return Promise.reject(new Error('Cette tâche ne provient pas du modèle.'));
        tpl.images.push({ id: nextId(), filename: img.filename, url: img.url });
        return ok(full(d));
      }
      return Promise.reject(new Error('Image introuvable.'));
    },
    updateTask: (id, data) => { const t = template.find((x) => x.id === id); Object.assign(t, fields({ ...t, ...data })); return ok(clone(t)); },
    deleteTask: (id) => { template.splice(template.findIndex((x) => x.id === id), 1); return ok({ ok: true }); },
    reorderTasks: (ids) => { template.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id)); return ok(clone(template)); },

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
      d.tasks = template.map((t) => fromTemplate(t));
      deliveries.push(d);
      return ok(full(d));
    },
    getDelivery: (id) => ok(full(findD(id))),
    updateDelivery: (id, data) => {
      const d = findD(id);
      if (data.version !== undefined) d.version = data.version.trim() || d.version;
      if (data.name !== undefined) d.name = data.name;
      if (data.variables) d.variables = { ...data.variables };
      if (data.status && data.status !== d.status) { d.status = data.status; d.completed_at = data.status === 'done' ? iso(new Date()) : null; }
      return ok(full(d));
    },
    deleteDelivery: (id) => { deliveries.splice(deliveries.indexOf(findD(id)), 1); return ok({ ok: true }); },
    addDeliveryTask: (id, data) => {
      const d = findD(id);
      let tplId = null;
      if (data.add_to_template) { const t = { id: nextId(), position: template.length, images: [], ...fields(data) }; template.push(t); tplId = t.id; }
      d.tasks.push(fromTemplate({ ...fields(data), id: tplId }));
      return ok(full(d));
    },
    reorderDeliveryTasks: (id, ids) => { const d = findD(id); d.tasks.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id)); return ok(full(d)); },

    updateDeliveryTask: (id, data) => { const [d, t] = findT(id); Object.assign(t, fields({ ...t, ...data })); return ok(full(d)); },
    deleteDeliveryTask: (id) => { const [d, t] = findT(id); d.tasks.splice(d.tasks.indexOf(t), 1); return ok(full(d)); },
    taskAction: (id, action) => {
      const [d, t] = findT(id);
      const now = iso(new Date());
      const el = elapsedNow(t);
      if (action === 'start' && !['running', 'done', 'skipped'].includes(t.status)) Object.assign(t, { status: 'running', running_since: now, started_at: t.started_at || now });
      else if (action === 'pause' && t.status === 'running') Object.assign(t, { status: 'paused', running_since: null, elapsed_seconds: el });
      else if (action === 'done' || action === 'skip') Object.assign(t, { status: action === 'done' ? 'done' : 'skipped', running_since: null, elapsed_seconds: el, completed_at: now });
      else if (action === 'reopen' && ['done', 'skipped'].includes(t.status)) Object.assign(t, { status: t.elapsed_seconds ? 'paused' : 'todo', completed_at: null });
      else if (action === 'reset') Object.assign(t, { status: 'todo', running_since: null, elapsed_seconds: 0, started_at: null, completed_at: null });
      return ok(full(d));
    },
    addComment: (id, body) => {
      if (!String(body || '').trim()) return Promise.reject(new Error('Le commentaire est vide.'));
      const [d, t] = findT(id);
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
      t.images.push({ id: nextId(), filename: file.name || 'capture.png', url: await readDataUrl(file), reference: false });
      return full(d);
    },
    exportTaskTable: () => Promise.reject(new Error(
      "Démo : le .docx est généré par le serveur Python de l'app locale. « Copier pour Word » fonctionne ici.")),
    exportReport: (id, fmt) => Promise.reject(new Error(
      `Démo : l'export ${fmt === 'pdf' ? 'PDF' : 'Word'} est généré par le serveur Python de l'app locale.`)),
  };
})();
