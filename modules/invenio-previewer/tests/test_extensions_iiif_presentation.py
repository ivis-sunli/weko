import pytest
import os
import json
from unittest.mock import patch, MagicMock, mock_open

from invenio_previewer.api import PreviewFile
from invenio_previewer.extensions.iiif_presentation import (
    validate_json,
    can_preview,
    preview
)


# def validate_json(file):
# .tox/c1/bin/pytest --cov=invenio_previewer tests/test_extensions_iiif_presentation.py::test_validate_json -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/invenio-previewer/.tox/c1/tmp
def test_validate_json(app):

    def _mock_file(json_body, size):
        file_mock = MagicMock()
        file_mock.size = size
        body = json_body if isinstance(json_body, str) else json.dumps(json_body)
        fp_mock = MagicMock()
        fp_mock.read.return_value.decode.return_value = body
        file_mock.open.return_value.__enter__.return_value = fp_mock
        return file_mock

    app.config['PREVIEWER_MAX_FILE_SIZE_BYTES'] = 1000

    file_mock = _mock_file({}, size=1001)
    assert validate_json(file=file_mock) is False

    file_mock = _mock_file(
        {"@context": ["http://iiif.io/api/presentation/2/context.json"]},
        size=999,
    )
    assert validate_json(file=file_mock) is True

    file_mock = _mock_file(
        {"@context": "http://iiif.io/api/presentation/3/context.json"},
        size=999,
    )
    assert validate_json(file=file_mock) is True

    file_mock = _mock_file({"@context": "not-matching"}, size=999)
    assert validate_json(file=file_mock) is False

    file_mock = _mock_file({"foo": "bar"}, size=999)
    assert validate_json(file=file_mock) is False

    file_mock = _mock_file("not a json string", size=999)
    assert validate_json(file=file_mock) is False



# def can_preview(file):
def test_can_preview(app):
    def is_local():
        return True

    file = MagicMock()
    file.is_local = is_local
    file.filename = 'manifest.json'

    with patch("invenio_previewer.extensions.iiif_presentation.validate_json", return_value=True):
        assert can_preview(file=file) == True

    with patch("invenio_previewer.extensions.iiif_presentation.validate_json", return_value=False):
        assert can_preview(file=file) == True


# def preview(file):
def test_preview(app):
    file = MagicMock()
    file.pid = MagicMock()
    file.pid.pid_value = "9999"
    file.uri = '/'
    with app.test_request_context():
        with patch("invenio_previewer.extensions.iiif_presentation.validate_json", return_value=False):
            result = preview(file=file)
            assert result is not None
            assert 'http://localhost/api/iiif/v2/records/9999/manifest.json' in result
