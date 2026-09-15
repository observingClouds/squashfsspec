"""Behavioural tests for SquashFSFileSystem beyond the basic smoke tests.

Tests marked ``xfail(strict=True)`` document known defects. They start
failing loudly (as XPASS) once the defect is fixed, so the marker must be
removed together with the fix.
"""

# Standard library
import io
import pathlib

# Third-party
import fsspec
import pytest

# First-party
from squashfsspec import OffsetWrapper, SquashFSFileSystem

A_CONTENT = b"Hello from a.txt\n"
B_CONTENT = b"Hello from sub/b.txt\n"
C_CONTENT = bytes(range(256)) * 64  # 16 KiB, exercises seeking


@pytest.fixture
def tree(tmp_path) -> pathlib.Path:
    """Directory tree with files, a nested directory and a symlink."""
    root = tmp_path / "tree"
    (root / "sub" / "nested").mkdir(parents=True)
    (root / "a.txt").write_bytes(A_CONTENT)
    (root / "sub" / "b.txt").write_bytes(B_CONTENT)
    (root / "sub" / "nested" / "c.bin").write_bytes(C_CONTENT)
    (root / "link.txt").symlink_to("a.txt")
    return root


@pytest.fixture
def image(tree, make_squashfs) -> str:
    return make_squashfs(tree, "tree.squash")


@pytest.fixture
def fs(image):
    with SquashFSFileSystem(image) as fs:
        yield fs


# --------------------------------------------------------------------------
# Registration and construction
# --------------------------------------------------------------------------


def test_registered_with_fsspec(image):
    assert fsspec.get_filesystem_class("squashfs") is SquashFSFileSystem
    fs = fsspec.filesystem("squashfs", fo=image)
    assert isinstance(fs, SquashFSFileSystem)
    assert fs.isfile("a.txt")
    fs.close()


def test_requires_fo():
    with pytest.raises(ValueError, match="requires 'fo'"):
        SquashFSFileSystem()


def test_filelike_input_is_not_closed_by_filesystem(image):
    buf = io.BytesIO(pathlib.Path(image).read_bytes())
    fs = SquashFSFileSystem(buf)
    assert fs.ls("/", detail=False) == ["a.txt", "link.txt", "sub"]
    with fs.open("a.txt") as f:
        assert f.read() == A_CONTENT
    fs.close()
    assert fs.closed
    # The filesystem does not own a caller-supplied file object.
    assert not buf.closed


def test_pathlike_input(image):
    with SquashFSFileSystem(pathlib.Path(image)) as fs:
        assert fs.isfile("a.txt")
        assert fs.cat_file("a.txt") == A_CONTENT
        assert not fs.fo.closed
    assert fs.fo.closed


def test_pathlike_input_via_fsspec(image):
    fs = fsspec.filesystem("squashfs", fo=pathlib.Path(image))
    assert fs.isfile("a.txt")
    fs.close()


# --------------------------------------------------------------------------
# Listing and metadata
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["", "/", "squashfs://", "squashfs:///"])
def test_ls_root(fs, path):
    assert fs.ls(path, detail=False) == ["a.txt", "link.txt", "sub"]


def test_ls_root_detail(fs):
    entries = {e["name"]: e for e in fs.ls("/")}
    assert entries["a.txt"] == {
        "name": "a.txt",
        "size": len(A_CONTENT),
        "type": "file",
    }
    assert entries["sub"]["type"] == "directory"
    assert entries["sub"]["size"] == 0


def test_ls_subdirectory_returns_full_paths(fs):
    assert fs.ls("sub", detail=False) == ["sub/b.txt", "sub/nested"]
    assert fs.ls("/sub/", detail=False) == ["sub/b.txt", "sub/nested"]


def test_ls_file_returns_single_entry(fs):
    assert fs.ls("sub/b.txt", detail=False) == ["sub/b.txt"]
    (entry,) = fs.ls("sub/b.txt")
    assert entry == {
        "name": "sub/b.txt",
        "size": len(B_CONTENT),
        "type": "file",
    }


def test_info(fs):
    assert fs.info("a.txt") == {
        "name": "a.txt",
        "size": len(A_CONTENT),
        "type": "file",
    }
    assert fs.info("sub") == {"name": "sub", "size": 0, "type": "directory"}
    assert fs.info("/") == {"name": "", "size": 0, "type": "directory"}


def test_size(fs):
    assert fs.size("sub/nested/c.bin") == len(C_CONTENT)


def test_exists_isdir_isfile(fs):
    assert fs.exists("a.txt")
    assert fs.exists("sub")
    assert fs.exists("/")
    assert not fs.exists("missing")
    assert not fs.exists("sub/missing.txt")

    assert fs.isdir("sub")
    assert fs.isdir("sub/nested")
    assert not fs.isdir("a.txt")
    assert not fs.isdir("missing")

    assert fs.isfile("a.txt")
    assert not fs.isfile("sub")
    assert not fs.isfile("missing")


def test_missing_paths_raise_filenotfound(fs):
    with pytest.raises(FileNotFoundError):
        fs.ls("missing")
    with pytest.raises(FileNotFoundError):
        fs.info("missing")
    with pytest.raises(FileNotFoundError):
        fs.open("missing")
    with pytest.raises(FileNotFoundError):
        fs.open("sub/missing.txt")


def test_open_directory_raises_isadirectoryerror(fs):
    with pytest.raises(IsADirectoryError):
        fs.open("sub")
    with pytest.raises(IsADirectoryError):
        fs.open("/")
    with pytest.raises(IsADirectoryError):
        fs.cat_file("sub/nested")


# --------------------------------------------------------------------------
# Tree traversal
# --------------------------------------------------------------------------


def test_find(fs):
    assert fs.find("/") == [
        "a.txt",
        "link.txt",
        "sub/b.txt",
        "sub/nested/c.bin",
    ]
    assert fs.find("sub") == ["sub/b.txt", "sub/nested/c.bin"]


@pytest.mark.xfail(
    strict=True,
    reason="the root of find(withdirs=True) is reported as '/sub' while its "
    "children have no leading slash",
)
def test_find_with_dirs(fs):
    assert fs.find("sub", withdirs=True) == [
        "sub",
        "sub/b.txt",
        "sub/nested",
        "sub/nested/c.bin",
    ]


def test_walk(fs):
    walked = [
        (root, sorted(dirs), sorted(files))
        for root, dirs, files in fs.walk("/")
    ]
    assert walked == [
        ("/", ["sub"], ["a.txt", "link.txt"]),
        ("/sub", ["nested"], ["b.txt"]),
        ("/sub/nested", [], ["c.bin"]),
    ]


def test_du(fs):
    expected = len(A_CONTENT) + len(B_CONTENT) + len(C_CONTENT)
    # The symlink is currently reported as a file with the length of its
    # target path; exclude it from the comparison.
    assert fs.du("sub") == len(B_CONTENT) + len(C_CONTENT)
    assert fs.du("/") >= expected


@pytest.mark.xfail(
    strict=True,
    reason="_strip_protocol roots paths at '/', but ls/find return names "
    "without the leading slash, so glob patterns never match",
)
@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("*.txt", ["a.txt", "link.txt"]),
        ("/*.txt", ["a.txt", "link.txt"]),
        ("sub/*", ["sub/b.txt", "sub/nested"]),
        ("**/*.bin", ["sub/nested/c.bin"]),
    ],
)
def test_glob(fs, pattern, expected):
    assert sorted(fs.glob(pattern)) == expected


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def test_read_whole_file(fs):
    with fs.open("sub/nested/c.bin") as f:
        assert f.read() == C_CONTENT


def test_read_seek_tell(fs):
    with fs.open("sub/nested/c.bin") as f:
        assert f.tell() == 0
        assert f.read(4) == C_CONTENT[:4]
        assert f.tell() == 4
        f.seek(1000)
        assert f.read(8) == C_CONTENT[1000:1008]
        f.seek(0, io.SEEK_END)
        assert f.tell() == len(C_CONTENT)
        assert f.read() == b""


def test_cat_file_and_ranges(fs):
    assert fs.cat_file("a.txt") == A_CONTENT
    assert fs.cat_file("a.txt", start=6, end=10) == A_CONTENT[6:10]
    assert fs.cat("a.txt") == A_CONTENT


@pytest.mark.xfail(
    strict=True,
    reason="cat() keys are the '/'-rooted _strip_protocol paths, while "
    "ls/find/info report names without the leading slash",
)
def test_cat_multiple_keys_match_listing_names(fs):
    assert fs.cat(["a.txt", "sub/b.txt"]) == {
        "a.txt": A_CONTENT,
        "sub/b.txt": B_CONTENT,
    }


def test_text_mode(fs):
    with fs.open("a.txt", "r") as f:
        assert f.read() == A_CONTENT.decode()


def test_write_modes_rejected(fs):
    for mode in ("wb", "ab", "r+b"):
        with pytest.raises(ValueError, match="ReadOnly"):
            fs.open("a.txt", mode)


def test_multiple_members_open_concurrently(fs):
    with fs.open("a.txt") as fa, fs.open("sub/b.txt") as fb:
        assert fa.read(5) == A_CONTENT[:5]
        assert fb.read(5) == B_CONTENT[:5]
        assert fa.read() == A_CONTENT[5:]
        assert fb.read() == B_CONTENT[5:]


@pytest.mark.xfail(
    strict=True,
    reason="symlinks are reported as regular files with the target path "
    "length as size, and opening them raises NotAFileError",
)
def test_symlink_resolves_to_target(fs):
    with fs.open("link.txt") as f:
        assert f.read() == A_CONTENT
    assert fs.info("link.txt")["size"] == len(A_CONTENT)


# --------------------------------------------------------------------------
# URL handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "/"),
        ("/", "/"),
        ("a/b", "/a/b"),
        ("/a/b", "/a/b"),
        ("squashfs://a/b", "/a/b"),
        ("squashfs:///a/b", "/a/b"),
        ("squashfs:a/b", "/a/b"),
    ],
)
def test_strip_protocol(raw, expected):
    assert SquashFSFileSystem._strip_protocol(raw) == expected


def test_chained_url_via_fsspec_open(image):
    with fsspec.open(f"squashfs://sub/b.txt::{image}") as f:
        assert f.read() == B_CONTENT
    with fsspec.open(f"squashfs:///a.txt::{image}") as f:
        assert f.read() == A_CONTENT


def test_url_to_fs(image):
    fs, path = fsspec.core.url_to_fs(f"squashfs://sub/b.txt::{image}")
    assert isinstance(fs, SquashFSFileSystem)
    assert path == "/sub/b.txt"
    assert fs.cat_file(path) == B_CONTENT
    fs.close()


@pytest.mark.xfail(
    strict=True,
    reason="__del__ closes the archive as soon as the filesystem instance is "
    "garbage collected, even while member files are still open",
)
def test_member_outlives_filesystem_reference(image):
    # Nothing but the returned file object keeps the filesystem alive here.
    f = fsspec.open(f"squashfs://a.txt::{image}").open()
    assert f.read() == A_CONTENT
    f.close()


# --------------------------------------------------------------------------
# Offsets
# --------------------------------------------------------------------------


def test_offset_wrapper_translates_absolute_seeks():
    raw = io.BytesIO(b"0123456789")
    wrapped = OffsetWrapper(raw, 5)
    wrapped.seek(0)
    assert wrapped.tell() == 0
    assert wrapped.read(2) == b"56"
    assert wrapped.tell() == 2
    wrapped.seek(1, io.SEEK_CUR)
    assert wrapped.read() == b"89"


@pytest.mark.xfail(
    strict=True,
    reason="OffsetWrapper never seeks to its base offset, so dissect reads "
    "the superblock from position 0 and fails",
)
def test_image_at_offset(image):
    padding = b"\0" * 1000
    buf = io.BytesIO(padding + pathlib.Path(image).read_bytes())
    with SquashFSFileSystem(buf, offset=1000) as fs:
        assert fs.ls("/", detail=False) == ["a.txt", "link.txt", "sub"]
        assert fs.cat_file("sub/b.txt") == B_CONTENT
