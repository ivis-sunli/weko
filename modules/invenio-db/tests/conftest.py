# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015-2018 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.


"""Pytest configuration."""

import invenio_db
import pytest
import os
import sys
import shutil
import tempfile
from uuid import uuid4
from sqlalchemy.engine.url import make_url
from sqlalchemy_utils.functions import drop_database
from flask import Flask
from flask_babel import Babel
from flask.cli import ScriptInfo
from invenio_db import shared
from invenio_db.utils import alembic_test_context
# from os.path import dirname, join
from unittest.mock import patch
from pkg_resources import EntryPoint
from sqlalchemy_utils.functions import create_database, database_exists
from werkzeug.utils import import_string



sys.path.append(os.path.dirname(__file__))

@pytest.yield_fixture()
def db(app, monkeypatch, mock_entry_points):
    """Database fixture with session sharing."""
    from invenio_db import ext, utils
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from sqlalchemy_continuum import remove_versioning, versioning_manager

    db_ = shared.SQLAlchemy(
        metadata=shared.MetaData(naming_convention=shared.NAMING_CONVENTION)
    )
    for module in (invenio_db, shared, ext, utils):
        monkeypatch.setattr(module, 'db', db_)
    options = versioning_manager.options.copy()
    db_.init_app(app)
    try:
        yield db_
    finally:
        extension = app.extensions.get('invenio-db')
        manager = getattr(extension, 'versioning_manager', None)
        if manager is not None and event.contains(
                Engine, 'before_execute', manager.track_association_operations):
            remove_versioning(manager=manager)
        versioning_manager.options.clear()
        versioning_manager.options.update(options)
        db_.session.remove()
        try:
            if database_exists(app.config['SQLALCHEMY_DATABASE_URI']):
                db_.drop_all()
        finally:
            db_.engine.dispose()


@pytest.yield_fixture()
def instance_path():
    """Temporary instance path."""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture()
def database_uri():
    """Create and remove only this test's PostgreSQL database."""
    configured = os.environ.get('SQLALCHEMY_DATABASE_URI')
    if configured:
        url = make_url(configured)
    else:
        from sqlalchemy.engine import URL
        url = URL.create(
            'postgresql+psycopg2',
            username=os.environ['INVENIO_POSTGRESQL_DBUSER'],
            password=os.environ['INVENIO_POSTGRESQL_DBPASS'],
            host='postgresql',
            port=5432,
        )
    if url.get_backend_name() != 'postgresql':
        raise ValueError('These migration tests require PostgreSQL')
    url = url.set(database='invenio_db_ut_' + uuid4().hex)
    uri = url.render_as_string(hide_password=False)
    create_database(uri)
    try:
        yield uri
    finally:
        if database_exists(uri):
            drop_database(uri)


@pytest.fixture()
def base_app(instance_path, database_uri):
    app_ = Flask(
        "testapp",
        instance_path=instance_path
    )
    app_.config.update(
        SECRET_KEY="SECRET_KEY",
        TESTING=True,
        SERVER_NAME="test_server",
        DB_VERSIONING=False,
        DB_VERSIONING_USER_MODEL=None,
        SQLALCHEMY_DATABASE_URI=database_uri,
        ALEMBIC_CONTEXT=alembic_test_context(),
    )

    #InvenioDB(app_)

    return app_

@pytest.yield_fixture()
def app(base_app):
    """Flask application fixture."""
    Babel(base_app)
    with base_app.app_context():
        yield base_app

@pytest.fixture()
def script_info(app):
    """Get ScriptInfo object for testing CLI."""
    return ScriptInfo(create_app=lambda: app)

class MockEntryPoint(EntryPoint):
    """Mocking of entrypoint."""

    def load(self):
        """Mock load entry point."""
        if self.name == 'importfail':
            raise ImportError()
        else:
            return import_string(self.name)
def _mock_entry_points(group=None):
    data = {
        'invenio_db.models': [MockEntryPoint('demo.child', 'demo.child'),
                              MockEntryPoint('demo.parent', 'demo.parent')],
        'invenio_db.models_a': [
            MockEntryPoint('demo.versioned_a', 'demo.versioned_a'),
        ],
        'invenio_db.models_b': [
            MockEntryPoint('demo.versioned_b', 'demo.versioned_b'),
        ],
    }
    names = data.keys() if group is None else [group]
    for key in names:
        for entry_point in data.get(key, []):
            yield entry_point

@pytest.yield_fixture()
def mock_entry_points():
    try:
        with patch("invenio_db.ext.importlib_metadata.entry_points", _mock_entry_points):
            yield
    finally:
        modules = ["demo", "demo.child", "demo.parent", "demo.versioned_a","demo.versioned_b"]
        for module in modules:
            if module in sys.modules:
                del sys.modules[module]
