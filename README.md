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
| `docs/`, `tests/` | Recuperación, controles de Git y pruebas locales. |

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

## Otro computador (Windows)

Sí: ambos repositorios pueden vivir como carpetas hermanas bajo **cualquier ruta**,
sin usar necesariamente la unidad E:. Los lanzadores incluidos son para Windows;
en Linux se necesita el arranque nativo de Strata, no estos scripts Win32.

Para reproducir las personalizaciones actuales, usar la rama
**`strata-local-installation` del fork Strata**, no su `main`. Esa rama está
publicada y contiene los ajustes locales; `Strata-data` usa `main`.

Ejemplo para una carpeta nueva; no clonar encima de destinos existentes no vacíos:

```powershell
$base = Join-Path $HOME 'Strata-local'
New-Item -ItemType Directory -Path $base -Force | Out-Null
git clone --branch strata-local-installation https://github.com/daandradec/Strata.git "$base\Strata"
git clone https://github.com/daandradec/Strata-data.git "$base\Strata-data"
```

**Clonar respalda código, no instala el modelo ni el entorno Python/engine.**
Si el nuevo equipo tiene hardware suficiente para IQ3_XXS y contexto 128K, preparar
la instalación con el instalador normal del fork, sin arrancar el modelo:

```powershell
& "$base\Strata\START-HERE.bat" --setup --family qwen --model IQ3_XXS --context 131072 --port 38181 --data-dir "$base\Strata-data" --no-browser --no-start
```

El instalador debe generar `.venv`, `strata-iq3_xxs.json` y `run-iq3_xxs.bat` con
las rutas y el hardware de esa máquina, y descargar o reutilizar los pesos.
No copiar la `.venv` ni los JSON/batches generados de otro computador: contienen
rutas y decisiones de hardware locales. Tampoco usar el migrador histórico
`install-iq3_xxs-local.py`, que contiene rutas específicas del equipo original.
Si se instala otro modelo, estos dos lanzadores IQ3_XXS no lo seleccionan: usar el
arranque nativo correspondiente o adaptar los lanzadores de forma explícita.

Después, el arranque sigue siendo manual:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$base\Strata-data\start_model_qwen.ps1"
# O bien, con interfaz web:
powershell -NoProfile -ExecutionPolicy Bypass -File "$base\Strata-data\start_web_strata.ps1"
```

Si también se usa Gentle Shell, instalarlo/configurarlo por separado: registrar el
proveedor en `http://127.0.0.1:38181/v1` y el modelo
`strata/qwen3.8-flash-next-iq3_xxs`, con contexto 131072. Al integrar
`settings.fragment.json`, reemplazar su ruta de ejemplo `E:/Strata-data/...` por
la **ruta absoluta real de la extensión en el nuevo equipo**, sin reemplazar los
demás ajustes. La autenticación y las sesiones no viajan en este repo.

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

Las pruebas se ejecutan **solo localmente**. Este repositorio no usa workflows de
GitHub Actions y Actions está deshabilitado en sus ajustes remotos. La protección
de `main` no exige CI ni revisiones de PR. El test de recarga con el cargador
público de Pi queda **omitido** si no se proporciona
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
