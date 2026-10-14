"""Extract the parts of the competition zip that the study needs, safely, and write a manifest of SHA-256 values.

    python -I estrai_dati.py <zip> <target folder>

Kept: tasks.jsonl, HARNESS_README.md, graphs/, embeddings/, snapshots/, sample_submission/, docker/, sandbox/. The
wheels are skipped (no code from the data is installed or run). Every member path is checked to stay inside the
target folder; links and absolute paths are refused.
"""

import hashlib
import json
import os
import sys
import zipfile

KEEP = ("tasks.jsonl", "HARNESS_README.md", "graphs/", "embeddings/", "snapshots/", "sample_submission/", "docker/",
        "sandbox/")


def safe_target(root, name):
    target = os.path.realpath(os.path.join(root, name))
    if os.path.isabs(name) or ".." in name.replace("\\", "/").split("/") or \
            not target.startswith(os.path.realpath(root) + os.sep):
        raise SystemExit(f"unsafe member path: {name!r}")
    return target


def main():
    zpath, root = sys.argv[1], sys.argv[2]
    os.makedirs(root, exist_ok=True)
    manifest = {}
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        prefix = ""
        if names and all(n.split("/", 1)[0] == names[0].split("/", 1)[0] and "/" in n for n in names):
            prefix = names[0].split("/", 1)[0] + "/"
        for info in z.infolist():
            rel = info.filename[len(prefix):] if info.filename.startswith(prefix) else info.filename
            if not rel or rel.endswith("/") or not rel.startswith(KEEP):
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise SystemExit(f"symbolic link in the archive: {info.filename!r}")
            target = safe_target(root, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            h = hashlib.sha256()
            with z.open(info) as src, open(target, "wb") as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    h.update(chunk)
                    dst.write(chunk)
            manifest[rel] = {"sha256": h.hexdigest(), "size": info.file_size}
    with open(os.path.join(root, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"zip": os.path.basename(zpath), "files": manifest}, fh, indent=1, sort_keys=True)
    print(f"extracted {len(manifest)} files into {root}")


if __name__ == "__main__":
    main()
