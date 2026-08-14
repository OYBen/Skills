[CmdletBinding()]
param(
  [string] $Destination = (Join-Path $env:LOCALAPPDATA "DingTalkCodexController"),
  [string] $TaskName = "DingTalkCodexController"
)

$ErrorActionPreference = "Stop"
$script = Join-Path ([System.IO.Path]::GetFullPath($Destination)) "ops\status-scheduled-task.ps1"
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Deployed status script was not found." }
& $script -TaskName $TaskName
