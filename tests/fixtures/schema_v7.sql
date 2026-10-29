BEGIN TRANSACTION;
CREATE TABLE comments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_task_id INTEGER NOT NULL REFERENCES delivery_tasks(id) ON DELETE CASCADE,
    body             TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
INSERT INTO "comments" VALUES(1,1,'Commentaire historique — accents éàç','2026-10-29T15:45:55Z');
CREATE TABLE deliveries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    version      TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    variables    TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | done
    created_at   TEXT NOT NULL,
    completed_at TEXT
);
INSERT INTO "deliveries" VALUES(1,'1.0.0','Ancienne livraison','{"prev_version": "0.9.0", "env": "prod"}','done','2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "deliveries" VALUES(2,'1.1.0','','{"prev_version": "1.0.0"}','in_progress','2026-10-29T15:45:55Z',NULL);
CREATE TABLE delivery_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id       INTEGER NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    template_task_id  INTEGER REFERENCES template_tasks(id) ON DELETE SET NULL,
    position          INTEGER NOT NULL DEFAULT 0,
    title             TEXT    NOT NULL,
    description       TEXT    NOT NULL DEFAULT '',
    blocks            TEXT    NOT NULL DEFAULT '[]', -- JSON content blocks, see blocks.py
    estimated_minutes INTEGER NOT NULL DEFAULT 0,    -- also the task's weight in the progress
    -- legacy columns, unused since v5 (kept so old databases and new ones stay identical):
    command           TEXT    NOT NULL DEFAULT '',
    table_spec        TEXT    NOT NULL DEFAULT '',
    commands          TEXT    NOT NULL DEFAULT '[]',
    link_tables       TEXT    NOT NULL DEFAULT '[]',
    weight            INTEGER NOT NULL DEFAULT 1,
    status            TEXT    NOT NULL DEFAULT 'todo', -- todo | running | paused | done | skipped
    elapsed_seconds   INTEGER NOT NULL DEFAULT 0,
    running_since     TEXT,
    started_at        TEXT,
    completed_at      TEXT
);
INSERT INTO "delivery_tasks" VALUES(1,1,1,0,'Mettre à jour le numéro de version','Mettre à jour le fichier de version et le changelog avant de créer la branche.','[{"id": "b234a18dc30", "type": "command", "label": "", "text": "git checkout develop && git pull\necho \"{{version}}\" > VERSION\ngit commit -am \"chore: bump version to {{version}}\""}, {"id": "bdb568da991", "type": "link", "label": "Pipeline", "url": "https://ci.example.com/{{version}}"}, {"id": "b4d7f78dcde", "type": "program", "name": "Outil", "path": "/opt/outil", "args": "--v {{version}}", "cwd": ""}, {"id": "baa73e4652c", "type": "note", "text": "Consigne"}, {"id": "b89d5f09853", "type": "media", "title": "Écran attendu", "files": [1]}]',10,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(2,1,2,1,'Créer la branche de release','La branche part de develop à jour.','[{"id": "be7ff8029f2", "type": "command", "label": "", "text": "git checkout -b release/{{version}}\ngit push -u origin release/{{version}}"}]',5,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(3,1,3,2,'Lancer la suite de tests','Tous les tests doivent passer. Joindre une capture du rapport en cas d''échec.','[{"id": "b66fce0b91f", "type": "command", "label": "Tests", "text": "make test"}, {"id": "b33b4698139", "type": "command", "label": "Qualité", "text": "make lint"}, {"id": "b4eecc190ac", "type": "link", "label": "Pipeline de la branche", "url": "https://ci.example.com/app/-/pipelines?ref=release/{{version}}"}]',30,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(4,1,4,3,'Construire les artefacts','Build de l''image et du paquet pour la version.','[{"id": "bb1178bca15", "type": "command", "label": "Image Docker", "text": "docker build -t registry.local/app:{{version}} .\ndocker push registry.local/app:{{version}}"}, {"id": "bbeab1e1b14", "type": "command", "label": "Paquet", "text": "make package VERSION={{version}}"}]',20,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(5,1,5,4,'Tagger la version','Tag annoté, comparé à la version précédente {{prev_version}}.','[{"id": "bc1a966d315", "type": "command", "label": "Créer le tag", "text": "git tag -a v{{version}} -m \"Release {{version}}\"\ngit push origin v{{version}}"}, {"id": "bb48eb389ad", "type": "command", "label": "Changements depuis {{prev_version}}", "text": "git log --oneline v{{prev_version}}..v{{version}}"}]',5,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(6,1,6,5,'Déployer en recette','Déployer puis vérifier que la recette répond avec la bonne version.','[{"id": "b347142324b", "type": "note", "text": "Prévenir l''équipe support avant de lancer le déploiement de {{version}}."}, {"id": "b58e4e92cb6", "type": "command", "label": "", "text": "./deploy.sh --env recette --version {{version}}"}, {"id": "b32f3ffbc49", "type": "link", "label": "Santé de la recette", "url": "https://recette.example.com/health"}]',25,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(7,1,7,6,'Rédiger les notes de version','Résumé des changements depuis {{prev_version}}, à envoyer à l''équipe.','[{"id": "b6fb1504bfb", "type": "table", "title": "Liens de la livraison", "spec": "Élément | Lien\nNotes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})\nTag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})\nComparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})"}, {"id": "b876c2d2c21", "type": "table", "title": "Livrables", "spec": "Livrable | Emplacement\nImage Docker | [registry.local/app:{{version}}](https://registry.local/harbor/projects/app/tags/{{version}})\nPaquet | [app-{{version}}.tar.gz](https://artifacts.example.com/app/{{version}}/app-{{version}}.tar.gz)"}]',20,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(8,1,8,7,'Tâche ajoutée au modèle','','[]',5,'','','[]','[]',1,'done',0,NULL,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(9,2,1,0,'Mettre à jour le numéro de version','Mettre à jour le fichier de version et le changelog avant de créer la branche.','[{"id": "b234a18dc30", "type": "command", "label": "", "text": "git checkout develop && git pull\necho \"{{version}}\" > VERSION\ngit commit -am \"chore: bump version to {{version}}\""}, {"id": "bdb568da991", "type": "link", "label": "Pipeline", "url": "https://ci.example.com/{{version}}"}, {"id": "b4d7f78dcde", "type": "program", "name": "Outil", "path": "/opt/outil", "args": "--v {{version}}", "cwd": ""}, {"id": "baa73e4652c", "type": "note", "text": "Consigne"}, {"id": "b89d5f09853", "type": "media", "title": "Écran attendu", "files": [1]}]',10,'','','[]','[]',1,'running',0,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',NULL);
INSERT INTO "delivery_tasks" VALUES(10,2,2,1,'Créer la branche de release','La branche part de develop à jour.','[{"id": "be7ff8029f2", "type": "command", "label": "", "text": "git checkout -b release/{{version}}\ngit push -u origin release/{{version}}"}]',5,'','','[]','[]',1,'skipped',0,NULL,NULL,'2026-10-29T15:45:55Z');
INSERT INTO "delivery_tasks" VALUES(11,2,3,2,'Lancer la suite de tests','Tous les tests doivent passer. Joindre une capture du rapport en cas d''échec.','[{"id": "b66fce0b91f", "type": "command", "label": "Tests", "text": "make test"}, {"id": "b33b4698139", "type": "command", "label": "Qualité", "text": "make lint"}, {"id": "b4eecc190ac", "type": "link", "label": "Pipeline de la branche", "url": "https://ci.example.com/app/-/pipelines?ref=release/{{version}}"}]',30,'','','[]','[]',1,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(12,2,4,3,'Construire les artefacts','Build de l''image et du paquet pour la version.','[{"id": "bb1178bca15", "type": "command", "label": "Image Docker", "text": "docker build -t registry.local/app:{{version}} .\ndocker push registry.local/app:{{version}}"}, {"id": "bbeab1e1b14", "type": "command", "label": "Paquet", "text": "make package VERSION={{version}}"}]',20,'','','[]','[]',1,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(13,2,5,4,'Tagger la version','Tag annoté, comparé à la version précédente {{prev_version}}.','[{"id": "bc1a966d315", "type": "command", "label": "Créer le tag", "text": "git tag -a v{{version}} -m \"Release {{version}}\"\ngit push origin v{{version}}"}, {"id": "bb48eb389ad", "type": "command", "label": "Changements depuis {{prev_version}}", "text": "git log --oneline v{{prev_version}}..v{{version}}"}]',5,'','','[]','[]',1,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(14,2,6,5,'Déployer en recette','Déployer puis vérifier que la recette répond avec la bonne version.','[{"id": "b347142324b", "type": "note", "text": "Prévenir l''équipe support avant de lancer le déploiement de {{version}}."}, {"id": "b58e4e92cb6", "type": "command", "label": "", "text": "./deploy.sh --env recette --version {{version}}"}, {"id": "b32f3ffbc49", "type": "link", "label": "Santé de la recette", "url": "https://recette.example.com/health"}]',25,'','','[]','[]',1,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(15,2,7,6,'Rédiger les notes de version','Résumé des changements depuis {{prev_version}}, à envoyer à l''équipe.','[{"id": "b6fb1504bfb", "type": "table", "title": "Liens de la livraison", "spec": "Élément | Lien\nNotes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})\nTag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})\nComparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})"}, {"id": "b876c2d2c21", "type": "table", "title": "Livrables", "spec": "Livrable | Emplacement\nImage Docker | [registry.local/app:{{version}}](https://registry.local/harbor/projects/app/tags/{{version}})\nPaquet | [app-{{version}}.tar.gz](https://artifacts.example.com/app/{{version}}/app-{{version}}.tar.gz)"}]',20,'','','[]','[]',1,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(16,2,8,7,'Tâche ajoutée au modèle','','[]',5,'','','[]','[]',1,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(17,2,NULL,8,'Tâche ad hoc','','[]',3,'','','[]','[]',1,'todo',0,NULL,NULL,NULL);
CREATE TABLE images (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_task_id INTEGER NOT NULL REFERENCES delivery_tasks(id) ON DELETE CASCADE,
    filename         TEXT NOT NULL,
    mime             TEXT NOT NULL,
    size             INTEGER NOT NULL,
    data             BLOB NOT NULL,
    created_at       TEXT NOT NULL,
    reference        INTEGER NOT NULL DEFAULT 0  -- 1 = copied from the template task at creation
);
INSERT INTO "images" VALUES(1,1,'capture.png','image/png',71,X'89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D49444154789C6360F8CFC0F01F0005000201E2213BC90000000049454E44AE426082','2026-10-29T15:45:55Z',0);
CREATE TABLE media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    filename   TEXT NOT NULL,
    mime       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    data       BLOB NOT NULL,
    created_at TEXT NOT NULL,
    file       TEXT NOT NULL DEFAULT ''
);
INSERT INTO "media" VALUES(1,'reference.png','image/png',71,X'89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D49444154789C6360F8CFC0F01F0005000201E2213BC90000000049454E44AE426082','2026-10-29T15:45:55Z','');
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO "settings" VALUES('schema_version','7');
INSERT INTO "settings" VALUES('default_variables','{"prev_version": "", "env": "recette"}');
CREATE TABLE template_images (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    template_task_id INTEGER NOT NULL REFERENCES template_tasks(id) ON DELETE CASCADE,
    filename         TEXT NOT NULL,
    mime             TEXT NOT NULL,
    size             INTEGER NOT NULL,
    data             BLOB NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE TABLE template_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    position          INTEGER NOT NULL DEFAULT 0,
    title             TEXT    NOT NULL,
    description       TEXT    NOT NULL DEFAULT '',
    blocks            TEXT    NOT NULL DEFAULT '[]', -- JSON content blocks, see blocks.py
    estimated_minutes INTEGER NOT NULL DEFAULT 0,    -- also the task's weight in the progress
    -- legacy columns, unused since v5 (kept so old databases and new ones stay identical):
    command           TEXT    NOT NULL DEFAULT '',
    table_spec        TEXT    NOT NULL DEFAULT '',
    commands          TEXT    NOT NULL DEFAULT '[]',
    link_tables       TEXT    NOT NULL DEFAULT '[]',
    weight            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    enabled           INTEGER NOT NULL DEFAULT 1     -- 0 = kept in the template, not copied (v7)
);
INSERT INTO "template_tasks" VALUES(1,0,'Mettre à jour le numéro de version','Mettre à jour le fichier de version et le changelog avant de créer la branche.','[{"id": "b234a18dc30", "type": "command", "label": "", "text": "git checkout develop && git pull\necho \"{{version}}\" > VERSION\ngit commit -am \"chore: bump version to {{version}}\""}, {"id": "bdb568da991", "type": "link", "label": "Pipeline", "url": "https://ci.example.com/{{version}}"}, {"id": "b4d7f78dcde", "type": "program", "name": "Outil", "path": "/opt/outil", "args": "--v {{version}}", "cwd": ""}, {"id": "baa73e4652c", "type": "note", "text": "Consigne"}, {"id": "b89d5f09853", "type": "media", "title": "Écran attendu", "files": [1]}]',10,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(2,1,'Créer la branche de release','La branche part de develop à jour.','[{"id": "be7ff8029f2", "type": "command", "label": "", "text": "git checkout -b release/{{version}}\ngit push -u origin release/{{version}}"}]',5,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(3,2,'Lancer la suite de tests','Tous les tests doivent passer. Joindre une capture du rapport en cas d''échec.','[{"id": "b66fce0b91f", "type": "command", "label": "Tests", "text": "make test"}, {"id": "b33b4698139", "type": "command", "label": "Qualité", "text": "make lint"}, {"id": "b4eecc190ac", "type": "link", "label": "Pipeline de la branche", "url": "https://ci.example.com/app/-/pipelines?ref=release/{{version}}"}]',30,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(4,3,'Construire les artefacts','Build de l''image et du paquet pour la version.','[{"id": "bb1178bca15", "type": "command", "label": "Image Docker", "text": "docker build -t registry.local/app:{{version}} .\ndocker push registry.local/app:{{version}}"}, {"id": "bbeab1e1b14", "type": "command", "label": "Paquet", "text": "make package VERSION={{version}}"}]',20,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(5,4,'Tagger la version','Tag annoté, comparé à la version précédente {{prev_version}}.','[{"id": "bc1a966d315", "type": "command", "label": "Créer le tag", "text": "git tag -a v{{version}} -m \"Release {{version}}\"\ngit push origin v{{version}}"}, {"id": "bb48eb389ad", "type": "command", "label": "Changements depuis {{prev_version}}", "text": "git log --oneline v{{prev_version}}..v{{version}}"}]',5,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(6,5,'Déployer en recette','Déployer puis vérifier que la recette répond avec la bonne version.','[{"id": "b347142324b", "type": "note", "text": "Prévenir l''équipe support avant de lancer le déploiement de {{version}}."}, {"id": "b58e4e92cb6", "type": "command", "label": "", "text": "./deploy.sh --env recette --version {{version}}"}, {"id": "b32f3ffbc49", "type": "link", "label": "Santé de la recette", "url": "https://recette.example.com/health"}]',25,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(7,6,'Rédiger les notes de version','Résumé des changements depuis {{prev_version}}, à envoyer à l''équipe.','[{"id": "b6fb1504bfb", "type": "table", "title": "Liens de la livraison", "spec": "Élément | Lien\nNotes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})\nTag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})\nComparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})"}, {"id": "b876c2d2c21", "type": "table", "title": "Livrables", "spec": "Livrable | Emplacement\nImage Docker | [registry.local/app:{{version}}](https://registry.local/harbor/projects/app/tags/{{version}})\nPaquet | [app-{{version}}.tar.gz](https://artifacts.example.com/app/{{version}}/app-{{version}}.tar.gz)"}]',20,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(8,7,'Tâche ajoutée au modèle','','[]',5,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',1);
INSERT INTO "template_tasks" VALUES(9,8,'Tâche désactivée','','[]',2,'','','[]','[]',1,'2026-10-29T15:45:55Z','2026-10-29T15:45:55Z',0);
CREATE INDEX idx_dtasks_delivery ON delivery_tasks(delivery_id);
CREATE INDEX idx_comments_task ON comments(delivery_task_id);
CREATE INDEX idx_images_task ON images(delivery_task_id);
CREATE INDEX idx_template_images_task ON template_images(template_task_id);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('template_tasks',9);
INSERT INTO "sqlite_sequence" VALUES('media',1);
INSERT INTO "sqlite_sequence" VALUES('deliveries',2);
INSERT INTO "sqlite_sequence" VALUES('delivery_tasks',17);
INSERT INTO "sqlite_sequence" VALUES('comments',1);
INSERT INTO "sqlite_sequence" VALUES('images',1);
COMMIT;
