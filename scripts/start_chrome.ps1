# Start a localhost server, prepare a RAM-only browser session, then open Chrome.
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chromePath = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chromePath) { throw 'Chrome was not found on this machine.' }
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements.txt first.' }

$session = $null
try { $session = Invoke-RestMethod 'http://127.0.0.1:8000/session' -TimeoutSec 3 } catch { }
if (-not $session -or $session.status -ne 'ready') {
    if (Get-Process -Name chrome -ErrorAction SilentlyContinue) {
        throw 'Close Chrome once, then run this script again to prepare the session.'
    }
    if (-not $session) {
        if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
            throw 'Port 8000 is already in use. Restart the existing app before using this launcher.'
        }
        $env:COOKIES_BROWSER = 'chrome'
        $toolsPath = Join-Path $projectPath '.tools'
        New-Item -ItemType Directory -Path $toolsPath -Force | Out-Null
        $ffmpegPath = Join-Path $toolsPath 'ffmpeg\ffmpeg-master-latest-win64-lgpl-shared\bin'
        if (Test-Path -LiteralPath $ffmpegPath) { $env:PATH = $ffmpegPath + ';' + $env:PATH }
        $serverArguments = @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000','--workers','1')
        if (Test-Path -LiteralPath (Join-Path $projectPath '.env')) { $serverArguments += @('--env-file','.env') }
        Start-Process -FilePath $pythonPath -ArgumentList $serverArguments -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $toolsPath 'server.stdout.log') -RedirectStandardError (Join-Path $toolsPath 'server.stderr.log') | Out-Null
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            try { $session = Invoke-RestMethod 'http://127.0.0.1:8000/session' -TimeoutSec 2; break } catch { Start-Sleep -Seconds 1 }
        }
    }
    if ($session -and $session.browser -ne 'chrome') { throw 'This server is not configured for Chrome. Restart it with COOKIES_BROWSER=chrome.' }
    if (-not $session -or $session.status -ne 'ready') {
        $session = Invoke-RestMethod 'http://127.0.0.1:8000/session/refresh' -Method Post -TimeoutSec 120
    }
}
if ($session.status -ne 'ready' -or $session.browser -ne 'chrome') {
    throw 'Chrome session could not be loaded. Check /session for the safe error message.'
}
Start-Process -FilePath $chromePath -ArgumentList 'http://localhost:8000' -WindowStyle Normal
Write-Output 'Chrome is open. The server will use its in-memory session; keep the server running.'
