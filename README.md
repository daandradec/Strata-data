# Strata-data

Personalizaciones y lanzadores para [tu fork de Strata](https://github.com/daandradec/Strata/tree/strata-local-installation).

## Otro computador (Windows)

1. Clona este repositorio en una carpeta nueva.
2. Abre **`install/Instalar.bat` con doble clic**.
3. Espera a que indique `Listo`.

Si prefieres PowerShell, desde la carpeta del repo ejecuta un solo comando:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install\Instalar-Strata.ps1
```

El script descarga tu fork en la carpeta hermana `Strata`, selecciona
`strata-local-installation`, instala lo necesario y configura IQ3_XXS con 128K de
contexto y puerto 38181. Si ya está preparado, lo reutiliza. El modelo **no se
inicia automáticamente**. Si detecta Gentle Shell, pregunta si quieres integrarlo
con respaldo de tus ajustes.

Necesitas Windows x64, Git, controlador compatible y hardware suficiente. El
perfil automático es conservador: al menos 60 GiB de RAM y GPU compatible de clase
20 GB o más; los pesos son aproximadamente 76 GB, más dependencias. No instala drivers ni fuerza
un equipo incompatible. [Detalles y opciones](install/README.md).

## Usar Strata

Desde esta carpeta, elige **uno** de los dos lanzadores:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_model_qwen.ps1
# O con interfaz web:
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_web_strata.ps1
```

Mantén abierta la consola que cargó el modelo. Los lanzadores no matan procesos ajenos.

## Datos y respaldo

Git guarda el código, los lanzadores y la extensión, **no** los modelos, cachés,
credenciales o sesiones. No borres una carpeta de datos existente para poder clonar.
GitHub Actions está deshabilitado; las pruebas se ejecutan solo localmente.

- [Instalador: seguridad, opciones y pruebas](install/README.md)
- [Instalación manual avanzada](docs/manual-installation.md#otro-computador-windows)
- [Respaldo y recuperación](docs/backup-and-restore.md)
- [Extensión de compactación](extensions/strata-compaction/README.md)
