' Double-click this to launch the Work Timer with no console window.
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir
shell.Run "pythonw """ & scriptDir & "\work_timer.py""", 0, False
