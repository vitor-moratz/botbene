# Lançador do BotBene (Windows). O instalador copia este arquivo para %LOCALAPPDATA%\BotBene
# trocando __DISTRO__ e __LINUX_ROOT__ pelos valores da sua instalação.
# 1) Se o servidor não estiver rodando, sobe ele no WSL, escondido.
# 2) Abre o painel numa janela própria do Edge (modo aplicativo, sem barra de endereço).
$ErrorActionPreference = 'Stop'
$Distro = '__DISTRO__'
$LinuxRoot = '__LINUX_ROOT__'
# 127.0.0.1 e não "localhost": no Windows, "localhost" tenta IPv6 primeiro e leva ~2 s para cair no IPv4 do WSL.
$Url = 'http://127.0.0.1:8000'

function Test-Server {
    try { Invoke-WebRequest -UseBasicParsing "$Url/api/status" -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

if (-not (Test-Server)) {
    Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', $Distro, '--exec', 'bash', "$LinuxRoot/desktop/start_server.sh") -WindowStyle Hidden
    $ok = $false
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Server) { $ok = $true; break }
    }
    if (-not $ok) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show("Não foi possível iniciar o servidor do BotBene.`nVeja o log em $LinuxRoot/data/server.log", 'BotBene') | Out-Null
        exit 1
    }
}

$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($edge) {
    Start-Process -FilePath $edge -ArgumentList @("--app=$Url", '--window-size=1440,920')
} else {
    Start-Process $Url
}
