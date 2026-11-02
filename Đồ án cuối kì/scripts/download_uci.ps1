param(
    [string]$ZipPath = '',
    [string]$DownloadedAt = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$config = Get-Content -Raw -LiteralPath (Join-Path $root 'configs/uci_501.json') | ConvertFrom-Json
$raw = Join-Path $root 'data/raw'
$reports = Join-Path $root 'reports'
New-Item -ItemType Directory -Force -Path $raw, $reports | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Copy-Entry($entry, [string]$destination) {
    $inputStream = $entry.Open()
    try {
        if (Test-Path -LiteralPath $destination) {
            $sha = [System.Security.Cryptography.SHA256]::Create()
            try { $entryHash = [BitConverter]::ToString($sha.ComputeHash($inputStream)).Replace('-', '') }
            finally { $sha.Dispose() }
            if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $entryHash) {
                throw "Existing raw file differs; refusing overwrite: $destination"
            }
        } else {
            $outputStream = [System.IO.File]::Open($destination, [System.IO.FileMode]::CreateNew)
            try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
        }
    } finally { $inputStream.Dispose() }
}

$acquisition = 'manual'
$downloadTime = $null
if ($DownloadedAt) {
    if ($DownloadedAt -notmatch '(Z|[+-]\d{2}:\d{2})$') { throw 'DownloadedAt must include an explicit timezone offset or Z.' }
    $downloadTime = [DateTimeOffset]::Parse($DownloadedAt).ToUniversalTime().ToString('o')
}
if ($ZipPath) {
    $archivePath = (Resolve-Path -LiteralPath $ZipPath).Path
} else {
    $archivePath = Join-Path $raw 'uci_501_download.zip'
    if (-not (Test-Path -LiteralPath $archivePath)) {
        $temporaryPath = "$archivePath.part"
        if (Test-Path -LiteralPath $temporaryPath) { throw "Incomplete download exists: $temporaryPath" }
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        try { Invoke-WebRequest -UseBasicParsing -Uri $config.download_url -OutFile $temporaryPath -TimeoutSec 180 }
        catch { throw "UCI download failed: $($_.Exception.Message). See README manual ZIP instructions." }
        Move-Item -LiteralPath $temporaryPath -Destination $archivePath
        $downloadTime = [DateTimeOffset]::UtcNow.ToString('o')
        $acquisition = 'download'
    } else { $acquisition = 'existing_archive' }
}

$manifestPath = Join-Path $reports 'data_manifest.json'
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$old = $null
if (Test-Path -LiteralPath $manifestPath) {
    $old = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    # A manual fallback may supply the already-recorded inner PRSA archive.
    if ($archiveHash -notin @($old.archive.sha256, $old.prsa_archive.sha256)) { throw 'Archive differs from existing manifest; refusing to replace provenance.' }
    $downloadTime = $old.downloaded_at
    $acquisition = $old.acquisition
}
$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    $nested = @($archive.Entries | Where-Object { $_.Name -eq $config.archive_name })
    if ($nested.Count -gt 1) { throw 'Duplicate PRSA2017 archives.' }
    if ($nested.Count -eq 1) {
        $prsaPath = Join-Path $raw $config.archive_name
        Copy-Entry $nested[0] $prsaPath
    } else { $prsaPath = $archivePath }
} finally { $archive.Dispose() }

$prsaHash = (Get-FileHash -LiteralPath $prsaPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($null -ne $old -and $old.prsa_archive.sha256 -ne $prsaHash) { throw 'PRSA archive differs from existing manifest; refusing to replace provenance.' }
$archive = [System.IO.Compression.ZipFile]::OpenRead($prsaPath)
$files = @()
try {
    $entries = @($archive.Entries | Where-Object { $_.Name -match '^PRSA_Data_.+_20130301-20170228\.csv$' })
    if ($entries.Count -eq 0) { throw 'Not a PRSA2017 multi-site archive; no station CSV files found.' }
    if ($entries.Count -ne $config.published_stations) { throw "Station file count $($entries.Count) differs from UCI metadata $($config.published_stations); refusing incomplete archive." }
    $names = @($entries | ForEach-Object { $_.Name })
    if (@($names | Select-Object -Unique).Count -ne $names.Count) { throw 'Duplicate station filenames in ZIP.' }
    foreach ($entry in $entries) {
        # Use only validated leaf names; archive paths never become filesystem paths.
        $destination = Join-Path $raw $entry.Name
        Copy-Entry $entry $destination
        $files += [ordered]@{ path = "data/raw/$($entry.Name)"; bytes = (Get-Item -LiteralPath $destination).Length; sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
} finally { $archive.Dispose() }

if ($null -ne $old) {
    foreach ($field in @('dataset_id', 'name', 'source_url', 'download_url', 'license', 'license_url', 'doi')) {
        if ($old.$field -ne $config.$field) { throw "Existing provenance metadata differs: $field. Review before changing the manifest." }
    }
    if (@($old.files).Count -ne $files.Count) { throw 'Station inventory differs from existing manifest.' }
    foreach ($file in $files) {
        $prior = @($old.files | Where-Object { $_.path -eq $file.path })
        if ($prior.Count -ne 1 -or $prior[0].sha256 -ne $file.sha256 -or $prior[0].bytes -ne $file.bytes) {
            throw "Station provenance differs from existing manifest: $($file.path)"
        }
    }
    # A verification rerun must not change recorded_at or the original archive
    # descriptor/acquisition date, even when it uses the inner ZIP directly.
    Write-Output "Verified $($files.Count) station files. Existing manifest preserved: $manifestPath"
    return
}

$manifest = [ordered]@{
    dataset_id = $config.dataset_id; name = $config.name
    source_url = $config.source_url; download_url = $config.download_url
    license = $config.license; license_url = $config.license_url; doi = $config.doi
    acquisition = $acquisition; downloaded_at = $downloadTime
    recorded_at = [DateTimeOffset]::UtcNow.ToString('o')
    download_date_note = 'downloaded_at is UTC; null means acquisition date unknown, not inferred from file modification time.'
    archive = [ordered]@{ name = [IO.Path]::GetFileName($archivePath); bytes = (Get-Item -LiteralPath $archivePath).Length; sha256 = $archiveHash }
    prsa_archive = [ordered]@{ name = [IO.Path]::GetFileName($prsaPath); sha256 = $prsaHash }
    files = $files
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $manifestPath
Write-Output "Extracted/verified $($files.Count) station files. Manifest: $manifestPath"
