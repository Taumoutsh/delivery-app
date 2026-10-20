BEGIN TRANSACTION;
CREATE TABLE comments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_task_id INTEGER NOT NULL REFERENCES delivery_tasks(id) ON DELETE CASCADE,
    body             TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
INSERT INTO "comments" VALUES(1,1,'Commentaire historique — accents éàç','2026-10-20T16:22:35Z');
CREATE TABLE deliveries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    version      TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    variables    TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | done
    created_at   TEXT NOT NULL,
    completed_at TEXT
);
INSERT INTO "deliveries" VALUES(1,'1.0.0','Ancienne livraison','{"prev_version": "0.9.0", "env": "prod"}','done','2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "deliveries" VALUES(2,'1.1.0','','{"prev_version": "1.0.0"}','in_progress','2026-10-20T16:22:35Z',NULL);
CREATE TABLE delivery_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id       INTEGER NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    template_task_id  INTEGER REFERENCES template_tasks(id) ON DELETE SET NULL,
    position          INTEGER NOT NULL DEFAULT 0,
    title             TEXT    NOT NULL,
    description       TEXT    NOT NULL DEFAULT '',
    command           TEXT    NOT NULL DEFAULT '',
    table_spec        TEXT    NOT NULL DEFAULT '',
    weight            INTEGER NOT NULL DEFAULT 1,
    estimated_minutes INTEGER NOT NULL DEFAULT 0,
    status            TEXT    NOT NULL DEFAULT 'todo', -- todo | running | paused | done | skipped
    elapsed_seconds   INTEGER NOT NULL DEFAULT 0,
    running_since     TEXT,
    started_at        TEXT,
    completed_at      TEXT
);
INSERT INTO "delivery_tasks" VALUES(1,1,1,0,'Mettre à jour le numéro de version','Mettre à jour le fichier de version et le changelog avant de créer la branche.','git checkout develop && git pull
echo "{{version}}" > VERSION
git commit -am "chore: bump version to {{version}}"','',2,10,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(2,1,2,1,'Créer la branche de release','La branche part de develop à jour.','git checkout -b release/{{version}}
git push -u origin release/{{version}}','',1,5,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(3,1,3,2,'Lancer la suite de tests','Tous les tests doivent passer. Joindre une capture du rapport en cas d''échec.','make test
make lint','',3,30,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(4,1,4,3,'Construire les artefacts','Build de l''image et du paquet pour la version.','docker build -t registry.local/app:{{version}} .
docker push registry.local/app:{{version}}','',3,20,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(5,1,5,4,'Tagger la version','Tag annoté, comparé à la version précédente {{prev_version}}.','git tag -a v{{version}} -m "Release {{version}}"
git push origin v{{version}}
git log --oneline v{{prev_version}}..v{{version}}','',1,5,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(6,1,6,5,'Déployer en recette','Vérifier les logs après déploiement.','./deploy.sh --env recette --version {{version}}','',3,25,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(7,1,7,6,'Rédiger les notes de version','Résumé des changements depuis {{prev_version}}, à envoyer à l''équipe.','','Élément | Lien
Notes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})
Tag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})
Comparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})',2,20,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(8,1,8,7,'Tâche ajoutée au modèle','','echo {{version}}','',2,5,'done',0,NULL,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(9,2,1,0,'Mettre à jour le numéro de version','Mettre à jour le fichier de version et le changelog avant de créer la branche.','git checkout develop && git pull
echo "{{version}}" > VERSION
git commit -am "chore: bump version to {{version}}"','',2,10,'running',0,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z',NULL);
INSERT INTO "delivery_tasks" VALUES(10,2,2,1,'Créer la branche de release','La branche part de develop à jour.','git checkout -b release/{{version}}
git push -u origin release/{{version}}','',1,5,'skipped',0,NULL,NULL,'2026-10-20T16:22:35Z');
INSERT INTO "delivery_tasks" VALUES(11,2,3,2,'Lancer la suite de tests','Tous les tests doivent passer. Joindre une capture du rapport en cas d''échec.','make test
make lint','',3,30,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(12,2,4,3,'Construire les artefacts','Build de l''image et du paquet pour la version.','docker build -t registry.local/app:{{version}} .
docker push registry.local/app:{{version}}','',3,20,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(13,2,5,4,'Tagger la version','Tag annoté, comparé à la version précédente {{prev_version}}.','git tag -a v{{version}} -m "Release {{version}}"
git push origin v{{version}}
git log --oneline v{{prev_version}}..v{{version}}','',1,5,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(14,2,6,5,'Déployer en recette','Vérifier les logs après déploiement.','./deploy.sh --env recette --version {{version}}','',3,25,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(15,2,7,6,'Rédiger les notes de version','Résumé des changements depuis {{prev_version}}, à envoyer à l''équipe.','','Élément | Lien
Notes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})
Tag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})
Comparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})',2,20,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(16,2,8,7,'Tâche ajoutée au modèle','','echo {{version}}','',2,5,'todo',0,NULL,NULL,NULL);
INSERT INTO "delivery_tasks" VALUES(17,2,NULL,8,'Tâche ad hoc','','','',1,3,'todo',0,NULL,NULL,NULL);
CREATE TABLE images (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_task_id INTEGER NOT NULL REFERENCES delivery_tasks(id) ON DELETE CASCADE,
    filename         TEXT NOT NULL,
    mime             TEXT NOT NULL,
    size             INTEGER NOT NULL,
    data             BLOB NOT NULL,
    created_at       TEXT NOT NULL
);
INSERT INTO "images" VALUES(1,1,'capture.png','image/png',71,X'89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D49444154789C6360F8CFC0F01F0005000201E2213BC90000000049454E44AE426082','2026-10-20T16:22:35Z');
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO "settings" VALUES('schema_version','2');
INSERT INTO "settings" VALUES('default_variables','{"prev_version": "", "env": "recette"}');
CREATE TABLE template_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    position          INTEGER NOT NULL DEFAULT 0,
    title             TEXT    NOT NULL,
    description       TEXT    NOT NULL DEFAULT '',
    command           TEXT    NOT NULL DEFAULT '',
    table_spec        TEXT    NOT NULL DEFAULT '',
    weight            INTEGER NOT NULL DEFAULT 1,
    estimated_minutes INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);
INSERT INTO "template_tasks" VALUES(1,0,'Mettre à jour le numéro de version','Mettre à jour le fichier de version et le changelog avant de créer la branche.','git checkout develop && git pull
echo "{{version}}" > VERSION
git commit -am "chore: bump version to {{version}}"','',2,10,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "template_tasks" VALUES(2,1,'Créer la branche de release','La branche part de develop à jour.','git checkout -b release/{{version}}
git push -u origin release/{{version}}','',1,5,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "template_tasks" VALUES(3,2,'Lancer la suite de tests','Tous les tests doivent passer. Joindre une capture du rapport en cas d''échec.','make test
make lint','',3,30,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "template_tasks" VALUES(4,3,'Construire les artefacts','Build de l''image et du paquet pour la version.','docker build -t registry.local/app:{{version}} .
docker push registry.local/app:{{version}}','',3,20,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "template_tasks" VALUES(5,4,'Tagger la version','Tag annoté, comparé à la version précédente {{prev_version}}.','git tag -a v{{version}} -m "Release {{version}}"
git push origin v{{version}}
git log --oneline v{{prev_version}}..v{{version}}','',1,5,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "template_tasks" VALUES(6,5,'Déployer en recette','Vérifier les logs après déploiement.','./deploy.sh --env recette --version {{version}}','',3,25,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "template_tasks" VALUES(7,6,'Rédiger les notes de version','Résumé des changements depuis {{prev_version}}, à envoyer à l''équipe.','','Élément | Lien
Notes de version {{version}} | [Wiki — release {{version}}](https://wiki.example.com/releases/{{version}})
Tag Git | [v{{version}}](https://git.example.com/app/-/tags/v{{version}})
Comparaison | [v{{prev_version}}...v{{version}}](https://git.example.com/app/-/compare/v{{prev_version}}...v{{version}})',2,20,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
INSERT INTO "template_tasks" VALUES(8,7,'Tâche ajoutée au modèle','','echo {{version}}','',2,5,'2026-10-20T16:22:35Z','2026-10-20T16:22:35Z');
CREATE INDEX idx_dtasks_delivery ON delivery_tasks(delivery_id);
CREATE INDEX idx_comments_task ON comments(delivery_task_id);
CREATE INDEX idx_images_task ON images(delivery_task_id);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('template_tasks',8);
INSERT INTO "sqlite_sequence" VALUES('deliveries',2);
INSERT INTO "sqlite_sequence" VALUES('delivery_tasks',17);
INSERT INTO "sqlite_sequence" VALUES('comments',1);
INSERT INTO "sqlite_sequence" VALUES('images',1);
COMMIT;
