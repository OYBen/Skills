[CmdletBinding()]
param(
  [string] $TaskName = "DingTalkCodexController",
  [switch] $StartNow
)

$ErrorActionPreference = "Stop"
$launcherPath = Join-Path $PSScriptRoot "launch-controller.vbs"
if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
  throw "Task launcher is missing: $launcherPath"
}

$wscriptPath = Join-Path $env:SystemRoot "System32\wscript.exe"
if (-not (Test-Path -LiteralPath $wscriptPath -PathType Leaf)) {
  throw "Windows Script Host is unavailable: $wscriptPath"
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$userName = $identity.Name
$arguments = '//B //NoLogo "{0}"' -f $launcherPath

$action = New-ScheduledTaskAction -Execute $wscriptPath -Argument $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userName
$watchdogTrigger = New-ScheduledTaskTrigger `
  -Once `
  -At (Get-Date).AddSeconds(20) `
  -RepetitionInterval (New-TimeSpan -Minutes 1) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)

$task = New-ScheduledTask -Action $action -Trigger @($logonTrigger, $watchdogTrigger) -Principal $principal -Settings $settings `
  -Description "Persistent DingTalk-to-Codex controller for the current interactive user."
Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

if ($StartNow) { Start-ScheduledTask -TaskName $TaskName }

[pscustomobject]@{
  taskName = $TaskName
  user = $userName
  triggers = @("AtLogOn", "EveryMinuteWatchdog")
  restartIntervalSeconds = 60
  restartCount = 999
  multipleInstances = "IgnoreNew"
  windowMode = "NoConsoleWScriptHost"
  started = [bool]$StartNow
} | ConvertTo-Json
