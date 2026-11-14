' Xiaoqing Ollama Launcher
' Detached start for the Ollama inference server.
' Reason: spawning ollama.exe directly from an agent shell puts it inside the
' Windows Job Object, so it dies when the agent session ends. wscript.exe runs
' outside that job and keeps the server alive.
' Install as a login item to start Ollama automatically with Windows.

Set shell = CreateObject("WScript.Shell")
shell.Run """C:\Users\User\AppData\Local\Programs\Ollama\ollama.exe"" serve", 0, False
