# ci_quick_check.ps1
# Quick local CI health check: installs dev deps (editable), runs pytest, mypy, flake8, black --check,
# and prints a concise PASS/FAIL summary with reliable numeric exit codes.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "Running quick CI health check" -ForegroundColor Cyan

Write-Host "`n[1/5] Installing dev dependencies (editable install)" -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -e .[dev] 2>&1 | Write-Host

function Run-Check($name, $exe, $arguments) {
    <#
    $name       - friendly name for output
    $exe        - executable or command (string)
    $arguments  - single string of arguments (e.g. "-q") or $null/empty
    #>

    Write-Host "`nRunning $name..." -ForegroundColor Yellow

    # Build a safe ArgumentList array for Start-Process
    if ([string]::IsNullOrWhiteSpace($arguments)) {
        $argList = @()
    } else {
        # Split on whitespace but preserve quoted groups
        # Use simple split for common cases; if you need complex quoting, pass an array instead.
        $argList = $arguments -split ' '
    }

    # Start the process, wait for it to finish, and capture the numeric exit code.
    # Use -NoNewWindow so output appears in the same console when possible.
    $proc = Start-Process -FilePath $exe -ArgumentList $argList -NoNewWindow -Wait -PassThru

    $code = $proc.ExitCode

    if ($code -eq 0) {
        Write-Host "$($name): PASS" -ForegroundColor Green
    } else {
        Write-Host "$($name): FAIL (exit code $code)" -ForegroundColor Red
    }

    return $code
}

# Run checks (exe and args separated to avoid quoting issues)
$pytest_code = Run-Check "pytest" "pytest" "-q"
$mypy_code   = Run-Check "mypy" "mypy" ". --no-incremental"
$flake_code  = Run-Check "flake8" "flake8" "."
$black_code  = Run-Check "black --check" "black" "--check ."

Write-Host "`n===== Quick CI Summary =====" -ForegroundColor Cyan

$results = @{
    "pytest" = $pytest_code
    "mypy" = $mypy_code
    "flake8" = $flake_code
    "black --check" = $black_code
}

foreach ($k in $results.Keys) {
    if ($results[$k] -eq 0) {
        Write-Host ("{0,-15} : {1}" -f $k, "PASS") -ForegroundColor Green
    } else {
        Write-Host ("{0,-15} : {1} (exit {2})" -f $k, "FAIL", $results[$k]) -ForegroundColor Red
    }
}

if ($results.Values | Where-Object { $_ -ne 0 }) {
    Write-Host "`nOne or more checks failed." -ForegroundColor Red
    exit 1
} else {
    Write-Host "`nAll checks passed." -ForegroundColor Green
    exit 0
}