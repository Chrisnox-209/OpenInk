# OpenInk Windows — bêta 1

Portage du socle 1.7.0 vers Windows 10/11 x64, préparé le 20 novembre 2026.

## Adaptations

- Exécutable portable avec Python 3.14.10, Tcl/Tk et dépendances inclus.
- Verrous natifs entre processus Windows et chemins dans LocalAppData.
- Agent et icône distincts de la fenêtre ; IPC loopback avec secret par session.
- Notifications de l’icône Windows et démarrage optionnel via HKCU Run.
- Moniteur actif et mise à l’échelle Windows ; textes adaptés à la plateforme.
- Lecture et assistant USB via le transport USBPRINT existant, sans modifier
  la bibliothèque tierce ni sa provenance.
- Files Windows, contrôle de destination et page de test via le pilote GDI,
  en une copie A4 couleur, recto seul.
- Journaux UTF-8, aperçu PDF et ouverture des sauvegardes avec Windows.
- Flash : inhibition de veille native, image V2 inchangée, sauvegarde et parcours
  de vérification complète après attente prudente. La détection rapide du
  redémarrage par sysfs reste réservée à Linux.

## Vérifications réalisées

- 117 tests Linux hors ligne réussis après adaptation du code commun.
- 23 tests du portage Windows réussis sous Wine avec Python Windows x64 :
  sélection USB, refus MFP-IPL et multi-appareils, verrous entre processus,
  authentification IPC, agent, autostart simulé et impression entièrement simulée.
- 30 vues graphiques vérifiées : cinq écrans × trois langues × deux thèmes,
  plus le dialogue d’aide. Captures inspectées sur un écran X11 virtuel.
- Exécutable compilé vérifié sous Wine : fenêtre Tk, ouverture unique, agent,
  icône, notification, fermeture de fenêtre conservant l’agent et arrêt explicite.
  La destination de suivi était uniquement 127.0.0.1.
- Archive portable : empreintes SHA-256 de chaque fichier et du ZIP.

Aucun transfert firmware, travail d’impression ni commande matérielle n’a été
effectué pour le portage. La recette matérielle sur Windows réel reste à faire :
USB normal, retour de veille, rendu papier avec le pilote Epson, notifications
dans la session Windows et parcours OpenFlow. La distribution est donc une bêta.

## Construction

Voir [windows/README.md](../windows/README.md). Les dépendances principales
sont épinglées dans `windows/requirements.txt`. Le constructeur sélectionne
uniquement l’application, ses ressources, les licences et son guide ; il
n’inclut ni base utilisateur, ni sauvegarde d’imprimante, ni diagnostic privé.
