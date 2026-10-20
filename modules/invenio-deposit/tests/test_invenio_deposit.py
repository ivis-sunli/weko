# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016-2019 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.


"""Module tests."""
import pytest

from copy import deepcopy
from flask import Flask, render_template_string
from invenio_deposit import InvenioDeposit, InvenioDepositREST
from invenio_deposit.proxies import current_deposit
from invenio_records_rest import InvenioRecordsREST
from invenio_records_rest.utils import PIDConverter


def _check_template():
    """Check template."""
    extended = """
        {% extends 'invenio_deposit/edit.html' %}
        {% block javascript %}{% endblock %}
        {% block css %}{% endblock %}
        {% block page_body %}{{ super() }}{% endblock %}
    """
    rendered = render_template_string(
        extended,
        pid=dict(pid_value=None),
        record=dict()
    )

    assert 'invenio-records' in rendered
    assert 'invenio-records-alert' in rendered
    assert 'invenio-records-form' in rendered
    assert 'invenio-records-actions' in rendered
    assert 'invenio-files-uploader' in rendered
    assert 'invenio-files-upload-zone' in rendered
    assert 'invenio-files-list' in rendered


def test_version():
    """Test version import."""
    from invenio_deposit import __version__
    assert __version__


def test_init():
    """Test extension initialization."""
    app = Flask('testapp')
    app.url_map.converters['pid'] = PIDConverter
    ext = InvenioDeposit(app)
    assert 'invenio-deposit' in app.extensions

    app = Flask('testapp')
    app.url_map.converters['pid'] = PIDConverter

    # check that current_deposit cannot be resolved
    with app.app_context():
        with pytest.raises(KeyError):
            current_deposit.app

    ext = InvenioDeposit()
    assert 'invenio-deposit' not in app.extensions
    ext.init_app(app)
    assert 'invenio-deposit' in app.extensions

    # check that current_deposit resolves correctly
    with app.app_context():
        current_deposit.app

# .tox/c1/bin/pytest --cov=invenio_deposit tests/test_invenio_deposit.py::test_conflict_in_endpoint_prefixes -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/invenio-deposit/.tox/c1/tmp
def test_conflict_in_endpoint_prefixes():
    """Test conflict in endpoint prefixes."""
    app = Flask('testapp')
    app.url_map.converters['pid'] = PIDConverter
    InvenioRecordsREST(app)
    ext = InvenioDepositREST()
    ext.init_config(app)

    endpoints = deepcopy(app.config['RECORDS_REST_ENDPOINTS'])
    app.config['RECORDS_REST_ENDPOINTS'] = endpoints
    # Due to incompatibilty with how we are registering endpoints between
    # invenio packages we need to now sanitize the endpoints registered in this
    # test.
    for endpoint in endpoints:
        endpoints[endpoint].pop('error_handlers', None)

    deposit_endpoints = deepcopy(app.config['DEPOSIT_REST_ENDPOINTS'])
    deposit_endpoints['recid'] = endpoints['recid']
    app.config['DEPOSIT_REST_ENDPOINTS'] = deposit_endpoints

    ext.init_app(app)

    with app.test_client() as c:
        assert 500 == c.get('/').status_code


def test_template(base_app):
    """Test view."""
    with base_app.test_request_context():
        _check_template()
