@echo off
setlocal
cd /d "%~dp0"
echo Building Rust Bridge...
cd discography_webapp\rust_bridge
maturin develop --release
echo Build complete.
pause
endlocal
