# OpenInk 1.5.0

## Icône du panneau et surveillance

Le démarrage automatique lance l’agent et l’icône, sans fenêtre Tk ni entrée de
fenêtre dans le dock. Le panneau expose l’état, les compteurs, l’ouverture de
l’application, l’actualisation et l’arrêt du suivi. Fermer la fenêtre laisse
ces deux processus actifs. Un nom D-Bus déterminé par la base évite de dupliquer
l’icône ; les verrous existants évitent de dupliquer l’agent et la fenêtre.

L’indicateur utilise Gio/GLib déjà requis par les notifications : aucune
dépendance GTK/AppIndicator supplémentaire. StatusNotifierItem et DBusMenu
sont exposés sur le bus de session. Le processus du panneau ne lit jamais
l’imprimante ; il consulte l’IPC local de l’agent. Les nettoyages et la
consommation non mesurable gardent les mêmes limites d’estimation.

## Interface et identité

La nouvelle goutte est symétrique avec un bas arrondi et les quatre bandes
CMJN. Elle remplace les icônes du menu, du dock, du panneau, de la fenêtre
et de la page de test. La barre latérale reste attachée au bord gauche,
même sur un écran large ; la taille minimale et les textes sont conservés.
La version affichée est 1.5.0.

Le firmware porte le nom **OpenFlow**. Son image et son manifeste épinglés
restent identiques à V2. Le changement de nom n’exige aucun flash. Un bandeau
rouge décrit le risque de blocage directement sur l’onglet. L’assistant place
l’avertissement avant les choix et conserve les confirmations de risques et
d’USB visibles dans son pied de fenêtre.

## Correction de la page de test

Le dialogue lit les états des files CUPS et évite de présélectionner une file
USB désactivée. Il interprète aussi les numéros de série USB encodés en hexadécimal.
Une file utilisable est choisie quand elle est identifiée ou seule disponible ;
une destination non identifiée demande toujours la confirmation de l’utilisateur.
Le bouton indique cette condition au lieu de laisser une erreur ambiguë.

Une nouvelle lecture d’état précède la soumission, en dehors du thread Tk.
L’identité est comparée avec celle affichée. Une seule copie est envoyée et le
bouton reste désactivé après acceptation. Le dialogue est défilant, avec les
actions et messages accessibles. Aucun travail existant n’est annulé.

## Validation

- 101 tests unitaires hors ligne : suivi, notifications, singleton de panneau,
  démarrage sans Tk, files désactivées et série USB hexadécimale.
- Contrôle graphique des cinq vues, absence de marge gauche, avertissement,
  confirmations et soumission d’une seule page simulée via le dialogue.
- Intégration D-Bus sur une session isolée : faux panneau, inscription réelle,
  propriétés, pixmap ARGB, menu, compteurs, activation et arrêt.
- Page A4 rendue et contrôlée visuellement après mise à jour du logo.
- Essai réel limité à une page : travail terminé dans CUPS, compteur couleur
  de 104 à 105, compteur monochrome inchangé et imprimante revenue prête.

La publication ne change pas l’image firmware et n’effectue aucun flash.
Les limites matérielles du contrôle ciblé restent celles décrites dans
[PERIMETRE_V2.md](PERIMETRE_V2.md).

## Références

- [StatusNotifierItem](https://specifications.freedesktop.org/status-notifier-item/latest/status-notifier-item.html).
- [CUPS : options d’impression](https://www.cups.org/doc/options.html).
