# Standard library
import io

# Third-party
import fsspec
from dissect.squashfs import SquashFS
from fsspec.spec import AbstractFileSystem


class SquashFSFileSystem(AbstractFileSystem):
    """Read-only fsspec filesystem for browsing SquashFS archives.

    Inputs:
    - fo: path or file-like object pointing to a SquashFS image.
    - offset: byte offset into ``fo`` where the SquashFS image starts.

    Outputs:
    - Standard fsspec directory listings and file-like readers for archive
      members.
    """

    protocol = "squashfs"
    cachable = False  # codespell:ignore cachable

    def __init__(self, fo=None, offset=0, **kwargs):
        super().__init__(**kwargs)
        if fo is None:
            # Try to get fo from kwargs if passed there
            fo = kwargs.get("fo")

        if fo is None:
            raise ValueError(
                "SquashFSFileSystem requires 'fo' (file-like object or path)"
            )

        self._close_fo = isinstance(fo, str)
        if isinstance(fo, str):
            self._fo_ref = fsspec.open(fo, "rb")
            self.fo = self._fo_ref.open()
        else:
            self.fo = fo
            self._fo_ref = None
        self.offset = offset
        # SquashFS in dissect can take a file-like object
        # We might need to wrap it if it has an offset
        if self.offset != 0:
            # Simple wrapper to handle offset if dissect doesn't
            self.sfs = SquashFS(OffsetWrapper(self.fo, self.offset))
        else:
            self.sfs = SquashFS(self.fo)
        self._closed = False

    @property
    def closed(self):
        """Return whether this filesystem should be treated as closed.
        Checks both internal state and underlying file-like object."""
        return self._closed or bool(getattr(self.fo, "closed", False))

    def _check_closed(self):
        if self.closed:
            raise ValueError("I/O operation on closed filesystem.")

    @classmethod
    def _strip_protocol(cls, path):
        """Normalize paths to absolute archive-internal paths.

        Input:
        - path: string path that may include protocol prefixes.

        Output:
        - Path string rooted at ``/`` within the SquashFS image.
        """
        path = super()._strip_protocol(path)

        # If the protocol is still there, it's often because
        # fsspec's split_protocol didn't match it or it's nested.
        for proto in ["squashfs://", "squashfs:"]:
            if path.startswith(proto):
                path = path[len(proto) :]
                break

        if "://" in path:
            # Handle cases like some_path://inner_path
            path = path.split("://", 1)[1]

        if not path.startswith("/"):
            path = "/" + path
        return path

    def ls(self, path, detail=True, **kwargs):
        """List members at ``path``.

        Input:
        - path: archive-internal directory or file path.
        - detail: if True return info dicts, else return names.

        Output:
        - ``list[dict]`` when ``detail=True`` else ``list[str]``.
        """
        self._check_closed()
        path = self._strip_protocol(path)

        try:
            entry = self.sfs.get(path)
        except Exception:
            raise FileNotFoundError(path)

        if entry.is_dir():
            out = []
            for name, child in entry.listdir().items():
                child_path = (path.rstrip("/") + "/" + name).lstrip("/")
                if detail:
                    out.append(
                        {
                            "name": child_path,
                            "size": child.size if not child.is_dir() else 0,
                            "type": "directory" if child.is_dir() else "file",
                        }
                    )
                else:
                    out.append(child_path)
            return out
        else:
            if detail:
                return [
                    {
                        "name": path.lstrip("/"),
                        "size": entry.size,
                        "type": "file",
                    }
                ]
            return [path.lstrip("/")]

    def info(self, path, **kwargs):
        """Return metadata for one archive member.

        Input:
        - path: archive-internal path.

        Output:
        - Dict with ``name``, ``size``, and ``type``.
        """
        self._check_closed()
        path = self._strip_protocol(path)
        try:
            entry = self.sfs.get(path)
        except Exception:
            raise FileNotFoundError(path)

        return {
            "name": path.lstrip("/"),
            "size": entry.size if not entry.is_dir() else 0,
            "type": "directory" if entry.is_dir() else "file",
        }

    def exists(self, path, **kwargs):
        self._check_closed()
        path = self._strip_protocol(path)
        try:
            self.sfs.get(path)
            return True
        except Exception:
            return False

    def isdir(self, path):
        self._check_closed()
        path = self._strip_protocol(path)
        try:
            return self.sfs.get(path).is_dir()
        except Exception:
            return False

    def isfile(self, path):
        self._check_closed()
        path = self._strip_protocol(path)
        try:
            return not self.sfs.get(path).is_dir()
        except Exception:
            return False

    def _open(self, path, mode="rb", **kwargs):
        """Open an archive member for binary reading.

        Input:
        - path: archive-internal file path.
        - mode: must be ``rb``.

        Output:
        - File-like object for reading bytes.
        """
        self._check_closed()
        if mode != "rb":
            raise ValueError("ReadOnly filesystem")
        path = self._strip_protocol(path)
        entry = self.sfs.get(path)
        return _MemberFileProxy(entry.open())

    def close(self):
        """Close filesystem resources and owned archive handle."""
        if hasattr(self, "_closed") and self._closed:
            return
        self._closed = True
        try:
            if hasattr(self, "sfs") and hasattr(self.sfs, "close"):
                self.sfs.close()
        finally:
            if (
                hasattr(self, "_close_fo")
                and self._close_fo
                and hasattr(self, "fo")
                and self.fo is not None
            ):
                self.fo.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()


class _MemberFileProxy(io.IOBase):
    """Minimal logical stream wrapper with real close semantics.
    Needed to enable closing a subfile stream without closing the entire
    SquashFS file-like object.
    """

    def __init__(self, raw):
        self._raw = raw

    def readable(self):
        return not self.closed

    def writable(self):
        return False

    def seekable(self):
        return not self.closed and hasattr(self._raw, "seek")

    def read(self, size=-1):
        self._checkClosed()
        return self._raw.read(size)

    def readline(self, size=-1):
        self._checkClosed()
        return self._raw.readline(size)

    def seek(self, offset, whence=io.SEEK_SET):
        self._checkClosed()
        return self._raw.seek(offset, whence)

    def tell(self):
        self._checkClosed()
        return self._raw.tell()

    def close(self):
        """Close the member stream and mark this wrapper as closed."""
        if self.closed:
            return
        try:
            self._raw.close()
        finally:
            super().close()

    def __getattr__(self, name):
        return getattr(self._raw, name)


class OffsetWrapper:
    """File-like view that applies a fixed base offset to absolute seeks.

    Input:
    - fo: underlying file-like object.
    - offset: base byte offset for whence=0 seeks.

    Output:
    - File-like object suitable for libraries expecting an offset-adjusted
      stream.
    """

    def __init__(self, fo, offset):
        self.fo = fo
        self.offset = offset

    def seek(self, offset, whence=0):
        if whence == 0:
            return self.fo.seek(self.offset + offset)
        return self.fo.seek(offset, whence)

    def read(self, size=-1):
        return self.fo.read(size)

    def tell(self):
        return self.fo.tell() - self.offset

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        return self.fo.close()
