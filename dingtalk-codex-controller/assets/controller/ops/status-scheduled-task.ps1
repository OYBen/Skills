[CmdletBinding()]
param([string] $TaskName = "DingTalkCodexController")

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName
$lastTaskResultHex = "0x{0:X8}" -f ([uint32]$info.LastTaskResult)
$controllerProcesses = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match '(launch-controller\.vbs|ops[\\/]supervisor\.js|src[\\/]cli\.js\s+serve\s+--config)' } |
  ForEach-Object {
    $process = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    [pscustomobject]@{
      processId = $_.ProcessId
      parentProcessId = $_.ParentProcessId
      name = $_.Name
      creationDate = $_.CreationDate
      hasMainWindow = [bool]($process -and $process.MainWindowHandle -ne 0)
    }
  }

[pscustomobject]@{
  taskName = $TaskName
  taskState = [string]$task.State
  enabled = $task.Settings.Enabled
  lastRunTime = $info.LastRunTime
  lastTaskResult = $info.LastTaskResult
  lastTaskResultHex = $lastTaskResultHex
  lastTaskResultMeaning = if ($lastTaskResultHex -eq "0x800710E0" -and $task.State -eq "Running") {
    "watchdog-trigger-ignored-while-instance-running"
  } elseif ($info.LastTaskResult -eq 267009 -and $task.State -eq "Running") {
    "task-running"
  } else {
    "inspect-task-result"
  }
  nextRunTime = $info.NextRunTime
  triggers = @($task.Triggers | ForEach-Object { $_.CimClass.CimClassName })
  controllerProcesses = @($controllerProcesses)
} | ConvertTo-Json -Depth 4
