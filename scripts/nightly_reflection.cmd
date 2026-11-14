@echo off
rem Xiaoqing Nightly Reflection launcher - ASCII only, no quoting issues.
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"C:/Users/User/xiaoqing/brain/venv/Scripts/python.exe" "C:/Users/User/xiaoqing/brain/scripts/nightly_reflection.py"
exit /b %ERRORLEVEL%
