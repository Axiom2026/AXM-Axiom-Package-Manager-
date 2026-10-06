import datetime
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from urllib.parse import unquote, urlparse


AXM_VERSION = "0.1.0"

# System paths
CONFIG_DIR = "/etc/axm"
REPOS_FILE = os.path.join(CONFIG_DIR, "repos.json")

DB_DIR = "/var/lib/axiom"
DB_FILE = os.path.join(DB_DIR, "installed.json")
HISTORY_FILE = os.path.join(DB_DIR, "history.json")
LOG_FILE = os.path.join(DB_DIR, "axiom.log")

# Set this to your official repository before publishing AXM.
# Example:
# DEFAULT_REPOSITORIES = {
#     "main": "https://raw.githubusercontent.com/YOUR_USERNAME/axiom-packages/main"
# }
DEFAULT_REPOSITORIES = {}

AUTO_YES = False


class AxiomError(Exception):
    """Base exception for AXM errors."""


def die(message, exit_code=1):
    print(f"[-] Error: {message}")
    sys.exit(exit_code)


def require_root():
    """Require root privileges for system-changing operations."""
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        die("Root privileges are required. Please run this command with sudo.")


def confirm_action(prompt):
    """Ask the user for confirmation unless automatic yes is enabled."""
    global AUTO_YES

    if AUTO_YES:
        return True

    while True:
        choice = input(f"{prompt} [Y/n]: ").strip().lower()

        if choice in ("", "y", "yes"):
            return True

        if choice in ("n", "no"):
            return False

        print("[-] Please enter 'y' or 'n'.")


def atomic_write_json(path, data, mode=0o644):
    """Write JSON atomically to reduce database corruption risk."""
    directory = os.path.dirname(path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".axm-",
        suffix=".tmp",
        dir=directory if directory else None,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
            file.write("\n")

        os.chmod(temp_path, mode)
        os.replace(temp_path, path)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def initialize_state():
    """Ensure AXM system state directories and files exist."""
    require_root()

    os.makedirs(DB_DIR, exist_ok=True)

    if not os.path.exists(DB_FILE):
        atomic_write_json(DB_FILE, {})

    if not os.path.exists(HISTORY_FILE):
        atomic_write_json(HISTORY_FILE, [])

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "a", encoding="utf-8"):
            pass
        os.chmod(LOG_FILE, 0o644)


def initialize_config():
    """Ensure the AXM configuration directory and repository file exist."""
    require_root()

    os.makedirs(CONFIG_DIR, exist_ok=True)

    if not os.path.exists(REPOS_FILE):
        atomic_write_json(REPOS_FILE, DEFAULT_REPOSITORIES)


def load_database():
    """Load the installed package database."""
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except (OSError, json.JSONDecodeError) as error:
        die(f"Could not read AXM database: {error}")


def save_database(data):
    """Save the installed package database."""
    require_root()
    initialize_state()
    atomic_write_json(DB_FILE, data)


def log_transaction(action, pkg_name, pkg_version):
    """Write a transaction to the AXM log."""
    require_root()
    initialize_state()

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"[{timestamp}] ACTION: {action} | "
            f"PACKAGE: {pkg_name} | VERSION: {pkg_version}\n"
        )


def log_history(action, pkg_name, version):
    """Record a package operation in history.json."""
    require_root()
    initialize_state()

    history = []

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                history = json.load(file)

            if not isinstance(history, list):
                history = []

        except json.JSONDecodeError:
            history = []

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    history.append(
        {
            "time": timestamp,
            "action": action,
            "package": pkg_name,
            "version": version,
        }
    )

    atomic_write_json(HISTORY_FILE, history)


def show_history():
    """Display AXM operation history."""
    if not os.path.exists(HISTORY_FILE):
        print("[*] No operation history found yet.")
        return

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            history = json.load(file)

    except json.JSONDecodeError:
        print("[-] Error: Invalid history database format.")
        return

    if not history:
        print("[*] History log is empty.")
        return

    print("=== Axiom Operation History ===")

    for entry in history:
        print(
            f"[{entry['time']}] "
            f"{entry['action'].upper()}: "
            f"{entry['package']} "
            f"(v{entry['version']})"
        )


def load_repos():
    """Load configured repositories."""
    if not os.path.exists(REPOS_FILE):
        return dict(DEFAULT_REPOSITORIES)

    try:
        with open(REPOS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Keep compatibility with the original list format.
        if isinstance(data, list):
            repositories = {}

            for index, url in enumerate(data):
                name = "main" if index == 0 else f"repo_{index + 1}"
                repositories[name] = url

            return repositories

        if isinstance(data, dict):
            return data

        return {}

    except (OSError, json.JSONDecodeError) as error:
        print(f"[-] Error reading repository configuration: {error}")
        return {}


def save_repos(data):
    """Save repository configuration."""
    require_root()
    initialize_config()
    atomic_write_json(REPOS_FILE, data)


def add_repo(name, url):
    """Add or replace a repository."""
    if not name.strip():
        die("Repository name cannot be empty.")

    if not url.strip():
        die("Repository URL cannot be empty.")

    repos = load_repos()
    repos[name] = url

    save_repos(repos)

    print(f"[+] Success! Repository '{name}' added.")
    print(f"    URL: {url}")


def list_repos():
    """Display configured repositories."""
    repos = load_repos()

    if not repos:
        print("[*] No repositories configured.")
        print("[*] Add one with:")
        print("    sudo axm add-repo main <repository_url>")
        return

    print("=== Configured Axiom Repositories ===")

    for name, url in repos.items():
        print(f"  - {name} -> {url}")


def repo_to_packages_url(repo_url):
    """Convert a repository base URL into its packages.json URL."""
    repo_url = repo_url.rstrip("/")

    if repo_url.endswith("packages.json"):
        return repo_url

    if repo_url.startswith(("http://", "https://", "file://")):
        return f"{repo_url}/packages.json"

    if os.path.isfile(repo_url):
        return repo_url

    return os.path.join(repo_url, "packages.json")


def fetch_repo_packages(repo_url):
    """Fetch and parse packages.json from a repository."""
    packages_url = repo_to_packages_url(repo_url)

    try:
        if packages_url.startswith("file://"):
            parsed = urlparse(packages_url)
            local_path = unquote(parsed.path)

            with open(local_path, "r", encoding="utf-8") as file:
                data = json.load(file)

        elif packages_url.startswith(("http://", "https://")):
            with urllib.request.urlopen(packages_url, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

        else:
            with open(packages_url, "r", encoding="utf-8") as file:
                data = json.load(file)

        if not isinstance(data, dict):
            print(f"[-] Error: Invalid packages.json format from {repo_url}")
            return {}

        return data

    except Exception as error:
        print(f"[-] Error fetching repository {repo_url}: {error}")
        return {}


def fetch_package_from_repos(pkg_name):
    """Search all configured repositories for a package."""
    repos = load_repos()

    for repo_name, repo_url in repos.items():
        repo_data = fetch_repo_packages(repo_url)

        if pkg_name in repo_data:
            package_metadata = repo_data[pkg_name]

            if not isinstance(package_metadata, dict):
                continue

            download_url = package_metadata.get("download_url")

            if not download_url:
                print(
                    f"[!] Warning: Package '{pkg_name}' in repository "
                    f"'{repo_name}' has no download_url."
                )
                continue

            return package_metadata, download_url

    return None, None


def download_package(download_url, destination):
    """Download a package from HTTP(S) or file://."""
    try:
        if download_url.startswith("file://"):
            parsed = urlparse(download_url)
            source_path = unquote(parsed.path)

            if not os.path.isfile(source_path):
                raise FileNotFoundError(source_path)

            shutil.copy2(source_path, destination)
            return

        with urllib.request.urlopen(download_url, timeout=60) as response:
            with open(destination, "wb") as output:
                shutil.copyfileobj(response, output)

    except Exception as error:
        die(f"Failed to download package: {error}")


def verify_sha256(file_path, expected_sha256):
    """Verify the SHA256 checksum of a file."""
    print("[*] Verifying package integrity (SHA256)...")

    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as file:
        for byte_block in iter(lambda: file.read(1024 * 1024), b""):
            sha256_hash.update(byte_block)

    calculated_sha256 = sha256_hash.hexdigest()

    if calculated_sha256.lower() != expected_sha256.lower():
        die(
            "Checksum mismatch. Package may be corrupted or tampered with.\n"
            f"    Expected : {expected_sha256}\n"
            f"    Calculated: {calculated_sha256}"
        )

    print("[+] Checksum verified successfully.")


def safe_extract_tar(archive_path, destination):
    """
    Extract a tar archive while rejecting paths that escape destination.

    Package archives are expected to contain relative paths.
    """
    destination = os.path.abspath(destination)

    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()

        for member in members:
            member_name = member.name

            if os.path.isabs(member_name):
                raise AxiomError(
                    f"Archive contains an absolute path: {member_name}"
                )

            target_path = os.path.abspath(
                os.path.join(destination, member_name)
            )

            try:
                common_path = os.path.commonpath(
                    [destination, target_path]
                )
            except ValueError:
                raise AxiomError(
                    f"Unsafe archive path: {member_name}"
                )

            if common_path != destination:
                raise AxiomError(
                    f"Unsafe archive path detected: {member_name}"
                )

        archive.extractall(destination)


def read_package_metadata(package_path, extraction_dir):
    """Extract an AXM package and read metadata.json."""
    safe_extract_tar(package_path, extraction_dir)

    metadata_path = os.path.join(extraction_dir, "metadata.json")

    if not os.path.exists(metadata_path):
        raise AxiomError(
            "'metadata.json' was not found inside the package archive."
        )

    try:
        with open(metadata_path, "r", encoding="utf-8") as file:
            metadata = json.load(file)

    except (OSError, json.JSONDecodeError) as error:
        raise AxiomError(f"Could not read metadata.json: {error}")

    if not isinstance(metadata, dict):
        raise AxiomError("metadata.json must contain a JSON object.")

    return metadata


def install_files_archive(files_archive_path):
    """
    Extract files.tar.xz into the system root.

    Paths are validated before extraction.
    """
    if not tarfile.is_tarfile(files_archive_path):
        raise AxiomError("files.tar.xz is not a valid tar archive.")

    print("[*] Installing package files...")

    safe_extract_tar(files_archive_path, "/")


def install_package(target, resolving=None):
    """Install a local .axm package or a package from repositories."""
    require_root()

    if resolving is None:
        resolving = set()

    resolution_key = target

    if resolution_key in resolving:
        raise AxiomError(
            f"Dependency cycle detected involving '{target}'."
        )

    resolving.add(resolution_key)

    temp_dir = None
    downloaded_package = None

    try:
        db = load_database()

        package_path = target
        package_metadata = None
        download_url = None

        # Repository package
        if not os.path.exists(target):
            print(
                f"[*] '{target}' is not a local file. "
                f"Searching configured repositories..."
            )

            package_metadata, download_url = fetch_package_from_repos(target)

            if package_metadata is None:
                raise AxiomError(
                    f"Package '{target}' was not found in any repository."
                )

            pkg_name = target
            pkg_version = package_metadata.get("version", "unknown")

            temp_dir = tempfile.mkdtemp(prefix="axm-download-")
            downloaded_package = os.path.join(
                temp_dir,
                f"{pkg_name}-{pkg_version}.axm",
            )

            print(f"[*] Downloading from: {download_url}")
            download_package(download_url, downloaded_package)

            package_path = downloaded_package

            expected_sha256 = package_metadata.get("sha256")

            if expected_sha256:
                verify_sha256(
                    package_path,
                    expected_sha256,
                )

        # Local package
        if not tarfile.is_tarfile(package_path):
            raise AxiomError(
                f"'{package_path}' is not a valid AXM package."
            )

        print(f"[*] Preparing package: {package_path}")

        extraction_dir = tempfile.mkdtemp(prefix="axm-package-")

        try:
            metadata = read_package_metadata(
                package_path,
                extraction_dir,
            )

            pkg_name = metadata.get("name")
            pkg_version = metadata.get("version")
            dependencies = metadata.get("dependencies", [])

            if not pkg_name or not pkg_version:
                raise AxiomError(
                    "Package metadata must contain 'name' and 'version'."
                )

            if not isinstance(dependencies, list):
                raise AxiomError(
                    "Package metadata field 'dependencies' must be a list."
                )

            print(f"[*] Package: {pkg_name}")
            print(f"[*] Version: {pkg_version}")

            if pkg_name in db:
                print(
                    f"[!] Warning: Package '{pkg_name}' is already installed."
                )
                print("[!] Existing files will be overwritten where necessary.")

            if not confirm_action(
                f"Do you want to install package '{pkg_name}'?"
            ):
                print("[*] Installation aborted by user.")
                return

            # Resolve dependencies first.
            for dependency in dependencies:
                if dependency not in db:
                    print(
                        f"[*] Resolving dependency: '{dependency}'..."
                    )
                    install_package(
                        dependency,
                        resolving=resolving,
                    )

            files_tar_xz = os.path.join(
                extraction_dir,
                "files.tar.xz",
            )

            if not os.path.exists(files_tar_xz):
                raise AxiomError(
                    "'files.tar.xz' was not found inside the package archive."
                )

            installed_files = []

            with tarfile.open(files_tar_xz, "r:xz") as files_tar:
                for member in files_tar.getmembers():
                    if member.name in ("", "."):
                        continue

                    member_name = member.name.lstrip("./")
                    if not member_name:
                        continue

                    if os.path.isabs(member.name):
                        raise AxiomError(
                            f"Package contains an absolute path: {member.name}"
                        )

                    installed_files.append(
                        "/" + member_name
                        if not member_name.startswith("/")
                        else member_name
                    )

            install_files_archive(files_tar_xz)

            db[pkg_name] = {
                "version": pkg_version,
                "files": sorted(set(installed_files)),
                "dependencies": dependencies,
            }

            save_database(db)

            log_transaction(
                "INSTALL",
                pkg_name,
                pkg_version,
            )

            log_history(
                "install",
                pkg_name,
                pkg_version,
            )

            print(
                f"[+] Success! Successfully installed "
                f"{pkg_name}-{pkg_version}"
            )

        finally:
            shutil.rmtree(extraction_dir, ignore_errors=True)

    finally:
        resolving.discard(resolution_key)

        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def remove_package(pkg_name):
    """Remove an installed AXM package."""
    require_root()

    db = load_database()

    if pkg_name not in db:
        die(f"Package '{pkg_name}' is not installed.")

    # Prevent removing a package that other installed packages depend on.
    dependents = []

    for installed_name, installed_info in db.items():
        if installed_name == pkg_name:
            continue

        dependencies = installed_info.get("dependencies", [])

        if pkg_name in dependencies:
            dependents.append(installed_name)

    if dependents:
        print(
            f"[-] Cannot remove '{pkg_name}' because it is required by:"
        )

        for dependent in dependents:
            print(f"    - {dependent}")

        sys.exit(1)

    if not confirm_action(
        f"Are you sure you want to remove package '{pkg_name}'?"
    ):
        print("[*] Removal aborted by user.")
        return

    package_info = db[pkg_name]
    pkg_version = package_info["version"]
    package_files = package_info.get("files", [])

    # Build a set of files owned by other packages.
    files_owned_elsewhere = set()

    for other_name, other_info in db.items():
        if other_name == pkg_name:
            continue

        for file_path in other_info.get("files", []):
            files_owned_elsewhere.add(file_path)

    for file_path in package_files:
        if file_path in files_owned_elsewhere:
            continue

        try:
            if os.path.islink(file_path) or os.path.isfile(file_path):
                os.remove(file_path)

            elif os.path.isdir(file_path):
                try:
                    os.rmdir(file_path)
                except OSError:
                    pass

        except OSError as error:
            print(
                f"[!] Warning: Could not remove "
                f"{file_path}: {error}"
            )

    del db[pkg_name]
    save_database(db)

    log_transaction(
        "REMOVE",
        pkg_name,
        pkg_version,
    )

    log_history(
        "remove",
        pkg_name,
        pkg_version,
    )

    print(
        f"[+] Success! Successfully removed {pkg_name}"
    )


def list_installed_packages():
    """Display installed AXM packages."""
    db = load_database()

    if not db:
        print("[*] No packages installed via Axiom yet.")
        return

    print("=== Installed Axiom Packages ===")

    for name, info in db.items():
        dependencies = info.get("dependencies", [])
        dependency_string = (
            ", ".join(dependencies)
            if dependencies
            else "None"
        )

        print(
            f"- {name} "
            f"(v{info['version']}) | "
            f"Dependencies: [{dependency_string}] -> "
            f"{len(info.get('files', []))} files"
        )


def package_info(pkg_name):
    """Display detailed information about an installed package."""
    db = load_database()

    if pkg_name not in db:
        print(
            f"[-] Error: Package '{pkg_name}' is not installed."
        )
        return

    info = db[pkg_name]

    dependencies = info.get("dependencies", [])
    dependency_string = (
        ", ".join(dependencies)
        if dependencies
        else "None"
    )

    print(f"=== Package Info: {pkg_name} ===")
    print(f"  Version      : {info['version']}")
    print(f"  Dependencies : [{dependency_string}]")
    print(
        f"  Installed Files "
        f"({len(info.get('files', []))} files):"
    )

    for file_path in info.get("files", []):
        print(f"    - {file_path}")


def search_packages(query):
    """Search configured repositories."""
    repos = load_repos()
    found_count = 0

    print(f"=== Search Results for '{query}' ===")

    for repo_name, repo_url in repos.items():
        repo_data = fetch_repo_packages(repo_url)

        if not repo_data:
            continue

        for name, info in repo_data.items():
            if not isinstance(info, dict):
                continue

            description = info.get(
                "description",
                "No description.",
            )

            version = info.get(
                "version",
                "unknown",
            )

            dependencies = info.get(
                "dependencies",
                [],
            )

            if (
                query.lower() in name.lower()
                or query.lower() in description.lower()
            ):
                dependency_string = (
                    ", ".join(dependencies)
                    if dependencies
                    else "None"
                )

                print(
                    f"  > [{repo_name}] "
                    f"{name} (v{version})"
                )

                print(
                    f"    Description: "
                    f"{description}"
                )

                print(
                    f"    Dependencies: "
                    f"[{dependency_string}]"
                )

                print("-" * 50)

                found_count += 1

    if found_count == 0:
        print(
            f"[*] No packages found matching '{query}'."
        )
    else:
        print(
            f"[*] Found {found_count} package(s)."
        )


def upgrade_packages():
    """Upgrade installed packages when repository versions differ."""
    require_root()

    db = load_database()

    if not db:
        print("[*] No packages installed to upgrade.")
        return

    print(
        "[*] Checking for package updates across repositories..."
    )

    upgraded_count = 0

    for pkg_name, info in list(db.items()):
        current_version = info["version"]

        package_metadata, _ = fetch_package_from_repos(
            pkg_name
        )

        if not package_metadata:
            print(
                f"[!] Warning: Package '{pkg_name}' "
                f"was not found in any repository."
            )
            continue

        repository_version = package_metadata.get(
            "version"
        )

        if repository_version != current_version:
            print(
                f"[+] Update found for '{pkg_name}': "
                f"v{current_version} -> "
                f"v{repository_version}"
            )

            install_package(pkg_name)
            upgraded_count += 1

        else:
            print(
                f"[*] '{pkg_name}' is already up-to-date "
                f"(v{current_version})."
            )

    if upgraded_count == 0:
        print(
            "[*] All installed packages are already up-to-date."
        )
    else:
        print(
            f"[+] Successfully upgraded "
            f"{upgraded_count} package(s)."
        )


def build_package_from_directory(source_dir):
    """Build an .axm package from a directory containing metadata.json."""
    if not os.path.isdir(source_dir):
        die(f"Directory '{source_dir}' not found.")

    metadata_path = os.path.join(
        source_dir,
        "metadata.json",
    )

    if not os.path.exists(metadata_path):
        die(
            f"'metadata.json' not found in '{source_dir}'."
        )

    try:
        with open(
            metadata_path,
            "r",
            encoding="utf-8",
        ) as file:
            metadata = json.load(file)

    except (OSError, json.JSONDecodeError) as error:
        die(f"Could not read metadata.json: {error}")

    pkg_name = metadata.get("name")
    pkg_version = metadata.get("version")

    if not pkg_name or not pkg_version:
        die(
            "'metadata.json' must contain "
            "'name' and 'version'."
        )

    print(
        f"[*] Building package "
        f"'{pkg_name}' version '{pkg_version}'..."
    )

    output_axm = os.path.abspath(
        f"{pkg_name}-{pkg_version}.axm"
    )

    with tempfile.TemporaryDirectory(
        prefix="axm-build-"
    ) as staging_dir:

        files_archive = os.path.join(
            staging_dir,
            "files.tar.xz",
        )

        with tarfile.open(
            files_archive,
            "w:xz",
        ) as tar:

            for item in os.listdir(source_dir):
                if item == "metadata.json":
                    continue

                full_path = os.path.join(
                    source_dir,
                    item,
                )

                tar.add(
                    full_path,
                    arcname=item,
                )

        with tarfile.open(
            output_axm,
            "w",
        ) as package_tar:

            package_tar.add(
                metadata_path,
                arcname="metadata.json",
            )

            package_tar.add(
                files_archive,
                arcname="files.tar.xz",
            )

    sha256_hash = hashlib.sha256()

    with open(output_axm, "rb") as file:
        for byte_block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha256_hash.update(byte_block)

    checksum = sha256_hash.hexdigest()

    print(
        f"[+] Success! Package created: "
        f"{output_axm}"
    )

    print(
        f"[+] SHA256 Checksum: {checksum}"
    )


def print_help():
    """Display AXM command help."""
    print("Axiom Package Manager (axm)")
    print()
    print("Usage:")
    print("  sudo axm install <package>")
    print("  sudo axm remove <package_name>")
    print("  axm list")
    print("  axm search <query>")
    print("  axm list-repo")
    print("  sudo axm add-repo <name> <url>")
    print("  axm history")
    print("  axm info <package_name>")
    print("  sudo axm upgrade")
    print("  axm build <source_directory>")
    print("  axm --version")
    print("  axm --help")


def main():
    """AXM command-line entry point."""
    global AUTO_YES

    args = sys.argv[1:]

    if "-y" in args:
        AUTO_YES = True
        args.remove("-y")

    if "--yes" in args:
        AUTO_YES = True
        args.remove("--yes")

    if not args:
        print_help()
        return 0

    if args[0] in ("help", "--help", "-h"):
        print_help()
        return 0

    if args[0] in ("--version", "-V"):
        print(f"axm {AXM_VERSION}")
        return 0

    command = args[0]

    try:
        if command == "install":
            if len(args) < 2:
                die("Please specify the package to install.")

            install_package(args[1])

        elif command == "remove":
            if len(args) < 2:
                die("Please specify the package to remove.")

            remove_package(args[1])

        elif command == "list":
            list_installed_packages()

        elif command == "search":
            if len(args) < 2:
                die("Please specify a search query.")

            search_packages(args[1])

        elif command == "list-repo":
            list_repos()

        elif command == "add-repo":
            if len(args) < 3:
                die(
                    "Please specify repository name and URL."
                )

            add_repo(args[1], args[2])

        elif command == "history":
            show_history()

        elif command == "info":
            if len(args) < 2:
                die(
                    "Please specify the package name."
                )

            package_info(args[1])

        elif command == "build":
            if len(args) < 2:
                die(
                    "Please specify the source directory."
                )

            build_package_from_directory(args[1])

        elif command == "upgrade":
            upgrade_packages()

        else:
            print(
                f"[-] Error: Unknown command '{command}'."
            )
            print()
            print_help()
            return 1

    except AxiomError as error:
        print(f"[-] Error: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
