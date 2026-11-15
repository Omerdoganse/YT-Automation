@echo off
rem Shorts Studyo'yu konsol penceresi olmadan baslatir.
cd /d "%~dp0"
start "" pythonw main.py %*
