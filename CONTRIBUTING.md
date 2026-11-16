# Contribuer à OpenInk Linux

## Périmètre

Ce dépôt contient seulement l’application Linux. Conserver les chemins de
données et l’alias `inkora` pour la migration. Ne pas ajouter de dépendance au
dossier de recherche d’origine, de données d’imprimante réelles, de sauvegarde
personnelle, d’exécutable de récupération ou de nouveau firmware expérimental.

Les fichiers `commun/inkora/firmware_assets/` sont épinglés par SHA-256. Une
modification de leur empreinte n’est pas une simple mise à jour de ressource.
Conserver l’acceptation explicite, USB obligatoire, la sauvegarde avant écriture,
les verrous partagés et l’absence de nouvelle programmation automatique.

## Vérifier une modification

Depuis la racine :

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning \
  python3 -m unittest discover -s linux/tests -v
python3 linux/build_deb.py
python3 linux/build_linux.py
git diff --check
```

Pour les modifications d’interface, utiliser les contrôles graphiques isolés :

```bash
python3 linux/tests/check_interface.py
python3 linux/tests/check_i18n.py
python3 linux/tests/check_appearance.py
dbus-run-session -- python3 linux/tests/check_tray.py
```

Les tests matériels ne doivent pas s’exécuter implicitement dans une suite de
tests. Les contrôles utilisent une base temporaire et une identité fictive.
Les captures de validation et fichiers construits restent ignorés par Git.
Seules les illustrations publiques de `docs/images/` sont versionnées.

Les catalogues `commun/inkora/locales/en.json` et `es.json` traduisent les
libellés français à l’affichage. Conserver les paramètres `{p0}`, `{p1}`, etc.
et les valeurs canoniques des formulaires : ne jamais traduire les identifiants
CUPS, les commandes matérielles ou les données persistantes. Le README par
défaut reste français ; maintenir les guides anglais et espagnol à jour.

Pour renouveler les illustrations des trois guides, sans accès matériel :

```bash
python3 linux/tests/capture_readme.py
```

La capture nécessite un affichage X11/XWayland et `xwd` (`x11-apps`). Elle lit
uniquement la fenêtre de test, pas le bureau. Vérifier visuellement les
images produites avant de les publier : trois vues claires et les réglages
sombres par langue, soit douze illustrations.

## Style des commits

Format extrait des fonctions `gchelp` de l’auteur :

```text
<emoji> <type>(<scope>): <message en français>
```

| Emoji | Type | Usage |
| --- | --- | --- |
| 🧩 | `feat` | Nouvelle fonctionnalité |
| 🐛 | `fix` | Correction de bug |
| 📝 | `docs` | Documentation |
| 🛠 | `tweak` | Ajustement ou renommage |
| 🔨 | `refactor` | Refactorisation |
| 💄 | `style` | Formatage |
| ➕ | `add` | Ajout de fichiers |
| 🚧 | `wip` | Travail en cours |
| 🔧 | `chore` | Maintenance |
| ✅ | `test` | Tests |
| ⚡ | `perf` | Performance |
| 👷 | `ci` | Intégration continue |
| ⏪ | `build` | Construction et artefacts |
| ❌ | `remove` | Suppression |
| 🎨 | `media` | Images et médias |
| ⚙️ | `config` | Configuration |
| ⬆️ | `upgrade` | Mise à niveau de dépendances |
| ⬇️ | `downgrade` | Retour de version |
| 🚑 | `hotfix` | Correctif urgent |
| 🔀 | `merge` | Fusion |

Exemples :

```text
🧩 feat(linux): ajoute OpenInk et le suivi local de l’encre
✅ test(core): couvre les alertes et les reprises du contrôleur V2
📝 docs(README): documente l’installation Ubuntu et les limites du suivi
```

Les fonctions `gcfeat`, `gcdocs`, etc. restent des outils locaux de terminal ;
elles ne sont pas nécessaires pour contribuer.
