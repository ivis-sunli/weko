import pytest
import os
import errno
import subprocess
import uuid
from unittest.mock import patch, MagicMock

from invenio_previewer.api import PreviewFile, convert_to, LibreOfficeError


# class PreviewFile(object):
# def bucket(self):
def test_bucket_PreviewFile(app):
    test = PreviewFile(
        pid=1,
        record={},
        fileobj={}
    )
    test.file = MagicMock()
    test.file.bucket_id = MagicMock()

    assert test.bucket is test.file.bucket_id


# def convert_to(folder, source):
# .tox/c1/bin/pytest --cov=invenio_previewer tests/test_api.py::test_convert_to -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/invenio-previewer/.tox/c1/tmp
def test_convert_to(app, tmp_path):
    folder = str(tmp_path)
    source = str(tmp_path / uuid.uuid4().hex / "is_being_used")
    profile = "/tmp/" + source.split("/")[-2] + "_libreoffice"
    app.config['PREVIEWER_CONVERT_PDF_RETRY_COUNT'] = 9

    with app.test_request_context('/records/1/preview'):
        process = subprocess.CompletedProcess([], 0, stdout=b'')
        with patch('invenio_previewer.api.subprocess.run', return_value=process) as run:
            with patch('invenio_previewer.api.sleep'):
                with pytest.raises(LibreOfficeError) as error:
                    convert_to(folder=folder, source=source)
            assert error.value.output == ''
            assert run.call_count == 10
            assert run.call_args.kwargs['env']['HOME'] == profile
        assert not os.path.exists(profile)

        filename = os.path.join(folder, 'converted.pdf')
        process.stdout = ('-> ' + filename + ' using filter').encode()
        with patch('invenio_previewer.api.subprocess.run', return_value=process) as run:
            assert convert_to(folder=folder, source=source) == filename
            assert run.call_count == 1
            assert run.call_args.args[0] == [
                'libreoffice', '--headless', '--convert-to', 'pdf',
                '--outdir', folder, source]
        assert not os.path.exists(profile)

        os.mkdir(profile)
        with patch('invenio_previewer.api.subprocess.run', return_value=process):
            assert convert_to(folder=folder, source=source) == filename
        assert not os.path.exists(profile)

        errors = []
        for exception in [FileNotFoundError('test'), PermissionError('test'),
                          OSError('test'), OSError(errno.ENOSPC, 'No space left on device')]:
            with patch('invenio_previewer.api.subprocess.run', side_effect=exception) as run:
                with patch('invenio_previewer.api.flash') as flash:
                    try:
                        convert_to(folder=folder, source=source)
                    except Exception as error:
                        errors.append(error)
                    else:
                        pytest.fail('Failed conversion must raise LibreOfficeError')
                    run.assert_called_once()
                    flash.assert_called_once()
            assert not os.path.exists(profile)
        assert all(isinstance(error, LibreOfficeError) for error in errors), errors


# class LibreOfficeError(Exception):
def test_LibreOfficeError(app):
    test = LibreOfficeError(
        output="output"
    )
    assert test.output == "output"
