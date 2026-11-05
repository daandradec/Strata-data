# Respaldo y recuperación segura

## Alcance

Este repo respalda código, lanzadores y notas seleccionadas, no toda la carpeta.
No incluye pesos, configuración externa, sesiones, autenticación o archivos
ignorados. GitHub solo conserva los commits que se hayan enviado correctamente.

| Estado de un archivo | Protección |
| --- | --- |
| Commit enviado a `origin/main` | Recuperable desde GitHub aunque se pierda el disco local. |
| Commit solo local | Recuperable mientras sobreviva `.git` o un bundle que lo incluya. |
| Cambios sin commit | No están respaldados por el remoto; guardarlos antes de reinstalar. |
| Archivo ignorado | No está protegido por este repo. Necesita respaldo independiente si importa. |

## Antes de actualizar o reinstalar

1. Revisar `git status --short`, `git diff` y `git ls-files --others --exclude-standard`.
2. Confirmar únicamente cambios revisados y ejecutar `git push`.
3. Comprobar que `git rev-parse HEAD` y `git rev-parse origin/main` coinciden en
   `main`, y consultar `git ls-remote origin refs/heads/main` para verificar el remoto.
4. Guardar por separado y de forma privada los ajustes locales que se quieran
   preservar: `E:\Strata\strata-iq3_xxs.json`, `E:\Strata\run-iq3_xxs.bat` y los
   ajustes/modelos de Gentle Shell bajo `$HOME\.gentle-shell\agent`. No publicar
   esos archivos ni copiar autenticación o sesiones a este repo.
5. No ejecutar limpiadores genéricos ni comandos como `git clean -fdx` en la
   carpeta de datos: también pueden eliminar archivos ignorados y modelos.

El instalador **actual auditado** usa `mkdir(exist_ok=True)` para el destino y migra
solo `models`, `packs` y `mtp`, conservando conflictos del destino. No es una
garantía para versiones futuras. `SETUP.bat` puede regenerar configuración y el
batch de arranque en `Strata`; el `.bak` de configuración no es un historial.
`install-iq3_xxs-local.py` es una migración específica que además reescribe
lanzadores y ajustes externos y contempla limpieza del modelo anterior: no es un
comando de reinstalación general.

## Copia adicional fuera de la carpeta de datos

Un bundle incluye el historial y las ramas de Git, pero no cambios sin commit ni
archivos ignorados. Usar un nombre nuevo evita sobrescribir un respaldo anterior:

```powershell
$backupRoot = 'E:\Strata-backups'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$bundle = Join-Path $backupRoot ('Strata-data-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.bundle')
git -C E:\Strata-data bundle create $bundle --all
git -C E:\Strata-data bundle verify $bundle
```

El bundle queda fuera de la carpeta que maneja el instalador, aunque no protege
contra la pérdida de toda la unidad E:. Mantener también el remoto o una copia en
otra unidad. Comprobar el código de salida de cada comando antes de continuar.

## Recuperar un archivo si todavía existe `.git`

Primero respaldar los cambios actuales del archivo: la restauración siguiente los
reemplaza. Comparar contra el remoto antes de decidir restaurar:

```powershell
git -C E:\Strata-data fetch origin
git -C E:\Strata-data diff origin/main -- start_web_strata.ps1
# Solo después de revisar y guardar cualquier cambio local que importe:
git -C E:\Strata-data restore --source=origin/main --worktree -- start_web_strata.ps1
```

Restaurar rutas concretas, no todo el árbol con `reset --hard`. Lo mismo aplica a
archivos de la extensión. Si se restaura la extensión, usar `/reload` en Gentle
Shell siguiendo su guía, sin editar paquetes instalados ni sesiones.

## Si se perdió `.git` o toda la carpeta

No clonar directamente sobre una carpeta de datos existente y no vacía. Recuperar
primero una copia separada en una ruta nueva:

```powershell
git clone https://github.com/daandradec/Strata-data.git "$HOME\Strata-data-recovery"
```

Si esa ruta ya existe, elegir otro nombre. Comparar los archivos antes de copiar
únicamente los lanzadores o la extensión que se necesite recuperar. No borrar ni
reemplazar `models`, `packs` o `mtp`; tampoco sobrescribir un `.git` existente con
el de otra copia. Si la carpeta destino ya tiene datos pero perdió `.git`, revisar
esa situación por separado antes de volver a asociarla al remoto.

En una máquina nueva sin carpeta previa, se puede clonar en la ubicación final y
después instalar Strata en el directorio hermano. Será necesario descargar o
restaurar los modelos y volver a integrar los ajustes externos por separado.
La [guía manual para otro computador](manual-installation.md#otro-computador-windows) indica la rama
correcta del fork (`strata-local-installation`), la disposición de carpetas y el
instalador normal que genera rutas/configuración específicas de la nueva máquina.

## Pruebas y límites de privacidad

El repositorio es público. No incluir claves, tokens, `.env`, archivos de
autenticación ni sesiones. Los controles automáticos detectan algunas firmas
conocidas y artefactos, no todos los posibles secretos. Revisar siempre
`git diff --cached` antes de publicar. No usar `git add -f` para eludir estas reglas.

La configuración local de Git y la protección de `main` en GitHub no se guardan
en los archivos de trabajo. Un clon nuevo configura su `origin` y seguimiento de
`main` automáticamente; para repetir las preferencias locales:

```powershell
git -C E:\Strata-data config --local pull.ff only
git -C E:\Strata-data config --local fetch.prune true
git -C E:\Strata-data config --local push.default simple
```
