@echo off
setlocal

set "PORT=%PORT%"
if "%PORT%"=="" set "PORT=8000"
set "PYTHON_BIN=%PYTHON_BIN%"
if "%PYTHON_BIN%"=="" set "PYTHON_BIN=python"
set "INSTALL_DEPS=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--install" (
  set "INSTALL_DEPS=1"
  shift
  goto parse_args
)
if /I "%~1"=="-h" goto usage
if /I "%~1"=="--help" goto usage
echo Unknown argument: %~1
goto usage_error

:args_done
where %PYTHON_BIN% >nul 2>nul
if errorlevel 1 (
  where python3 >nul 2>nul
  if errorlevel 1 (
    echo Python executable not found. Set PYTHON_BIN or install Python.
    exit /b 1
  )
  set "PYTHON_BIN=python3"
)

pushd "%~dp0"
if errorlevel 1 exit /b 1

if "%INSTALL_DEPS%"=="1" (
  %PYTHON_BIN% -m pip install -r requirements.txt
  if errorlevel 1 (
    popd
    exit /b 1
  )
)

if not exist "inspection_jobs" mkdir "inspection_jobs"
for /d %%D in ("inspection_jobs\*") do rmdir /s /q "%%~fD"
for %%F in ("inspection_jobs\*") do if exist "%%~fF" del /f /q "%%~fF"

%PYTHON_BIN% qms.py serve --port %PORT%
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:usage
echo Usage: start.bat [--install]
echo.
echo Deletes previous inspection job output and starts the offline server.
echo.
echo Options:
echo   --install   Install requirements.txt before starting
echo.
echo Environment:
echo   PORT        Server port ^(default: 8000^)
echo   PYTHON_BIN  Python executable to use ^(default: python^)
exit /b 0

:usage_error
call :usage
exit /b 1
