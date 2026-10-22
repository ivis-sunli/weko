import pytest
from mock import patch, MagicMock

from invenio_previewer.ext import (
    obj_or_import_string,
    _InvenioPreviewerState
)


# def obj_or_import_string(value, default=None):
def test_obj_or_import_string(app):
    value = "invenio_previewer"
    assert obj_or_import_string(value=value) != None

    value = ["invenio_previewer"]
    assert obj_or_import_string(value=value) != None

    value = None
    assert obj_or_import_string(value=value) == None


# class _InvenioPreviewerState
# def previewable_extensions(self):
# ERROR ~ TypeError: 'str' object is not callable
def test_previewable_extensions(app):
    test = _InvenioPreviewerState(
        app=app, entry_point_group="invenio_previewer.previewers")

    assert test.previewable_extensions != None
    assert {"pdf", "md"}.issubset(test.previewable_extensions)
    assert test.entry_point_group is None


# def record_file_factory(self):
def test_record_file_factory(app):
    def invenio_previewer():
        return True

    data1 = MagicMock()
    data1.config = {"PREVIEWER_RECORD_FILE_FACOTRY": invenio_previewer}
    test = _InvenioPreviewerState(app=data1)

    assert test.record_file_factory is invenio_previewer
    assert test.record_file_factory() != None


# def register_previewer(self, name, previewer):
def test_register_previewer(app):
    data1 = MagicMock()
    test = _InvenioPreviewerState(app=data1)
    test.previewers = {"previewable_extensions": "previewable_extensions"}
    name = "previewable_extensions"
    previewer = MagicMock()
    previewer.previewable_extensions = "previewable_extensions"

    # Exception coverage
    with pytest.raises(AssertionError, match="Previewer with same name already registered"):
        test.register_previewer(
            name=name,
            previewer=previewer
        )
    assert test.previewers[name] == "previewable_extensions"

    name = "test"

    assert test.register_previewer(
        name=name,
        previewer=previewer
    ) == None
    assert test.previewers[name] is previewer


# def iter_previewers(self, previewers=None):
# Not able to call "iter_previewers" function
def test_iter_previewers(app):
    data1 = MagicMock()
    test = _InvenioPreviewerState(app=data1)
    previewer = MagicMock()
    test.previewers = {"test": previewer}
    previewers = ["test"]

    assert test.iter_previewers(previewers=previewers) != None
    assert list(test.iter_previewers(previewers=previewers)) == [previewer]
