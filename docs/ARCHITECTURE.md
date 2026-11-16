# Architecture Linux

## Couches

- `ui.py`, `dialogs.py`, `branding.py` : fenêtre Tkinter, mise à l’échelle,
  jauges et identité graphique.
- `printer.py`, `usb.py`, `diagnostics.py` : lectures d’état, transports et
  interprétation des erreurs signalées par couleur.
- `store.py` : SQLite, observations, profils, consommation, réserve et alertes.
- `agent.py`, `service.py`, `notifications.py` : processus de session, singleton,
  IPC local et notifications natives.
- `tray.py` : indicateur StatusNotifierItem et menu DBusMenu, distinct de Tk et
  du lecteur matériel ; il ouvre l’application ou affiche les compteurs de l’agent.
- `printing.py`, `print_ui.py` : choix de file CUPS, validation, aperçu et envoi
  explicite d’une seule page PDF.
- `firmware.py`, `firmware_usb.py`, `flash_worker.py`, `firmware_ui.py` : image
  épinglée, journal privé, verrous USB, contrôleur et interface de l’opération.
- `_vendor/epson_usb/` : transport bas niveau tiers avec licence conservée.

## Flux normal

L’agent lit les compteurs, enregistre une observation, estime la consommation
depuis les déclarations de cartouche et déclenche les alertes persistantes.
La fenêtre consulte les données et permet une actualisation ou une calibration
explicite. Le remplissage local ne correspond à aucune écriture de puce.

L’envoi d’une page de test passe par CUPS, et sa consommation sera prise en
compte par les compteurs normaux. Le programme n’ajoute pas une déduction
manuelle supplémentaire.

## Exclusivité matérielle

Lecteurs et contrôleur firmware partagent un verrou. Pendant une opération
firmware, les lectures normales et la page de test sont suspendues. Le journal
conserve les étapes de sauvegarde, transfert, commit et vérification.
Une réponse incertaine n’entraîne jamais une répétition du commit.

## Construction autonome

`linux/build_deb.py` vérifie les ressources puis assemble le paquet dans un
répertoire temporaire. Il n’installe rien, n’ouvre pas le périphérique et
produit un `.deb` avec SHA-256 dans `linux/dist/`.

`linux/build_linux.py` archive seulement les fichiers applicatifs, la
documentation et les tests explicitement sélectionnés. Une table des empreintes
est intégrée dans `BUILD_INFO.json`. Aucun chemin du dossier de diagnostic
historique n’est nécessaire pour ces deux constructions.

`linux/build_brand_assets.py` peut régénérer les icônes et le PDF avec ReportLab,
Pillow, Poppler et Lato. Les ressources déjà incluses suffisent à utiliser et
construire l’application.
