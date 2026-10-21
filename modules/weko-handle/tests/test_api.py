import pytest
import json
from mock import patch, MagicMock
from flask import Flask
from b2handle.handleexceptions import HandleAlreadyExistsException, HandleNotFoundException, HandleAuthenticationError

from weko_handle.api import Handle


# class Handle(object):
# def register_handle(self, location, hdl="", overwrite=False):
def test_register_handle(app):
    sample = Handle()

    # Exception coveraga ~ Line 86 - 89
    location = 1
    sample.register_handle(
        location=location
    )


    sample.register_handle(
        location=None,hdl=1
    )

    # Exception coveraga
    with patch("weko_handle.api.PIDClientCredentials.load_from_JSON", side_effect=HandleAlreadyExistsException()):
        location = 1
        sample.register_handle(
            location=location
        )

    with patch("weko_handle.api.PIDClientCredentials.load_from_JSON", side_effect=HandleAuthenticationError()):
            location = 1
            sample.register_handle(
                location=location
            )

    mock_client = MagicMock()
    mock_client.register_handle.return_value = "test/handle"
    with patch("weko_handle.api.PIDClientCredentials.load_from_JSON") as load_credentials:
        with patch("weko_handle.api.EUDATHandleClient.instantiate_with_credentials",
                   return_value=mock_client) as factory:
            assert sample.register_handle(
                location=None, hdl="test/handle"
            ) == "test/handle"
            factory.assert_called_once_with(load_credentials.return_value)
            mock_client.register_handle.assert_called_once_with(
                "test/handle", None, overwrite=False)

def test_delete_handle(app):
    sample = Handle()

    assert sample.delete_handle(hdl=1) is None

    # HandleNotFoundException coveraga
    with patch("weko_handle.api.PIDClientCredentials.load_from_JSON", side_effect=HandleNotFoundException()):
        assert sample.delete_handle(hdl=1) == 1

    # AttributeError coveraga
    with patch("weko_handle.api.PIDClientCredentials.load_from_JSON", side_effect=AttributeError()):
        assert sample.delete_handle(hdl=1) is None

# def get_prefix(self):
def test_get_prefix(app):
    sample = Handle()

    def load_from_JSON(item):

        def get_prefix():
            return "get_prefix"

        load_from_JSON_MagicMock = MagicMock()
        load_from_JSON_MagicMock.get_prefix = get_prefix

        return load_from_JSON_MagicMock

    with app.app_context():
        with patch("weko_handle.api.PIDClientCredentials.load_from_JSON",
                   side_effect=load_from_JSON) as load_credentials:
            assert sample.get_prefix() == "get_prefix"
            load_credentials.assert_called_once_with(sample.credential_path)
