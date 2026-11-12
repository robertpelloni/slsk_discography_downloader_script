@echo off
setlocal
cd /d "%~dp0"

echo Building Rust Bridge (bob_soulseek_rs)...
if "%PYO3_USE_ABI3_FORWARD_COMPATIBILITY%"=="" set "PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1"
if "%PYO3_PYTHON%"=="" (
    if exist "C:\Python314\python.exe" (
        set "PYO3_PYTHON=C:\Python314\python.exe"
    ) else if exist "discography_webapp\venv\Scripts\python.exe" (
        set "PYO3_PYTHON=%~dp0discography_webapp\venv\Scripts\python.exe"
    )
)

cargo build --release --manifest-path "discography_webapp\rust_bridge\Cargo.toml"
if %ERRORLEVEL% EQU 0 (
    if exist "discography_webapp\rust_bridge\target\release\bob_soulseek_rs.dll" (
        copy /Y "discography_webapp\rust_bridge\target\release\bob_soulseek_rs.dll" "discography_webapp\bob_soulseek_rs.pyd" >nul
        echo Built and updated discography_webapp\bob_soulseek_rs.pyd successfully.
    )
) else (
    echo Warning: cargo build exited with code %ERRORLEVEL%; preserving existing built binaries.
)

echo Rust Bridge build step finished.
if /I not "%~1"=="--no-pause" if "%CI%"=="" pause
endlocal
