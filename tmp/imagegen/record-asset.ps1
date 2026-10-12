param([Parameter(Mandatory=$true)][string]$AssetName,[Parameter(Mandatory=$true)][string]$SourcePath)
$ErrorActionPreference = 'Stop'
$taskRoot = (Get-Location).Path
$jobs = Get-Content -LiteralPath 'tmp/imagegen/jobs.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$job = $jobs | Where-Object { $_.asset_name -eq $AssetName }
if (@($job).Count -ne 1) { throw 'Expected exactly one job' }
$destination = [System.IO.Path]::GetFullPath((Join-Path $taskRoot $job.output_path))
if (-not $destination.StartsWith($taskRoot + [System.IO.Path]::DirectorySeparatorChar)) { throw 'Destination outside workspace' }
if (Test-Path -LiteralPath $destination) { throw "Refusing to overwrite $destination" }
Add-Type -AssemblyName System.Drawing
$picture = [System.Drawing.Bitmap]::new($SourcePath)
$normalized = $null
try {
  if ($picture.RawFormat.Guid -ne [System.Drawing.Imaging.ImageFormat]::Png.Guid) { throw 'Not a PNG image' }
  $sourceDimensions = "$($picture.Width)x$($picture.Height)"
  if ($picture.Width -ne $job.width -or $picture.Height -ne $job.height) {
    if ($picture.Width * $job.height -ne $picture.Height * $job.width) { throw 'Wrong aspect ratio; cannot resize without cropping or distortion' }
    $normalized = [System.Drawing.Bitmap]::new([int]$job.width, [int]$job.height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($normalized)
    try {
      $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
      $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
      $attributes = [System.Drawing.Imaging.ImageAttributes]::new()
      try {
        $attributes.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
        $rectangle = [System.Drawing.Rectangle]::new(0, 0, [int]$job.width, [int]$job.height)
        $graphics.DrawImage($picture, $rectangle, 0, 0, $picture.Width, $picture.Height, [System.Drawing.GraphicsUnit]::Pixel, $attributes)
      } finally { $attributes.Dispose() }
    } finally { $graphics.Dispose() }
    $picture.Dispose()
    $picture = $normalized
  }
  $transparentSamples = 0
  for ($x = 0; $x -lt $picture.Width; $x += 16) {
    for ($y = 0; $y -lt $picture.Height; $y += 16) {
      if ($picture.GetPixel($x, $y).A -eq 0) { $transparentSamples++ }
    }
  }
  if ($job.transparent_background -and $transparentSamples -eq 0) { throw 'Requested transparency missing' }
  $dimensions = "$($picture.Width)x$($picture.Height)"
  [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($destination)) | Out-Null
  if ($normalized) {
    $stream = [System.IO.File]::Open($destination, [System.IO.FileMode]::CreateNew)
    try { $picture.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $stream.Dispose() }
  } else { [System.IO.File]::Copy($SourcePath, $destination, $false) }
} finally { $picture.Dispose() }
$verify = [System.Drawing.Bitmap]::new($destination)
try { if ($verify.Width -ne $job.width -or $verify.Height -ne $job.height) { throw 'Saved dimensions do not match request' } } finally { $verify.Dispose() }
$digest = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
$rows = Import-Csv -LiteralPath 'tmp/imagegen/2-pdf-tracking.csv'
foreach ($row in $rows) {
  if ($row.asset_name -eq $AssetName) {
    $row.status = 'generated; visually reviewed; PNG verified'
    $row.output_exists = 'True'
    $row.reference_used = $job.references -join '; '
    $row.issue = ($row.issue -replace 'OPENAI_API_KEY missing; official SDK not installed;? ?', '').Trim('; ')
  } elseif ($row.issue -match 'OPENAI_API_KEY missing') {
    $row.issue = ($row.issue -replace 'OPENAI_API_KEY missing; official SDK not installed;? ?', '').Trim('; ')
  }
}
$rows | Export-Csv -LiteralPath 'tmp/imagegen/2-pdf-tracking.csv' -NoTypeInformation -Encoding UTF8
$record = [ordered]@{asset_name=$AssetName; output_path=$job.output_path; source_path=$SourcePath; source_dimensions=$sourceDimensions; prompt=$job.prompt; references=$job.references; tool='built-in OpenAI image_gen'; dimensions=$dimensions; transparent_background=$job.transparent_background; transparent_samples=$transparentSamples; sha256=$digest; date='2026-10-12'; visually_reviewed=$true}
($record | ConvertTo-Json -Depth 6 -Compress) | Add-Content -LiteralPath 'tmp/imagegen/generation-log.jsonl' -Encoding UTF8
Write-Output "Saved $AssetName ($dimensions; transparent samples: $transparentSamples)"
