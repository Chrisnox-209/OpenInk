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

Pour les modifications d’interface, utiliser le contrôle en démo :

```bash
python3 linux/tests/check_interface.py
```

Les tests matériels ne doivent pas s’exécuter implicitement dans une suite de
tests. Les captures et fichiers construits restent ignorés par Git. Les tests
d’imprimante et les fixtures doivent utiliser une identité fictive.

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
