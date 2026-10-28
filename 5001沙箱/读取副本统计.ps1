# 读取 5001 隔离副本的预标注统计（阈值对比用）
# 用法：powershell -ExecutionPolicy Bypass -File 读取副本统计.ps1 [-Path 副本根目录]
param(
    [string]$Path = (Join-Path $env:TEMP 'isolated_5001')
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$annDir = Join-Path $Path 'data\annotations'
if (-not (Test-Path -LiteralPath $annDir)) {
    Write-Host "副本不存在或缺少 data\annotations：$annDir" -ForegroundColor Red
    Write-Host '请先运行 5001隔离启动.bat demo-预标注'
    exit 1
}

$files = @(Get-ChildItem -LiteralPath $annDir -Filter '*.json' -File | Sort-Object Name)
if ($files.Count -eq 0) {
    Write-Host "副本还没有标注 JSON，先跑预标注（$annDir）" -ForegroundColor Yellow
    exit 0
}

function Fmt([object]$v) { if ($null -eq $v) { '—' } else { '{0:N3}' -f [double]$v } }

$rows = New-Object System.Collections.Generic.List[object]
$allConf = New-Object System.Collections.Generic.List[double]
$totalInst = 0
foreach ($f in $files) {
    try {
        $doc = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        $rows.Add([pscustomobject]@{ 图名 = $f.BaseName; 阈值 = '解析失败'; 实例数 = ''; 'min(conf)' = ''; 'avg(conf)' = ''; 'max(conf)' = '' })
        continue
    }
    $live = @($doc.instances | Where-Object { $_ -and $_.mark -ne 'deleted' })
    $confs = @($live | Where-Object { $null -ne $_.conf } | ForEach-Object { [double]$_.conf })
    $th = if ($doc.prelabel -and $null -ne $doc.prelabel.conf) { [double]$doc.prelabel.conf } else { $null }
    $m = if ($confs.Count) { $confs | Measure-Object -Minimum -Average -Maximum } else { $null }
    $rows.Add([pscustomobject]@{
        图名        = if ($doc.image) { $doc.image } else { $f.BaseName }
        阈值        = if ($null -ne $th) { '{0:N2}' -f $th } else { '—' }
        实例数      = $live.Count
        'min(conf)' = Fmt $(if ($m) { $m.Minimum })
        'avg(conf)' = Fmt $(if ($m) { $m.Average })
        'max(conf)' = Fmt $(if ($m) { $m.Maximum })
    })
    $totalInst += $live.Count
    foreach ($c in $confs) { $allConf.Add($c) }
}

$all = if ($allConf.Count) { $allConf | Measure-Object -Minimum -Average -Maximum } else { $null }
$rows.Add([pscustomobject]@{
    图名        = "合计（$($files.Count) 张）"
    阈值        = ''
    实例数      = $totalInst
    'min(conf)' = Fmt $(if ($all) { $all.Minimum })
    'avg(conf)' = Fmt $(if ($all) { $all.Average })
    'max(conf)' = Fmt $(if ($all) { $all.Maximum })
})

Write-Host "副本：$Path"
$rows | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
