# AXM - Axiom Package Manager

A simple and transparent package manager for Axeri Linux.

AXM is a Python-based package manager designed to handle `.axm` packages, repositories, dependencies, package installation and removal.

## Features

- Install and remove `.axm` packages
- Install packages directly from configured repositories
- Dependency resolution
- Repository management
- SHA256 package verification
- Installed package database
- Package history and transaction logging
- Package information and search
- Package upgrades
- `.axm` package building

## Status

AXM is currently in early development (`0.1.0`).

The core package management system is functional, but the project is still being developed and tested.

## Commands

### Install a package

```bash
sudo axm install <package>
```

### Remove a package

```bash
sudo axm remove <package_name>
```

### List installed packages

```bash
axm list
```

### Search for packages

```bash
axm search <query>
```

### List repositories

```bash
axm list-repo
```

### Add a repository

```bash
sudo axm add-repo <name> <url>
```

### Show package information

```bash
axm info <package_name>
```

### Show operation history

```bash
axm history
```

### Upgrade installed packages

```bash
sudo axm upgrade
```

### Build an `.axm` package

```bash
axm build <source_directory>
```

### Show version

```bash
axm --version
```

### Show help

```bash
axm --help
```

For non-interactive operations, `-y` or `--yes` can be used.

Example:

```bash
sudo axm install axiom-demo -y
```

## Package Format

AXM packages use the `.axm` format.

A package contains:

```text
package-name-version.axm
├── metadata.json
└── files.tar.xz
```

### Example metadata

```json
{
    "name": "example",
    "version": "1.0.0",
    "description": "An example AXM package",
    "dependencies": []
}
```

The `files.tar.xz` archive contains the files that will be installed on the system.

## Repositories

AXM repositories use a `packages.json` index.

Example:

```json
{
    "example": {
        "version": "1.0.0",
        "description": "An example package",
        "filename": "example-1.0.0.axm",
        "download_url": "https://example.com/example-1.0.0.axm",
        "sha256": "..."
    }
}
```

Repositories can be hosted remotely or stored locally.

## Installation

### Requirements

- Python 3.12 or newer
- Linux
- Root privileges for system package installation and removal

### From source

Clone the repository:

```bash
git clone https://github.com/Axiom2026/AXM-Axiom-Package-Manager-.git
cd AXM-Axiom-Package-Manager-
```

Create a virtual environment for development:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install AXM in editable mode:

```bash
python -m pip install -e .
```

The `axm` command will then be available in the environment.

## Development

AXM is written in Python.

Main files:

```text
axm.py       - AXM command-line interface and package manager
builder.py   - AXM package builder
pyproject.toml
```

## Security

AXM verifies package SHA256 checksums when a repository provides them.

Package archives are also checked for unsafe paths before extraction.

Security is an ongoing part of AXM development.

## License

AXM is licensed under the GNU General Public License v3.0.

See the [LICENSE](LICENSE) file for the full license text.
