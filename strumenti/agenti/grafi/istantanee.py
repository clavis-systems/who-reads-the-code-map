"""Read the files of a task snapshot (snapshots/<instance_id>.tgz) straight from the archive, without extracting it.

Only regular files are read, never written to disk, so nothing in the archive can escape its folder or run. The
.git folder is skipped. If every member sits under one top-level folder, that folder is removed from the paths.
"""

import posixpath
import tarfile

TEXT_EXT = (".py", ".pyi", ".md", ".rst", ".txt", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml")
MAX_FILE = 1_000_000


def read_snapshot(path, extensions=TEXT_EXT):
    files = {}
    with tarfile.open(path, "r:*") as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        names = [posixpath.normpath(m.name.removeprefix("./")) for m in members]      # keeps '.github' as it is
        tops = {n.split("/", 1)[0] for n in names}
        strip = len(tops) == 1 and all("/" in n for n in names)
        for m, name in zip(members, names):
            rel = name.split("/", 1)[1] if strip else name
            if rel.startswith(".git/") or "/.git/" in rel or rel.startswith("../") or rel.startswith("/"):
                continue
            if not rel.endswith(extensions) or m.size > MAX_FILE:
                continue
            fh = tar.extractfile(m)
            if fh is None:
                continue
            files[rel] = fh.read().decode("utf-8", errors="replace")
    return files
