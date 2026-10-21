# -*- coding: utf-8 -*-
#
# Copyright (C) 2019 National Institute of Informatics.
#
# WEKO-Handle is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration.

See https://pytest-invenio.readthedocs.io/ for documentation on which test
fixtures are available.
"""

import json
import os
import pytest
import shutil
import tempfile
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Mapper, Session
from sqlalchemy_continuum import versioning_manager

from flask import Flask
from flask_babel import Babel
from invenio_db import InvenioDB
from invenio_db import db as db_
from os.path import dirname, exists, join
from sqlalchemy_utils.functions import create_database, database_exists, drop_database

from weko_handle import WekoHandle
from weko_handle.views import blueprint


@pytest.yield_fixture()
def instance_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


@pytest.fixture()
def versioning_listeners():
    """Release only versioning listeners installed by this app."""
    listeners = []
    for target, hooks in (
        (Session, versioning_manager.session_listeners),
        (Mapper, versioning_manager.mapper_listeners),
        (Mapper, versioning_manager.class_config_listeners),
        (Engine, {
            'before_execute': versioning_manager.track_association_operations,
            'rollback': versioning_manager.clear_connection,
            'set_connection_execution_options':
                versioning_manager.track_cloned_connections,
        }),
    ):
        for name, listener in hooks.items():
            listeners.append((target, name, listener,
                              event.contains(target, name, listener)))
    try:
        yield
    finally:
        for target, name, listener, existed in reversed(listeners):
            if not existed and event.contains(target, name, listener):
                event.remove(target, name, listener)


@pytest.fixture()
def base_app(instance_path, versioning_listeners):
    """Flask application fixture."""
    app_ = Flask(
        "testapp",
        instance_path=instance_path,
        static_folder=join(instance_path, "static"),
    )
    database_url = make_url(os.environ["SQLALCHEMY_DATABASE_URI"])
    database_url = database_url.set(database="handle_ut_" + uuid4().hex)
    app_.config.update(
        CELERY_ALWAYS_EAGER=True,
        CELERY_CACHE_BACKEND="memory",
        CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
        CELERY_RESULT_BACKEND="cache",
        CACHE_REDIS_URL=os.environ.get("CACHE_REDIS_URL", "redis://redis:6379/0"),
        CACHE_REDIS_DB=0,
        CACHE_REDIS_HOST="redis",
        REDIS_PORT="6379",
        JSONSCHEMAS_URL_SCHEME="http",
        SECRET_KEY="CHANGE_ME",
        SECURITY_PASSWORD_SALT="CHANGE_ME_ALSO",
        # SQLALCHEMY_DATABASE_URI=os.environ.get(
        #     "SQLALCHEMY_DATABASE_URI", "sqlite:///test.db"
        # ),
        SQLALCHEMY_DATABASE_URI=database_url,
        WEKO_HANDLE_CREDS_JSON_PATH=join(instance_path, "missing-handle-creds.json"),
        SQLALCHEMY_TRACK_MODIFICATIONS=True,
        SQLALCHEMY_ECHO=False,
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        DEPOSIT_SEARCH_API="/api/search",
        SECURITY_PASSWORD_HASH="plaintext",
        SECURITY_PASSWORD_SCHEMES=["plaintext"],
        SECURITY_DEPRECATED_PASSWORD_SCHEMES=[],
        OAUTHLIB_INSECURE_TRANSPORT=True,
        OAUTH2_CACHE_TYPE="simple",
        ACCOUNTS_JWT_ENABLE=False,
        INDEXER_DEFAULT_INDEX="{}-weko-item-v1.0.0".format("test"),
        INDEXER_FILE_DOC_TYPE="content",
        WEKO_INDEX_TREE_STYLE_OPTIONS={
            "id": "weko",
            "widths": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
        },
        WEKO_INDEX_TREE_UPATED=True,
        I18N_LANGUAGES=[("ja", "Japanese"), ("en", "English")],
        SERVER_NAME="TEST_SERVER",
        SEARCH_OPENSEARCH_HOSTS = os.environ.get("SEARCH_OPENSEARCH_HOSTS", "opensearch"),
        SEARCH_INDEX_PREFIX="test-",
        WEKO_PERMISSION_ROLE_USER=[
            "System Administrator",
            "Repository Administrator",
            "Contributor",
            "General",
            "Community Administrator",
        ],
        WEKO_PERMISSION_SUPER_ROLE_USER=[
            "System Administrator",
            "Repository Administrator",
        ]
    )
    # with ESTestServer(timeout=30) as server:
    try:
        Babel(app_)
        InvenioDB(app_)
        WekoHandle(app_)
        app_.register_blueprint(blueprint)
        yield app_
    finally:
        if 'sqlalchemy' in app_.extensions:
            with app_.app_context():
                db_.session.remove()
                db_.engine.dispose()


@pytest.yield_fixture()
def app(base_app):
    """Flask application fixture."""
    with base_app.app_context():
        yield base_app


@pytest.yield_fixture()
def client(app):
    """Get test client."""
    with app.test_client() as client:
        yield client


@pytest.yield_fixture()
def db(app):
    """Database fixture."""
    url = db_.engine.url
    assert url.database.startswith('handle_ut_')
    assert not database_exists(url)
    create_database(url)
    try:
        db_.create_all()
        yield db_
    finally:
        db_.session.remove()
        db_.engine.dispose()
        drop_database(url)


@pytest.fixture()
def handle_credentials(app):
    """Local, non-secret credentials for the mocked Handle client."""
    path = app.config['WEKO_HANDLE_CREDS_JSON_PATH']
    with open(path, 'w') as stream:
        json.dump({
            'prefix': '123',
            'username': '300:123/TEST',
            'password': 'test-only',
            'handle_server_url': 'https://handle.invalid',
        }, stream)
    return path
