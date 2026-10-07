from LungViZ.file_browser import FileBrowser, FileDialogRequest, FileFilter


GEOMETRY = FileFilter("Geometry", ("*.exnode", "*.exelem"))


def test_open_files_filters_entries_and_supports_multiple_selection(tmp_path):
    (tmp_path / "nested").mkdir()
    node = tmp_path / "tree.exnode"
    element = tmp_path / "tree.exelem"
    ignored = tmp_path / "notes.txt"
    node.write_text("node")
    element.write_text("element")
    ignored.write_text("notes")

    browser = FileBrowser()
    browser.open(
        FileDialogRequest(
            "Load geometry",
            "open_files",
            initial_directory=tmp_path,
            filters=(GEOMETRY,),
        )
    )

    assert [path.name for path in browser.visible_entries()] == [
        "nested",
        "tree.exelem",
        "tree.exnode",
    ]
    browser.select(node)
    browser.select(element)
    outcome = browser.confirm()

    assert outcome.paths == (node.resolve(), element.resolve())
    assert not browser.active


def test_open_file_requires_a_selection(tmp_path):
    browser = FileBrowser()
    browser.open(FileDialogRequest("Open", "open_file", tmp_path, (GEOMETRY,)))

    assert browser.confirm() is None
    assert browser.error == "Select at least one file."


def test_typed_file_path_selects_the_file(tmp_path):
    node = tmp_path / "tree.exnode"
    node.write_text("node")
    browser = FileBrowser()
    browser.open(FileDialogRequest("Open", "open_file", tmp_path, (GEOMETRY,)))
    browser.path_input = str(node)

    assert browser.go_to_input()
    assert browser.selected == [node.resolve()]


def test_directory_selection_returns_current_directory(tmp_path):
    child = tmp_path / "dicom"
    child.mkdir()
    browser = FileBrowser()
    browser.open(FileDialogRequest("DICOM", "select_directory", tmp_path))

    assert browser.navigate(child)
    outcome = browser.confirm()

    assert outcome.paths == (child.resolve(),)


def test_save_adds_default_extension_and_requires_overwrite_confirmation(tmp_path):
    browser = FileBrowser()
    request = FileDialogRequest(
        "Screenshot",
        "save_file",
        tmp_path,
        (FileFilter("PNG", ("*.png",)),),
        "lungviz_view",
    )
    browser.open(request)

    outcome = browser.confirm()
    assert outcome.paths == ((tmp_path / "lungviz_view.png").resolve(),)

    existing = tmp_path / "existing.png"
    existing.write_bytes(b"image")
    browser.open(request)
    browser.filename_input = existing.name

    assert browser.confirm() is None
    assert "already exists" in browser.error
    outcome = browser.confirm()
    assert outcome.paths == (existing.resolve(),)


def test_cancel_returns_an_empty_outcome(tmp_path):
    browser = FileBrowser()
    browser.open(FileDialogRequest("Open", "open_file", tmp_path))

    outcome = browser.cancel()

    assert not outcome.accepted
    assert outcome.paths == ()
    assert not browser.active
