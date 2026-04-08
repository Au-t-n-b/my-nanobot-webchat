# 交付claw — 一键安装依赖（Windows）
# 用法：在仓库根目录执行
#   powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
# 或：npm run setup

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "[交付claw] 仓库根目录: $Root"

if (-not (Test-Command python)) {
    Write-Error "未找到 python。请先安装 Python 3.11 或更高版本，并加入 PATH。"
}
# python -c 参数在 PS 5.1 传至 python.exe 时会错误处理「外层单引号 + 内层双引号」；此处 Python 代码不使用任何双引号（见 README）
# 本脚本须以 UTF-8 with BOM 保存（见 README「常见问题」）
$pyver = & python -c 'import sys; v=sys.version_info; print(str(v.major)+chr(46)+str(v.minor))' 2>$null
if (-not $pyver) {
    Write-Error "无法检测 Python 版本。"
}
$maj, $min = $pyver.Split(".")
if ([int]$maj -lt 3 -or ([int]$maj -eq 3 -and [int]$min -lt 11)) {
    Write-Error "需要 Python >= 3.11，当前: $pyver"
}
Write-Host "[交付claw] Python: $pyver"

Write-Host "[交付claw] 安装/升级 pip 并安装 nanobot（可编辑模式）..."
python -m pip install -U pip
python -m pip install -e "."

if (-not (Test-Command node)) {
    Write-Error "未找到 node。请先安装 Node.js LTS，并加入 PATH。"
}
$nodeVer = node -v
Write-Host "[交付claw] Node: $nodeVer"

Write-Host "[交付claw] 安装前端依赖（frontend）..."
Push-Location (Join-Path $Root "frontend")
try {
    npm ci
} finally {
    Pop-Location
}

Write-Host "[交付claw] 跳过根目录 npm install（dev 不再依赖 concurrently；避免公司网络/权限导致安装失败）"

$envLocal = Join-Path $Root "frontend\.env.local"
$envExample = Join-Path $Root "frontend\.env.local.example"
if (-not (Test-Path $envLocal) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envLocal
    Write-Host "[交付claw] 已创建 frontend/.env.local（可按需修改 NEXT_PUBLIC_*）"
}

Write-Host ""
Write-Host "[交付claw] 安装完成。下一步在仓库根目录执行: npm run dev"
Write-Host "  浏览器访问: http://localhost:3000  （AGUI 后端默认 http://127.0.0.1:8765 ）"
Write-Host "  首次使用请在界面中打开「配置中心」填写模型与 API Key。"
Write-Host ""
