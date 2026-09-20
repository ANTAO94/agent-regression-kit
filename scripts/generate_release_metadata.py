"""Generate checksums and a small SPDX 2.3 release SBOM without dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ARTIFACT_SUFFIXES = (".whl", ".tar.gz")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_artifacts(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name.endswith(ARTIFACT_SUFFIXES)
    )


def build_spdx(
    artifacts: Iterable[Path], version: str, *, created: str | None = None
) -> dict[str, Any]:
    files = list(artifacts)
    if not files:
        raise ValueError("at least one wheel or source archive is required")
    if not version or any(character.isspace() for character in version):
        raise ValueError("version must be non-empty and contain no whitespace")
    checksums = {path.name: _sha256(path) for path in files}
    namespace_seed = "\n".join(
        f"{name}:{digest}" for name, digest in sorted(checksums.items())
    )
    namespace_digest = hashlib.sha256(namespace_seed.encode("utf-8")).hexdigest()
    generated_at = created or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    spdx_files = []
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package",
        }
    ]
    for index, path in enumerate(files, start=1):
        file_id = f"SPDXRef-Artifact-{index}"
        spdx_files.append(
            {
                "fileName": f"./{path.name}",
                "SPDXID": file_id,
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": checksums[path.name]}
                ],
                "licenseConcluded": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_id,
            }
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"agent-regression-kit-{version}-release",
        "documentNamespace": (
            "https://github.com/ANTAO94/agent-regression-kit/releases/"
            f"download/v{version}/spdx-{namespace_digest}"
        ),
        "creationInfo": {
            "created": generated_at,
            "creators": ["Tool: agent-regression-kit-release-metadata"],
        },
        "packages": [
            {
                "name": "agent-regression-kit",
                "SPDXID": "SPDXRef-Package",
                "versionInfo": version,
                "downloadLocation": (
                    "https://github.com/ANTAO94/agent-regression-kit/"
                    f"releases/tag/v{version}"
                ),
                "filesAnalyzed": False,
                "licenseConcluded": "MIT",
                "licenseDeclared": "MIT",
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": (
                            f"pkg:github/ANTAO94/agent-regression-kit@{version}"
                        ),
                    }
                ],
            }
        ],
        "files": spdx_files,
        "relationships": relationships,
    }


def write_release_metadata(directory: Path, version: str) -> tuple[Path, Path]:
    artifacts = release_artifacts(directory)
    document = build_spdx(artifacts, version)
    checksums_path = directory / "SHA256SUMS"
    checksums_path.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    sbom_path = directory / f"agent-regression-kit-{version}.spdx.json"
    sbom_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return checksums_path, sbom_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    checksums, sbom = write_release_metadata(args.dist_dir, args.version)
    print(checksums)
    print(sbom)


if __name__ == "__main__":
    main()
