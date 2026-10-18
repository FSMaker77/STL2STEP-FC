@echo off
cd /d "%~dp0"
"%~dp0python.exe" "%~dp0diagnostica_dll.py" > "%~dp0diagnostica.txt" 2>&1
start "" notepad "%~dp0diagnostica.txt"
