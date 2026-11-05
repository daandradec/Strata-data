# Default context: 131072 tokens (128K).
# Starts Strata and opens its web app, or opens an already running Strata without loading another model.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File E:\Strata-data\start_web_strata.ps1
# PreferredPort defaults to the configured model port. For configured ports above 8099,
# the implicit maximum follows that port; an explicit MaxPort remains authoritative.
[CmdletBinding()]
param(
    [string]$StrataRoot,
    [ValidateRange(1024, 65535)][int]$PreferredPort = 8080,
    [ValidateRange(1024, 65535)][int]$MaxPort = 8099,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
if (-not $StrataRoot) { $StrataRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'Strata' }
# Embedded support: this script needs no other PowerShell file.
Set-StrictMode -Version Latest

if (-not ('StrataLauncher.OwnedProcess' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace StrataLauncher {
    public sealed class OwnedProcess : IDisposable {
        [StructLayout(LayoutKind.Sequential)]
        struct BasicLimits {
            public long ProcessTime, JobTime;
            public uint Flags;
            public UIntPtr MinWorkingSet, MaxWorkingSet;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
        [StructLayout(LayoutKind.Sequential)]
        struct ExtendedLimits {
            public BasicLimits Basic;
            public IoCounters Io;
            public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
        }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct StartupInfo {
            public uint Size;
            public string Reserved, Desktop, Title;
            public uint X, Y, Width, Height, XChars, YChars, Fill, Flags;
            public ushort ShowWindow, ReservedSize;
            public IntPtr ReservedBytes, Stdin, Stdout, Stderr;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct ProcessInfo { public IntPtr Process, Thread; public uint ProcessId, ThreadId; }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr CreateJobObjectW(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref ExtendedLimits info, uint size);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern bool CreateProcessW(string application, StringBuilder command, IntPtr processAttributes,
            IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment, string directory,
            ref StartupInfo startup, out ProcessInfo process);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll")]
        static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll")]
        static extern bool GetExitCodeProcess(IntPtr process, out uint code);
        [DllImport("kernel32.dll")]
        static extern bool CloseHandle(IntPtr handle);

        IntPtr job, process;
        public uint ProcessId { get; private set; }
        public bool HasExited { get { return process == IntPtr.Zero || WaitForSingleObject(process, 0) == 0; } }
        public uint ExitCode { get { uint code; return GetExitCodeProcess(process, out code) ? code : 1; } }

        public OwnedProcess(string commandLine, string directory) {
            ProcessInfo child = new ProcessInfo();
            try {
                job = CreateJobObjectW(IntPtr.Zero, null);
                if (job == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
                ExtendedLimits limits = new ExtendedLimits();
                limits.Basic.Flags = 0x2000; // KILL_ON_JOB_CLOSE; the child never inherits this handle.
                if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(typeof(ExtendedLimits))))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                StartupInfo startup = new StartupInfo();
                startup.Size = (uint)Marshal.SizeOf(typeof(StartupInfo));
                // Suspend before assignment so neither Python nor the engine can escape containment.
                if (!CreateProcessW(null, new StringBuilder(commandLine), IntPtr.Zero, IntPtr.Zero,
                    false, 0x08000004, IntPtr.Zero, directory, ref startup, out child))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                process = child.Process;
                ProcessId = child.ProcessId;
                if (!AssignProcessToJobObject(job, process))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                if (ResumeThread(child.Thread) == UInt32.MaxValue)
                    throw new Win32Exception(Marshal.GetLastWin32Error());
            } catch {
                if (process != IntPtr.Zero) TerminateProcess(process, 1);
                Dispose();
                throw;
            } finally {
                if (child.Thread != IntPtr.Zero) CloseHandle(child.Thread);
            }
        }

        public void Dispose() {
            if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
            if (process != IntPtr.Zero) { CloseHandle(process); process = IntPtr.Zero; }
            GC.SuppressFinalize(this);
        }
        ~OwnedProcess() { Dispose(); }
    }
}
'@
}

function Test-StrataPortAvailable {
    param([int]$Port)
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    } catch { return $false } finally { $listener.Stop() }
}

function Get-StrataHealth {
    param([int]$Port)
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 -ErrorAction Stop
        if ($health.PSObject.Properties['service'] -and $health.service -eq 'strata' -and $health.status -eq 'ok') {
            return $health
        }
    } catch { }
    return $null
}

function Get-StrataFreePort {
    param([int]$PreferredPort = 8080, [int]$MaxPort = 8099)
    for ($candidate = $PreferredPort; $candidate -le $MaxPort; $candidate++) {
        if (Test-StrataPortAvailable -Port $candidate) { return $candidate }
    }
    throw "No hay un puerto libre entre $PreferredPort y $MaxPort."
}

function ConvertTo-StrataCmdPath {
    param([string]$Path)
    # CMD expands percent signs even inside quotes; disallow shell metacharacters in configurable paths.
    if ($Path -match '[%"!&|<>\r\n]') { throw "La ruta contiene caracteres no admitidos: $Path" }
    return '"' + $Path + '"'
}

function Invoke-StrataOwnedServer {
    param([string]$Command, [string]$WorkingDirectory, [int]$Port, [string]$LogPath,
          [switch]$OpenBrowser, [int]$StartupTimeoutSeconds = 900)
    $cmdPath = ConvertTo-StrataCmdPath -Path $env:ComSpec
    $quotedLog = ConvertTo-StrataCmdPath -Path $LogPath
    $commandLine = "$cmdPath /d /s /c `"$Command > $quotedLog 2>&1`""
    $owned = $null
    try {
        $owned = [StrataLauncher.OwnedProcess]::new($commandLine, $WorkingDirectory)
        Write-Host "Cargando IQ3_XXS. URL: http://127.0.0.1:$Port"
        Write-Host "Registro: $LogPath"
        Write-Host 'Ctrl+C o cerrar esta consola detiene este servidor y su modelo.'
        $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
        $ready = $false
        $nextProbe = [DateTime]::UtcNow
        while (-not $owned.HasExited) {
            if (-not $ready -and [DateTime]::UtcNow -ge $nextProbe) {
                $health = Get-StrataHealth -Port $Port
                if ($null -ne $health -and $health.loaded) {
                    $ready = $true
                    Write-Host "Listo: http://127.0.0.1:$Port (API: http://127.0.0.1:$Port/v1)" -ForegroundColor Green
                    if ($OpenBrowser) { Start-Process -FilePath "http://127.0.0.1:$Port" | Out-Null }
                }
                $nextProbe = [DateTime]::UtcNow.AddSeconds(3)
            }
            if (-not $ready -and [DateTime]::UtcNow -gt $deadline) {
                throw "El servidor no estuvo listo en $StartupTimeoutSeconds segundos. Revisa $LogPath"
            }
            Start-Sleep -Milliseconds 250
        }
        if (-not $ready -or $owned.ExitCode -ne 0) {
            if (Test-Path -LiteralPath $LogPath) { Get-Content -LiteralPath $LogPath -Tail 12 | Out-Host }
            throw "El servidor termino antes de lo esperado. Revisa $LogPath"
        }
    } finally {
        # Ctrl+C runs finally; closing/killing PowerShell makes Windows close the same job handle.
        if ($null -ne $owned) { $owned.Dispose() }
    }
}

function Set-StrataDefaultContext {
    param([string]$ConfigPath)
    $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    $index = [Array]::IndexOf([object[]]$config.args, '--max-context')
    if ($index -lt 0) { throw "Falta --max-context en $ConfigPath" }
    if ([string]$config.args[$index + 1] -ne '131072') {
        $backup = $ConfigPath + '.before-launcher-128k.bak'
        if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $ConfigPath -Destination $backup }
        $config.args[$index + 1] = '131072'
        $temporary = $ConfigPath + '.launcher-' + $PID + '.tmp'
        [IO.File]::WriteAllText($temporary, (($config | ConvertTo-Json -Depth 50) + "`n"), [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $ConfigPath -Force
    }
}

if ($MaxPort -lt $PreferredPort) { throw 'MaxPort debe ser igual o mayor que PreferredPort.' }
$python = Join-Path $StrataRoot '.venv\Scripts\python.exe'
$config = Join-Path $StrataRoot 'strata-iq3_xxs.json'
foreach ($file in @($python, $config)) {
    if (-not (Test-Path -LiteralPath $file)) { throw "No se encontro $file" }
}

$modelConfig = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
if (-not $PSBoundParameters.ContainsKey('PreferredPort') -and $modelConfig.PSObject.Properties['port']) {
    $PreferredPort = [int]$modelConfig.port
}
if (-not $PSBoundParameters.ContainsKey('MaxPort') -and $MaxPort -lt $PreferredPort) {
    $MaxPort = $PreferredPort
}
if ($MaxPort -lt $PreferredPort) { throw 'MaxPort debe ser igual o mayor que PreferredPort.' }
# Only probe occupied ports; do not reuse or stop unrelated applications.
for ($candidate = $PreferredPort; $candidate -le $MaxPort; $candidate++) {
    if (-not (Test-StrataPortAvailable -Port $candidate)) {
        $health = Get-StrataHealth -Port $candidate
        if ($null -ne $health) {
            if (-not $health.PSObject.Properties['max_context'] -or $health.max_context -ne 131072) {
                throw 'Strata ya esta activo con otro contexto. Cierra la consola que lo inicio y vuelve a ejecutar este script para iniciar con 131072 tokens.'
            }
            Write-Host "Strata ya esta activo: http://127.0.0.1:$candidate"
            Write-Host 'Se reutiliza ese servidor. Su cierre corresponde a la consola o proceso que lo inicio.'
            if (-not $NoBrowser) { Start-Process -FilePath "http://127.0.0.1:$candidate" | Out-Null }
            return
        }
    }
}
Set-StrataDefaultContext -ConfigPath $config
$port = Get-StrataFreePort -PreferredPort $PreferredPort -MaxPort $MaxPort
$logDirectory = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$log = Join-Path $logDirectory ('web-' + $port + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$command = (ConvertTo-StrataCmdPath -Path $python) + ' -u -m serve.server --engine strata --config ' +
           (ConvertTo-StrataCmdPath -Path $config) + " --host 127.0.0.1 --port $port"
Invoke-StrataOwnedServer -Command $command -WorkingDirectory $StrataRoot -Port $port -LogPath $log -OpenBrowser:(-not $NoBrowser)
