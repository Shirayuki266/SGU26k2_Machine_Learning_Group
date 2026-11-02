param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot), [string]$LibreOfficePath = '')
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$cfg = Get-Content -LiteralPath (Join-Path $taskRoot 'configs/midterm.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$taskOutput = Join-Path $taskRoot 'reports/midterm/previews'
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskDoc = Join-Path $taskRoot ('reports/midterm/' + $cfg.filename_stem + '.docx')
$taskPpt = Join-Path $taskRoot ('reports/midterm/' + $cfg.filename_stem + '.pptx')
$beforeDoc = (Get-FileHash -LiteralPath $taskDoc -Algorithm SHA256).Hash
$beforePpt = (Get-FileHash -LiteralPath $taskPpt -Algorithm SHA256).Hash
if (-not $LibreOfficePath) {
    $candidate = Get-ChildItem -LiteralPath (Join-Path $taskRoot 'artifacts/midterm_tools/libreoffice_admin') -Filter 'soffice.com' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) { $LibreOfficePath = $candidate.FullName }
}
if (-not $LibreOfficePath -or -not (Test-Path -LiteralPath $LibreOfficePath)) { throw 'Pass -LibreOfficePath to trusted soffice.com. Word export was unresponsive on this machine.' }
$taskProfile = Join-Path $taskRoot 'artifacts/midterm_tools/lo_profile'
New-Item -ItemType Directory -Path $taskProfile -Force | Out-Null
$taskUri = ([Uri]($taskProfile + [IO.Path]::DirectorySeparatorChar)).AbsoluteUri
$taskArgs = @(('-env:UserInstallation=' + $taskUri), '--headless', '--convert-to', 'pdf:writer_pdf_Export', '--outdir', ('"' + $taskOutput + '"'), ('"' + $taskDoc + '"'))
$taskLo = Start-Process -FilePath $LibreOfficePath -ArgumentList $taskArgs -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $taskProfile 'render.stdout') -RedirectStandardError (Join-Path $taskProfile 'render.stderr')
if ($taskLo.ExitCode -ne 0) { throw 'LibreOffice render failed; inspect task-local logs' }
$generated = Join-Path $taskOutput ($cfg.filename_stem + '.pdf')
if (-not (Test-Path -LiteralPath $generated)) { throw 'Expected PDF not produced' }
Move-Item -LiteralPath $generated -Destination (Join-Path $taskOutput 'report.pdf') -Force
$pptApp = $null; $pptDeck = $null; $pptVersion = $null; $slideCount = 0
try {
    $pptApp = New-Object -ComObject PowerPoint.Application
    $pptApp.AutomationSecurity = 3
    $pptVersion = $pptApp.Version
    $pptDeck = $pptApp.Presentations.Open($taskPpt, -1, 0, 0)
    $slideCount = $pptDeck.Slides.Count
    $pptDeck.SaveAs((Join-Path $taskOutput 'slides.pdf'),32)
    $pptDeck.Close(); $pptDeck = $null
} finally {
    if ($null -ne $pptDeck) { $pptDeck.Saved = -1; $pptDeck.Close() }
    if ($null -ne $pptApp) {
        if ($pptApp.Presentations.Count -eq 0) { $pptApp.Quit() }
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($pptApp)
    }
}
if ((Get-FileHash -LiteralPath $taskDoc).Hash -ne $beforeDoc -or (Get-FileHash -LiteralPath $taskPpt).Hash -ne $beforePpt) { throw 'Original Office file changed' }
$taskPython = Join-Path $taskRoot '.venv/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe' }
$pages = & $taskPython -c 'import pymupdf,sys; print(len(pymupdf.open(sys.argv[1])))' (Join-Path $taskOutput 'report.pdf')
if ($LASTEXITCODE -ne 0) { throw 'Cannot count rendered pages' }
$result = [ordered]@{
    renderer = 'LibreOffice DOCX / Microsoft PowerPoint PPTX'
    libreoffice_version = (Get-Item -LiteralPath $LibreOfficePath).VersionInfo.ProductVersion
    powerpoint_version = $pptVersion
    word_export = 'Unresponsive on authoring machine; no successful Word export claim'
    docx_pages = [int]$pages; pptx_slides = $slideCount
    docx_sha256 = $beforeDoc.ToLower(); pptx_sha256 = $beforePpt.ToLower()
    report_pdf_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskOutput 'report.pdf')).Hash.ToLower()
    slides_pdf_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskOutput 'slides.pdf')).Hash.ToLower()
    originals_unchanged = $true
}
[IO.File]::WriteAllText((Join-Path $taskOutput 'render_manifest.json'), (($result | ConvertTo-Json -Depth 5) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
$result | ConvertTo-Json -Depth 5
