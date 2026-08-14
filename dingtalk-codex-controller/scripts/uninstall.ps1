[CmdletBinding(SupportsShouldProcess)]
param(
  [string] $Destination = (Join-Path $env:LOCALAPPDATA "DingTalkCodexController"),
  [string] $TaskName = "DingTalkCodexController"
)

$ErrorActionPreference = "Stop"
$script = Join-Path ([System.IO.Path]::GetFullPath($Destination)) "ops\uninstall-scheduled-task.ps1"
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Deployed uninstall script was not found." }
if ($PSCmdlet.ShouldProcess($TaskName, "Stop and unregister controller task")) {
  & $script -TaskName $TaskName -Confirm:$false
}
