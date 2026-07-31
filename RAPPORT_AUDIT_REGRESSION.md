# CIENTO IMMOBILIER — Audit complet de régression

**Date :** 30 juillet 2026
**Portée :** validation pré-production du logiciel de gestion immobilière (Python/Flask 3.0.2, SQLAlchemy 2.0, PostgreSQL 18, mode web + desktop).
**Méthode :** analyse statique + comparaison Git (commit `45f7f30` vs working copy) + exécution réelle de l'application contre la base `ciento_immobilier_db` + vérification schéma ORM/PostgreSQL + tests.
**Environnement :** Windows, Python 3.14.6, venv local, serveur `postgresql-x64-18`.

---

## Phase 1 — Analyse

### 1.1 Architecture

- **App factory** `app/__init__.py` : extensions `SQLAlchemy`, `Bcrypt`, `LoginManager`, `CSRFProtect` ; contexte global `ROLES` ; filtre Jinja `format_price` ; injection CSP nonce ; en-têtes de sécurité (CSP, HSTS, Cache-Control) ; gestionnaires d'erreurs 403/404/500 sans fuite d'information ; healthcheck `/health`.
- **12 blueprints** : `auth`, `dashboard`, `clients`, `owners`, `properties`, `transactions`, `settings`, `airbnb`, `agents`, `finance`, `partenaires`, `occupation`.
- **Modèles** : 30 tables définies dans `app/models/__init__.py`.
- **Services** : `excel_service.py` (exports/imports), `pdf_service.py` (fiches transaction/occupation/airbnb/paiement).
- **Sécurité** : CSP par nonces, validation d'upload par magic-bytes (`upload_security.py`), anti path-traversal (`safe_path_join`), anti injection LIKE (`sanitize_search`), anti open-redirect (`_is_safe_redirect_url`), rate-limiting login (5 tentatives / 5 min), contrôle d'accès par rôles (`role_required`, Administrateur/Directeur super-utilisateurs).
- **Entry points** : `run.py` (web / `--desktop` / `--headless`), `app_desktop.py` + `desktop/` (PyWebView), `init_db.py`, `migrate_db.py`.

### 1.2 Stack des dépendances (`requirements.txt`)

`Flask==3.0.2`, `Flask-SQLAlchemy==3.1.1`, `Flask-Login==0.6.3`, `Flask-Bcrypt==1.0.1`, `Flask-WTF==1.2.1`, `psycopg2-binary`, `python-dotenv`, `reportlab==4.1.0`, `openpyxl==3.1.2`, `gunicorn==21.2.0`.

---

## Phase 2 — Comparaison ancienne vs actuelle

Diff complet entre le commit **`45f7f30` (« Audit globale et update »)** et la **working copy** (modifications non commitées).

| Fichier | Changement | Nature | Régression ? |
|---|---|---|---|
| `app/__init__.py` | `inject_csp_nonce` : passe `generate_nonce` (référence de fonction) au lieu de `generate_nonce()` | Correctif : les templates appellent `{{ csp_nonce() }}` | Non |
| `app/models/__init__.py` | `index=True` sur `Occupant.occupation_id`, `RapportVisite.occupation_id`, `DocumentOccupation.occupation_id` | Perf / cohérence index | Non |
| `app/routes/agents.py` | `sanitize_search` sur la recherche d'agents | Sécurité (échappement `%`/`_`) | Non |
| `app/routes/partenaires.py` | `sanitize_search` sur la recherche de partenaires | Sécurité | Non |
| `app/routes/settings.py` | `sanitize_search` sur la recherche d'utilisateurs | Sécurité | Non |
| `app/routes/finance.py` | `sanitize_search` sur recettes/dépenses/caisse/banque/factures/reçus/budgets ; suppression import `abort` ; flash sans détails d'exception | Sécurité + hygiène | Non |
| `app/routes/airbnb.py` | `@role_required('Administrateur','Directeur')` sur `delete_reservation` | Sécurité (privilège) | Non |
| `app/routes/transactions.py` | Suppression import `update` inutilisé | Hygiène | Non |
| `app/templates/_pagination.html` | Sélecteur `per_page` réécrit en `URLSearchParams` | Correctif : query-string mal encodé | Non |
| `run.py` | Entry point réécrit : modes `--desktop`, `--headless`, `--port` | Nouvelle fonctionnalité | Non |

**Conclusion : aucun changement de comportement métier ; toutes les modifications sont des correctifs de sécurité/robustesse/UX. Aucune régression fonctionnelle introduite par la working copy.**

---

## Phase 3 — Dashboards

### 3.1 Méthode

Sweep automatique de toutes les routes GET via test client Flask (compte Directeur), avec les IDs réels de la base, puis vérification de la cohérence des compteurs par requêtes SQL indépendantes.

### 3.2 Résultats

**Toutes les pages et dashboards répondent HTTP 200 avec les données réelles** (aucun 500). Les 405 relevés correspondent aux routes POST-only appelées en GET (comportement attendu).

| Dashboard | Compteurs affichés | Vérification indépendante | Conforme |
|---|---|---|---|
| Principal `/` | biens 7, disponibles 7, clients 174, ventes mois 0, locations finalisées 0, Airbnb 2, agents actifs 10, réservations mois 0 | agrégats SQL recalculés | Oui |
| Finances `/finance/` | soldes banque/caisse, recettes/dépenses jour & mois (SUM SQL) | requêtes rejouées | Oui |
| Airbnb `/airbnb/` | biens 2, actifs, réservations mois (0 — les 4 réservations sont « En attente ») | requêtes rejouées | Oui |
| Occupation `/occupations/dashboard` | actives/terminées/entrées/sorties/taux d'occupation | table vide → zéros réels | Oui |
| Agents `/agents/` | transactions/visites/commissions par agent | agrégats rejoués | Oui |
| Transactions `/transactions/` | liste vide (0 transactions) | table vide | Oui |

Aucun faux compteur n'a été trouvé : chaque valeur provient d'une agrégation SQL sur les tables réelles.

---

## Phase 4 — Base de données

### 4.1 Inventaire

Base `ciento_immobilier_db` (PostgreSQL) — 30 tables, aucune table orpheline, aucune table manquante.

Compteurs réels : utilisateurs 13, clients 174, propriétaires 18, propriétés 7, visites 3, biens_airbnb 2, réservations_airbnb 4, mouvements_financiers 5, factures 1, reçus 1, comptes_bancaires 1, partenaires 2, journal_activites 575, demandes_clients 126, photos_proprietes 3, documents_proprietes 1, criteres_partenaires 1, caracteristiques 7.
Tables vides : transactions, commissions, contrats, paiements, caisses, occupations, occupants, rapports_visites, budgets, documents_occupations, documents_partenaires.

### 4.2 Colonnes

- `clients.numero_identite` (VARCHAR(50)) et `clients.type_piece` (VARCHAR(30)) : **présentes** (appliquées par `migrate_db.py`).
- `contrats.montant_loyer`, `depot_garantie`, `mode_paiement`, `frequence`, `statut` : **présentes**.
- Vérification automatisée modèle ↔ schéma : **0 colonne manquante, 0 colonne en trop**.

### 4.3 Index

**24 index définis dans les modèles étaient absents de la base** (la base avait été créée avant l'ajout de `index=True` dans les modèles, et `db.create_all()` ne modifie pas les tables existantes).

Liste corrigée : `utilisateurs(actif, role)`, `clients(email, nom, telephone)`, `proprietaires(telephone, email, nom)`, `proprietes(ville, type_bien, statut)`, `transactions(statut, type_transaction, date_transaction)`, `biens_airbnb(statut)`, `reservations_airbnb(statut, date_arrivee)`, `mouvements_financiers(type_mouvement, date_mouvement)`, `factures(date_emission, statut)`, `partenaires(telephone, nom, email)`.

### 4.4 Sauvegarde

`backups/ciento_backup_20260730_135512.zip` (13,9 Mo) — référence de l'état antérieur disponible pour comparaison.

---

## Phase 5 — SQLAlchemy

- Les **30 modèles** se chargent sans `MapperError` (ambiguïtés multi-FK levées).
- Relations multi-FK correctement désambiguïsées : `Caisse.responsable`, `Facture.client_facture`/`transaction_facture`, `Recu.client_recu`, `Occupation.agent` (`foreign_keys=[agent_id]`, backref `occupations_agent`).
- `joinedload` des dashboards (finance, transactions, airbnb) : exécution validée sans erreur sur données réelles.
- Relations dynamiques (`Client.occupations`, `Occupation.occupants`, etc.) et cascades (`all, delete-orphan`) cohérentes avec les FK `ondelete` de la base.
- Écarts ORM ↔ schéma **résolus** : après la Phase 8, synchronisation totale (0 table, 0 colonne, 0 index manquant).

---

## Phase 6 — Debug logs

- `logs/error.log` : dernières erreurs **2026-07-30 15:03–15:04**, toutes antérieures à la migration :
  - `UndefinedColumn: column clients.numero_identite does not exist` (dashboard `/`, user 1).
  - `UndefinedTable: relation "occupations" does not exist` (`/occupations/dashboard`).
  - → **Erreurs résolues** : colonnes et table désormais présentes.
- Dernier run (22:14, mode desktop) : `Database schema OK - 30 tables found` — **aucune erreur depuis la migration**.
- Avertissement non bloquant : notifications toast indisponibles — `cannot import name 'SetCurrentProcessExplicitAppUserModelID' from 'win32api'` (mismatch pywin32 / Python 3.14).
- Aucun log temporaire d'audit laissé dans le dépôt (scripts de contrôle isolés hors workspace).

---

## Phase 7 — Régression

- **Tests unitaires** (`tests/test_app.py`, unittest, SQLite in-memory) : **4/4 OK** (`python -m unittest discover tests`).
- **Sweep de routes** : toutes les routes GET des 12 blueprints → 200 ; les actions POST uniquement → 405 attendu ; pas de 500.
- **Comparaison ancien/actuel** : aucun changement métier, donc aucun périmètre de régression fonctionnelle introduit.
- **Session** : login/logout validés ; note — `SESSION_COOKIE_SECURE=True` par défaut : le cookie ne persiste pas sur HTTP hors `localhost` (toléré par Chromium/Edge sur `http://localhost`, d'où le fonctionnement du mode desktop).
- **Intégrité des écritures** : CRUD testé par ORM dans une transaction **annulée** (aucune donnée fictive créée) — INSERT/UPDATE/DELETE + rollback OK.

---

## Phase 8 — Correction (cause réelle uniquement)

**Un seul écart réel restant : le décalage d'index ORM ↔ schéma.**

`migrate_db.py` a été étendu d'une section de **synchronisation des index** (idempotente, `CREATE INDEX IF NOT EXISTS`, construite depuis les métadonnées SQLAlchemy) et exécuté :

```python
logger.info('\nCreation des index manquants (synchronisation des modeles)...')
with db.engine.connect() as conn:
    created = 0
    for table_name, table in db.metadata.tables.items():
        if table_name not in final_tables:
            continue
        existing_indexes = {ix['name'] for ix in inspector.get_indexes(table_name)}
        for index in table.indexes:
            index_name = index.name
            if index_name in existing_indexes:
                continue
            columns = ', '.join(c.name for c in index.columns)
            if not columns:
                continue
            sql = (
                f'CREATE INDEX IF NOT EXISTS {index_name} '
                f'ON {table_name} ({columns})'
            )
            conn.execute(text(sql))
            logger.info(f'  Index cree: {index_name} ON {table_name} ({columns})')
            created += 1
    conn.commit()
```

Résultat : **24 index créés** (« 24 index cree(s) avec succes »). Aucune donnée modifiée, aucune table recréée.

---

## Phase 9 — Validation

| Contrôle | Résultat |
|---|---|
| `python -m unittest discover tests` | 4/4 OK |
| 5 exports Excel (clients, propriétaires, propriétés, transactions, occupations) | HTTP 200, mimetype xlsx correct |
| Export PDF fiche Airbnb | HTTP 200, `application/pdf`, magic `%PDF` vérifié |
| CRUD ORM (transaction annulée) | OK, comptage client inchangé avant/après |
| Schéma ORM ↔ PostgreSQL (tables, colonnes, index) | 0 écart |
| Performance (EXPLAIN + mesures) | 0,30–0,82 ms / requête ; index disponibles pour la croissance |

### Performance avant / après

- **Avant** : les filtres sur les colonnes indexées (statut, type, date, nom, email…) forçaient des *seq scans* sans alternative ; coût négligeable aux volumes actuels (≤ 575 lignes) mais dégradation garantie à la montée en charge (surtout `journal_activites`, `mouvements_financiers`, `demandes_clients`).
- **Après** : 24 index présents ; le planificateur peut choisir des *index scans* ; mesures post-correction : `activités` 0,58 ms, `clients` 0,45 ms, `agents` 0,39 ms, `mouvements` 0,82 ms.

---

## Phase 10 — Rapport final

### 10.1 Bugs constatés et statut

| # | Bug | Gravité | Cause | Fichier(s) | Statut |
|---|---|---|---|---|---|
| 1 | `UndefinedColumn: clients.numero_identite` (dashboard en erreur) | Haute | Schéma antérieur sans colonnes `numero_identite`/`type_piece` | `app/models/__init__.py`, `migrate_db.py` | **Résolu** (colonnes ajoutées) |
| 2 | `UndefinedTable: occupations` (dashboard occupation en erreur) | Haute | Table absente de la base initiale | `migrate_db.py`, `init_db.py` | **Résolu** (table présente) |
| 3 | 24 index ORM manquants en base | Moyenne | Base créée avant l'ajout de `index=True` ; `create_all()` ne modifie pas les tables existantes | `app/models/__init__.py`, `migrate_db.py` | **Résolu** (index créés) |
| 4 | Injection LIKE (`%`/`_` non échappés dans les recherches) | Moyenne | Construction `%{search}%` brute | `finance.py`, `agents.py`, `partenaires.py`, `settings.py`, `transactions.py`, `occupation.py`, `airbnb.py` | **Résolu** (`sanitize_search`) |
| 5 | Nonce CSP incohérent (valeur vs fonction) | Moyenne | `csp_nonce` injecté comme résultat au lieu de la fonction | `app/__init__.py` | **Résolu** |
| 6 | Suppression de réservation Airbnb sans restriction de rôle | Moyenne | Absence de `role_required` | `app/routes/airbnb.py` | **Résolu** |
| 7 | Pagination : `per_page` corrompt la query-string (caractères encodés) | Basse | Concatenation brute de `request.query_string` | `app/templates/_pagination.html` | **Résolu** (`URLSearchParams`) |
| 8 | Flash divulguant le détail d'exception | Basse | `flash(f"...{e}")` | `app/routes/finance.py` | **Résolu** |

### 10.2 Risques restants (non corrigés, volontairement)

| # | Risque | Impact | Recommandation |
|---|---|---|---|
| 1 | Références générées par `count + 1` (`TX-`, `AIR-`, `OCC-`) : collision possible après suppression (contrainte `unique` → `IntegrityError`). | Faible (0 transaction/occupation à ce jour) | Passer à une séquence SQL ou `max(id)+1` verrouillée ; gérer le conflit par re-tentative |
| 2 | `Locations en cours` (dashboard) = `statut == 'Finalisée'` sans vérification `date_fin >= aujourd'hui`. | Faible (sémantique) | Ajouter le filtre de date de fin si « en cours » = location non expirée |
| 3 | `SESSION_COOKIE_SECURE=True` par défaut : session perdue sur HTTP hors `localhost`. | Moyen (contexte) | Forcer via variable d'environnement ; HTTPS en production |
| 4 | Uploads sans scan antivirus : `pyclamd` absent du requirements ; le chemin de détection essaie toujours le socket Unix sur Windows (fail-open). | Moyen | Installer ClamAV + pyclamd, ou un scanner compatible Windows ; au minimum scanner les PDF |
| 5 | Notifications toast desktop inopérantes (`win32api` / Python 3.14). | Faible | Mettre à jour `pywin32` ou remplacer par une implémentation compatible |
| 6 | Templates transactions supposent `client`/`propriete` non-null (FK `SET NULL`) | Faible | Affichage conditionnel si relation absente |
| 7 | Pas de tests automatisés sur auth (lockout/roles), exports, dashboards | Moyen | Compléter `tests/test_app.py` |
| 8 | Journal d'activités (575 lignes) non archivé/purgé | Faible | Archivage périodique |

### 10.3 Fichiers modifiés au cours de l'audit

- `migrate_db.py` — ajout de la section de synchronisation des index (modification **unique** apportée pendant l'audit).
- Les modifications préexistantes de la working copy (10 fichiers, cf. Phase 2) ont été conservées et validées.

### 10.4 Validation des dashboards

Tous les dashboards affichent des **agrégats SQL réels** (vérifiés indépendamment) et répondent **200**. Aucun faux compteur, aucune donnée fictive introduite, aucune modification du comportement métier.

### 10.5 Améliorations recommandées avant production

1. Adopter **Alembic** pour versionner le schéma (dossier `migrations/` actuellement vide).
2. Générer les références de documents via séquences PostgreSQL (suppression du pattern `count + 1`).
3. Automatiser les **backups** (planificateur) et tester une restauration.
4. Renforcer les **tests** (auth, rôles, exports, dashboards) et les intégrer à un pipeline CI.
5. Sécuriser la politique de mot de passe (le compte par défaut `admin@ciento.immo / AdminCiento123!` a été remplacé par `cientoimmobilier@gmail.com` — vérifier la rotation du mot de passe).
6. Vérifier `render.yaml` / `vercel.json` et l'utilisation de `gunicorn` en production.
7. Documenter le mode desktop et ses prérequis (`requirements-desktop.txt` : `pywebview`, `waitress`).
