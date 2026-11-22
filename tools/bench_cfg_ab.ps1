param(
    [Parameter(Mandatory=$true)]
    [string]$Tag,
    [switch]$UseDXVK,
    [string]$Malloc = '',
    [hashtable]$CfgOverrides = @{},
    [hashtable]$ProfileOverrides = @{},
    [string]$ProfileName = 'ViVi141'
)

$ErrorActionPreference = 'Stop'
$cfgPath = Join-Path $env:USERPROFILE 'Documents\Arma 3\Arma3.cfg'
$profPath = Join-Path $env:USERPROFILE "Documents\Arma 3 - Other Profiles\$ProfileName\$ProfileName.Arma3Profile"

$cfgBak = Get-Content $cfgPath -Raw
$profBak = Get-Content $profPath -Raw

function Apply-KV([string]$text, [hashtable]$map) {
    foreach ($k in $map.Keys) {
        $v = $map[$k]
        if ($text -match "(?m)^$k=[^;]*;") {
            $text = [regex]::Replace($text, "(?m)^$k=[^;]*;", "$k=$v;")
        } else {
            $text += "`r`n$k=$v;"
        }
    }
    return $text
}

try {
    if ($CfgOverrides.Count -gt 0) {
        $newCfg = Apply-KV $cfgBak $CfgOverrides
        Set-Content -Path $cfgPath -Value $newCfg -NoNewline -Encoding UTF8
        Write-Host "[$Tag] Temp Arma3.cfg overrides: $($CfgOverrides | ConvertTo-Json -Compress)" -ForegroundColor Yellow
    }
    if ($ProfileOverrides.Count -gt 0) {
        $newProf = Apply-KV $profBak $ProfileOverrides
        Set-Content -Path $profPath -Value $newProf -NoNewline -Encoding UTF8
        Write-Host "[$Tag] Temp Profile overrides: $($ProfileOverrides | ConvertTo-Json -Compress)" -ForegroundColor Yellow
    }

    $params = @{ Tag = $Tag; ProfileName = $ProfileName; TimeoutSec = 220 }
    if ($UseDXVK) { $params['UseDXVK'] = $true }
    if ($Malloc) { $params['Malloc'] = $Malloc }
    & (Join-Path $PSScriptRoot 'bench_route2.ps1') @params
}
finally {
    Set-Content -Path $cfgPath -Value $cfgBak -NoNewline -Encoding UTF8
    Set-Content -Path $profPath -Value $profBak -NoNewline -Encoding UTF8
    Write-Host "[$Tag] Restored original Arma3.cfg and $ProfileName.Arma3Profile" -ForegroundColor DarkGray
}

