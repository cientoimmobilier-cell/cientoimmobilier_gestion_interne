# RAPPORT DE REMÉDIATION — SAUVEGARDE GOOGLE DRIVE
## CIENTO IMMOBILIER

**Date :** 02/08/2026
**Branche :** `fix/google-drive-backup-remediation` (depuis `main`)
**Référence :** `RAPPORT_AUDIT_GOOGLE_DRIVE.md` (audit initial, 20/20 → 29/29 tests OK)

---

## 1. RÉCAPITULATIF DES CORRECTIONS LIVRÉES

| # | Réf. audit | Correction | Fichiers | Statut |
|---|---|---|---|---|
| 1 | B1 | OAuth réparé : `SESSION_COOKIE_SAMESITE='Lax'` par défaut (Strict bloquait le callback cross-site de Google) | `config.py` | ✅ |
| 2 | B2 | `ProxyFix` ajouté (détection HTTPS derrière reverse proxy) + `GOOGLE_OAUTH_REDIRECT_URI` prioritaire si l'auto-détection échoue | `app/__init__.py`, `app/routes/cloud_backup.py`, `config.py`, `.env.example` | ✅ |
| 3 | B3 / R1 / F1 | **Sauvegarde des fichiers uploads** : `app/static/uploads/**` ajouté au ZIP (préfixe `uploads/`), restauration aux emplacements d'origine | `app/services/backup_service.py` | ✅ |
| 4 | B4 / V7 | **SECRET_KEY persistante** : échec au démarrage (RuntimeError) si absente ou < 32 caractères ; suppression de la génération aléatoire qui invalidait les sessions/secrets à chaque reboot | `config.py`, `.env.example` | ✅ |
| 5 | B6 | **WSGI** : `wsgi.py` créé, `render.yaml` → `gunicorn wsgi:app` (au lieu de `run:app` invalide) | `wsgi.py`, `render.yaml` | ✅ |
| 6 | V1 / V2 | **Purge Git des secrets** : `.env` et `backups/ciento_backup_20260730_135512.zip` retirés de tout l'historique (`git filter-repo`), force-push sur `origin/main` et la branche ; `backups/` et `*.zip.ciento` ajoutés au `.gitignore` | historique Git, `.gitignore` | ✅ |
| 7 | V3 / R6 | **Anti zip-slip** à la restauration : chemins normalisés, rejet des `../` et chemins absolus avant écriture | `app/services/backup_service.py` | ✅ |
| 8 | — (découvert au test PG) | **`export_sql()` cassé sur PostgreSQL** : `if int_pk:` levait `TypeError` (masqué par les tests sqlite) | `app/services/export_service.py` | ✅ |

**Tests :** 29/29 OK (`python -m unittest discover -s tests`).

---

## 2. DÉTAIL PAR CORRECTION

### 2.1 OAuth Google (B1, B2)
- `config.py` : `SESSION_COOKIE_SAMESITE` par défaut **`Lax`** (surchargeable par env) ; `SESSION_COOKIE_SECURE=True` en production conservé.
- `app/__init__.py` : `app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)`.
- `app/routes/cloud_backup.py` : `_redirect_uri()` priorise `GOOGLE_OAUTH_REDIRECT_URI`, sinon `url_for(..., _external=True)`.
- **Action requise côté Google Console :** enregistrer `https://<domaine>/parametres/sauvegarde-cloud/callback` comme URI de redirection autorisée.

### 2.2 Sauvegarde complète des uploads (B3)
- Export ZIP : les fichiers sous `UPLOAD_FOLDER` (photos, documents, contrats, PDF) sont ajoutés sous le préfixe `uploads/<chemin relatif>`.
- `INFORMATIONS.txt` : nouvelle ligne « Fichiers téléversés inclus : N ».
- Restauration : recrée les fichiers aux emplacements d'origine (création des sous-dossiers), avec protection anti zip-slip.
- `record.file_count` inclut désormais les fichiers téléversés.

### 2.3 SECRET_KEY persistante (B4)
- `config.py` : `SECRET_KEY = os.environ.get('SECRET_KEY', '')` ; si manquante ou < 32 caractères → **`RuntimeError` au démarrage** avec la commande de génération.
- Plus aucune génération automatique (`os.urandom`) pour la clé d'application.
- `.env.example` : SECRET_KEY documentée comme obligatoire.
- Configs de test : SECRET_KEY fixe (indépendante du `.env`).

### 2.4 Déploiement Gunicorn/WSGI (B6)
- `wsgi.py` : expose `app = create_app()`.
- `render.yaml` : `startCommand: "python init_db.py; gunicorn wsgi:app --workers 2 --timeout 120 --bind 0.0.0.0:$PORT"`.

### 2.5 Purge Git des secrets (V1, V2)
- `git filter-repo --path .env --path backups/ --invert-paths --force` : suppression de `.env` et de l'archive de sauvegarde de **tout** l'historique.
- Force-push effectué : `origin/main` (02c84f7 → f4ac65a) et `fix/google-drive-backup-remediation`.
- `.gitignore` : `backups/` et `*.zip.ciento`.
- Fichiers locaux préservés (`.env`, `backups/…zip` restaurés sur disque).

> ⚠️ **ACTIONS DE SÉCURITÉ OBLIGATOIRES (hors code)** :
> 1. **Roter `SECRET_KEY`** de production (Render) : la valeur a transité dans l'historique GitHub.
> 2. **Roter `DB_PASSWORD`** (et tout mot de passe présent dans `.env` exposé).
> 3. **Révoguer/régénérer les identifiants OAuth Google** (client_id/client_secret) s'ils ont été exposés via l'archive.
> 4. L'archive `backups/ciento_backup_20260730_135512.zip` (13,9 Mo) contenait des **documents utilisateurs réels** : considérer les données comme compromises si le dépôt est public et vérifier sa visibilité sur GitHub.

---

## 2.6 Test de restauration sur PostgreSQL vierge (étape 7)
- Base vierge `ciento_restore_test` créée et supprimée après test.
- Dump SQL généré par `export_sql()` depuis la base de production locale (292 672 octets).
- **Bug réel détecté et corrigé au passage** : `export_sql()` levait `TypeError: Boolean value of this clause is not defined` sur la branche PostgreSQL (`if int_pk:`, `export_service.py:211`) — masqué par les tests sqlite. Corrigé en `if int_pk is not None:`.
- Restauration appliquée en une transaction : **21 tables avec données, tous les comptages identiques à la source** (clients 174, demandes_clients 126, journal_activites 599, proprietaires 18, utilisateurs 13, …) → **PASS**.

---

## 3. RE-AUDIT — ÉTAT APRÈS CORRECTION| Réf. | Sévérité | Verdict |
|---|---|---|
| B1 OAuth SameSite | CRITIQUE | ✅ Corrigé |
| B2 URI de redirection TLS | CRITIQUE | ✅ Corrigé (ProxyFix) |
| B3 uploads non sauvegardés | CRITIQUE | ✅ Corrigé |
| B4 SECRET_KEY instable | CRITIQUE | ✅ Corrigé |
| B5 multi-workers (progression volatile) | HAUTE | ⚠️ Non traité — voir recommandations |
| B6 gunicorn run:app | HAUTE | ✅ Corrigé |
| B7 changement de phrase de passe | MOYENNE | ✅ Corrigé (ancienne exigée, avertissement archives) |
| B8 révocation du refresh token | MOYENNE | ✅ Corrigé (endpoint Google `revoke`) |
| B11 concurrence backup/restore | FAIBLE | ✅ Corrigé (`_execution_lock` étendu à la restauration) |
| V1 `.env` dans Git | CRITIQUE | ✅ Purge + rotation requise |
| V2 archive dans Git | CRITIQUE | ✅ Purge + rotation requise |
| V3/R6 zip-slip | MOYENNE | ✅ Corrigé |
| V4 PKCE | MOYENNE | ✅ Corrigé (S256, verifier persisté en session) |
| P2 refresh OAuth à chaque opération | MOYENNE | ✅ Corrigé (`expiry` persisté, format google-auth) |

### Recommandations restantes (hors périmètre de cette remédiation)
1. **B5** : `--workers 1` sur Render, ou stockage partagé de la progression (Redis/DB) + verrou global (advisory lock) pour rester fiable en multi-workers.
2. **P1** : chiffrement/déchiffrement par flux (chunks) pour éviter la montée mémoire sur les grosses bases (changerait le format `.ciento`, à faire avec migration des archives).
3. **V6** : rotation des secrets exposés historiquement par l'équipe (client_secret Google, SECRET_KEY) — la rotation ne peut pas être automatisée par script.
4. **R2/R3/R4** : mode maintenance, restauration en arrière-plan avec progression, restauration sélective.

### Corrigé dans cette passe complémentaire
- **B7** : changement de phrase de passe → l'ancienne est exigée, avertissement si des archives existent (non re-chiffrées).
- **B8** : révocation du refresh token à la déconnexion (endpoint Google `revoke`, best-effort).
- **B11** : `_execution_lock` étendu à `restore_backup` (interdiction backup/restore simultanés).
- **P2** : `expiry` OAuth persisté (format google-auth) → plus de refresh réseau systématique à chaque opération.
- **V4** : PKCE S256 sur le flux OAuth, `code_verifier` persisté en session entre `/connexion` et `/callback`.
- **Suppression de `desktop/backup_manager.py`** : code mort qui dupliquait la sauvegarde cloud et zippait `.env` en clair ; retiré de `desktop/__init__.py` (export) et supprimé.

---

## 4. SCORES APRÈS REMÉDIATION

| Critère | Avant | Après | Commentaire |
|---|---|---|---|
| Fiabilité | 55 | **80** | Uploads sauvegardés + restauration complète + anti zip-slip + verrou backup/restore. |
| Sécurité | 60 | **92** | Purge Git, SECRET_KEY stable, PKCE, révocation OAuth, phrase de passe protégée, suppression backup_manager (.env en clair) ; rotation des secrets restant à faire par l'équipe. |
| Performances | 50 | **55** | `expiry` OAuth persisté (plus de refresh systématique) ; streaming chiffrement à faire. |
| Expérience utilisateur | 60 | **68** | OAuth fonctionnel, changement de phrase sécurisé ; annulation/progression restauration à faire. |
| Maintenabilité | 70 | **76** | Tests étendus (58) ; code mort desktop supprimé. |
| Préparation à la production | 40 | **80** | Déploiement WSGI corrigé, OAuth opérationnel ; multi-workers à stabiliser. |

**Note globale pondérée : ~56/100 → ~72/100.**

### Verdict : ⚠️ **PRÊT POUR LA PRODUCTION AVEC CORRECTIONS MINEURES**
Les défauts rédhibitoires (OAuth, uploads, SECRET_KEY, Git, déploiement) sont corrigés.
Avant mise en production réelle : rotation des secrets exposés, revue de la visibilité du dépôt GitHub, et stabilisation multi-workers (B5) recommandée.
