# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016-2022 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration."""

import os
import shutil
import tempfile
import uuid

import pytest
from celery.messaging import establish_connection
from flask import Flask
from flask_celeryext import FlaskCeleryExt
from invenio_db import InvenioDB, db
from invenio_records import InvenioRecords
from invenio_search import InvenioSearch
from invenio_search.engine import dsl
from sqlalchemy.engine.url import make_url
from sqlalchemy_utils.functions import create_database, database_exists, drop_database

from invenio_indexer import InvenioIndexer
from invenio_indexer.signals import before_record_index
from kombu import Exchange, Queue


@pytest.fixture()
def base_app(request, monkeypatch):
    """Base application fixture."""
    instance_path = tempfile.mkdtemp()
    app = Flask("testapp", instance_path=instance_path)
    signal_receivers = set(before_record_index.receivers_for(app))
    database_url = make_url(os.environ['SQLALCHEMY_DATABASE_URI']).set(
        database='indexer_ut_' + uuid.uuid4().hex)
    index_prefix = 'indexer-ut-' + uuid.uuid4().hex + '-'
    queue_name = 'indexer-ut-' + uuid.uuid4().hex
    exchange = Exchange(queue_name, type='direct')
    app.config.update(
        BROKER_URL=os.environ['BROKER_URL'],
        CELERY_BROKER_URL=os.environ['BROKER_URL'],
        BROKER_TRANSPORT_OPTIONS={'confirm_publish': True},
        CELERY_ALWAYS_EAGER=True,
        CELERY_CACHE_BACKEND="memory",
        CELERY_EAGER_PROPAGATES=True,
        CELERY_RESULT_BACKEND="cache",
        JSONSCHEMAS_URL_SCHEME='http',
        SECRET_KEY='CHANGE_ME',
        SECURITY_PASSWORD_SALT='CHANGE_ME_ALSO',
        INDEXER_DEFAULT_INDEX=index_prefix + "records-default-v1.0.0",
        INDEXER_MQ_QUEUE=Queue(
            queue_name, exchange=exchange, routing_key=queue_name,
            auto_delete=False, queue_arguments={"x-queue-type": "quorum"}),
        INDEXER_MQ_EXCHANGE=exchange,
        INDEXER_MQ_ROUTING_KEY=queue_name,
        SQLALCHEMY_DATABASE_URI=database_url,
        SEARCH_HOSTS=[os.environ['SEARCH_OPENSEARCH_HOSTS']],
        SEARCH_INDEX_PREFIX="",
        SEARCH_UI_SEARCH_INDEX=index_prefix + "records-default-v1.0.0",
        SEARCH_CLIENT_CONFIG={
            "http_auth": (os.environ['INVENIO_OPENSEARCH_USER'],
                          os.environ['INVENIO_OPENSEARCH_PASS']),
            "use_ssl": True, "verify_certs": False,
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TESTING=True,
    )
    try:
        celery_extension = FlaskCeleryExt(app)
        monkeypatch.setattr(celery_extension.celery, 'flask_app', app)
        assert celery_extension.celery.conf.task_always_eager
        InvenioDB(app)
        InvenioRecords(app)
        search = InvenioSearch(app, entry_point_group=None)
        search.register_mappings("records", "tests.data")

        with app.app_context():
            create_database(database_url)
            db.create_all()

        yield app
    finally:
        try:
            for receiver in set(before_record_index.receivers_for(app)) - signal_receivers:
                before_record_index.disconnect(receiver)
            with app.app_context():
                queues = {queue_name: app.config['INDEXER_MQ_QUEUE']}
                extension = app.extensions.get('invenio-indexer')
                if extension is not None:
                    for indexer in extension.registry.all().values():
                        queues[indexer.mq_queue.name] = indexer.mq_queue
                with establish_connection() as connection:
                    for item in queues.values():
                        item(connection).delete()
                    exchange(connection).delete(if_unused=True)
        finally:
            try:
                celery_extension = app.extensions.get('flask-celeryext')
                if celery_extension is not None:
                    celery_extension.celery.close()
            finally:
                try:
                    if 'invenio-search' in app.extensions:
                        with app.app_context():
                            client = app.extensions['invenio-search'].client
                            owned = client.indices.get(index=index_prefix + '*', ignore=[404])
                            if 'error' not in owned:
                                for name in owned:
                                    assert name.startswith(index_prefix)
                                    client.indices.delete(index=name)
                            client.close()
                finally:
                    try:
                        if 'sqlalchemy' in app.extensions:
                            with app.app_context():
                                db.session.remove()
                                db.engine.dispose()
                        if database_exists(database_url):
                            drop_database(database_url)
                    finally:
                        shutil.rmtree(instance_path)


@pytest.fixture()
def app(base_app):
    """Flask application fixture."""
    InvenioIndexer(base_app)
    return base_app


@pytest.fixture()
def queue(app):
    """Get queue object for testing bulk operations."""
    _queue = (app.config['INDEXER_MQ_QUEUE'])

    with app.app_context():
        with establish_connection() as c:
            q = _queue(c)
            q.declare()
            q.purge()

    return _queue


@pytest.fixture(scope="function")
def search_prefix(app):
    """Sets the search prefix."""
    tmp = app.config["SEARCH_INDEX_PREFIX"]
    app.config["SEARCH_INDEX_PREFIX"] = "test-"
    yield
    app.config["SEARCH_INDEX_PREFIX"] = tmp


@pytest.fixture(scope="function")
def record_cls_with_index(app):
    """Record class with index field."""

    class Record:
        """Simulates a record class with an IndexField.

        Since the IndexField has the __get__ method overwritten
        to return the actual index object this class behaves in
        the same way.
        """

        index = dsl.Index(app.config["INDEXER_DEFAULT_INDEX"])

    return Record
