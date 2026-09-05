param(
    [Parameter(Mandatory = $true)][string]$PiHost,
    [string]$PiUser = "pi",
    [string]$RemoteDir = "/opt/spielraum"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bundle = Join-Path ([IO.Path]::GetTempPath()) "spielraum-source.tar.gz"

Push-Location $projectRoot
try {
    tar.exe -czf $bundle `
        --exclude=.git --exclude=.venv --exclude=.idea --exclude=.uv-cache `
        --exclude=web/node_modules --exclude=web/.npm-cache --exclude=web/dist `
        --exclude=runtime --exclude=runtime-test --exclude=outputs --exclude=v2/output .
    ssh "$PiUser@$PiHost" "mkdir -p '$RemoteDir'"
    scp $bundle "${PiUser}@${PiHost}:/tmp/spielraum-source.tar.gz"
    ssh "$PiUser@$PiHost" "tar -xzf /tmp/spielraum-source.tar.gz -C '$RemoteDir' && cd '$RemoteDir' && docker compose up -d --build"
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $bundle) { Remove-Item -LiteralPath $bundle }
}
