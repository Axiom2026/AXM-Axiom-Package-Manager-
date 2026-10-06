import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile


def build_package(
    name,
    version,
    source_dir,
    output_path,
    dependencies=None,
    description=None,
):
    """
    Build an .axm package from a filesystem tree.
    """

    if dependencies is None:
        dependencies = []

    if description is None:
        description = f"A custom AXM package for {name}"

    if not os.path.isdir(source_dir):
        print(
            f"[-] Error: Source directory '{source_dir}' not found."
        )
        sys.exit(1)

    print(
        f"[*] Building package: "
        f"{name} (v{version})..."
    )

    output_path = os.path.abspath(output_path)

    with tempfile.TemporaryDirectory(
        prefix="axm-builder-"
    ) as staging_dir:

        metadata_path = os.path.join(
            staging_dir,
            "metadata.json",
        )

        files_archive_path = os.path.join(
            staging_dir,
            "files.tar.xz",
        )

        metadata = {
            "name": name,
            "version": version,
            "description": description,
            "dependencies": dependencies,
        }

        try:
            # 1. Write metadata.
            with open(
                metadata_path,
                "w",
                encoding="utf-8",
            ) as metadata_file:
                json.dump(
                    metadata,
                    metadata_file,
                    indent=4,
                )
                metadata_file.write("\n")

            # 2. Build the filesystem archive.
            with tarfile.open(
                files_archive_path,
                "w:xz",
            ) as tar:

                for item in os.listdir(source_dir):
                    full_path = os.path.join(
                        source_dir,
                        item,
                    )

                    tar.add(
                        full_path,
                        arcname=item,
                    )

            # 3. Build the final .axm archive.
            with tarfile.open(
                output_path,
                "w",
            ) as axm_package:

                axm_package.add(
                    metadata_path,
                    arcname="metadata.json",
                )

                axm_package.add(
                    files_archive_path,
                    arcname="files.tar.xz",
                )

        except Exception as error:
            print(
                f"[-] Error while building package: "
                f"{error}"
            )
            sys.exit(1)

    # 4. Calculate SHA256.
    sha256_hash = hashlib.sha256()

    with open(
        output_path,
        "rb",
    ) as package_file:

        for block in iter(
            lambda: package_file.read(1024 * 1024),
            b"",
        ):
            sha256_hash.update(block)

    checksum = sha256_hash.hexdigest()

    print(
        f"[+] Success! Package created at: "
        f"{output_path}"
    )

    print(
        f"[+] SHA256: {checksum}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(
            "Usage: "
            "python3 builder.py "
            "<name> <version> "
            "<source_dir> <output.axm> "
            "[dep1,dep2,...]"
        )
        sys.exit(1)

    package_name = sys.argv[1]
    package_version = sys.argv[2]
    source_directory = sys.argv[3]
    output_file = sys.argv[4]

    dependencies = []

    if len(sys.argv) > 5:
        dependencies = [
            dependency.strip()
            for dependency in sys.argv[5].split(",")
            if dependency.strip()
        ]

    build_package(
        package_name,
        package_version,
        source_directory,
        output_file,
        dependencies,
    )
