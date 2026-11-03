# Cria os atalhos "BotBene" na Area de Trabalho e no Menu Iniciar.
# Rode uma vez (e de novo sempre que o icone mudar), no PowerShell do Windows:
#   powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\moratz\botbene\desktop\instalar_atalho.ps1"
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
if ($here -notmatch '^\\\\wsl(?:\.localhost|\$)\\([^\\]+)\\(.+)$') {
    throw "Rode este script a partir da pasta do BotBene dentro do WSL (\\wsl.localhost\...)."
}
$distro = $Matches[1]
$linuxRoot = '/' + (($Matches[2] -replace '\\', '/') -replace '/desktop$', '')

# Identidade da janela do painel na barra de tarefas. O Edge em modo aplicativo (--app=http://127.0.0.1:8000)
# usa "MSEdge.<host>_<caminho>". Com o mesmo ID no atalho, o Windows liga a janela aberta ao atalho:
# a barra de tarefas mostra o icone do BotBene (e nao o icone que o Edge guardou do site) e "Fixar" fixa o atalho.
$appId = 'MSEdge.127.0.0.1_/'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class ShortcutAppId {
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class ShellLink { }
    [StructLayout(LayoutKind.Sequential, Pack = 4)] struct PROPERTYKEY { public Guid fmtid; public uint pid; }
    [StructLayout(LayoutKind.Explicit)] struct PROPVARIANT { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; [FieldOffset(16)] public IntPtr pad; }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        void GetCount(out uint c); void GetAt(uint i, out PROPERTYKEY k);
        void GetValue(ref PROPERTYKEY k, out PROPVARIANT v); void SetValue(ref PROPERTYKEY k, ref PROPVARIANT v); void Commit();
    }
    [DllImport("shell32.dll")] static extern void SHChangeNotify(int eventId, uint flags, IntPtr a, IntPtr b);

    // Grava System.AppUserModel.ID no atalho .lnk.
    public static void Set(string lnk, string appId) {
        object link = new ShellLink();
        ((IPersistFile)link).Load(lnk, 2 /* STGM_READWRITE */);
        var key = new PROPERTYKEY { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
        var v = new PROPVARIANT { vt = 31 /* VT_LPWSTR */, p = Marshal.StringToCoTaskMemUni(appId) };
        try {
            var store = (IPropertyStore)link;
            store.SetValue(ref key, ref v);
            store.Commit();
        } finally { Marshal.FreeCoTaskMem(v.p); }
        ((IPersistFile)link).Save(lnk, true);
        Marshal.ReleaseComObject(link);
    }

    // Avisa o Explorer para recarregar os icones (Area de Trabalho, Menu Iniciar, barra de tarefas).
    public static void RefreshIcons() { SHChangeNotify(0x08000000 /* SHCNE_ASSOCCHANGED */, 0, IntPtr.Zero, IntPtr.Zero); }
}
'@

$installDir = Join-Path $env:LOCALAPPDATA 'BotBene'
New-Item -ItemType Directory -Force $installDir | Out-Null

# O Windows guarda os icones em cache pelo caminho do arquivo. Por isso o nome leva a "versao" do icone:
# quando o icone muda, o caminho muda e o Windows e obrigado a ler o novo.
$ico = Join-Path $here 'botbene.ico'
$version = (Get-FileHash $ico -Algorithm SHA256).Hash.Substring(0, 8).ToLower()
$icoInstalled = Join-Path $installDir "botbene-$version.ico"
Copy-Item $ico $icoInstalled -Force
Get-ChildItem $installDir -Filter 'botbene*.ico' | Where-Object { $_.FullName -ne $icoInstalled } | Remove-Item -Force

$launcher = Join-Path $installDir 'BotBene.ps1'
$content = (Get-Content (Join-Path $here 'BotBene.ps1') -Raw -Encoding UTF8).Replace('__DISTRO__', $distro).Replace('__LINUX_ROOT__', $linuxRoot)
Set-Content -Path $launcher -Value $content -Encoding UTF8

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'BotBene.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'BotBene.lnk')
)
# Se o BotBene foi fixado na barra de tarefas ou no Iniciar, atualiza esse atalho tambem.
$pinned = @("$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar",
            "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\StartMenu") |
    Where-Object { Test-Path $_ } | ForEach-Object { Get-ChildItem $_ -Filter 'BotBene*.lnk' } | ForEach-Object { $_.FullName }
foreach ($path in @($targets) + @($pinned)) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $lnk.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"'
    $lnk.IconLocation = $icoInstalled + ',0'
    $lnk.WorkingDirectory = $installDir
    $lnk.WindowStyle = 7
    $lnk.Description = 'BotBene - bot da Logica do Preco'
    $lnk.Save()
    [ShortcutAppId]::Set($path, $appId)
    Write-Output "Atalho criado: $path"
}
[ShortcutAppId]::RefreshIcons()
Write-Output "Pronto. WSL: $distro | projeto: $linuxRoot | icone: $(Split-Path $icoInstalled -Leaf)"
Write-Output "Se o BotBene estiver aberto, feche a janela e abra de novo pelo atalho para a barra de tarefas pegar o icone novo."
