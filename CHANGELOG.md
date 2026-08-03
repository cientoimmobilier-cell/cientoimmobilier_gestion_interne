# CHANGELOG — CIENTO IMMOBILIER

Toutes les modifications notables du projet sont documentées dans ce fichier.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [2026-08-02] — Remédiation Enterprise (sécurité, fiabilité, schéma)

Remédiation en 15 phases (audit → correction → tests). Toutes les corrections
sont couvertes par la suite de tests `python -m unittest discover -s tests -q`
(78 tests, OK).

### Correctif : planificateur de sauvegardes cloud
- `app/services/scheduler_service.py` : comparaison des échéances en UTC naïf
  (`next_run_at` est stocké dans une colonne TIMESTAMP sans fuseau). L'ancienne
  comparaison aware/naïve levait un `TypeError` qui désactivait silencieusement
  toutes les sauvegardes automatiques.
- `start()` efface désormais l'événement d'arrêt : un redémarrage du
  planificateur fonctionne.
- Les exceptions de `_loop` sont journalisées (`logger.exception`) et le
  rollback de session est assuré — le thread ne meurt plus silencieusement.

### Correctif : base de données et transactions
- `app/routes/transactions.py` : vérification **côté serveur** du statut
  « Disponible » avant création/modification d'une transaction (anti double
  réservation, y compris via requête POST forgée).
- `migrate_db.py` : synchronisation du schéma sans perte (colonnes, tables,
  index). Ajout des **index implicites** des colonnes `index=True`
  (`ix_<table>_<colonne>`) : 35 index de clés étrangères manquaient en base.
  La migration est désormais **idempotente** (dédoublonnage des candidats) et
  n'exige plus `python migrate_db.py` : le bureau la lance au démarrage.
- `migrate_db.py` : suppression de l'app Flask créée à l'import (aucun thread
  de planificateur parasite).

### Correctif : sauvegarde cloud Google Drive
- `app/services/backup_service.py` :
  - insertion de l'enregistrement dans `_run_backup` sous `try/except`
    (un échec marque la sauvegarde en échec au lieu de tuer le thread) ;
  - rétention : si la suppression Drive échoue, `drive_file_id` est **conservé**
    (plus de fichier orphelin invisible) et l'erreur est journalisée ;
  - ajout de `logging`/`logger` manquant (crash possible dans le gestionnaire
    d'échec de suppression) ;
  - restauration : base de données **avant** fichiers uploadés ; les uploads ne
    sont touchés que si le SQL est valide ;
  - `_restore_upload_files` : garde `realpath`+`normcase` contre l'échappement
    de chemin (zip-slip, y compris cible racine du système de fichiers) ;
  - `_validate_restore_sql` : neutralisation des commentaires-bloc
    (`DELETE/**/FROM`) avant l'application des motifs d'interdiction.
- `app/services/export_service.py` : `Decimal` sérialisé via `str()` (précision),
  dates UTC naïves dans les exports, horodatages des fichiers en UTC.

### Correctif : imports Excel
- `app/services/excel_service.py` : nouveau convertisseur tolérant `_to_number`
  (formats `1 500`, `1 500,50 €`, `1,5`, `None`, vide, invalide). Un import ne
  plante plus sur une cellule inhabituelle.

### Correctif : sécurité des uploads
- `app/utils/upload_security.py` : branchement réel de la config ClamAV
  (`CLAMAV_HOST/PORT/TIMEOUT`) dans les appels réseau ; nettoyage CR/LF des
  logs ; suppression d'une condition morte qui désactivait l'extension interdite.

### Correctif : bureau Windows (démarrage)
- `config.py` : en mode frozen, `BASE_DIR` = dossier du `.exe` (le `.env` et
  les uploads ne sont pas cherchés dans `_MEIPASS`). `UPLOAD_FOLDER` est rendu
  absolu. Rejet d'un `SECRET_KEY` placeholder.
- `CIENTO-IMMOBILIER.spec` : exclusion de `app/static/uploads/*` (photos,
  contrats, données personnelles) de l'exécutable ; `upx=False` (faux positifs
  antivirus).
- `app_desktop.py` : application Flask **unique** par lancement (l'ancien code
  en créait deux → double planificateur). Démarrage **bloqué** avec boîte de
  dialogue en cas d'erreur critique (PostgreSQL arrêté, `.env` absent).
  Synchronisation du schéma automatique avant de servir.
- `desktop/startup_checks.py` : la vérification du schéma ne crée plus d'app
  Flask (check psycopg2 léger).
- `desktop/port_manager.py` : repli de port **borné** (plage déterministe
  10500-10600 puis échec propre) — plus de boucle infinie `random`/`while`.
- `desktop/logger_config.py` : configuration de la journalisation **idempotente**
  (plus de handlers dupliqués ni de fichiers recréés).

### Correctif : interface web
- `app/static/js/main.js` : garde nul sur la sidebar dans le gestionnaire
  d'overlay (plus d'erreur JS quand la sidebar est absente).
- `app/templates/_pagination.html` : les liens de pagination **conservent les
  filtres** de l'URL courante (`?search=...&statut=...`), comme le sélecteur
  « lignes par page ».

### Correctif : build figé (exécutable)
- **Cause racine** : PyInstaller exécute le `.spec` avec un `sys.path` réduit
  qui n'inclut pas le répertoire du projet. Sans lui,
  `collect_all('app')`/`collect_data_files('app')` ne trouvent pas le package
  et retournent **silencieusement une liste vide**. Résultat : l'exécutable
  était généré **sans aucun template Jinja2, CSS ou JS** (écran de connexion en
  erreur 500 `TemplateNotFound`, interface inutilisable).
- `CIENTO-IMMOBILIER.spec` : `sys.path.insert(0, dossier_du_spec)` avant toute
  collecte (verrouillage via le dossier du `.spec`, pas le cwd), et ajout
  explicite et redondant de `app/templates` (défensif, dédoublonné par
  PyInstaller).
- Vérifié : `Analysis-00.toc`/`EXE-00.toc` contiennent désormais les 48
  templates + le static (`css`/`js`) et **toujours 0 uploads** (exclusion
  `app/static/uploads/*` conservée). Smoke test figé : `/health` 200,
  `/login` 200 (formulaire complet), `/static/...` servi, `error.log` vide.
- `desktop/startup_checks.py` : `_env_dir()` retourne `BASE_DIR` (dossier de
  l'exe) au lieu de `_MEIPASS` quand figé — cohérent avec `config.py`
  (`import sys` supprimé).

### Tests
- `tests/test_enterprise_fixes.py` (20 tests) : planificateur naïf/aware,
  bypass SQL par commentaires, zip-slip par chemins réels, `_to_number`,
  disponibilité serveur des transactions, rétention en cas d'échec Drive,
  repli de port borné, journalisation idempotente, migration idempotente,
  rejet du `SECRET_KEY` placeholder, `_env_dir()` = `BASE_DIR` quand figé.

### Base de données
- 35 index de clés étrangères créés sur `ciento_immobilier_db` (114 index au
  total) — amélioration des performances des jointures et de la recherche.
