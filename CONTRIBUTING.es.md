# Contribuir a OpenInk Linux

[Français](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md) · **Español**

## Alcance

Este repositorio contiene únicamente la aplicación Linux. Conserva las rutas
de datos y el alias `inkora` para mantener la compatibilidad de migración.
No añadas dependencias del directorio de investigación original, datos reales
de impresoras, copias personales, ejecutables de recuperación ni nuevo firmware
experimental.

Los archivos de `commun/inkora/firmware_assets/` están fijados mediante SHA-256.
Cambiar sus huellas no es una simple actualización de recursos. Conserva la
aceptación expresa, la conexión USB obligatoria, la copia previa a la escritura,
los bloqueos compartidos y que el firmware no vuelva a programarse automáticamente.

## Verificar un cambio

Desde la raíz del repositorio:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning \
  python3 -m unittest discover -s linux/tests -v
python3 linux/build_deb.py
python3 linux/build_linux.py
git diff --check
```

Para cambios de interfaz, ejecuta las comprobaciones gráficas aisladas:

```bash
python3 linux/tests/check_interface.py
python3 linux/tests/check_i18n.py
python3 linux/tests/check_appearance.py
dbus-run-session -- python3 linux/tests/check_tray.py
```

Las pruebas de hardware no deben ejecutarse de forma implícita dentro de una
batería de pruebas. Las comprobaciones utilizan una base temporal y una identidad
de impresora ficticia. Las capturas de validación y los archivos generados se
mantienen ignorados por Git. Solo se versionan las ilustraciones públicas de
`docs/images/`.

Los catálogos `commun/inkora/locales/en.json` y `es.json` traducen las etiquetas
francesas al mostrarlas. Conserva los parámetros `{p0}`, `{p1}`, etc., y los
valores canónicos de los formularios: nunca traduzcas identificadores CUPS,
comandos de hardware ni datos persistentes. El README predeterminado sigue
en francés; mantén al día las guías inglesa y española. Actualiza también las
tres versiones de esta guía de contribución cuando cambie una regla.

Para regenerar las ilustraciones de las tres guías sin acceder al hardware:

```bash
python3 linux/tests/capture_readme.py
```

La captura requiere una pantalla X11/XWayland y `xwd` (`x11-apps`). El script
lee únicamente la ventana de prueba, no el escritorio. Revisa visualmente
las imágenes antes de publicarlas: tres vistas claras y los ajustes oscuros
por idioma, doce ilustraciones en total.

## Estilo de los commits

El formato sigue las funciones de terminal `gchelp` del autor:

```text
<emoji> <type>(<scope>): <mensaje en francés>
```

| Emoji | Tipo | Uso |
| --- | --- | --- |
| 🧩 | `feat` | Nueva función |
| 🐛 | `fix` | Corrección de errores |
| 📝 | `docs` | Documentación |
| 🛠 | `tweak` | Ajuste o cambio de nombre |
| 🔨 | `refactor` | Refactorización |
| 💄 | `style` | Formato |
| ➕ | `add` | Incorporación de archivos |
| 🚧 | `wip` | Trabajo en curso |
| 🔧 | `chore` | Mantenimiento |
| ✅ | `test` | Pruebas |
| ⚡ | `perf` | Rendimiento |
| 👷 | `ci` | Integración continua |
| ⏪ | `build` | Construcción y artefactos |
| ❌ | `remove` | Eliminación |
| 🎨 | `media` | Imágenes y medios |
| ⚙️ | `config` | Configuración |
| ⬆️ | `upgrade` | Actualización de dependencias |
| ⬇️ | `downgrade` | Reversión de dependencias |
| 🚑 | `hotfix` | Corrección urgente |
| 🔀 | `merge` | Fusión |

Los ejemplos conservan los mensajes de commit en francés del proyecto:

```text
🧩 feat(linux): ajoute OpenInk et le suivi local de l’encre
✅ test(core): couvre les alertes et les reprises du contrôleur V2
📝 docs(README): documente l’installation Ubuntu et les limites du suivi
```

Las funciones `gcfeat`, `gcdocs`, etc., son herramientas locales de terminal;
no son necesarias para contribuir.
