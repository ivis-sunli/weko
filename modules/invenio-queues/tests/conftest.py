# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2017-2022 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration."""

from collections import namedtuple
from importlib.metadata import entry_points

import pytest
import os
import uuid
from urllib.parse import quote

from flask import Flask
from kombu import Exchange
from kombu.pools import connections
from kombu.transport.memory import Channel as MemoryChannel
from unittest.mock import patch

from invenio_queues import InvenioQueues

MOCK_MQ_EXCHANGE = Exchange(
    "queues_ut_" + uuid.uuid4().hex,
    type="direct",
    delivery_mode="transient",  # in-memory queue
    durable=True,
)


def remove_queues(app):
    """Delete all queues declared on the current app."""
    with app.app_context():
        ext = app.extensions["invenio-queues"]
        for name, queue in ext.queues.items():
            if app.config['QUEUES_BROKER_URL'].startswith('redis:') or queue.exists:
                queue.queue.delete()
        if ext.queues:
            queue = next(iter(ext.queues.values()))
            with queue.connection_pool.acquire(block=True) as conn:
                if (conn.transport.driver_type != 'memory' or
                        MOCK_MQ_EXCHANGE.name in conn.default_channel.state.exchanges):
                    MOCK_MQ_EXCHANGE(conn).delete()


def mock_iter_entry_points_factory(data):
    """Create a mock iter_entry_points function."""

    def entrypoints(group, name=None):
        if group == "invenio_queues.queues":
            for entrypoint in data:
                yield entrypoint
        else:
            for x in entry_points(group=group, name=name):
                yield x

    return entrypoints



@pytest.fixture
def MockEntryPoint():
    """Mock entry point for testing."""
    return namedtuple("MockEntryPoint", ["name", "value", "group", "load"])


@pytest.fixture
def test_queues_entrypoints(app, MockEntryPoint):
    """Declare some queues by mocking the invenio_queues.queues entrypoint.

    It yields a list like [{name: queue_name, exchange: conf}, ...].
    """
    data = []
    result = []
    for idx in range(5):
        queue_name = "queue{}".format(idx)
        conf = dict(name=queue_name, exchange=MOCK_MQ_EXCHANGE)
        entrypoint = MockEntryPoint(
            name=queue_name,
            value=queue_name,
            group="invenio_queues.queues",
            load=lambda conf=conf: (lambda: [conf]),
        )
        data.append(entrypoint)
        result.append(conf)

    entrypoints = mock_iter_entry_points_factory(data)

    with patch("importlib.metadata.entry_points", entrypoints):
        try:
            yield result
        finally:
            remove_queues(app)


@pytest.fixture
def test_queues(app, test_queues_entrypoints):
    """Declare test queues."""
    with app.app_context():
        ext = app.extensions["invenio-queues"]
        for conf in test_queues_entrypoints:
            queue = ext.queues[conf["name"]]
            declared_queue = queue.queue
            # Keep queue type aligned with forked kombu.compat.Consumer default.
            declared_queue.queue_arguments = {"x-queue-type": "quorum"}
            declared_queue.declare()
            with queue.connection_pool.acquire(block=True) as conn:
                if conn.transport.driver_type == 'redis':
                    assert (queue.routing_key, '', declared_queue.name) in conn.default_channel.get_table(
                        queue.exchange.name)
                else:
                    assert queue.exists
    yield test_queues_entrypoints


@pytest.fixture
def app(request, monkeypatch):
    """Flask application fixture."""
    existing_pools = {id(pool) for pool in connections.values()}
    existing_memory_queues = set(MemoryChannel.queues)
    app_ = Flask("testapp")
    broker_url = 'amqp://{}:{}@{}:5672/{}'.format(
        quote(os.environ['INVENIO_RABBITMQ_USER'], safe=''),
        quote(os.environ['INVENIO_RABBITMQ_PASS'], safe=''),
        os.environ['INVENIO_RABBITMQ_HOST'],
        quote(os.environ['QUEUES_TEST_VHOST'], safe=''))
    selected = request.getfixturevalue('config') if 'config' in request.fixturenames else {}
    configured_url = selected.get('QUEUES_BROKER_URL', '')
    if configured_url.startswith('amqp:'):
        monkeypatch.setitem(selected, 'QUEUES_BROKER_URL', broker_url)
    elif configured_url.startswith('redis:'):
        monkeypatch.setitem(selected, 'QUEUES_BROKER_URL',
                            'redis://{}:6379/13'.format(os.environ['INVENIO_REDIS_HOST']))
    app_.config.update(
        SECRET_KEY="SECRET_KEY",
        TESTING=True,
        BROKER_URL=broker_url,
        QUEUES_BROKER_URL=broker_url,
    )
    app_.config.update(selected)
    InvenioQueues(app_)

    try:
        with app_.app_context():
            yield app_
    finally:
        for name in (app_.extensions['invenio-queues']._queues or {}):
            if name not in existing_memory_queues:
                MemoryChannel.queues.pop(name, None)
        for key, pool in list(connections.items()):
            if id(pool) not in existing_pools:
                pool.force_close_all()
                dict.__delitem__(connections, key)
