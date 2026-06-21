$ErrorActionPreference = 'Stop'

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Install-Binary -file "$toolsDir\everkm-publish.exe" -exe 'everkm-publish.exe'
