# Portage macOS — kit bêta 1

Préparé le 20 novembre 2026 à partir du socle OpenInk 1.7.0.

## Livraison

L’archive est un **kit d’installation macOS**, contenant le code, les lanceurs
`.command`, la configuration PyInstaller et les dépendances précompilées pour
Python 3.14, séparément pour Intel `x86_64` et Apple Silicon `arm64`.
Elle ne contient pas de binaire OpenInk.app construit ou exécuté sur Mac.

`Lancer-OpenInk.command` prépare un environnement isolé et ouvre les sources.
`Installer-OpenInk.command` construit sur le Mac une application autonome et
la copie dans `~/Applications` si aucune application OpenInk n’y existe.
Une installation existante est conservée. Les outils en ligne de commande
Apple sont nécessaires pour la construction du .app.

## Intégration

- Barre de menus Cocoa via pystray, dans un processus avec boucle principale dédiée.
- Agent, verrous POSIX et sockets Unix dans un dossier privé au chemin court.
- Notifications AppleScript avec paramètres séparés du script.
- Autostart optionnel avec LaunchAgent utilisateur et arguments conservant les espaces.
- Base et journaux dans `~/Library/Application Support/inkora`.
- Géométrie NSScreen adaptée aux coordonnées Tk ; aperçu avec `/usr/bin/open`.
- Impression CUPS avec une copie A4 couleur, recto seul, et contrôle de la destination.
- libusb fourni dans le paquet et sélectionné sans altérer la bibliothèque USB tierce.
- OpenFlow : image V2 inchangée, sauvegarde et contrôles conservés, inhibition
  de veille par `caffeinate`, attente prudente et vérification complète.

## Validation effectuée sur Linux

- 117 tests du socle Linux réussis.
- 21 tests du portage macOS réussis avec commandes natives et matériel simulés.
- 30 vues contrôlées avec la branche macOS activée : cinq écrans, trois langues,
  deux thèmes et dialogue d’aide. Ces captures sont produites par Tk sous Linux,
  elles ne valident pas Aqua.
- Pour chaque architecture, compatibilité des wheels CPython 3.14/macOS 11,
  fermeture des dépendances avec les marqueurs Darwin, archives intactes et SHA-256.
  La liste d’installation est entièrement épinglée avec empreintes.
- Lanceurs shell vérifiés syntaxiquement ; construction native explicitement
  refusée sur un hôte non macOS. ZIP du kit vérifié fichier par fichier.

Aucune imprimante n’a été commandée, aucun travail papier ni transfert de
firmware n’a été lancé. La compilation/signature réelle, Aqua, la barre de
menus Cocoa, les permissions de notification, l’USB et l’impression restent
à valider sur un Mac. Le kit est donc une bêta de portage.

Le guide utilisateur est [macos/README.md](../macos/README.md).
