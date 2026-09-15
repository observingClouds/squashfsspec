# Third-party
import pytest

# First-party
from squashfsspec import SquashFSFileSystem


@pytest.fixture
def squashfs_file(tmp_path, make_squashfs):
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    subdir = test_dir / "subdir"
    subdir.mkdir()

    (test_dir / "file1.txt").write_text("Hello from file 1")
    (subdir / "file2.txt").write_text("Hello from file 2 in subdir")

    return make_squashfs(test_dir, "test.squash")


def test_driver(squashfs_file):
    fs = SquashFSFileSystem(squashfs_file)

    # Listing root
    ls_root = fs.ls("")
    assert any(
        "file1.txt" in item
        if isinstance(item, str)
        else "file1.txt" in item["name"]
        for item in ls_root
    )

    # Reading file1.txt
    with fs.open("file1.txt", "rb") as f:
        assert f.read().decode() == "Hello from file 1"

    # Reading subdir/file2.txt
    with fs.open("subdir/file2.txt", "rb") as f:
        assert f.read().decode() == "Hello from file 2 in subdir"


def test_close_semantics(squashfs_file):
    fs = SquashFSFileSystem(squashfs_file)
    assert not fs.closed

    f = fs.open("file1.txt", "rb")
    assert not f.closed
    assert not fs.fo.closed

    f.close()
    assert f.closed
    assert not fs.fo.closed
    with pytest.raises(ValueError, match="I/O operation on closed file\\."):
        f.read(1)

    with fs.open("file1.txt", "rb") as g:
        assert not g.closed
        _ = g.read(1)

    assert g.closed
    assert not fs.fo.closed

    fs.close()
    assert fs.closed
    assert fs.fo.closed
    with pytest.raises(
        ValueError, match="I/O operation on closed filesystem\\."
    ):
        fs.open("file1.txt", "rb")


def test_nested_context_managers(squashfs_file):
    with SquashFSFileSystem(squashfs_file) as fs:
        assert not fs.closed
        assert not fs.fo.closed
        with fs.open("file1.txt", "rb") as f:
            assert f.read().decode() == "Hello from file 1"
        assert f.closed

    assert fs.closed
    assert fs.fo.closed
