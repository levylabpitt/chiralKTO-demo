# Launch the demo. Nothing to install first - uv fetches everything on the
# first run and caches it, so run this once before you are in front of people.
#
#   .\demo.ps1            edit mode (cells + code visible)
#   .\demo.ps1 present    presentation mode (code hidden, big)
#   .\demo.ps1 test       run the analysis self-test only

param([ValidateSet("edit", "present", "test")][string]$Mode = "edit")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$deps = @(
    "--with", "marimo",
    "--with", "numpy",
    "--with", "pandas",
    "--with", "altair",
    "--with", "scipy",
    "--with", "pyarrow",
    "--with", "npTDMS"
)

switch ($Mode) {
    "test" {
        uv run --active selftest.py
    }
    "present" {
        uv run --active @deps marimo run --no-sandbox chirality_demo.py
    }
    default {
        uv run --active @deps marimo edit --no-sandbox chirality_demo.py
    }
}
