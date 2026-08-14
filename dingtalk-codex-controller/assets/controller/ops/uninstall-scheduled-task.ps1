[CmdletBinding(SupportsShouldProcess)]
param([string] $TaskName = "DingTalkCodexController")

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
  [pscustomobject]@{ taskName = $TaskName; removed = $false; reason = "not-found" } | ConvertTo-Json
  exit 0
}

if ($PSCmdlet.ShouldProcess($TaskName, "Stop and unregister scheduled task")) {
  if ($task.State -eq "Running") { Stop-ScheduledTask -TaskName $TaskName }
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  [pscustomobject]@{ taskName = $TaskName; removed = $true } | ConvertTo-Json
}
