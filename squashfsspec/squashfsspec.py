# Standard library
import io
import os
import shutil
import subprocess
import tempfile

# Third-party
import fsspec
from dissect.squashfs import SquashFS
from fsspec.implementations.local import LocalFileSystem
from fsspec.spec import AbstractFileSystem
from zarr.storage import LocalStore


class SquashFSFileSystem(AbstractFileSystem):
    """fsspec filesystem for SquashFS archives — supports both reading and writing.

    The operating mode is determined automatically from context:

    * **Read mode** (default): ``fo`` points to an *existing* SquashFS image.
    * **Write mode**: ``fo`` (or ``target``) is a path that does *not* yet
      exist on disk, or you pass ``mode="w"`` explicitly.

    In write mode all file operations are staged in a temporary local
    directory.  When ``close()`` is called (or the context manager exits
    without an exception), ``mksquashfs`` is invoked to pack that directory
    into the target SquashFS image.

    Parameters
    ----------
    fo : str or file-like, optional
        Path to an existing SquashFS image (read mode) **or** the destination
        path for a new image (write mode).  For write mode you can also use
        the ``target`` alias.
    target : str, optional
        Alias for ``fo`` in write mode.  Ignored when ``fo`` is given.
    mode : {"r", "w"}, optional
        Force read (``"r"``) or write (``"w"``) mode.  When omitted the mode
        is inferred: if ``fo`` / ``target`` is a string pointing to a file
        that does not yet exist the filesystem opens in write mode; otherwise
        it opens in read mode.
    offset : int, optional
        Byte offset into ``fo`` where the SquashFS image starts (read mode
        only).  Defaults to ``0``.
    compressor : str, optional
        Compression algorithm passed to ``mksquashfs`` via ``-comp`` (write
        mode only).  Defaults to ``"gzip"``.
    mksquashfs_args : list[str], optional
        Extra CLI arguments forwarded verbatim to ``mksquashfs`` (write mode
        only).

    Examples
    --------
    Read an existing image::

        fs = SquashFSFileSystem("data.squash")
        print(fs.ls("/"))

    Write a new image (mode inferred because the file does not exist)::

        with SquashFSFileSystem("output.squash") as fs:
            with fs.open("/hello.txt", "wb") as f:
                f.write(b"Hello, SquashFS!")

    Force write mode explicitly::

        with SquashFSFileSystem("output.squash", mode="w") as fs:
            ds.to_zarr(fs.get_mapper("/"), mode="w")

    One-liner URL write syntax (xarray infers write mode; call
    ``gc.collect()`` after ``to_zarr`` to trigger the commit)::

        ds.to_zarr(
            "squashfs:///data.zarr",
            consolidated=False,
            storage_options={"fo": "output.squash"},
        )

    One-liner URL read syntax::

        ds = xr.open_dataset(
            "squashfs:///data.zarr",
            engine="zarr",
            consolidated=False,
            backend_kwargs={"storage_options": {"fo": "output.squash"}},
        )
    """

    protocol = "squashfs"
    cachable = False  # codespell:ignore cachable

    def __init__(
        self,
        fo=None,
        target=None,
        mode=None,
        offset=0,
        compressor="gzip",
        mksquashfs_args=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        # Resolve the target path / file-like object.
        if fo is None:
            fo = kwargs.get("fo") or target

        # Infer mode when not given explicitly.
        if mode is None:
            if isinstance(fo, str) and not os.path.exists(fo):
                mode = "w"
            else:
                mode = "r"

        self._mode = mode

        if mode == "w":
            # ---- write mode -----------------------------------------------
            if fo is None:
                raise ValueError(
                    "SquashFSFileSystem in write mode requires a target path "
                    "via 'fo' or 'target'."
                )
            self._target = os.fspath(fo)
            self._compressor = compressor
            self._mksquashfs_args = list(mksquashfs_args or [])
            self._staging_dir = tempfile.mkdtemp(prefix="squashfsspec_write_")
            self._local = LocalFileSystem(auto_mkdir=True)
            self._closed = False
            # When True, __del__ will auto-commit if close() was never called.
            # Set to False by discard() so GC doesn't re-create a discarded image.
            self._auto_commit = True
        else:
            # ---- read mode ------------------------------------------------
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
            if self.offset != 0:
                self.sfs = SquashFS(OffsetWrapper(self.fo, self.offset))
            else:
                self.sfs = SquashFS(self.fo)
            self._closed = False

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @property
    def closed(self):
        """Return whether this filesystem should be treated as closed."""
        if self._mode == "w":
            return self._closed
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

    # ------------------------------------------------------------------
    # Write-mode internal helpers
    # ------------------------------------------------------------------

    def _stage_path(self, path):
        """Translate an archive-internal path to an absolute staging path."""
        path = self._strip_protocol(path)
        rel = path.lstrip("/")
        return os.path.join(self._staging_dir, rel) if rel else self._staging_dir

    # ------------------------------------------------------------------
    # AbstractFileSystem interface — dispatches on mode
    # ------------------------------------------------------------------

    def ls(self, path, detail=True, **kwargs):
        """List members at ``path``.

        Input:
        - path: archive-internal directory or file path.
        - detail: if True return info dicts, else return names.

        Output:
        - ``list[dict]`` when ``detail=True`` else ``list[str]``.
        """
        self._check_closed()
        if self._mode == "w":
            return self._ls_write(path, detail=detail)
        return self._ls_read(path, detail=detail)

    def _ls_read(self, path, detail=True):
        path = self._strip_protocol(path)
        try:
            entry = self.sfs.get(path)
        except Exception:
            raise FileNotFoundError(path)

        if entry.is_dir():
            out = []
            for name, child in entry.listdir().items():
                child_path = path.rstrip("/") + "/" + name
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
                        "name": path,
                        "size": entry.size,
                        "type": "file",
                    }
                ]
            return [path]

    def _ls_write(self, path, detail=True):
        stage = self._stage_path(path)
        if not os.path.exists(stage):
            raise FileNotFoundError(path)

        strip = len(self._staging_dir.rstrip("/"))
        if os.path.isfile(stage):
            archive_path = stage[strip:] or "/"
            if detail:
                return [{"name": archive_path, "size": os.path.getsize(stage), "type": "file"}]
            return [archive_path]

        out = []
        for name in os.listdir(stage):
            child = os.path.join(stage, name)
            archive_path = child[strip:] or "/"
            if detail:
                out.append(
                    {
                        "name": archive_path,
                        "size": os.path.getsize(child) if os.path.isfile(child) else 0,
                        "type": "directory" if os.path.isdir(child) else "file",
                    }
                )
            else:
                out.append(archive_path)
        return out

    def info(self, path, **kwargs):
        """Return metadata for one archive member or staged path.

        Input:
        - path: archive-internal path.

        Output:
        - Dict with ``name``, ``size``, and ``type``.
        """
        self._check_closed()
        if self._mode == "w":
            stage = self._stage_path(path)
            if not os.path.exists(stage):
                raise FileNotFoundError(path)
            strip = len(self._staging_dir.rstrip("/"))
            archive_path = stage[strip:] or "/"
            return {
                "name": archive_path,
                "size": os.path.getsize(stage) if os.path.isfile(stage) else 0,
                "type": "directory" if os.path.isdir(stage) else "file",
            }

        path = self._strip_protocol(path)
        try:
            entry = self.sfs.get(path)
        except Exception:
            raise FileNotFoundError(path)

        return {
            "name": path,
            "size": entry.size if not entry.is_dir() else 0,
            "type": "directory" if entry.is_dir() else "file",
        }

    def exists(self, path, **kwargs):
        self._check_closed()
        if self._mode == "w":
            return os.path.exists(self._stage_path(path))
        path = self._strip_protocol(path)
        try:
            self.sfs.get(path)
            return True
        except Exception:
            return False

    def isdir(self, path):
        self._check_closed()
        if self._mode == "w":
            return os.path.isdir(self._stage_path(path))
        path = self._strip_protocol(path)
        try:
            return self.sfs.get(path).is_dir()
        except Exception:
            return False

    def isfile(self, path):
        self._check_closed()
        if self._mode == "w":
            return os.path.isfile(self._stage_path(path))
        path = self._strip_protocol(path)
        try:
            return not self.sfs.get(path).is_dir()
        except Exception:
            return False

    def mkdir(self, path, create_parents=True, **kwargs):
        """Create a directory in the staging area (write mode only).

        Input:
        - path: archive-internal directory path.
        - create_parents: if True (default), create intermediate directories.
        """
        self._check_closed()
        if self._mode != "w":
            raise ValueError("mkdir is not supported in read mode.")
        stage = self._stage_path(path)
        os.makedirs(stage, exist_ok=True) if create_parents else os.mkdir(stage)

    def makedirs(self, path, exist_ok=False):
        """Recursively create directories in the staging area (write mode only)."""
        self._check_closed()
        if self._mode != "w":
            raise ValueError("makedirs is not supported in read mode.")
        os.makedirs(self._stage_path(path), exist_ok=exist_ok)

    def rm(self, path, recursive=False, maxdepth=None):
        """Remove a file or directory from the staging area (write mode only).

        Input:
        - path: archive-internal path or list of paths.
        - recursive: if True, remove directories and their contents.
        """
        self._check_closed()
        if self._mode != "w":
            raise ValueError("rm is not supported in read mode.")
        paths = [path] if isinstance(path, str) else path
        for p in paths:
            stage = self._stage_path(p)
            if os.path.isdir(stage):
                if recursive:
                    shutil.rmtree(stage)
                else:
                    os.rmdir(stage)
            elif os.path.exists(stage):
                os.remove(stage)

    def _open(self, path, mode="rb", **kwargs):
        """Open an archive member or staging file.

        In read mode ``mode`` must be ``"rb"``.  In write mode any standard
        file mode (``"rb"``, ``"wb"``, ``"ab"`` …) is accepted.

        Input:
        - path: archive-internal file path.
        - mode: file open mode.

        Output:
        - File-like object.
        """
        self._check_closed()
        if self._mode == "w":
            stage = self._stage_path(path)
            if "w" in mode or "a" in mode or "x" in mode:
                os.makedirs(os.path.dirname(stage), exist_ok=True)
            return open(stage, mode)  # noqa: PTH123

        if mode != "rb":
            raise ValueError("ReadOnly filesystem")
        path = self._strip_protocol(path)
        entry = self.sfs.get(path)
        return _MemberFileProxy(entry.open())

    # ------------------------------------------------------------------
    # Write-mode commit / discard
    # ------------------------------------------------------------------

    def commit(self):
        """Pack the staging directory into the target SquashFS image (write mode only).

        Calls ``mksquashfs <staging_dir> <target> -noappend -comp <compressor>``
        plus any extra args supplied at construction time.

        Raises:
        - ``RuntimeError`` if ``mksquashfs`` is not found or exits non-zero.
        - ``ValueError`` if called in read mode.
        """
        if self._mode != "w":
            raise ValueError("commit() is only available in write mode.")
        cmd = [
            "mksquashfs",
            self._staging_dir,
            self._target,
            "-noappend",
            "-comp",
            self._compressor,
        ] + self._mksquashfs_args
        try:
            result = subprocess.run(cmd, check=True, capture_output=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "mksquashfs not found. Install squashfs-tools to enable writing."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"mksquashfs failed (exit {exc.returncode}):\n"
                f"{exc.stderr.decode(errors='replace')}"
            ) from exc
        return result

    def discard(self):
        """Discard all staged writes without creating a SquashFS image (write mode only)."""
        if self._mode != "w":
            raise ValueError("discard() is only available in write mode.")
        if self._closed:
            return
        self._auto_commit = False
        self._closed = True
        shutil.rmtree(self._staging_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Close filesystem resources."""
        if self._closed:
            return
        if self._mode == "w":
            try:
                self.commit()
            finally:
                self._closed = True
                shutil.rmtree(self._staging_dir, ignore_errors=True)
        else:
            self._closed = True
            try:
                if hasattr(self.sfs, "close"):
                    self.sfs.close()
            finally:
                if self._close_fo and self.fo is not None:
                    self.fo.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._mode == "w" and exc_type is not None:
            self._auto_commit = False
            self.discard()
        else:
            self.close()

    def __del__(self):
        if getattr(self, "_closed", False):
            return
        if getattr(self, "_mode", None) == "w":
            if getattr(self, "_auto_commit", False):
                # Auto-commit: fires when the write-mode FS is garbage-collected
                # (e.g. after an explicit gc.collect() call by the caller).
                try:
                    self.commit()
                except Exception:
                    pass  # best-effort — don't propagate from __del__
                finally:
                    self._closed = True
                    shutil.rmtree(
                        getattr(self, "_staging_dir", ""), ignore_errors=True
                    )
            else:
                shutil.rmtree(getattr(self, "_staging_dir", ""), ignore_errors=True)
            return
        self.close()


class SquashFSStore(LocalStore):
    """Zarr v3 store that stages writes locally and packs them into a SquashFS image on close.

    This is the cleanest alternative to :class:`SquashFSFileSystem` for zarr-based
    write workflows.  It relies entirely on zarr's documented ``Store.close()``
    contract — no ``gc.collect()`` calls or context-manager tricks are needed.

    Parameters
    ----------
    path : str
        Destination path for the SquashFS image (e.g. ``"output.squash"``).
    compressor : str, optional
        Compression algorithm passed to ``mksquashfs`` via ``-comp``.
        Defaults to ``"gzip"``.
    mksquashfs_args : list[str], optional
        Extra CLI arguments forwarded verbatim to ``mksquashfs``.

    Examples
    --------
    Write an xarray dataset directly into a SquashFS image::

        import xarray as xr
        from squashfsspec import SquashFSStore

        ds = xr.open_dataset("input.nc")
        with SquashFSStore("output.squash") as store:
            ds.to_zarr(store, consolidated=False)

    Read back::

        ds_back = xr.open_dataset(
            "squashfs:///",
            engine="zarr",
            consolidated=False,
            backend_kwargs={"storage_options": {"fo": "output.squash"}},
        )

    Or write multiple datasets under sub-paths::

        with SquashFSStore("archive.squash") as store:
            ds1.to_zarr(store.with_prefix("ds1.zarr"), consolidated=False)
            ds2.to_zarr(store.with_prefix("ds2.zarr"), consolidated=False)
    """

    def __init__(
        self,
        path: str,
        compressor: str = "gzip",
        mksquashfs_args: list | None = None,
    ) -> None:
        self._squash_path = os.path.abspath(path)
        self._compressor = compressor
        self._mksquashfs_args = mksquashfs_args or []
        self._staging_dir = tempfile.mkdtemp(prefix="squashfsstore_")
        self._committed = False
        self._discarded = False
        super().__init__(root=self._staging_dir)

    # ------------------------------------------------------------------
    # zarr Store protocol
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Pack the staging directory into the SquashFS image and clean up.

        Called automatically by the context manager's ``__exit__``.
        Raises ``RuntimeError`` if ``mksquashfs`` is not found or fails.
        """
        if self._committed or self._discarded:
            super().close()
            return
        self._commit()
        super().close()

    def discard(self) -> None:
        """Abandon staged writes without creating a SquashFS image.

        The staging directory is removed and no output file is produced.
        Safe to call multiple times.
        """
        if self._discarded or self._committed:
            return
        self._discarded = True
        shutil.rmtree(self._staging_dir, ignore_errors=True)
        self._is_open = False

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.discard()
        else:
            self.close()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def with_prefix(self, prefix: str) -> "SquashFSStore":
        """Return a view of this store rooted at *prefix* (no copy/commit).

        Useful for writing multiple datasets into sub-paths of the same archive::

            with SquashFSStore("archive.squash") as store:
                ds1.to_zarr(store.with_prefix("ds1.zarr"))
                ds2.to_zarr(store.with_prefix("ds2.zarr"))

        Parameters
        ----------
        prefix : str
            Sub-directory path within the staging area.

        Returns
        -------
        SquashFSStore
            A new store instance whose ``root`` is ``<staging_dir>/<prefix>``.
            Calling ``close()`` or ``discard()`` on the returned view is a
            no-op — lifecycle is managed by the parent store.
        """
        import pathlib

        sub_root = pathlib.Path(self._staging_dir) / prefix
        sub_root.mkdir(parents=True, exist_ok=True)

        # Create a view that shares the same staging area but is rooted at the
        # sub-path.  We bypass the async _open() because the directory already
        # exists; we just mark the store as open directly.
        view = object.__new__(_SquashFSStoreView)
        LocalStore.__init__(view, root=sub_root)
        view._is_open = True  # directory exists — skip async _open()
        return view

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _commit(self) -> None:
        cmd = [
            "mksquashfs",
            self._staging_dir,
            self._squash_path,
            "-noappend",
            "-comp",
            self._compressor,
        ] + self._mksquashfs_args
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "mksquashfs not found. Install squashfs-tools to enable writing."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"mksquashfs failed (exit {exc.returncode}):\n"
                f"{exc.stderr.decode(errors='replace')}"
            ) from exc
        finally:
            shutil.rmtree(self._staging_dir, ignore_errors=True)
        self._committed = True

    def __del__(self) -> None:
        # Best-effort cleanup of the staging directory on GC.
        if not getattr(self, "_committed", False) and not getattr(
            self, "_discarded", False
        ):
            shutil.rmtree(getattr(self, "_staging_dir", ""), ignore_errors=True)


class _SquashFSStoreView(LocalStore):
    """Internal view returned by ``SquashFSStore.with_prefix``.

    ``close()`` and ``discard()`` are no-ops — lifecycle is managed by the
    parent ``SquashFSStore`` instance.
    """

    def close(self) -> None:
        self._is_open = False

    def discard(self) -> None:
        pass


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


