# Composants et ressources embarqués

## epson-usb 0.1.2

Sources vendues dans `commun/inkora/_vendor/epson_usb/`.

- Projet : <https://pypi.org/project/epson-usb/0.1.2/>
- Licence : [MIT, texte intégral](commun/inkora/_vendor/epson_usb/LICENSE).
- Copyrights : Onur Kesim et Ircama, tels qu’indiqués dans la licence fournie.
- Origine et SHA-256 du wheel :
  [PROVENANCE.json](commun/inkora/_vendor/PROVENANCE.json).

L’ensemble embarqué conserve ses modules de transport d’origine, y compris
ceux spécifiques à d’autres plateformes. Cela ne constitue pas une version
Windows ou macOS d’OpenInk ; l’application et ses lanceurs ciblent Linux.

## Firmware V2 XP-2200

`commun/inkora/firmware_assets/xp2200-v2.bin.gz` est une charge historique
modifiée pour la XP-2200 IU05P2. Elle contient du code constructeur et n’est
pas couverte par la licence MIT de la bibliothèque USB. Les empreintes de
l’image et du manifeste sont décrites dans [le périmètre V2](docs/PERIMETRE_V2.md).
Ce dépôt privé n’accorde pas de droit supplémentaire sur ce code constructeur.

## Logo et page de test

Le logo CMJN distribué est un dessin vectoriel original généré par
`linux/build_brand_assets.py`. Aucune image de référence filigranée n’est
incluse dans le dépôt. Le PDF de test contient des polices Lato intégrées ;
le texte de licence correspondant est conservé dans
[docs/licenses/Lato-copyright](docs/licenses/Lato-copyright).

## Dépendances système

Python/Tk, Pillow, PyGObject, GLib, libusb, CUPS, systemd et les outils Ubuntu
restent fournis par le système, sous leurs licences respectives. ReportLab,
Poppler et Lato servent uniquement à régénérer les ressources. Les paquets
Python ou exécutables système ne sont pas vendus dans ce dépôt.

Epson est une marque de ses titulaires. OpenInk est un projet indépendant.
