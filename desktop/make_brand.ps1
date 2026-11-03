# Gera todos os tamanhos do ícone e do logo a partir dos originais em assets/brand/
# (icone.png e logo.png, com fundo transparente). Rode no PowerShell do Windows:
#   powershell -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\moratz\botbene\desktop\make_brand.ps1"
# Saídas:
#   frontend/icon-32.png, icon-64.png, icon-192.png, icon-512.png   (página, barra lateral, app)
#   desktop/botbene.ico                                              (atalho do Windows, 16 a 256 px)
#   docs/img/icone.png, docs/img/logo.png, docs/img/logo-escuro.png  (README e PDFs)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;

public static class BrandTools {
    static byte[] Read(Bitmap b, out int stride) {
        var d = b.LockBits(new Rectangle(0, 0, b.Width, b.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        stride = d.Stride;
        var px = new byte[d.Stride * b.Height];
        Marshal.Copy(d.Scan0, px, 0, px.Length);
        b.UnlockBits(d);
        return px;
    }

    // Retângulo dos pixels com opacidade >= minAlpha (ignora o brilho fraco em volta).
    public static Rectangle OpaqueBox(Bitmap b, int minAlpha) {
        int stride; var px = Read(b, out stride);
        int x0 = b.Width, y0 = b.Height, x1 = -1, y1 = -1;
        for (int y = 0; y < b.Height; y++)
            for (int x = 0; x < b.Width; x++)
                if (px[y * stride + x * 4 + 3] >= minAlpha) {
                    if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
                }
        return x1 < 0 ? new Rectangle(0, 0, b.Width, b.Height) : Rectangle.FromLTRB(x0, y0, x1 + 1, y1 + 1);
    }

    public static Bitmap Resize(Bitmap src, Rectangle crop, int w, int h) {
        var dst = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(dst)) {
            g.Clear(Color.Transparent);
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = PixelOffsetMode.HighQuality;
            g.CompositingQuality = CompositingQuality.HighQuality;
            g.SmoothingMode = SmoothingMode.HighQuality;
            using (var attr = new ImageAttributes()) {
                attr.SetWrapMode(WrapMode.TileFlipXY);  // sem borda clara nas pontas
                g.DrawImage(src, new Rectangle(0, 0, w, h), crop.X, crop.Y, crop.Width, crop.Height, GraphicsUnit.Pixel, attr);
            }
        }
        return dst;
    }

    // Pinta de "to" os pixels escuros à direita de fromX (o "Bot" preto do logo, para fundo escuro).
    public static void RecolorDark(Bitmap b, int fromX, int maxChannel, Color to) {
        var d = b.LockBits(new Rectangle(0, 0, b.Width, b.Height), ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        var px = new byte[d.Stride * b.Height];
        Marshal.Copy(d.Scan0, px, 0, px.Length);
        for (int y = 0; y < b.Height; y++)
            for (int x = fromX; x < b.Width; x++) {
                int i = y * d.Stride + x * 4;
                if (px[i + 3] == 0) continue;
                if (px[i] <= maxChannel && px[i + 1] <= maxChannel && px[i + 2] <= maxChannel) {
                    px[i] = to.B; px[i + 1] = to.G; px[i + 2] = to.R;
                }
            }
        Marshal.Copy(px, 0, d.Scan0, px.Length);
        b.UnlockBits(d);
    }

    public static byte[] Png(Bitmap b) {
        using (var ms = new MemoryStream()) { b.Save(ms, ImageFormat.Png); return ms.ToArray(); }
    }

    // Imagem do .ico no formato BMP (DIB 32 bits, de baixo para cima, + máscara AND zerada): é o que todo o
    // Windows lê nos tamanhos pequenos. PNG dentro do .ico só no de 256 px.
    static byte[] Dib(Bitmap b) {
        int w = b.Width, h = b.Height, stride;
        var px = Read(b, out stride);
        int maskRow = ((w + 31) / 32) * 4;
        using (var ms = new MemoryStream())
        using (var bw = new BinaryWriter(ms)) {
            bw.Write(40); bw.Write(w); bw.Write(h * 2); bw.Write((short)1); bw.Write((short)32);
            bw.Write(0); bw.Write(w * h * 4 + maskRow * h); bw.Write(0); bw.Write(0); bw.Write(0); bw.Write(0);
            for (int y = h - 1; y >= 0; y--) bw.Write(px, y * stride, w * 4);
            bw.Write(new byte[maskRow * h]);
            return ms.ToArray();
        }
    }

    public static byte[] Ico(Bitmap[] images) {
        using (var ms = new MemoryStream())
        using (var w = new BinaryWriter(ms)) {
            var blobs = new byte[images.Length][];
            for (int i = 0; i < images.Length; i++) blobs[i] = images[i].Width >= 256 ? Png(images[i]) : Dib(images[i]);
            w.Write((short)0); w.Write((short)1); w.Write((short)images.Length);
            int offset = 6 + 16 * images.Length;
            for (int i = 0; i < images.Length; i++) {
                int s = images[i].Width;
                w.Write((byte)(s >= 256 ? 0 : s)); w.Write((byte)(s >= 256 ? 0 : s));
                w.Write((byte)0); w.Write((byte)0); w.Write((short)1); w.Write((short)32);
                w.Write(blobs[i].Length); w.Write(offset);
                offset += blobs[i].Length;
            }
            foreach (var blob in blobs) w.Write(blob);
            return ms.ToArray();
        }
    }
}
'@

$root = Split-Path $PSScriptRoot -Parent
$brand = Join-Path $root 'assets\brand'
$frontend = Join-Path $root 'frontend'
$img = Join-Path $root 'docs\img'
New-Item -ItemType Directory -Force $img | Out-Null

function Save-Png($bmp, $path) { [IO.File]::WriteAllBytes($path, [BrandTools]::Png($bmp)); Write-Output "  $path ($($bmp.Width)x$($bmp.Height))" }

# ---------------------------------------------------------------- ícone
$icon = [System.Drawing.Bitmap]::FromFile((Join-Path $brand 'icone.png'))
$box = [BrandTools]::OpaqueBox($icon, 200)
# quadrado em volta do ícone, com um respiro de 2% para não cortar o brilho da borda
$side = [Math]::Max($box.Width, $box.Height)
$pad = [int]($side * 0.02)
$side += 2 * $pad
$cx = $box.X + $box.Width / 2; $cy = $box.Y + $box.Height / 2
$crop = New-Object System.Drawing.Rectangle ([int]($cx - $side / 2)), ([int]($cy - $side / 2)), $side, $side
Write-Output "Ícone: recorte $crop de $($icon.Width)x$($icon.Height)"
foreach ($s in 32, 64, 192, 512) { $b = [BrandTools]::Resize($icon, $crop, $s, $s); Save-Png $b (Join-Path $frontend "icon-$s.png"); $b.Dispose() }
$b = [BrandTools]::Resize($icon, $crop, 256, 256); Save-Png $b (Join-Path $img 'icone.png'); $b.Dispose()
$sizes = 16, 24, 32, 48, 64, 128, 256
$frames = @($sizes | ForEach-Object { [BrandTools]::Resize($icon, $crop, $_, $_) })
[IO.File]::WriteAllBytes((Join-Path $PSScriptRoot 'botbene.ico'), [BrandTools]::Ico($frames))
Write-Output "  $(Join-Path $PSScriptRoot 'botbene.ico') ($($sizes -join ', ') px)"
$frames | ForEach-Object { $_.Dispose() }
$icon.Dispose()

# ---------------------------------------------------------------- logo (versão clara e versão para fundo escuro)
$logo = [System.Drawing.Bitmap]::FromFile((Join-Path $brand 'logo.png'))
$dark = New-Object System.Drawing.Bitmap $logo
# o "Bot" preto começa depois do robô (a orelha direita termina em ~32% da largura e o "B" começa em ~34%):
# no fundo escuro as letras viram claras
[BrandTools]::RecolorDark($dark, [int]($logo.Width * 0.334), 90, [System.Drawing.Color]::FromArgb(240, 239, 236))
$box = [BrandTools]::OpaqueBox($logo, 40)
$pad = [int]($box.Height * 0.04)
$crop = [System.Drawing.Rectangle]::FromLTRB([Math]::Max(0, $box.Left - $pad), [Math]::Max(0, $box.Top - $pad),
    [Math]::Min($logo.Width, $box.Right + $pad), [Math]::Min($logo.Height, $box.Bottom + $pad))
$w = 900; $h = [int]($crop.Height * $w / $crop.Width)
Write-Output "Logo: recorte $crop"
$b = [BrandTools]::Resize($logo, $crop, $w, $h); Save-Png $b (Join-Path $img 'logo.png'); $b.Dispose()
$b = [BrandTools]::Resize($dark, $crop, $w, $h); Save-Png $b (Join-Path $img 'logo-escuro.png'); $b.Dispose()
$logo.Dispose(); $dark.Dispose()
Write-Output 'Pronto.'
