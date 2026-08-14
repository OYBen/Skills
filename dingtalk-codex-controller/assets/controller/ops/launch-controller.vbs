Option Explicit

Dim shell, fileSystem, opsDirectory, supervisorPath, nodePath, command, exitCode
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

opsDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
supervisorPath = fileSystem.BuildPath(opsDirectory, "supervisor.js")
nodePath = shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\nodejs\node.exe"

If Not fileSystem.FileExists(nodePath) Then WScript.Quit 2
If Not fileSystem.FileExists(supervisorPath) Then WScript.Quit 3

command = Chr(34) & nodePath & Chr(34) & " " & Chr(34) & supervisorPath & Chr(34)
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
