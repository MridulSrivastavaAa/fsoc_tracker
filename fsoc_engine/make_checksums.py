"""
make_checksums.py
=================
Generates SHA-256 checksums for all release binaries (.exe, .zip)
in fsoc_engine/release/ and writes them to release/checksums.txt.
"""
import hashlib
from pathlib import Path


def main():
    base_dir = Path(__file__).resolve().parent
    release_dir = base_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [
            p
            for p in release_dir.iterdir()
            if p.suffix.lower() in (".exe", ".zip") and p.name != "checksums.txt"
        ]
    )

    lines = []
    print("[CHECKSUMS] Generating SHA-256 for release artifacts:")
    for p in files:
        h = hashlib.sha256(p.read_bytes()).hexdigest().upper()
        entry = f"{h}  {p.name}"
        lines.append(entry)
        print(f"  {entry}")

    checksum_file = release_dir / "checksums.txt"
    checksum_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="ascii")
    print(f"[CHECKSUMS] Written to {checksum_file} ({len(lines)} file(s))")


if __name__ == "__main__":
    main()
