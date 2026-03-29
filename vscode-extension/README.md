# Icosele Vault VSCode Extension

Control your Icosele Vault virtual machines directly from VSCode.

## Prerequisites

- Icosele Vault running with the REST API enabled on port 47820
- VSCode 1.80+

## Installation

1. Package: `cd vscode-extension && npx vsce package`
2. Install: VSCode > Extensions > ... > Install from VSIX

## Commands

| Command | Description |
|---------|-------------|
| `Icosele Vault: List VMs` | Show all VMs in a quick pick |
| `Icosele Vault: Start VM` | Pick and start a VM |
| `Icosele Vault: Stop VM` | Pick and stop a VM |
| `Icosele Vault: Take Snapshot` | Create a named snapshot |
| `Icosele Vault: Open Dashboard` | Open the web dashboard |
| `Icosele Vault: Show Status` | Update status bar item |

## Status Bar

Shows running/total VM count, updates every 30 seconds. Click to open VM list.

## API

Communicates via HTTP to `localhost:47820`. No external dependencies.
