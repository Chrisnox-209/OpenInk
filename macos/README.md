# OpenInk pour macOS — kit bêta 1

> [!WARNING]
> **BÊTA NON TESTÉE sur un Mac.** Aucune compilation native ni exécution macOS n’a été réalisée. Ce kit ne contient pas de `.app` compilé. Le bon fonctionnement, l’USB, l’impression, les notifications et le flash ne sont pas garantis sur macOS.
> Voir [l’avertissement complet](../DISCLAIMER.md).

Ce kit porte OpenInk 1.7 sur macOS **11 ou plus récent**, Intel et Apple Silicon.
Il construit une application autonome **OpenInk.app sur votre Mac**, pour
l’architecture du Python utilisé. Cette archive est un kit d’installation,
pas une application déjà compilée. La compilation native et le fonctionnement
sur Mac n’ont pas pu être vérifiés depuis le poste Linux de préparation.

## Lancer OpenInk

1. Extraire tout le ZIP dans un dossier permanent et accessible en écriture.
2. Installer **Python 3.14 pour macOS** depuis la
   [page officielle Python](https://www.python.org/downloads/release/python-31410/).
   Le paquet macOS contient Tkinter et fonctionne sur Intel et Apple Silicon.
3. Dans le sous-dossier `macos`, ouvrir **Lancer-OpenInk.command**.
   Les dépendances Intel et Apple Silicon sont incluses dans le kit, avec leurs
   empreintes. Elles s’installent dans un environnement isolé à l’intérieur du kit.
   Depuis un clone du dépôt sans ces fichiers, elles sont téléchargées depuis PyPI.
4. L’application s’ouvre. Conserver le dossier du kit pour les prochains lancements.

## Produire une application autonome

Installer les **outils en ligne de commande Apple**, s’ils sont absents,
avec `xcode-select --install` dans Terminal. Ouvrir ensuite
**Installer-OpenInk.command** : les tests et la construction s’exécutent sur
le Mac. En cas de succès, OpenInk.app est copié dans **~/Applications** puis ouvert.

Aucun mot de passe administrateur n’est requis par OpenInk. L’installation
de Python peut demander une autorisation selon le programme d’installation.
Une application OpenInk déjà présente n’est pas remplacée : le Finder affiche
alors la nouvelle version dans `macos/dist/`.

L’application produite embarque Python, Cocoa, Pillow et libusb. Elle peut
ensuite être utilisée sans garder l’environnement de construction. Le dossier
`macos/dist/` contient aussi un ZIP de l’application et son empreinte SHA-256.
La signature est locale (« ad hoc ») ; cette bêta n’est pas notarisée par Apple.

**Arreter-OpenInk.command** arrête fenêtre, icône et
surveillance. Aucun lancement ou installation ne déclenche un flash.

## Connexion et fonctions

- Choisir Wi-Fi avec l’adresse IPv4 de l’Epson, ou USB, dans Réglages.
- L’USB utilise libusb, fourni par les dépendances. Aucune commande sudo ni
  désactivation des protections macOS n’est utilisée. Si le pilote Apple/Epson
  occupe l’interface USB, le réseau reste utilisable.
- La page de test utilise une file Epson configurée dans les réglages
  Imprimantes et scanners de macOS. Son aperçu s’ouvre dans Aperçu ou votre
  lecteur PDF. Une seule page A4 couleur, recto seul, est envoyée après clic.
- L’icône reste dans la barre de menus après fermeture de la fenêtre.
  Son menu permet d’ouvrir OpenInk, d’actualiser ou de quitter et arrêter le suivi.
- Les alertes utilisent les notifications AppleScript de macOS avec un titre
  OpenInk. Selon la version de macOS, l’autorisation se règle pour **Éditeur
  de scripts / Script Editor** dans Réglages système > Notifications.
- Le démarrage automatique est désactivé initialement. Son interrupteur crée
  un LaunchAgent utilisateur pour les prochaines connexions, sans arrêter
  le suivi en cours. Déplacer l’application exige de réactiver ce réglage.

Les thèmes clair/sombre, les langues français/anglais/espagnol, l’historique,
les profils et les exports JSON utilisent le même socle que Linux et Windows.

## Données

La base, les journaux et les sauvegardes restent locaux :
`~/Library/Application Support/inkora/`. Le verrou USB se trouve dans
`~/Library/Caches/inkora/` et les sockets de session dans un répertoire privé
`/tmp/openink-<uid>/`. Le LaunchAgent optionnel se trouve dans
`~/Library/LaunchAgents/io.github.Chrisnox209.OpenInk.plist`.

Pour désinstaller : désactiver le démarrage automatique, quitter OpenInk,
puis supprimer l’application. Les données et sauvegardes sont conservées.

## OpenFlow et validation

L’image V2 IU05P2 et ses empreintes restent inchangées. Le parcours conserve
les confirmations, le contrôle de l’identité, la sauvegarde complète et la
vérification. La veille est inhibée par `caffeinate`. La détection rapide du
redémarrage Linux est remplacée par l’attente prudente et le contrôle complet.

**Cette bêta n’a pas encore été validée sur un Mac ni sur une imprimante
connectée au Mac.** Le portage et ses tests simulés sont vérifiés sous Linux.
L’interface Aqua, la barre de menus, les permissions de notifications, le rendu
papier et l’accès USB nécessitent une recette réelle. Un flash peut bloquer
l’appareil ; conserver ses sauvegardes et ne jamais répéter un transfert incertain.

## Développement

```
python3.14 -m venv .venv-macos
.venv-macos/bin/python -m pip install --only-binary=:all: -r macos/requirements.txt
.venv-macos/bin/python -m unittest discover -s macos/tests -v
.venv-macos/bin/python macos/tests/check_macos_ui.py
.venv-macos/bin/python macos/build_macos.py
```

La construction doit être faite séparément pour `arm64` et `x86_64`.
Le kit refuse explicitement de produire un faux binaire macOS depuis Linux.
