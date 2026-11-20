# OpenInk 1.7.0 — Windows, bêta 1

> [!WARNING]
> **BÊTA NON TESTÉE sur un vrai PC Windows.** Vérifications logicielles sous Wine/Linux uniquement. Le bon fonctionnement, l’USB, l’impression, les notifications natives et le flash ne sont pas garantis sur Windows.
> Voir [l’avertissement complet](../DISCLAIMER.md).

Version portable pour Windows 10/11 **64 bits (Intel/AMD)**. Python et les
dépendances sont inclus dans l’archive compilée ; aucune installation Python
ni droit administrateur n’est nécessaire pour la lancer.

## Lancer

1. Extraire entièrement l’archive ZIP dans un dossier permanent.
2. Ouvrir le dossier OpenInk, puis double-cliquer sur **OpenInk.exe**.
3. Dans Réglages, choisir Wi-Fi (adresse IPv4 de l’Epson) ou USB.
4. Initialiser les couleurs dans Cartouches avec leur niveau réellement estimé.

Ne pas lancer l’application directement dans le ZIP. Conserver le dossier
`_internal` à côté de l’exécutable. Le programme est fourni sans signature
numérique ; Windows peut donc signaler un éditeur inconnu.

Le pilote Epson XP-2200 doit être installé pour l’USB et la page de test.
L’accès USB utilise le pilote Windows existant (USBPRINT), sans remplacement
par WinUSB/Zadig. Une seule XP-2200 doit être branchée. Les lectures USB sont
différées lorsqu’une file d’impression est occupée ou inaccessible.

## Suivi et notifications

Les thèmes clair/sombre, les trois langues, l’historique, les estimations et
les exports sont conservés. L’icône OpenInk apparaît près de l’horloge ;
Windows peut la ranger dans les icônes masquées. Fermer la fenêtre conserve
l’agent et les alertes. Le menu de l’icône propose **Quitter et arrêter le suivi**.
`Arreter-OpenInk.cmd` permet également de les arrêter.

Le démarrage à la connexion est **désactivé initialement**. L’interrupteur
dans Réglages l’active pour cet utilisateur Windows. Déplacer le dossier
après l’activation exige de désactiver puis réactiver l’interrupteur.
Les notifications suivent les réglages de Windows et de Ne pas déranger.

Les données sont locales, dans `%LOCALAPPDATA%\inkora\` : base SQLite,
`agent.log`, `launcher.log`, communication de session et sauvegardes firmware.
Supprimer le dossier de l’application ne supprime pas ces données. Désactiver
le lancement automatique et arrêter OpenInk avant de supprimer son dossier.

## Page de test

La page est envoyée au spouleur Windows via le pilote Epson, en A4 portrait,
couleur, recto seul et une seule copie. Choisir explicitement la file Epson
et confirmer sa destination. L’aperçu PDF s’ouvre dans le lecteur Windows.
Une acceptation par le spouleur ne prouve pas la sortie papier.

## OpenFlow

L’image V2 historique et ses empreintes restent identiques. L’assistant conserve
les confirmations, le contrôle IU05P2, la sauvegarde complète et la vérification.
Sur Windows, la vérification suit le parcours prudent avec attente jusqu’à
15 minutes et contrôle complet : la détection rapide du redémarrage USB Linux
n’est pas utilisée. L’ordinateur est maintenu éveillé durant l’opération.

**Cette bêta n’a pas été validée sur une imprimante sous Windows réel.**
Le démarrage et les tests logiciels sont vérifiés sous Wine. L’USB, l’impression
papier, les notifications dans une vraie session Windows et le flash nécessitent
encore une recette sur Windows avec la XP-2200. Un flash peut bloquer l’appareil.
Conserver une sauvegarde, ne pas débrancher et ne pas relancer un transfert
incertain. Aucune opération matérielle ne part au simple lancement.

Les niveaux Epson à 100 % sous OpenFlow sont simulés ; OpenInk estime l’encre
à partir des pages et du niveau déclaré. Il ne mesure pas le volume physique.

## Depuis les sources / reconstruire

Depuis la racine OpenInk, avec Python Windows 3.14 64 bits et Tkinter :

```
py -3.14 -m pip install -r windows\requirements.txt
py -3.14 windows\openink_windows.py
py -3.14 -m unittest discover -s windows\tests -v
py -3.14 windows\build_windows.py
```

Les binaires et leur SHA-256 sont générés dans `windows/dist/`.
Le constructeur n’ouvre aucune imprimante et n’inclut aucune donnée privée.
