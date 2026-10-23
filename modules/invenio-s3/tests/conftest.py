# -*- coding: utf-8 -*-
#
# Copyright (C) 2018, 2019 Esteban J. G. Gabancho.
#
# Invenio-S3 is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Pytest configuration."""

import boto3
import copy
import hashlib
import os
import pytest
import shutil
import tempfile
import uuid

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Mapper, Session
from sqlalchemy_continuum import versioning_manager

from flask import Flask, current_app
from moto import mock_aws
from sqlalchemy_utils.functions import create_database, database_exists, drop_database

from invenio_app.factory import create_api
from invenio_db import InvenioDB
from invenio_db import db as db_
from invenio_files_rest import InvenioFilesREST
from invenio_files_rest.models import Location
from invenio_s3 import InvenioS3, S3FSFileStorage

from weko_deposit.config import (
    WEKO_BUCKET_QUOTA_SIZE,
    WEKO_DEPOSIT_REST_ENDPOINTS as _WEKO_DEPOSIT_REST_ENDPOINTS,
    _PID,
    DEPOSIT_REST_ENDPOINTS as _DEPOSIT_REST_ENDPOINTS,
    WEKO_MIMETYPE_WHITELIST_FOR_SEARCH as _WEKO_MIMETYPE_WHITELIST_FOR_SEARCH,
    WEKO_DEPOSIT_BIBLIOGRAPHIC_INFO_SYS_KEY as _WEKO_DEPOSIT_BIBLIOGRAPHIC_INFO_SYS_KEY
)
from weko_indextree_journal.config import (
    WEKO_INDEXTREE_JOURNAL_REST_ENDPOINTS as _WEKO_INDEXTREE_JOURNAL_REST_ENDPOINTS,
)
from weko_schema_ui.config import (
    WEKO_SCHEMA_REST_ENDPOINTS as _WEKO_SCHEMA_REST_ENDPOINTS,
)


@pytest.fixture(scope='module')
def app_config(app_config):
    """Customize application configuration."""
    app_config[
        'FILES_REST_STORAGE_FACTORY'] = 'invenio_s3.s3fs_storage_factory'
    app_config['S3_ENDPOINT_URL'] = None

    app_config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI',
                                           'postgresql+psycopg2://invenio:dbpass123@postgresql:5432/wekotest')
    app_config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
    app_config['TESTING'] = True
    app_config['S3_ACCESS_KEY_ID'] = 'test'
    app_config['S3_SECRET_ACCESS_KEY'] = 'test'
    app_config['S3_DEFAULT_BLOCK_SIZE'] = 1024  # 1 KB
    app_config['S3_MAXIMUM_NUMBER_OF_PARTS'] = 10
    return app_config


@pytest.fixture(scope='module')
def create_app():
    """Application factory fixture."""
    def factory(**config):
        app = Flask('testapp')
        app.config.update(**config)

        InvenioDB(app)
        InvenioFilesREST(app)
        InvenioS3(app)

        return app

    return factory

@pytest.fixture(scope='module')
def instance_path():
    path = tempfile.mkdtemp()
    try:
        yield path
    finally:
        shutil.rmtree(path)

@pytest.fixture(scope='module')
def base_app(instance_path, versioning_listeners):
    """Flask application fixture."""
    app = Flask('testapp', instance_path=instance_path)

    app.config.update(
    FILES_REST_STORAGE_FACTORY='invenio_s3:s3_storage_factory',
    S3_ENDPOINT_URL=None,
    S3_ACCESS_KEY_ID= '',
    S3_SECRET_ACCESS_KEY = '',
    SQLALCHEMY_DATABASE_URI = make_url(os.environ['SQLALCHEMY_DATABASE_URI']).set(
        database='s3_ut_' + uuid.uuid4().hex),
    SQLALCHEMY_TRACK_MODIFICATIONS = True,
    TESTING = True
    )

    try:
        InvenioDB(app)
        InvenioFilesREST(app)
        InvenioS3(app)

        yield app
    finally:
        if 'sqlalchemy' in app.extensions:
            with app.app_context():
                db_.session.remove()
                db_.engine.dispose()

@pytest.fixture(scope='module')
def app(base_app):
    """Flask application fixture."""
    with base_app.app_context():
        yield base_app


@pytest.fixture(scope='module')
def database(app):
    """Get setup database."""
    database_url = db_.engine.url
    if database_exists(database_url):
        raise RuntimeError('Refusing to reuse an existing test database')
    create_database(database_url)
    try:
        db_.create_all()
        yield db_
    finally:
        db_.session.remove()
        db_.engine.dispose()
        drop_database(database_url)

@pytest.fixture(scope='module')
def location_path(instance_path):
    """Temporary directory for location path."""
    tmppath = tempfile.mkdtemp(dir=instance_path)
    try:
        yield str(tmppath)
    finally:
        shutil.rmtree(tmppath)


@pytest.fixture(scope='module')
def location(location_path, database):
    """File system locations."""
    loc = Location(
        name='testloc',
        uri=location_path,
        default=True,
        type='s3',
        access_key='',
        secret_key='',
        s3_endpoint_url="https://s3.amazonaws.com",
        s3_send_file_directly=True,
        s3_maximum_number_of_parts=1000,
        s3_default_block_size=10*1024*1024,
        s3_url_expiration=3600
    )
    database.session.add(loc)
    database.session.commit()
    return loc

@pytest.fixture(scope='function')
def s3_bucket(app, monkeypatch):
    """S3 bucket fixture."""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'test')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'test')
    with mock_aws():
        session = boto3.Session(
            aws_access_key_id='test',
            aws_secret_access_key='test',
        )
        s3 = session.resource('s3')
        bucket = s3.create_bucket(Bucket='invenio-s3-ut-' + uuid.uuid4().hex)

        try:
            yield bucket
        finally:
            for obj in bucket.objects.all():
                obj.delete()
            bucket.delete()


@pytest.fixture(scope='function')
def s3fs_testpath(s3_bucket):
    """S3 test path."""
    return 's3://{}/path/to/data'.format(s3_bucket.name)


@pytest.fixture(scope='function')
def s3fs(s3_bucket, s3fs_testpath, location):
    """Instance of S3FSFileStorage."""
    s3_storage = S3FSFileStorage(
        s3fs_testpath,
        size=0,
        modified=None,
        clean_dir=True,
        location=location
    )
    return s3_storage


@pytest.fixture
def file_instance_mock(s3fs_testpath):
    """Mock of a file instance."""
    class FileInstance(object):
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    return FileInstance(
        id='deadbeef-65bd-4d9b-93e2-ec88cc59aec5',
        uri=s3fs_testpath,
        size=4,
        updated=None)


@pytest.fixture()
def get_md5():
    """Get MD5 of data."""
    def inner(data, prefix=True):
        m = hashlib.md5()
        m.update(data)
        return "md5:{0}".format(m.hexdigest()) if prefix else m.hexdigest()

    return inner

@pytest.fixture(scope='module')
def celery_config():
    """Override pytest-invenio fixture.

    TODO: Remove this fixture if you add Celery support.
    """
    return {}

@pytest.fixture(scope='module')
def versioning_listeners():
    """Release only the versioning listeners installed by this application."""
    registrations = [
        (target, name, listener)
        for target, listeners in (
            (Session, versioning_manager.session_listeners),
            (Mapper, versioning_manager.mapper_listeners),
            (Mapper, versioning_manager.class_config_listeners),
        )
        for name, listener in listeners.items()
    ]
    registrations.extend([
        (Engine, 'before_execute', versioning_manager.track_association_operations),
        (Engine, 'rollback', versioning_manager.clear_connection),
        (Engine, 'set_connection_execution_options', versioning_manager.track_cloned_connections),
    ])
    owned = [registration for registration in registrations
             if not event.contains(*registration)]
    try:
        yield
    finally:
        for registration in reversed(owned):
            if event.contains(*registration):
                event.remove(*registration)
