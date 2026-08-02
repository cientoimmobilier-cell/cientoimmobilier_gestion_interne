# AUDIT COMPLET — SYSTÈME DE SAUVEGARDE GOOGLE DRIVE
## CIENTO IMMOBILIER

**Date de l'audit :** 02/08/2026
**Périmètre :** module « Sauvegarde Cloud Google Drive » + composants liés
**Méthode :** revue de code statique, exécution des tests existants (20/20 OK), simulations hors-ligne (Drive indisponible, dossier supprimé, refresh token), revue de l'historique Git.

---

## 1. ARCHITECTURE ACTUELLE (cartographie)

### Fichiers du module
| Rôle | Fichier | Rôle dans le système |
|---|---|---|
| Orchestrateur | `app/services/backup_service.py` | Export → ZIP → AES-256 → upload Drive → historique → rétention → restauration. Thread de fond + `ProgressStore` en mémoire. |
| API Google | `app/services/google_drive_service.py` | OAuth 2.0, arborescence `CIENTO-IMMOBILIER-BACKUPS/{Daily,Weekly,Monthly,Archive}`, upload/download/delete, quota. |
| Chiffrement | `app/services/crypto_service.py` | AES-256-GCM (PBKDF2-SHA256, 200 000 itérations) pour les archives + « enveloppe » des secrets via SECRET_KEY. |
| Exports | `app/services/export_service.py` | Rapports CSV/XLSX/PDF + dump SQL complet multi-dialecte (sqlite/postgres). |
| Planification | `app/services/scheduler_service.py` | Thread démon (30 s), fréquences hourly/daily/weekly/monthly, calcul `next_run_at`. |
| Routes | `app/routes/cloud_backup.py` | Blueprint `/parametres/sauvegarde-cloud`, réservé Administrateur/Directeur. |
| Templates | `app/templates/cloud_backup/*.html` (5) | index, backups, history, progress (polling AJAX), restore. |
| Modèles | `app/models/__init__.py:635-714` | `CloudBackupSetting`, `CloudBackupSchedule`, `CloudBackupRecord`. |
| Dépendances | `requirements.txt:18-22` | `cryptography`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`. |
| Tests | `tests/test_cloud_backup.py` | 14 tests (crypto, planification, exports, backup/restore avec Drive simulé, routes). |

### Variables d'environnement liées
Aucune variable d'environnement n'est nécessaire pour le module : les secrets Google (client_id, client_secret, token, refresh token, phrase de passe) sont **tous stockés chiffrés en base** dans `cloud_backup_settings`. Dépendances indirectes : `SECRET_KEY` (clé d'enveloppe) et `PREFERRED_URL_SCHEME`.

### Flux global
1. L'utilisateur saisit client_id/secret → chiffrés (`wrap_secret`) → base.
2. Connexion OAuth 2.0 (flow serveur, `drive.file`) → token + refresh token chiffrés → base.
3. Sauvegarde : exports (8 groupes × 3 formats) + `base_de_donnees.sql` + `INFORMATIONS.txt` → ZIP → chiffré AES-256-GCM → upload Drive.
4. Rétention : suppression des plus anciens fichiers par dossier.
5. Restauration : download → déchiffrement → extraction → exécution du script SQL (DROP/CREATE/INSERT/sequences).

---

## 2. FONCTIONNEMENT RÉEL DU SYSTÈME

**Ce qui fonctionne correctement (vérifié) :**
- ✅ Chiffrement AES-256-GCM : roundtrip, phrase erronée, fichier altéré → `CryptoError` (tests OK).
- ✅ Enveloppe des secrets : aucun secret Google en clair en base (`wrap_secret`/`unwrap_secret`, tests OK).
- ✅ Scope minimal `drive.file` (`google_drive_service.py:16`) — le plus restrictif pour des fichiers créés par l'app.
- ✅ Aucun mot de passe Google n'est demandé ni stocké (OAuth 2.0 uniquement).
- ✅ Sauvegarde manuelle en thread de fond, progression temps réel (vitesse, ETA), verrou anti-concurrence.
- ✅ Échec propre si Drive indisponible (simulé : `status=failed`, message clair).
- ✅ Dossier Drive supprimé → l'arborescence est recréée automatiquement (simulé : root + 4 sous-dossiers recréés, IDs recâchés).
- ✅ `state` OAuth vérifié (anti-CSRF), CSRF global, `role_required` sur toutes les routes, aucun token dans les logs.
- ✅ Dump SQL transactionnel (BEGIN/COMMIT), ordre topologique, `setval()` des séquences postgres.
- ✅ Tests existants : **20/20 passent** (sqlite en mémoire).
- ✅ Restauration protégée : confirmation + phrase de passe requises ; transaction unique (échec → rollback complet).
- ✅ Rétention : appliquée et testée.

---

## 3. BUGS DÉTECTÉS (avec causes exactes)

| # | Sévérité | Bug | Cause exacte | Impact |
|---|---|---|---|---|
| B1 | **CRITIQUE** | La **première connexion Google échoue par configuration par défaut** | `config.py:47` `SESSION_COOKIE_SAMESITE='Strict'`. Le cookie de session (qui porte `cloud_oauth_state`) n'est pas envoyé sur la redirection cross-site de Google → `cloud_backup.py:107` `session.pop('cloud_oauth_state')` = `None` → « état de session incorrect ». | OAuth impossible sans surcharger l'env. |
| B2 | **CRITIQUE** | URI de redirection invalide derrière un proxy TLS | Aucun `ProxyFix` (`app/__init__.py`). `url_for(_external=True)` (`cloud_backup.py:37-38`) renvoie `http://…` derrière Render/Vercel alors que Google exige la correspondance exacte `https://…`. | Connexion Google impossible en production cloud. |
| B3 | **CRITIQUE** | **Les documents, images et fichiers (uploads) ne sont JAMAIS sauvegardés** | `backup_service.py:144-174` n'écrit que les exports CSV/XLSX/PDF + SQL + INFORMATIONS. Aucune copie de `app/static/uploads/**` (photos, documents, contrats PDF, factures/recus PDF). | Perte de données en cas de sinistre : seules les références en base survivent, les fichiers sont perdus. |
| B4 | **CRITIQUE** | `SECRET_KEY` aléatoire à chaque démarrage si non définie | `config.py:9` `os.environ.get('SECRET_KEY') or os.urandom(32).hex()`. Si la variable manque (Vercel, machine sans .env), chaque redémarrage change la clé → tous les secrets enveloppés (token Google, client_secret, phrase de passe) deviennent illisibles (`unwrap_secret` → `CryptoError`). | Déconnexion silencieuse + reconfiguration forcée à chaque redémarrage. |
| B5 | **HAUTE** | **Progression/sauvegardes incohérentes avec plusieurs workers** | `render.yaml:12` `--workers 2`. `ProgressStore` et le verrou `_execution_lock` sont **en mémoire par processus** (`backup_service.py:88-89`). Deux workers = deux schedulers (lancé dans `create_app`) et deux magasins de progression ; le polling `/statut/<job>` peut tomber sur l'autre worker → « introuvable » ; deux sauvegardes planifiées simultanées possibles. | Fausse progression, doublons de sauvegardes. |
| B6 | **HAUTE** | `gunicorn run:app` est invalide | `render.yaml:12` référence `run:app` mais `run.py` ne définit **aucune variable `app`** au niveau module. | Le déploiement Render ne démarre pas (500/erreur d'import). |
| B7 | **MOYENNE** | Changement de phrase de passe → les sauvegardes existantes deviennent **indéchiffrables** | `cloud_backup.py:157-174` permet de remplacer la phrase sans vérifier l'ancienne et **sans aucun avertissement** ; les archives ne sont pas ré-chiffrées. | Si un admin modifie la phrase par erreur, toutes les archives passées sont perdues. |
| B8 | **MOYENNE** | Refresh token jamais révoqué à la déconnexion | `google_drive_service.py:108-111` `clear_credentials` ne fait pas d'appel `revoke` à Google. | Le refresh token reste actif côté Google (fuite potentielle si la base est compromise). |
| B9 | **MOYENNE** | Suppression de l'enregistrement même si le fichier Drive n'a pas pu être supprimé | `cloud_backup.py:384-392` : en cas d'exception Drive, le log est écrit mais `db.session.delete(record)` s'exécute quand même. | Fichier « orphelin » sur Drive, impossible à supprimer depuis l'UI ensuite. |
| B10 | **FAIBLE** | Fuite de détails internes dans les messages d'échec | `backup_service.py:229-237` stocke `str(exc)` brut dans `record.message` affiché dans l'UI. | Paths/noms internes visibles par les admins (acceptable) mais hors du niveau « message métier ». |
| B11 | **FAIBLE** | Concurrence backup/restore | Le verrou `_execution_lock` ne couvre pas la restauration (`restore_backup` sans lock). | Une restauration pendant une sauvegarde peut corrompre l'état. |

---

## 4. VULNÉRABILITÉS

| # | Sévérité | Description | Emplacement |
|---|---|---|---|
| V1 | **CRITIQUE** | **`.env` versionné dans Git** (contient `SECRET_KEY` réel 64 car. et `DB_PASSWORD` réel) | `git ls-files` → `.env` ; historique `28cda42`, `209650a`. `.gitignore:37` ignore `.env` mais le fichier a été ajouté AVANT. |
| V2 | **CRITIQUE** | **Archive de sauvegarde complète commitée dans Git** (`backups/ciento_backup_20260730_135512.zip`, 13,9 Mo, vérifiée) : contient `app/` (code source + `__pycache__`), **`.env`** et **un document utilisateur réel** (`Manuel de Pilotage…docx`). | `git ls-files backups`. Créée par `desktop/backup_manager.py:57-59` qui zippe `.env` en clair et `app/static/uploads`. |
| V3 | **MOYENNE** | **Zip-slip lors de la restauration** | `backup_service.py:285-287` `zf.extractall(tmpdir)` sans validation des membres (`../`). L'archive est chiffrée (atténue le risque), mais toute personne connaissant la phrase de passe peut déposer des fichiers hors du répertoire. |
| V4 | **MOYENNE** | Absence de PKCE | `google_drive_service.py:52-68` flow serveur classique. Acceptable car client confidentiel, mais PKCE est la pratique recommandée (notamment desktop). |
| V5 | **FAIBLE** | CSP `style-src 'unsafe-inline'` | `app/utils/security.py:26`. Atténué : nonces sur les scripts. |
| V6 | **FAIBLE** | Mot de passe admin par défaut codé en dur et affiché | `init_db.py:44-50` `AdminCiento123!` imprimé en console. À changer/forcer. |
| V7 | **FAIBLE** | `render.yaml` `generateValue: true` sur SECRET_KEY : correct, mais à confirmer que la valeur est stable (une rotation invalide les secrets enveloppés, cf. B4). | — |

---

## 5. PROBLÈMES DE SÉCURITÉ

- **Points forts :** aucun secret en clair en base ; archives chiffrées **avant** envoi (AES-256-GCM + PBKDF2 200k) ; scope `drive.file` minimal ; CSRF + `role_required` partout ; headers de sécurité + CSP ; aucun `credentials.json`/token dans le dépôt (recherche effectuée) ; `Session`/`Remember` cookies sécurisés en prod.
- **Faiblesses :** V1 et V2 (secrets et données réelles dans l'historique Git — priorité absolue, incluant la **rotation** des secrets exposés) ; B4 (SECRET_KEY non persistante) ; B8 (pas de révocation) ; V3 (zip-slip).

---

## 6. PROBLÈMES DE PERFORMANCE

| # | Sévérité | Problème | Cause |
|---|---|---|---|
| P1 | HAUTE | **Consommation mémoire élevée** : le ZIP complet est lu en RAM pour le chiffrement (`backup_service.py:186-187` `fh.read()`) puis, à la restauration, téléchargé + déchiffré en RAM (`backup_service.py:279-285`). | Pas de chiffrement/déchiffrement par flux. Risque OOM (plan gratuit Render ~512 Mo) pour de grosses bases. |
| P2 | MOYENNE | **Refresh OAuth à chaque opération** | `_store_credentials` (`google_drive_service.py:84-93`) ne persiste pas `expiry` ; `from_authorized_user_info` (google-auth 2.56.2) fixe alors `expiry` dans le passé → `expired=True` → `get_credentials()` déclenche un échange de token réseau **à chaque appel**. Vérifié dans la source de la lib. |
| P3 | MOYENNE | **Restauration synchrone et bloquante** dans la requête HTTP | `cloud_backup.py:363-373`. Aucune progression, aucun thread ; timeout possible (gunicorn 120 s / proxy). |
| P4 | FAIBLE | Dump SQL mono-bloc `cursor.execute(script)` (psycopg2) | Gros script = mémoire serveur + blocage du verrou de requête. |
| P5 | FAIBLE | `list_files` (`google_drive_service.py:200-214`) jamais utilisé | Code mort. |

**Tailles mesurées :** 10 fichiers d'upload = 6,6 Mo (projet actuel) ; archive de référence commitée = 13,9 Mo. Les exports CSV/XLSX/PDF par groupe sont générés en mémoire sans streaming.

---

## 7. PROBLÈMES DE RESTAURATION

| # | Sévérité | Problème |
|---|---|---|
| R1 | CRITIQUE | **La restauration ne restaure QUE la base de données** : les documents/photos/PDF (uploads) ne sont pas dans l'archive → après restauration, toutes les références `chemin_fichier` pointent vers des fichiers absents. |
| R2 | HAUTE | **Pas de mode maintenance** : DROP/CREATE/INSERT s'exécutent pendant que l'app continue de tourner (autres utilisateurs, scheduler) → 500 et incohérences pendant la fenêtre de restauration. |
| R3 | HAUTE | **Restauration partielle impossible** : tout ou rien, sans sélection de tables, sans « prévisualisation », sans restauration d'un seul fichier/document. |
| R4 | MOYENNE | Pas de progression ni d'annulation ; la page HTTP peut expirer. |
| R5 | MOYENNE | Pas de validation de la compatibilité du schéma : une archive d'une version antérieure (colonnes manquantes) échoue en cours d'exécution (rollback intégral heureusement). |
| R6 | FAIBLE | Zip-slip (V3) sur `extractall`. |

**Scénarios testés :** restauration complète (test OK), phrase erronée (test OK), sauvegarde corrompue/altérée (test OK — détecté par le tag GCM), Drive indisponible (simulé → échec propre), dossier supprimé (simulé → recréé). **Non testés :** token expiré en production, perte de connexion mi-upload, restauration partielle, gros fichier.

---

## 8. QUALITÉ DU CODE

**Points forts :**
- Bonne séparation des couches : services / blueprints / modèles / templates ; injection des dépendances dans `GoogleDriveService` (testable) ; orchestrateur indépendant.
- `ProgressStore` verrouillé, `_execution_lock` anti-doublon, `KEEP_JOB_AFTER_DONE` gère la purge mémoire.
- Docstrings claires en français, constantes nommées, `_human_size` propre.
- Tests unitaires pertinents (crypto, planning, exports, backup/restore, rétention, routes).

**Faiblesses :**
- Duplication : logique de sauvegarde ZIP dupliquée dans `desktop/backup_manager.py` (sans chiffrement, inclut `.env` — à supprimer/réaligner).
- Code mort : `list_files` (Drive), import `SAJSON` inutilisé (`export_service.py:19`).
- `_parse_include` / listes `include_data` gérées par chaînes CSV — fragile mais fonctionnel.
- Exceptions attrapées largement (`except Exception`) dans plusieurs routes avec rollback manuel — acceptable, à fiabiliser par des erreurs typées.
- `record.message` = exception brute (B10).

---

## 9. FONCTIONNALITÉS MANQUANTES

1. **Sauvegarde des fichiers uploads** (photos, documents, contrats, factures, recus, rapports) — le point le plus important.
2. **Annulation d'une sauvegarde** en cours (demande explicite de l'audit).
3. **Sélection/compte Google** : pas de sélecteur de compte, pas de ré-autorisation PKCE.
4. **Vérification de la phrase de passe** (test de déchiffrement d'une ancienne archive avant changement ; avertissement si des archives existent).
5. **Progression de la restauration** + exécution en arrière-plan.
6. **Pré-vérification du quota** Drive avant upload.
7. **Notification** (web ou desktop) à la fin de chaque sauvegarde (le desktop a `NotificationManager`, non branché au module).
8. **Chiffrement de l'en-tête `INFORMATIONS.txt`** (déjà couvert par l'archive, OK) — N/A.
9. **Test de connectivité Drive** (bouton « tester la connexion »).
10. **Journalisation structurée** du module (`logger` sous-utilisé dans `backup_service`).

---

## 10. RECOMMANDATIONS (par ordre de priorité)

1. **[CRITIQUE] Supprimer `.env` et l'archive `backups/ciento_backup_*.zip` de l'historique Git** (`git rm --cached`, `filter-repo`/BFG, purge de l'historique), puis **rotater SECRET_KEY, DB_PASSWORD** et tout secret exposé. Exclure `backups/`, `exports/`, `temp/` via `.gitignore`.
2. **[CRITIQUE] Inclure les uploads dans l'archive cloud** : copier `app/static/uploads/**` dans le dossier d'export avant ZIP (et dans la restauration).
3. **[CRITIQUE] Forcer SECRET_KEY stable** : lever une erreur au démarrage si absente (au lieu de `os.urandom`).
4. **[HAUTE] Réparer l'OAuth** : `SESSION_COOKIE_SAMESITE='Lax'` par défaut (ou `None`), ajouter `ProxyFix` pour l'URI de redirection, enregistrer `https://…/callback` dans Google.
5. **[HAUTE] Réparer le déploiement** : `render.yaml` → `gunicorn "app:create_app()"` ; un seul worker ou passer la progression/rétention en stockage partagé (Redis/DB) + verrou global (DB advisory lock).
6. **[HAUTE] Chiffrement par flux** (chunks) pour éviter la montée mémoire sur les grosses bases.
7. **[HAUTE] Restauration** : mode maintenance (flag global), exécution en thread avec progression, restauration sélective, validation de schéma, extraction sécurisée (rejeter `../`).
8. **[MOYENNE] Phrase de passe** : exiger l'ancienne phrase + avertir si des archives existent ; proposer le re-chiffrement.
9. **[MOYENNE] Révocation** du refresh token à la déconnexion (endpoint Google revoke).
10. **[MOYENNE] Persister `expiry`** dans `_store_credentials` pour ne rafraîchir qu'en cas réel d'expiration.
11. **[MOYENNE] Verrouiller la restauration** par le même `_execution_lock`.
12. **[FAIBLE] Ajouter les scénarios manquants en tests** : perte de connexion mi-upload, Drive indisponible, token expiré (mock 401 + refresh), dossier supprimé, gros fichier, restauration partielle, download.

---

## 11. TESTS — ÉTAT DES LIEUX

Exécution : `venv\Scripts\python.exe -m unittest discover -s tests` → **20/20 OK** (14 cloud + 6 app).

| Scénario demandé | Couvert ? | Verdict |
|---|---|---|
| Première connexion Google | Partiel | Flow mocké (routes), MAIS l'OAuth réel est cassé (B1/B2). |
| Renouvellement du Token | Non testé | Logique présente mais `expiry` non persisté (P2) → test à ajouter (mock 401 → refresh). |
| Sauvegarde locale | Oui | `test_backup_flow_and_restore` (fichiers générés). |
| Sauvegarde Google Drive | Oui (simulée) | FakeDrive. |
| Upload d'un gros fichier | Non | À ajouter (chunking resumable à valider > 1 Mo). |
| Téléchargement | Non | `download()` non testé (route + API). |
| Restauration | Oui (base seule) | `test_backup_flow_and_restore` (restaure la base). |
| Perte de connexion Internet | Non testé | Comportement vérifié manuellement → échec propre (simulation A). |
| Google Drive indisponible | Non testé | Vérifié manuellement (simulation A). |
| Token expiré | Non | À ajouter. |
| Dossier supprimé sur Google Drive | Non | Vérifié manuellement → recréé (simulation B). |

---

## 12. SCORES & VERDICT FINAL

| Critère | Note /100 | Commentaire |
|---|---|---|
| Fiabilité | **55** | Architecture saine et erreurs gérées, mais fichiers uploads non sauvegardés, OAuth cassé par défaut, progression volatile multi-workers. |
| Sécurité | **60** | Excellent chiffrement (AES-256-GCM) et scope minimal, mais `.env` + archive avec données réelles dans Git, SECRET_KEY instable, pas de révocation, zip-slip. |
| Performances | **50** | Mémoire élevée (chargement total en RAM), refresh OAuth à chaque opération, restauration synchrone. |
| Expérience utilisateur | **60** | Très bon suivi de progression/historique/rétention, mais pas d'annulation, pas de sélecteur de compte, restauration sans retour visuel. |
| Maintenabilité | **70** | Découpage clair, tests, docstrings ; duplication desktop, code mort, messages d'erreur bruts. |
| Préparation à la production | **40** | Déploiement cassé (`gunicorn run:app`), OAuth inopérant derrière proxy/TLS et en multi-workers. |

**Note globale pondérée : ~56/100**

### Verdict final : ❌ **NON PRÊT POUR LA PRODUCTION**

Le module est **bien conçu** (chiffrement de qualité, architecture propre, tests) mais il présente **deux défauts rédhibitoires** : (1) la **première connexion Google est inopérante** par configuration par défaut (SameSite Strict + absence de ProxyFix), et (2) les **documents/images/uploads ne sont pas sauvegardés**, rendant la restauration incomplète en cas de sinistre réel. S'y ajoutent des **secrets en clair dans l'historique Git** et un **déploiement Render invalide**.

Après application des corrections critiques (items 1–4 des recommandations), le système serait proche du niveau **⚠️ Prêt avec corrections mineures** puis **✅ utilisable en production**.
