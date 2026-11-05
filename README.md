# Strata-data: personalizaciones y respaldo

Repositorio de código y documentación para las personalizaciones locales de
[Strata](https://github.com/Niko1221/Strata). **No contiene los modelos ni es un
instalador de Strata.** Puede convivir con los datos descargados en la misma carpeta.

## Qué se respalda

| Ruta | Contenido |
| --- | --- |
| `start_model_qwen.ps1` | Arranque manual del modelo/API, sin abrir navegador. |
| `start_web_strata.ps1` | Abre/reutiliza Strata o inicia un servidor propio; incluye el rango de puerto alto. |
| `extensions/strata-compaction/` | Compactación acotada para Qwen Strata, pruebas y fragmento de ajustes. |
| `odd/tasks/` | Las tres notas de trabajo expresamente permitidas en `.gitignore`. |
| `docs/`, `tests/`, `.github/` | Recuperación, controles de Git y verificación automática. |

Se excluyen modelos (`models/`, `packs/`, `mtp/`), cachés, logs, índices CodeGraph,
pruebas temporales, dependencias y credenciales. El `.gitignore` bloquea rutas raíz
desconocidas y también secretos/artefactos dentro de los directorios permitidos.
No se necesita Git LFS para este respaldo.

## Uso local

La disposición actual es `E:\Strata` junto a `E:\Strata-data`. Los lanzadores buscan
el directorio hermano `Strata`; aceptan `-StrataRoot` si está en otro lugar.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File E:\Strata-data\start_model_qwen.ps1
# Alternativa con interfaz web:
powershell -NoProfile -ExecutionPolicy Bypass -File E:\Strata-data\start_web_strata.ps1
```

El puerto de la instalación actual es **38181**, el contexto es **131072** tokens
y los lanzadores leen el puerto del archivo de configuración de Strata. Clonar
este repo no descarga modelos, no modifica ajustes externos y no inicia servidores.
Para la extensión, consultar su [guía específica](extensions/strata-compaction/README.md):
el fragmento de ajustes se integra, nunca reemplaza el archivo completo de ajustes.

## Guardar cambios

`origin` apunta a <https://github.com/daandradec/Strata-data.git>; la rama principal es
`main`. El historial anterior de compactación se conserva.

```powershell
git -C E:\Strata-data status --short
git -C E:\Strata-data diff
# Agregar solo los archivos revisados; no usar git add -f para sortear exclusiones.
git -C E:\Strata-data add -- start_model_qwen.ps1 start_web_strata.ps1
git -C E:\Strata-data diff --cached
git -C E:\Strata-data commit -m "docs: describe the reviewed change"
git -C E:\Strata-data push
```

Las nuevas ramas de trabajo usan el prefijo `codex/`. Antes de publicar cualquier
archivo, revisar su contenido: un `.gitignore` no detecta todos los secretos y los
archivos ya versionados no dejan de estarlo por añadir una regla de exclusión.
La configuración local usa `pull.ff=only`, `fetch.prune=true` y `push.default=simple`;
no cambia la configuración global de Git.

## Verificación sin modelo

Requiere Git, Node **26** y, para las pruebas de lanzadores en Windows, Python 3.10+.
No hay dependencias npm que instalar para estas pruebas.

```powershell
node --test tests/repository.test.mjs extensions/strata-compaction/*.test.mjs
python -m unittest discover -s tests -p test_launchers.py -v
```

Los controles verifican la allowlist, archivos privados/generados, el índice de Git
y señales evidentes de tokens secretos. No sustituyen una revisión manual. Las
pruebas de lanzadores usan servidores HTTP simulados en puertos efímeros y raíces
temporales, nunca el modelo ni su configuración real.

GitHub Actions ejecuta las pruebas de Node en Linux y Windows y los controles de
lanzadores en Windows, sin secretos y con permiso de lectura. El test de recarga
con el cargador público de Pi queda **omitido** si no se proporciona
`STRATA_PI_ROOT`; una omisión no prueba la recarga. La guía de la extensión explica
cómo ejecutarlo contra la instalación local, sin leer sesiones ni credenciales.

## Antes de reinstalar

El instalador auditado reutiliza `Strata-data` y no elimina esta extensión ni su
`.git`. Sin embargo, una reconfiguración puede regenerar archivos en `Strata` y el
migrador IQ3_XXS puede reescribir los lanzadores de aquí. **Git permite recuperar
lo confirmado y publicado; no bloquea las escrituras del instalador.**

La versión vigente de los lanzadores queda en este repositorio. La copia histórica
en `E:\Strata\local-installation\launchers` no debe usarse como respaldo actual
del lanzador web: no incluía el ajuste de `MaxPort` para el puerto 38181.

Seguir la [guía de respaldo y recuperación](docs/backup-and-restore.md) antes de
reinstalar. Los ajustes externos de Gentle Shell y Strata requieren su propio
respaldo privado; no están incluidos en este repositorio público.
