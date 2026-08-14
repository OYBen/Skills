[CmdletBinding()]
param(
  [string] $Destination = (Join-Path $env:LOCALAPPDATA "DingTalkCodexController"),
  [string] $TaskName = "DingTalkCodexController",
  [switch] $RegisterTask,
  [switch] $StartNow
)

$ErrorActionPreference = "Stop"
$source = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\assets\controller"))
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$destinationRoot = [System.IO.Path]::GetPathRoot($destinationPath)
if ($destinationPath -eq $destinationRoot) { throw "Destination must not be a drive root." }
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Bundled controller asset is missing." }

New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
Get-ChildItem -LiteralPath $source -Force | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $destinationPath -Recurse -Force
}

Push-Location $destinationPath
try {
  & node --version | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Node.js is unavailable." }
  & node --test | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Bundled controller tests failed." }
} finally {
  Pop-Location
}

$taskRegistration = $null
if ($RegisterTask) {
  $configPath = Join-Path $destinationPath "config\config.json"
  if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "RegisterTask requires a validated config\config.json in the destination."
  }
  $taskRegistrationJson = & (Join-Path $destinationPath "ops\install-scheduled-task.ps1") `
    -TaskName $TaskName -StartNow:$StartNow
  $taskRegistration = ConvertFrom-Json -InputObject ($taskRegistrationJson -join [Environment]::NewLine)
}

[pscustomobject]@{
  destination = $destinationPath
  version = "0.2.0"
  testsPassed = $true
  taskRegistered = [bool]$RegisterTask
  started = [bool]($RegisterTask -and $StartNow)
  taskRegistration = $taskRegistration
  preserved = @("config/config.json", "data", "logs", "payload history")
} | ConvertTo-Json -Depth 4
