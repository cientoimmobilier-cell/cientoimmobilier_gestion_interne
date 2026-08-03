# RAPPORT D'AUDIT FINAL — MODULE DE SAUVEGARDE CIENTO IMMOBILIER
## CIENTO IMMOBILIER

**Date :** 03/08/2026
**Branche :** `fix/google-drive-backup-remediation`
**Références :** `RAPPORT_AUDIT_GOOGLE_DRIVE.md` (audit initial), `RAPPORT_REMEDIATION_GOOGLE_DRIVE.md` (première passe), `RAPPORT_ROTATION_SECRETS.md` (rotation des secrets).

---

## 1. OBJECTIF

Finaliser la sécurité du cycle de sauvegarde cloud Google Drive après la découverte
d'une archive locale non chiffrée (`backups/ciento_backup_20260730_135512.zip`)
contenant `.env` (SECRET_KEY, DB_PASSWORD, identifiants OAuth Google) et des
documents utilisateurs réels. Six étapes ont été exécutées, du nettoyage jusqu'à
la validation bout-en-bout sur une base PostgreSQL vierge.

---

## 2. RÉCAPITULATIF DES ÉTAPES

| Étape | Contenu | Résultat |
|---|---|---|
| 1 — Nettoyage | Suppression de l'archive compromettante, du `client_secret_*.json`, des dossiers `dist/` (contenait un `.env` avec l'ancienne SECRET_KEY) et `build/`, des `.pyc` orphelins ; `git rm --cached` des 6 documents/photos clients suivis dans Git ; `.gitignore` + `exports/`, `temp/`. | ✅ Commit `3e14e5e` |
| 2 — Rotation des secrets | Nouvelle `SECRET_KEY` (64 hex), nouveau `DB_PASSWORD` (24 caractères aléatoires), `ALTER USER postgres`, re-enveloppement de tous les secrets Google avec la nouvelle clé, suppression des artefacts compromis. | ✅ `RAPPORT_ROTATION_SECRETS.md` |
| 3 — Suppression de la dépendance circulaire | La phrase de passe de chiffrement n'est plus stockée dans le dump : les colonnes secrètes (`google_client_id_wrapped`, `google_client_secret_wrapped`, `token_encrypted`, `encryption_passphrase_wrapped`) sont émises `NULL` à l'export. | ✅ |
| 4 — Versionnage des archives | `manifest.json` embarqué dans l'archive chiffrée : signature `ciento-backup`, `format_version=2`, version logicielle, empreinte SHA-256 du schéma, liste des tables, checksum du dump SQL. La restauration **refuse** toute archive sans manifest, au format inconnu, au schéma incompatible, ou dont le checksum ne correspond pas. | ✅ |
| 5 — Validation réelle | Sauvegarde complète de la base de production (Drive simulé) → restauration sur une base PostgreSQL **vierge** → comparaison automatique : lignes et contenu par table (992 lignes, 33 tables), intégrité des 40 clés étrangères, uploads octet pour octet, manifest/checksum, absence de secrets dans l'archive. | ✅ **58/58 contrôles** |

---

## 3. BUG RÉEL DÉCOUVERT PAR LA VALIDATION (Étape 5)

La comparaison production ↔ restauré a mis en évidence un défaut de
`_reinject_cloud_secrets()` : lors d'une restauration sur une base sans
configuration locale (base vierge), l'**email du compte Google restauré depuis
l'archive était écrasé par `None`** (la machine n'avait rien à préserver).

**Correction** (`app/services/backup_service.py`) : l'email archivé n'est plus
écrasé lorsqu'aucun email local n'existe — seule une configuration locale
existante (restauration sur machine déjà configurée) continue de primer.

---

## 4. VALIDATION BOUT-EN-BOUT — RÉSULTATS (58/58)

Rejouable à tout moment :

```
python scripts/validate_backup_restore.py
```

- **Archive** : déchiffrement OK, manifest v2 valide (schéma + checksum),
  33 tables listées, aucun secret (phrase de passe, client_secret Google,
  jeton OAuth, SECRET_KEY, DB_PASSWORD) dans le contenu déchiffré ni dans le dump.
- **Restauration** sur base vierge `ciento_validation_<ts>` (créée puis
  supprimée) : script SQL appliqué en une transaction.
- **Données** : les 33 tables ont un contenu strictement identique (comparaison
  dans l'ordre des métadonnées, insensible à l'ordre physique des colonnes) :
  clients 175, demandes_clients 127, journal_activites 605, proprietaires 18,
  utilisateurs 14, etc.
- **Intégrité référentielle** : aucune ligne orpheline sur les 40 contraintes FK.
- **Uploads** : 10 fichiers restaurés, octet pour octet (SHA-256), aucun manquant
  ni inattendu.
- **Configuration cloud restaurée** : identifiants Google NULL (aucune clé dans
  l'archive), phrase de passe ré-injectée et déchiffrable avec la SECRET_KEY
  locale, email Google préservé (fix §3).

**Tests automatisés : 84/84 OK** (`python -m unittest discover -s tests`),
dont 43 sur le module cloud backup (manifest, redaction, refus d'archives
incompatibles, préservation de la configuration Google).

---

## 5. ÉTAT GIT

- `3e14e5e` — Securite: retirer les donnees client des archives, purger les fichiers sensibles
- `48daf0b` — Securite: sauvegardes versionnees (manifest v2), secrets jamais dans les archives, validation restauration sur base PostgreSQL vierge

Fichiers du cœur de la correction :
- `app/services/backup_manifest.py` (nouveau) — versionnage, checksums, refus d'incompatibilité.
- `app/services/backup_service.py` — manifest dans l'archive, écriture binaire du dump, restauration validée, préservation/ré-injection de la configuration, fix email.
- `app/services/export_service.py` — `SECRET_COLUMNS` + `export_sql(redact=True)`.
- `app/version.py` (nouveau) — source unique `CIENTO_VERSION`.
- `scripts/validate_backup_restore.py` (nouveau) — validation bout-en-bout rejouable.
- `tests/test_cloud_backup.py` — nouveaux tests manifest/redaction/restauration (43 tests module, 84 au total).

---

## 6. ACTIONS MANUELLES RESTANTES (hors code)

Ces actions ne peuvent pas être automatisées par script :

| Action | Détail | Risque si non réalisée |
|---|---|---|
| Rotation du client OAuth Google | Régénérer `client_id`/`client_secret` dans Google Cloud Console (le secret a transité dans l'archive), puis saisir les nouvelles valeurs dans Paramètres → Sauvegarde Cloud et reconnecter le compte. | Le secret OAuth historique reste valide si quiconque l'a récupéré. |
| Purge de l'historique GitHub | L'historique public du dépôt contient encore l'archive compromettante et les documents clients. Appliquer `git filter-repo` (cf. `RAPPORT_ROTATION_SECRETS.md`) puis force-push. | Données clients et secrets récupérables par toute personne ayant accès au dépôt. |
| Contrôle de la visibilité du dépôt | Vérifier que le dépôt est privé sur GitHub. | Exposition publique des données. |

---

## 7. POINTS D'ATTENTION / RECOMMANDATIONS

1. **Version du format** : incrémenter `BACKUP_FORMAT_VERSION` dans
   `app/services/backup_manifest.py` à chaque évolution incompatible de la
   structure d'archive. Les anciennes archives seront alors refusées
   proprement (message explicite) plutôt que mal restaurées.
2. **Harmonisation des versions** : `app/version.py` (`CIENTO_VERSION`) n'est pas
   encore utilisé par `desktop/app_desktop.py` (qui porte sa propre `APP_VERSION`).
   Unifier pour un affichage cohérent.
3. **Streaming du chiffrement** (recommandation P1 de la passe précédente) :
   le chiffrement/déchiffrement se fait en mémoire ; sur une très grosse base,
   un flux par chunks limiterait la consommation RAM (changement de format à
   planifier avec migration des archives).
4. **Multi-workers** (B5) : conserver `--workers 1` ou partager verrou et
   progression si passage à plusieurs workers.
5. **Sauvegarde de contrôle** : après toute évolution du schéma (ajout de
   table/colonne), rejouer `scripts/validate_backup_restore.py` — le manifest
   refuse automatiquement les archives hors schéma, ce script valide le cycle
   complet sur des données réelles.

---

## 8. VERDICT

**✅ MODULE DE SAUVEGARDE FINALISÉ ET VALIDÉ BOUT-EN-BOUT.**

- Les archives ne contiennent plus **aucune clé** (AES-256-GCM + redaction SQL +
  manifest versionné) ;
- la restauration est protégée contre les archives inconnues, corrompues ou
  hors schéma (manifest + checksum + validation du script SQL) ;
- le cycle complet a été prouvé sur une base PostgreSQL vierge avec les données
  de production : **zéro perte de données, zéro orphelin, uploads intacts** ;
- restent à l'équipe, hors code : rotation du client OAuth Google, purge de
  l'historique GitHub et contrôle de la visibilité du dépôt.
