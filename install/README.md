# Instalador de un comando (Windows)

Desde la carpeta `Strata-data`, abrir `install/Instalar.bat` con doble clic, o:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install\Instalar-Strata.ps1
```

No necesita PowerShell 7 ni instalar módulos de PowerShell. Git debe estar
instalado. El fork prepara Python privado y las dependencias que falten.

## Qué hace

1. Obtiene `https://github.com/daandradec/Strata`, rama
   `strata-local-installation`, en una carpeta hermana llamada `Strata`.
2. Valida el repositorio existente; no hace reset, limpieza forzada ni descarta
   cambios. Solo cambia/adelanta una rama existente si el checkout está limpio y
   necesita el protocolo de instalación. Los adelantos son `--ff-only`.
3. Prepara Python con `START-HERE.bat --help`; esto no instala el modelo ni llama
   al selector/migrador de datos. Luego usa el diagnóstico realmente read-only
   `--bootstrap-check`, **no** el antiguo `--check`.
4. Instala el perfil mediante `--bootstrap-install`: IQ3_XXS, contexto 131072,
   puerto 38181, host 127.0.0.1, KV int8, sin visión, sin inicio automático.
   No mueve datos de otras instalaciones ni cambia el registro global de rutas
   de Strata. El instalador original calcula el espacio restante y reutiliza
   descargas/preparaciones válidas; no se duplica el downloader.
5. Comprueba rutas, configuración, engine, pack, tokenizer, MTP y que ambos GGUF
   estén completos según su directorio de tensores. No hace inferencia: el
   arranque real sigue siendo manual.

El perfil automático es deliberadamente conservador: Windows x64, CPU AVX2,
al menos 60 GiB de RAM física, una GPU discreta soportada de clase 20 GB o más
(19.5 GiB reportados), controlador compatible y archivo de paginación adecuado.
No selecciona modos experimentales ni acepta advertencias de hardware a ciegas.
Esto **no** es el mínimo universal de Strata; equipos menores pueden seguir la
[instalación manual](../docs/manual-installation.md#otro-computador-windows).
Los pesos de IQ3_XXS son aproximadamente 76 GB, más engine/dependencias/MTP.

## Gentle Shell es opcional

Si existe `$HOME\.gentle-shell\agent`, el instalador pregunta una sola vez si se
desea integrar este modelo. Por defecto la respuesta es no. No instala Gentle
Shell ni toca autenticación o sesiones.

- `-SinGentleShell`: no preguntar ni integrar.
- `-IntegrarGentleShell`: consentimiento explícito para integrar sin preguntar.

La integración conserva otros modelos, overrides y nivel global de pensamiento.
Solo prepara el proveedor local, el modelo, la ruta real de la extensión,
`reserveTokens=32768` y pensamiento `high` para ese modelo. Si el proveedor ya
usa otra URL/autenticación, se detiene sin reemplazarlo. Los respaldos quedan
dentro de `agent/.strata-install-backups/`, con la privacidad del perfil original,
nunca en este repositorio público. Después usar `/reload` o una sesión nueva.

## Repetir y resolver errores

Se puede ejecutar otra vez: valida y reutiliza una instalación completa, o repara
archivos propios sin volver a descargar lo válido. Una configuración modificada
por el usuario no se reemplaza para reparar. Los recibos y registros quedan en
`Strata-data/.install-state/`, ignorado por Git. Los archivos originales de
configuración se respaldan y restauran si la instalación no termina bien. Un
journal registra los hashes previstos **antes** de escribirlos: después de un
cierre abrupto se recuperan solo cambios demostrablemente propios. Si encuentra
una edición personal posterior, se detiene conservándola en lugar de adivinar.
El `.bak` histórico del fork no se modifica.

La consola contiene todo su árbol de procesos en un Windows Job Object. Cerrarla
detiene sus propios instaladores; no mata servidores ajenos. No ejecutar dos
instaladores simultáneamente en la misma carpeta. El modelo no se inicia al final.

Si el primer clon del fork se interrumpe, el staging incompleto queda aislado en
`.install-state/`; el siguiente intento usa otro staging, sin borrar datos del
usuario. Una carpeta `Strata` ajena o un checkout con cambios se rechaza.

Una carpeta `Strata-data` preexistente y no vacía **sin Git** no permite clonar
este repo encima. Ese caso se recupera por separado según la
[guía de respaldo](../docs/backup-and-restore.md); nunca borrar pesos para clonar.

## Pruebas locales

```powershell
python -m unittest discover -s tests -p test_bootstrap.py -v
python -m unittest discover -s tests -p test_launchers.py -v
node --test tests/repository.test.mjs extensions/strata-compaction/*.test.mjs
```

Las pruebas usan repositorios temporales, hardware/instaladores ficticios y
servidores de prueba. No descargan pesos ni alteran la instalación real. La
prueba completa ejecuta el PS y worker reales dos veces contra un fork ficticio
y comprueba que solo se instala una vez. GitHub Actions permanece deshabilitado.
