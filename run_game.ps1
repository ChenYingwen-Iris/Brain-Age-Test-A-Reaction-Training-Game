param(
    [string]$Python = ""
)

# Change to the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Target game file (quoted for parentheses in name)
$target = Join-Path $scriptDir "ReactionTest-Mini-Game(1).py"

function Try-Run([string]$exe) {
    try {
        & $exe --version > $null 2>&1
        & $exe $target
        exit $LASTEXITCODE
    } catch {
        return $false
    }
}

if ($Python) {
    & $Python $target
    exit $LASTEXITCODE
}

# Prefer python, then py
if (Try-Run "python") { return }
if (Try-Run "py") { return }

Write-Error "未找到 Python。请安装 Python 3 或将其添加到 PATH。您也可以这样运行：`n  .\run_game.ps1 -Python 'C:\\Path\\To\\python.exe'"