# Strata-data: personalizaciones y respaldo

Repositorio de código y documentación para las personalizaciones locales de
[Strata](https://github.com/Niko1221/Strata). **No contiene los modelos ni es un
instalador de Strata.** Puede convivir con los datos descargados en la misma carpeta.

**Instalación en un equipo nuevo:** seguir la
[guía paso a paso de clonación e instalación](#otro-computador-windows).

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

### 1. Preparar una ubicación nueva

Requisitos: Git instalado, Windows con PowerShell, conexión para las descargas y
hardware/espacio suficientes para IQ3_XXS con contexto 128K. El instalador prepara
el entorno privado de Python y el engine; no se copian desde otro computador.

Abrir PowerShell y comprobar que Git está disponible:

```powershell
git --version
```

El ejemplo usa una carpeta dentro del usuario actual. Se puede cambiar `$base`
por otra ruta absoluta. Usar la misma consola para los bloques siguientes; si se
abre una consola nueva, volver a definir `$base`.

```powershell
$base = Join-Path $HOME 'Strata-local'
New-Item -ItemType Directory -Path $base -Force | Out-Null

# Detenerse antes de clonar si alguno de los destinos ya existe.
foreach ($destino in @("$base\Strata", "$base\Strata-data")) {
    if (Test-Path -LiteralPath $destino) {
        throw "El destino ya existe: $destino. No clonar encima ni borrar sus datos."
    }
}
```

Si Strata ya generó una carpeta de datos, no borrarla para poder clonar. Consultar
la [guía de recuperación](docs/backup-and-restore.md) antes de continuar.

### 2. Clonar los dos repositorios y las ramas correctas

Primero clonar ambos repositorios; **después** ejecutar el instalador. Así
`Strata-data` ya es un repositorio Git cuando Strata empieza a guardar sus datos.

```powershell
git clone --branch strata-local-installation https://github.com/daandradec/Strata.git "$base\Strata"
if ($LASTEXITCODE -ne 0) { throw 'No se pudo clonar el fork Strata.' }

git clone --branch main https://github.com/daandradec/Strata-data.git "$base\Strata-data"
if ($LASTEXITCODE -ne 0) { throw 'No se pudo clonar Strata-data.' }
```

`--branch strata-local-installation` selecciona las personalizaciones del fork;
clonar solamente su `main` no reproduce esta instalación. El segundo comando
recupera los lanzadores vigentes y la extensión, no los pesos del modelo.

Comprobar las ramas:

```powershell
git -C "$base\Strata" branch --show-current
# Esperado: strata-local-installation
git -C "$base\Strata-data" branch --show-current
# Esperado: main
```

La disposición final debe ser:

```text
Strata-local/
  Strata/        <- fork, instalador, engine y configuración de la máquina
  Strata-data/   <- este repo, lanzadores, extensión y datos locales ignorados
```

**Clonar respalda código, no instala el modelo ni el entorno Python/engine.**

### 3. Instalar IQ3_XXS sin arrancarlo automáticamente

Solo si el equipo es adecuado para ese modelo/contexto, ejecutar el instalador
normal del fork. Se usa `--setup` explícitamente para generar configuración con
las rutas y el hardware nuevos, en lugar de arrancar con archivos heredados:

```powershell
& "$base\Strata\START-HERE.bat" --setup --family qwen --model IQ3_XXS `
    --context 131072 --port 38181 --host 127.0.0.1 `
    --data-dir "$base\Strata-data" --no-browser --no-start
if ($LASTEXITCODE -ne 0) { throw 'La instalación no terminó correctamente. Revisar el error antes de arrancar.' }
```

| Opción | Para qué sirve |
| --- | --- |
| `--setup` | Reconfigura/instala para la máquina actual. |
| `--family qwen --model IQ3_XXS` | Elige el modelo que esperan estos lanzadores. |
| `--context 131072` | Configura 128K de contexto. |
| `--port 38181` | Mantiene el puerto dedicado usado por esta integración. |
| `--host 127.0.0.1` | Limita el servidor al propio computador. |
| `--data-dir` | Guarda los pesos y paquetes junto a este repo, aunque hubiera otra ruta recordada. |
| `--no-browser --no-start` | Instala sin abrir navegador ni cargar el modelo al terminar. |

Seguir las indicaciones del instalador y esperar a que finalice sin errores.
El instalador debe generar `.venv`, `strata-iq3_xxs.json` y `run-iq3_xxs.bat` con
las rutas y el hardware de esa máquina, y descargar o reutilizar los pesos.

Comprobar que existen los archivos básicos; las tres respuestas deben ser `True`:

```powershell
Test-Path -LiteralPath "$base\Strata\.venv\Scripts\python.exe"
Test-Path -LiteralPath "$base\Strata\strata-iq3_xxs.json"
Test-Path -LiteralPath "$base\Strata\run-iq3_xxs.bat"
```

No copiar la `.venv` ni los JSON/batches generados de otro computador: contienen
rutas y decisiones de hardware locales. Tampoco usar el migrador histórico
`install-iq3_xxs-local.py`, que contiene rutas específicas del equipo original.
Si se instala otro modelo, estos dos lanzadores IQ3_XXS no lo seleccionan: usar el
arranque nativo correspondiente o adaptar los lanzadores de forma explícita.

### 4. Arrancar manualmente

Elegir **una** de estas opciones, no ambas para cargar dos servidores:

```powershell
# Modelo/API sin navegador:
powershell -NoProfile -ExecutionPolicy Bypass -File "$base\Strata-data\start_model_qwen.ps1"
```

O bien:

```powershell
# Modelo con interfaz web; puede reutilizar un Strata compatible ya activo:
powershell -NoProfile -ExecutionPolicy Bypass -File "$base\Strata-data\start_web_strata.ps1"
```

Mantener abierta la consola que cargó el modelo y esperar el mensaje `Listo`.
Cerrar esa consola o usar Ctrl+C detiene el servidor que ella inició. Si el
lanzador web reutilizó un servidor existente, su cierre corresponde al proceso
que lo inició. Los scripts no detienen procesos ajenos para liberar un puerto.

### 5. Comprobar la API

Desde otra consola PowerShell, una vez terminada la carga:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:38181/health'
Invoke-RestMethod -Uri 'http://127.0.0.1:38181/v1/models'
```

El estado esperado incluye `loaded = True`, `max_context = 131072` y el modelo
`qwen3.8-flash-next-iq3_xxs`. Si la carga sigue en curso, esperar y volver a
consultar. Un puerto ocupado por otro servicio no demuestra que Strata esté listo.

### 6. Integrar Gentle Shell, si se necesita

Gentle Shell y sus ajustes se preparan por separado; no se instalan al clonar:

| Ajuste | Valor de esta integración |
| --- | --- |
| Proveedor | `strata` |
| API | `openai-completions` |
| Base URL | `http://127.0.0.1:38181/v1` |
| ID del modelo dentro del proveedor | `qwen3.8-flash-next-iq3_xxs` |
| Referencia completa en los ajustes | `strata/qwen3.8-flash-next-iq3_xxs` |
| Ventana de contexto | `131072` |

Para la compactación, integrar
[`settings.fragment.json`](extensions/strata-compaction/settings.fragment.json)
siguiendo la [guía de la extensión](extensions/strata-compaction/README.md).
Reemplazar su ruta de ejemplo `E:/Strata-data/...` por la **ruta absoluta real** de
la extensión en el equipo nuevo. Este comando imprime una ruta válida para el
ejemplo de esta guía, con barras compatibles con JSON:

```powershell
(Join-Path $base 'Strata-data\extensions\strata-compaction\index.ts').Replace('\', '/')
```

Combinar únicamente la entrada de extensión y el override del modelo
(`reserveTokens: 32768`); nunca reemplazar todo el archivo de ajustes ni eliminar
otros modelos/extensiones. Después usar `/reload` o abrir una nueva sesión de
Gentle Shell. La autenticación, las sesiones y las preferencias personales como el
esfuerzo de pensamiento no viajan en este repo.

### Si algo falla

- **El destino de clonación ya existe:** no borrar modelos ni ejecutar una
  limpieza forzada; revisar la guía de recuperación antes de continuar.
- **Aparecen rutas antiguas como `E:/Strata`:** verificar que se ejecutó el
  instalador normal con `--setup`, no el migrador histórico ni un batch copiado.
- **Puerto 38181 ocupado:** identificar qué servicio lo usa; los lanzadores no
  matan procesos ajenos. Si se elige otro puerto, mantener coherentes el instalador
  y la URL del cliente.
- **Modelo distinto o contexto incompatible:** usar la configuración y el
  lanzador correspondientes; estos scripts están orientados a IQ3_XXS/128K.
- **La API funciona pero Gentle Shell no:** revisar proveedor, URL, ID del modelo
  y ruta de la extensión del nuevo equipo.

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
