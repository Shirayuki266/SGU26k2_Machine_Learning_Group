param([ValidateSet('smoke', 'full')][string]$Mode = 'full', [int]$SmokeRowsPerFile = 100)
$ErrorActionPreference = 'Stop'
if ($SmokeRowsPerFile -lt 1) { throw 'SmokeRowsPerFile must be positive.' }
$root = Split-Path -Parent $PSScriptRoot
$config = Get-Content -Raw -LiteralPath (Join-Path $root 'configs/uci_501.json') | ConvertFrom-Json
$manifest = Get-Content -Raw -LiteralPath (Join-Path $root 'reports/data_manifest.json') | ConvertFrom-Json
$files = @(Get-ChildItem -LiteralPath (Join-Path $root 'data/raw') -Filter 'PRSA_Data_*_20130301-20170228.csv' | Sort-Object Name)
if ($files.Count -eq 0) { throw 'No PRSA2017 station CSV files. Run download_uci.ps1 first.' }
$culture = [Globalization.CultureInfo]::InvariantCulture
$results = @(); $issues = [Collections.Generic.List[string]]::new()
$allStations = [Collections.Generic.HashSet[string]]::new()
$totalMissing = [ordered]@{}
foreach ($column in $config.columns) { $totalMissing[$column] = 0L }
foreach ($file in $files) {
    Write-Output "Auditing $($file.Name) ($Mode)"
    $hashBefore = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $record = @($manifest.files | Where-Object { $_.path -eq "data/raw/$($file.Name)" })
    if ($record.Count -ne 1 -or $record[0].sha256 -ne $hashBefore) { throw "Raw differs from manifest: $($file.Name)" }
    $header = (Get-Content -LiteralPath $file.FullName -TotalCount 1).Split(',') | ForEach-Object { $_.Trim('"') }
    if (($header -join ',') -ne ($config.columns -join ',')) { throw "Unexpected schema: $($file.Name)" }
    $missing = [ordered]@{}; $types = [ordered]@{}
    foreach ($column in $header) { $missing[$column] = 0L; $types[$column] = 'integer' }
    $stations = [Collections.Generic.HashSet[string]]::new()
    $timestamps = [Collections.Generic.HashSet[long]]::new()
    $rows = 0L; $invalidTimestamp = 0L; $duplicates = 0L; $gaps = 0L; $outOfOrder = 0L
    $minimum = $null; $maximum = $null; $previous = $null
    # Stream each row; do not load or rewrite all CSVs, impute, or drop NA.
    Import-Csv -LiteralPath $file.FullName | ForEach-Object {
        if ($Mode -eq 'full' -or $rows -lt $SmokeRowsPerFile) {
            $row = $_; $rows++
            foreach ($column in $header) {
                $value = [string]$row.$column
                if ($value -eq 'NA' -or [string]::IsNullOrWhiteSpace($value)) { $missing[$column]++; continue }
                $integer = 0L; $number = 0.0
                if ([long]::TryParse($value, [Globalization.NumberStyles]::Integer, $culture, [ref]$integer)) { }
                elseif ([double]::TryParse($value, [Globalization.NumberStyles]::Float, $culture, [ref]$number)) {
                    if ($types[$column] -ne 'string') { $types[$column] = 'real' }
                } else { $types[$column] = 'string' }
            }
            if ($row.station -and $row.station -ne 'NA') { [void]$stations.Add($row.station); [void]$allStations.Add($row.station) }
            try { $timestamp = [datetime]::new([int]$row.year, [int]$row.month, [int]$row.day, [int]$row.hour, 0, 0) }
            catch { $invalidTimestamp++; $timestamp = $null }
            if ($null -ne $timestamp) {
                if (-not $timestamps.Add($timestamp.Ticks)) { $duplicates++ }
                if ($null -eq $minimum -or $timestamp -lt $minimum) { $minimum = $timestamp }
                if ($null -eq $maximum -or $timestamp -gt $maximum) { $maximum = $timestamp }
                if ($null -ne $previous) {
                    $delta = ($timestamp - $previous).TotalHours
                    if ($delta -gt 1) { $gaps++ }
                    if ($delta -le 0) { $outOfOrder++ }
                }
                $previous = $timestamp
            }
        }
    }
    if ($stations.Count -ne 1) { $issues.Add("$($file.Name): station count $($stations.Count)") }
    if ($stations.Count -eq 1 -and $file.Name -ne "PRSA_Data_$(@($stations)[0])_20130301-20170228.csv") { $issues.Add("$($file.Name): station name differs from filename") }
    if ($invalidTimestamp + $duplicates + $gaps + $outOfOrder -gt 0) { $issues.Add("$($file.Name): timestamp integrity issue") }
    foreach ($column in $header) {
        $totalMissing[$column] += $missing[$column]
        if ($missing[$column] -eq $rows) { $types[$column] = 'all_missing' }
        if ($column -notin @('wd', 'station') -and $types[$column] -eq 'string') { $issues.Add("$($file.Name): nonnumeric $column") }
    }
    if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hashBefore) { throw 'Raw changed during audit.' }
    $results += [ordered]@{
        file = $file.Name; sha256 = $hashBefore; rows = $rows; columns = @($header)
        stations = @($stations | Sort-Object); inferred_value_types = $types; missing = $missing
        timestamp_min = $(if ($null -ne $minimum) { $minimum.ToString('yyyy-MM-dd HH:mm:ss') } else { $null })
        timestamp_max = $(if ($null -ne $maximum) { $maximum.ToString('yyyy-MM-dd HH:mm:ss') } else { $null })
        invalid_timestamps = $invalidTimestamp; duplicate_timestamps = $duplicates
        hourly_gap_transitions = $gaps; non_increasing_transitions = $outOfOrder
    }
}
$totalRows = 0L
foreach ($result in $results) { $totalRows += $result['rows'] }
if ($Mode -eq 'full') {
    if ($totalRows -ne $config.published_rows) { $issues.Add("Observed rows $totalRows differ from published $($config.published_rows)") }
    if ($files.Count -ne $config.published_stations -or $allStations.Count -ne $config.published_stations) { $issues.Add('Observed file/station count differs from UCI metadata.') }
}
$audit = [ordered]@{
    dataset_id = 501; mode = $Mode; audited_at = [DateTimeOffset]::UtcNow.ToString('o')
    runtime = $PSVersionTable.PSVersion.ToString(); source_url = $config.source_url
    observed_rows = $totalRows; observed_station_files = $files.Count; observed_stations = $allStations.Count
    published_rows = $config.published_rows; published_stations = $config.published_stations
    row_difference = $(if ($Mode -eq 'full') { $totalRows - $config.published_rows } else { $null })
    note = 'Types inferred from nonmissing CSV values, not pandas dtypes. Raw NA/blank counted without imputation. Smoke is not official full audit.'
    missing = $totalMissing; files = $results; issues = @($issues)
}
$output = Join-Path $root "reports/raw_audit_$Mode.json"
$audit | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 -LiteralPath $output
Write-Output "Observed: $totalRows rows, $($files.Count) files, $($allStations.Count) stations. Issues: $($issues.Count). Report: $output"
if ($issues.Count -gt 0) { throw 'Audit found discrepancies; see report. Counts were not forced to published values.' }
