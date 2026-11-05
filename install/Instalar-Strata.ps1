# Windows PowerShell 5.1+. Installs the fixed profile; never loads the model.
[CmdletBinding()]
param(
    [switch]$SinGentleShell,
    [switch]$IntegrarGentleShell,
    [Parameter(DontShow=$true)][switch]$FunctionsOnly
)

function Assert-InstallPath {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -match '[%"!&|<>\r\n]') { throw 'Usa una ruta sin comillas ni caracteres especiales de CMD. Los espacios si estan admitidos.' }
    $item = [IO.DirectoryInfo]::new($full)
    while ($null -ne $item) {
        if ($item.Exists -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'No se admiten enlaces o junctions en las rutas de instalacion.'
        }
        $item = $item.Parent
    }
    return $full
}

function Get-InstallPaths {
    param([string]$InstallDirectory)
    $data = Assert-InstallPath ([IO.Directory]::GetParent($InstallDirectory).FullName)
    $fork = Assert-InstallPath (Join-Path ([IO.Directory]::GetParent($data).FullName) 'Strata')
    if ($data -eq $fork) { throw 'El clon Strata-data no puede llamarse Strata.' }
    return [pscustomobject]@{ Data=$data; Fork=$fork; State=(Join-Path $data '.install-state') }
}

function Invoke-InstallCommand {
    param([string]$Executable, [string[]]$Arguments, [string]$Directory, [string]$State)
    $id = [Guid]::NewGuid().ToString('N')
    $stdout = Join-Path $State ($id + '.stdout.log')
    $stderr = Join-Path $State ($id + '.stderr.log')
    $words = @($Executable) + @($Arguments)
    $command = ($words | ForEach-Object { ConvertTo-StrataCmdPath -Path $_ }) -join ' '
    $cmd = ConvertTo-StrataCmdPath -Path $env:ComSpec
    $out = ConvertTo-StrataCmdPath -Path $stdout
    $err = ConvertTo-StrataCmdPath -Path $stderr
    $owned = $null
    try {
        # Reuse the tested Windows Job Object: closing this console kills its entire
        # owned installer tree, not an unrelated server. No helper window is shown.
        $line = "$cmd /d /s /c `"$command > $out 2> $err < nul`""
        [IO.File]::WriteAllText((Join-Path $State ($id + '.command.log')), $line)
        $owned = [StrataLauncher.OwnedProcess]::new($line, $Directory)
        $started = [DateTime]::UtcNow
        while (-not $owned.HasExited) {
            $seconds = [int]([DateTime]::UtcNow - $started).TotalSeconds
            Write-Progress -Activity 'Preparando Strata' -Status "Trabajando... $seconds segundos. No cierres esta consola."
            Start-Sleep -Milliseconds 250
        }
        $code = [int]$owned.ExitCode
    } finally {
        Write-Progress -Activity 'Preparando Strata' -Completed
        if ($null -ne $owned) { $owned.Dispose() }
    }
    $text = if (Test-Path -LiteralPath $stdout) { [IO.File]::ReadAllText($stdout, [Text.Encoding]::UTF8) } else { '' }
    return [pscustomobject]@{ Code=$code; Text=$text.Trim(); ErrorLog=$stderr; OutputLog=$stdout }
}

function Invoke-InstallGit {
    param([string]$Git, [string]$Root, [string[]]$GitArguments, [string]$State, [switch]$AllowFailure)
    $result = Invoke-InstallCommand -Executable $Git -Arguments (@('-C', $Root) + $GitArguments) -Directory $Root -State $State
    if ($result.Code -ne 0 -and -not $AllowFailure) {
        throw "Git no pudo completar la operacion. No se hizo reset ni se borraron archivos. Registro: $($result.ErrorLog)"
    }
    return $result
}

function Assert-InstallRepository {
    param([string]$Git, [string]$Root, [string]$State)
    Assert-InstallPath $Root | Out-Null
    $top = (Invoke-InstallGit $Git $Root @('rev-parse','--show-toplevel') $State).Text
    if ([IO.Path]::GetFullPath($top) -ne [IO.Path]::GetFullPath($Root)) { throw 'Strata no es la raiz de su repositorio.' }
    $origin = (Invoke-InstallGit $Git $Root @('remote','get-url','origin') $State).Text.ToLowerInvariant().TrimEnd('/')
    $allowed = @('https://github.com/daandradec/strata','https://github.com/daandradec/strata.git',
                 'git@github.com:daandradec/strata','git@github.com:daandradec/strata.git',
                 'ssh://git@github.com/daandradec/strata','ssh://git@github.com/daandradec/strata.git')
    if ($origin -notin $allowed) { throw 'La carpeta Strata pertenece a otro repositorio. No se modifico.' }
    $changed = (Invoke-InstallGit $Git $Root @('diff','--name-only','HEAD') $State).Text
    foreach ($name in @($changed -split '\r?\n' | Where-Object { $_ })) {
        if ($name -notin @('strata-iq3_xxs.json','run-iq3_xxs.bat')) { throw 'Hay cambios locales de codigo en Strata. Guardalos antes de continuar.' }
    }
}

function Ensure-InstallFork {
    param([string]$Git, [string]$Fork, [string]$State)
    $branch = 'strata-local-installation'
    if (-not (Test-Path -LiteralPath $Fork)) {
        $stage = Join-Path $State ('clone-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $stage | Out-Null
        $checkout = Join-Path $stage 'Strata'
        $result = Invoke-InstallCommand $Git @('clone','--branch',$branch,'--single-branch',
            'https://github.com/daandradec/Strata.git',$checkout) $stage $State
        if ($result.Code -ne 0) { throw "No se pudo descargar el fork. Repite el instalador; no se borraron datos. Registro: $($result.ErrorLog)" }
        Assert-InstallRepository $Git $checkout $State
        if ((Invoke-InstallGit $Git $checkout @('branch','--show-current') $State).Text -ne $branch) { throw 'La descarga no corresponde a la rama esperada.' }
        # Same-volume rename, only after validating both exact paths and absence of target.
        Assert-InstallPath $checkout | Out-Null
        Assert-InstallPath $Fork | Out-Null
        if (Test-Path -LiteralPath $Fork) { throw 'Strata aparecio durante la descarga; no se reemplazo.' }
        [IO.Directory]::Move($checkout, $Fork)
    }
    Assert-InstallRepository $Git $Fork $State
    $current = (Invoke-InstallGit $Git $Fork @('branch','--show-current') $State).Text
    $protocol = Join-Path $Fork 'tools\bootstrap_setup.py'
    if ($current -ne $branch -or -not (Test-Path -LiteralPath $protocol)) {
        # Existing customizations are never discarded to switch/update a checkout.
        if ((Invoke-InstallGit $Git $Fork @('status','--porcelain') $State).Text) {
            throw 'La instalacion existente necesita la rama compatible, pero tiene cambios locales. No se modifico.'
        }
        Invoke-InstallGit $Git $Fork @('fetch','origin',('refs/heads/' + $branch + ':refs/remotes/origin/' + $branch)) $State | Out-Null
        if ($current -ne $branch) {
            $exists = Invoke-InstallGit $Git $Fork @('show-ref','--verify',('refs/heads/' + $branch)) $State -AllowFailure
            if ($exists.Code -eq 0) { Invoke-InstallGit $Git $Fork @('switch',$branch) $State | Out-Null }
            else { Invoke-InstallGit $Git $Fork @('switch','--create',$branch,'--track',('origin/' + $branch)) $State | Out-Null }
        }
        Invoke-InstallGit $Git $Fork @('merge','--ff-only',('origin/' + $branch)) $State | Out-Null
    }
    Assert-InstallRepository $Git $Fork $State
    Invoke-InstallGit $Git $Fork @('ls-files','--error-unmatch','setup.py','START-HERE.bat','tools/bootstrap_setup.py') $State | Out-Null
    if (-not (Test-Path -LiteralPath $protocol)) { throw 'El fork aun no incluye el instalador seguro. No se inicio la instalacion.' }
}

function Invoke-InstallWorker {
    param([string]$Python, [string]$Worker, [string[]]$WorkerArguments, [string]$Directory, [string]$State)
    $result = Invoke-InstallCommand $Python (@($Worker) + $WorkerArguments) $Directory $State
    try { $answer = $result.Text | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "No se obtuvo un resultado valido. Registro: $($result.OutputLog)" }
    if ($result.Code -ne 0) { throw $answer.message }
    return $answer
}

if ($FunctionsOnly) { return }
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$lock = $null
try {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'Este instalador requiere Windows de 64 bits.' }
    if ($SinGentleShell -and $IntegrarGentleShell) { throw 'Elige solo una opcion de Gentle Shell.' }
    $layout = Get-InstallPaths $PSScriptRoot
    $worker = Join-Path $PSScriptRoot 'bootstrap.py'
    $launcher = Join-Path $layout.Data 'start_model_qwen.ps1'
    foreach ($file in @($worker,$launcher)) { if (-not (Test-Path -LiteralPath $file)) { throw 'Faltan archivos del clon Strata-data.' } }
    $gitCommand = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $gitCommand) { throw 'No se encontro Git. Instala Git para Windows, abre una consola nueva y repite el instalador.' }
    $git = $gitCommand.Source
    Assert-InstallPath $layout.State | Out-Null
    New-Item -ItemType Directory -Path $layout.State -Force | Out-Null
    try { $lock = [IO.File]::Open((Join-Path $layout.State 'install.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
    catch { throw 'Ya hay otro instalador en esta carpeta. Espera a que termine.' }
    # FunctionsOnly defines the tested process container; it never starts a server.
    . $launcher -FunctionsOnly
    Write-Host '[1/4] Comprobando el fork Strata y su rama...'
    Ensure-InstallFork $git $layout.Fork $layout.State
    Write-Host '[2/4] Preparando Python privado...'
    $python = Join-Path $layout.Fork '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        # --help exits argparse before hardware/data_folder; bootstrap Python/venv only.
        $result = Invoke-InstallCommand (Join-Path $layout.Fork 'START-HERE.bat') @('--help') $layout.Fork $layout.State
        if ($result.Code -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw "No se pudo preparar Python. Registro: $($result.ErrorLog)" }
    }
    $version = Invoke-InstallCommand $python @('-c','import sys,struct;print(sys.version_info.major,sys.version_info.minor,struct.calcsize(chr(80))*8)') $layout.Fork $layout.State
    $numbers = @($version.Text -split ' ')
    if ($version.Code -ne 0 -or $numbers.Count -ne 3 -or [int]$numbers[0] -ne 3 -or [int]$numbers[1] -lt 10 -or [int]$numbers[2] -ne 64) { throw 'El entorno Python no es valido (se requiere Python 3.10+ de 64 bits). No se reemplazo.' }
    Write-Host '[3/4] Comprobando e instalando IQ3_XXS / 128K / puerto 38181...'
    Write-Host 'Si faltan los pesos, se descargaran aproximadamente 76 GB, mas dependencias. Puede tardar bastante.'
    $answer = Invoke-InstallWorker $python $worker @('prepare','--data-dir',$layout.Data,'--strata-dir',$layout.Fork) $layout.Data $layout.State
    Write-Host $answer.message
    Write-Host '[4/4] Integracion opcional con Gentle Shell...'
    $agent = Join-Path $HOME '.gentle-shell\agent'
    $integrate = $IntegrarGentleShell.IsPresent
    if (-not $SinGentleShell -and -not $integrate -and (Test-Path -LiteralPath $agent)) {
        $choice = Read-Host 'Configurar este modelo en Gentle Shell con respaldo de ajustes? [s/N]'
        $integrate = $choice -in @('s','si')
    }
    if ($integrate) {
        $answer = Invoke-InstallWorker $python $worker @('gentle','--data-dir',$layout.Data,'--agent-dir',$agent) $layout.Data $layout.State
        Write-Host $answer.message
    }
    Write-Host 'Listo. El modelo NO se inicio. Para usarlo, ejecuta start_model_qwen.ps1 o start_web_strata.ps1 en Strata-data.' -ForegroundColor Green
    exit 0
} catch {
    Write-Host ('No se completo la instalacion: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'No se descartan cambios de Git ni se detienen servidores ajenos. Puedes repetir el instalador despues de resolver el error.'
    exit 1
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
}
