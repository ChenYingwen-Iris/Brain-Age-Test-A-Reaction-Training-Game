                    @echo off
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

rem Prefer py launcher, then python
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py "ReactionTest-Mini-Game.py"
  goto :eof
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "ReactionTest-Mini-Game.py"
  goto :eof
)

echo [ERROR] Python not found. Please install Python 3 and ensure it's on PATH.
endlocal
