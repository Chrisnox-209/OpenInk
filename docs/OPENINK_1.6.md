# OpenInk 1.6.0 : français, anglais et espagnol

Le README principal reste en français. `README.en.md` et `README.es.md`
présentent les mêmes fonctions et les mêmes limites. Les trois guides
expliquent dès leur introduction le rôle du flash OpenFlow pour les cartouches
compatibles rejetées et celui du suivi indicatif après installation.

Chaque guide contient des captures réelles de l’interface dans sa langue :
vue d’ensemble, réglages et OpenFlow. Les captures utilisent uniquement des
valeurs d’exemple et aucune donnée personnelle ou connexion matérielle.

## Programme

- Choix Français / English / Español / Automatique dans Réglages.
- Préférence persistante et mise à jour immédiate de la fenêtre.
- Options `--lang fr`, `--lang en` et `--lang es` pour le lancement.
- Traduction du panneau, des notifications, des diagnostics, des dialogues
  et des avertissements de flash.
- Page de test PDF dans la langue sélectionnée.
- Retrait du mode démonstration des options publiques et de la documentation.

Les profils et sélections des formulaires gardent leurs valeurs canoniques
internes. Les traductions n’altèrent ni les compteurs, ni les niveaux stockés,
ni les identifiants CUPS, ni les commandes matérielles. Les anciennes entrées
françaises du journal peuvent être traduites à l’affichage sans les réécrire.

## Vérification

Les 113 tests hors ligne passent. Ils contrôlent les catalogues et leurs paramètres, les préférences,
les valeurs internes des listes traduites, les avertissements et les ressources
PDF. Les cinq vues sont vérifiées dans les trois langues avec des données
isolées. Le panneau est testé dans les trois langues sur un bus D-Bus isolé.
Le rendu des neuf captures et des trois PDF est contrôlé visuellement.

Les fichiers du firmware et leur manifeste restent exactement ceux de 1.5.0.
Cette mise à jour logicielle n’exige pas de nouveau flash. Aucun flash ni
travail d’impression réel n’est envoyé pour sa préparation.

Le périmètre matériel et les limites d’estimation restent ceux décrits dans
[PERIMETRE_V2.md](PERIMETRE_V2.md).
