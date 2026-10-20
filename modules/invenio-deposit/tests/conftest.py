# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016-2019 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.


"""Pytest configuration."""

import datetime
import os
import pytest
import shutil
import tempfile
import uuid

from flask import Flask, g
from flask.cli import ScriptInfo
from flask_babel import Babel
from flask_celeryext import FlaskCeleryExt
from flask_oauthlib.provider import OAuth2Provider
from flask_security import login_user
from invenio_access import InvenioAccess
from invenio_access.models import ActionUsers
from invenio_accounts import InvenioAccounts
from invenio_accounts.views.rest import create_rest_blueprint
from invenio_accounts.views.settings import create_settings_blueprint
from invenio_i18n import InvenioI18N
from invenio_assets import InvenioAssets
from invenio_db import InvenioDB, db
from invenio_deposit import InvenioDeposit, InvenioDepositREST
from invenio_deposit.api import Deposit
from invenio_deposit.scopes import write_scope
from invenio_deposit.signals import post_action
from invenio_deposit.receivers import index_deposit_after_publish
from invenio_files_rest import InvenioFilesREST
from invenio_files_rest.models import Location
from invenio_indexer import InvenioIndexer
from invenio_jsonschemas import InvenioJSONSchemas
from invenio_oauth2server import InvenioOAuth2Server, InvenioOAuth2ServerREST
from invenio_oauth2server.models import Client, Token
from invenio_oauth2server.views import \
    settings_blueprint as oauth2server_settings_blueprint
from invenio_pidstore import InvenioPIDStore
from invenio_records import InvenioRecords
from invenio_records_rest import InvenioRecordsREST
from invenio_records_rest.utils import PIDConverter
from invenio_records_rest.views import \
    create_blueprint_from_app as records_rest_bp
from invenio_records_ui import InvenioRecordsUI
from invenio_records_ui.views import create_blueprint_from_app as records_ui_bp
from invenio_rest import InvenioREST
from invenio_search import InvenioSearch, current_search, current_search_client
from invenio_search_ui import InvenioSearchUI
from kombu import Exchange, Queue

from io import BytesIO
from sqlalchemy import inspect
from sqlalchemy.engine.url import make_url
from sqlalchemy_utils.functions import create_database, database_exists, \
    drop_database
from werkzeug.middleware.dispatcher import DispatcherMiddleware


from .helpers import fill_oauth2_headers

def object_as_dict(obj):
    """Make a dict from SQLAlchemy object."""
    return {c.key: getattr(obj, c.key)
            for c in inspect(obj).mapper.column_attrs}


@pytest.yield_fixture()
def base_app(request):
    """Flask application fixture."""
    instance_path = tempfile.mkdtemp()

    database_url = make_url(os.environ['SQLALCHEMY_DATABASE_URI'])
    database_url = database_url.set(database='deposit_ut_' + uuid.uuid4().hex)
    index_prefix = 'deposit-ut-' + uuid.uuid4().hex + '-'
    apps = []

    def init_app(app_):
        apps.append(app_)
        app_.config.update(
            BROKER_URL='amqp://guest:guest@rabbitmq:5672/',
            CELERY_BROKER_URL='amqp://guest:guest@rabbitmq:5672/',
            CELERY_ALWAYS_EAGER=True,
            CELERY_CACHE_BACKEND='memory',
            CELERY_EAGER_PROPAGATES=True,
            FILES_REST_DEFAULT_STORAGE_CLASS='S',
            FILES_REST_STORAGE_CLASS_LIST={
            'S': 'Standard',
            'A': 'Archive',
            },
            FILES_REST_DEFAULT_QUOTA_SIZE=None,
            FILES_REST_DEFAULT_MAX_FILE_SIZE=None,
            CELERY_RESULT_BACKEND='cache',
            JSONSCHEMAS_URL_SCHEME='http',
            SECRET_KEY='CHANGE_ME',
            SECURITY_PASSWORD_SALT='CHANGE_ME_ALSO',
            SQLALCHEMY_DATABASE_URI=database_url,
            SEARCH_INDEX_PREFIX=index_prefix,
            SEARCH_OPENSEARCH_HOSTS=os.environ.get(
                    'SEARCH_OPENSEARCH_HOSTS', 'opensearch'),
            SEARCH_HOSTS=os.environ.get(
                'SEARCH_HOST', 'opensearch'
            ),
            SEARCH_CLIENT_CONFIG={"http_auth":(os.environ['INVENIO_OPENSEARCH_USER'],os.environ['INVENIO_OPENSEARCH_PASS']),"use_ssl":True, "verify_certs":False},
            SQLALCHEMY_TRACK_MODIFICATIONS=True,
            SQLALCHEMY_ECHO=False,
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            DEPOSIT_SEARCH_API='/api/search',
            SECURITY_PASSWORD_HASH='plaintext',
            SECURITY_PASSWORD_SCHEMES=['plaintext'],
            SECURITY_DEPRECATED_PASSWORD_SCHEMES=[],
            OAUTHLIB_INSECURE_TRANSPORT=True,
            OAUTH2_CACHE_TYPE='simple',
            ACCOUNTS_JWT_ENABLE=False,
            INDEXER_DEFAULT_INDEX='records-default-v1.0.0',
            INDEXER_MQ_QUEUE = Queue("indexer",
                exchange=Exchange("indexer", type="direct"), routing_key="indexer",auto_delete=False,queue_arguments={"x-queue-type":"quorum"}),
            WEKO_PERMISSION_SUPER_ROLE_USER=[
                "System Administrator",
                "Repository Administrator",
            ],
            WEKO_RECORDS_UI_EMAIL_ITEM_KEYS = ['creatorMails', 'contributorMails', 'mails'],
            WEKO_PERMISSION_ROLE_COMMUNITY = ['Community Administrator'],
            ACCOUNTS_COVER_TEMPLATE="invenio_accounts/base_cover.html",
            ACCOUNTS_BASE_TEMPLATE="invenio_accounts/base.html"
        )

        @app_.before_request
        def clear_login_cache():
            # Each client request must load its own session/OAuth identity.
            g.pop('_login_user', None)

        Babel(app_)
        FlaskCeleryExt(app_)
        OAuth2Provider(app_)
        InvenioI18N(app_)
        InvenioDB(app_)
        InvenioAccounts(app_)
        InvenioAccess(app_)
        InvenioIndexer(app_)
        InvenioJSONSchemas(app_)
        InvenioOAuth2Server(app_)
        InvenioFilesREST(app_)
        InvenioPIDStore(app_)
        InvenioRecords(app_)
        search = InvenioSearch(app_)
        search.register_mappings('deposits', 'invenio_deposit.mappings')

    try:
        api_app = Flask('testapiapp', instance_path=instance_path)
        api_app.url_map.converters['pid'] = PIDConverter
        # initialize InvenioDeposit first in order to detect any invalid dependency
        InvenioDepositREST(api_app)

        init_app(api_app)
        InvenioREST(api_app)
        InvenioOAuth2ServerREST(api_app)
        InvenioRecordsREST(api_app)

        app_ = Flask('testapp', instance_path=instance_path)
        app_.url_map.converters['pid'] = PIDConverter
        # initialize InvenioDeposit first in order to detect any invalid dependency
        InvenioDeposit(app_)
        init_app(app_)
        app_.register_blueprint(create_settings_blueprint(app_))
        app_.register_blueprint(create_rest_blueprint(app_))
        app_.register_blueprint(oauth2server_settings_blueprint)
        InvenioAssets(app_)
        InvenioSearchUI(app_)
        InvenioRecordsUI(app_)
        app_.register_blueprint(records_ui_bp(app_))
        app_.register_blueprint(records_rest_bp(app_))
        app_.wsgi_app = DispatcherMiddleware(app_.wsgi_app, {
            '/api': api_app.wsgi_app
        })

        with app_.app_context():
            if str(db.engine.url) != 'sqlite://' and \
               not database_exists(database_url):
                create_database(database_url)
            db.create_all()

        yield app_

    finally:
        try:
            for application in apps:
                with application.app_context():
                    if 'invenio-search' in application.extensions:
                        # Include indices auto-created by API-internal indexers.
                        owned_indices = current_search_client.indices.get(
                            index=index_prefix + '*', ignore=[404])
                        for name in owned_indices:
                            if name.startswith(index_prefix):
                                current_search_client.indices.delete(index=name)
                        current_search_client.close()
        finally:
            for application in apps:
                post_action.disconnect(index_deposit_after_publish,
                                       sender=application)
                if 'sqlalchemy' not in application.extensions:
                    continue
                with application.app_context():
                    db.session.remove()
                    db.engine.dispose()
            if database_exists(database_url):
                drop_database(database_url)
            shutil.rmtree(instance_path)


@pytest.yield_fixture()
def app(base_app):
    """Yield the REST API application in its context."""
    with base_app.app_context():
        yield base_app


@pytest.yield_fixture()
def api(base_app):
    """Yield the REST API application in its context."""
    api = base_app.wsgi_app.mounts['/api'].__self__
    api.register_blueprint(records_rest_bp(api))
    with api.app_context():
        yield api


@pytest.yield_fixture()
def test_client(base_app):
    """Test client."""
    with base_app.test_client() as client_:
        yield client_


@pytest.fixture()
def users(app):
    """Create users."""
    with db.session.begin_nested():
        datastore = app.extensions['security'].datastore
        user1 = datastore.create_user(email='info@inveniosoftware.org',
                                      password='tester', active=True)
        user2 = datastore.create_user(email='test@inveniosoftware.org',
                                      password='tester2', active=True)
        admin = datastore.create_user(email='admin@inveniosoftware.org',
                                      password='tester3', active=True)
        # Assign deposit-admin-access to admin only.
        db.session.add(ActionUsers(
            action='deposit-admin-access', user=admin
        ))
    db.session.commit()
    return [
        {"email": user1.email, "id": user1.id, "obj": user1},
        {"email": user2.email, "id": user2.id, "obj": user2},
        {"email": admin.email, "id": admin.id, "obj": admin},
    ]


@pytest.fixture()
def client(app, users):
    """Create client."""
    with db.session.begin_nested():
        # create resource_owner -> client_1
        client_ = Client(
            client_id='client_test_u1c1',
            client_secret='client_test_u1c1',
            name='client_test_u1c1',
            description='',
            is_confidential=False,
            user_id=users[0]['id'],
            _redirect_uris='',
            _default_scopes='',
        )
        db.session.add(client_)
    db.session.commit()
    return client_


@pytest.fixture()
def write_token_user_1(app, client, users):
    """Create token."""
    with db.session.begin_nested():
        token_ = Token(
            client=client,
            user_id=users[0]['id'],
            access_token='dev_access_1',
            refresh_token='dev_refresh_1',
            expires=datetime.datetime.now() + datetime.timedelta(hours=10),
            is_personal=False,
            is_internal=True,
            _scopes=write_scope.id,
        )
        db.session.add(token_)
    db.session.commit()
    access_token = token_.access_token
    return token_


@pytest.fixture()
def write_token_user_2(app, client, users):
    """Create token."""
    with db.session.begin_nested():
        token_ = Token(
            client=client,
            user_id=users[1]['id'],
            access_token='dev_access_2',
            refresh_token='dev_refresh_2',
            expires=datetime.datetime.now() + datetime.timedelta(hours=10),
            is_personal=False,
            is_internal=True,
            _scopes=write_scope.id,
        )
        db.session.add(token_)
    db.session.commit()
    return token_


@pytest.fixture()
def fake_schemas(app, api, search, tmpdir):
    """Fake schema."""
    schemas = tmpdir.mkdir('schemas')
    empty_schema = '{"title": "Empty"}'
    for path in (('deposit-v1.0.0.json', ),
                 ('deposits', 'test-v1.0.0.json'),
                 ('test-v1.0.0.json', ), ):
        schema = schemas
        for section in path[:-1]:
            schema = schema.mkdir(section)
        schema = schema.join(path[-1])
        schema.write(empty_schema)

    app.extensions['invenio-jsonschemas'].register_schemas_dir(schemas.strpath)
    api.extensions['invenio-jsonschemas'].register_schemas_dir(schemas.strpath)


@pytest.yield_fixture()
def search(app):
    """Search fixture."""
    try:
        list(current_search.create())
        current_search_client.indices.refresh(index=app.config['SEARCH_INDEX_PREFIX'] + '*')
        yield current_search_client
    finally:
        list(current_search.delete(ignore=[404]))


@pytest.fixture()
def location(app):
    """Create default location."""
    tmppath = tempfile.mkdtemp()
    try:
        with db.session.begin_nested():
            loc = Location(name='local', uri=tmppath, default=True)
            db.session.add(loc)
        db.session.commit()
        yield loc
    finally:
        shutil.rmtree(tmppath)


@pytest.fixture()
def deposit_factory(app, search, users, location):
    """Create independently stored deposits, optionally without a bucket."""
    def create(with_bucket=True):
        record = {'title': 'fuu'}
        with app.test_request_context():
            datastore = app.extensions['security'].datastore
            login_user(datastore.find_user(email=users[0]['email']))
            deposit = Deposit.create(record, with_bucket=with_bucket)
            deposit.pid.register()
            deposit.commit()
            db.session.commit()
        current_search_client.indices.refresh(
            index=app.config['SEARCH_INDEX_PREFIX'] + '*')
        return deposit
    return create


@pytest.fixture()
def deposit(deposit_factory):
    """New deposit with an explicitly created file bucket."""
    return deposit_factory()


@pytest.fixture()
def deposit_without_bucket(deposit_factory):
    """Deposit for the existing missing-bucket case."""
    return deposit_factory(with_bucket=False)


@pytest.fixture()
def files(app, deposit):
    """Add a file to the deposit."""
    content = b'### Testing textfile ###'
    stream = BytesIO(content)
    key = 'hello.txt'
    deposit.files[key] = stream
    deposit.commit()
    db.session.commit()
    obj = list(deposit.files)[0]

    return [{
    "key": obj.key,
    "checksum": obj.file.checksum,
    "size": obj.file.size,
    "file_id": obj.file.id,
    }]


@pytest.fixture()
def pdf_file(app):
    """Create a test pdf file."""
    # return {'file': make_pdf_fixture('test.pdf'), 'name': 'test.pdf'}
    return None


@pytest.fixture()
def pdf_file2(app):
    """Create a test pdf file."""
    # return {'file': make_pdf_fixture('test2.pdf', 'test'),
    #  'name': 'test2.pdf'}
    return None


@pytest.fixture()
def pdf_file2_samename(app):
    """Create a test pdf file."""
    # return {'file': make_pdf_fixture('test2.pdf', 'test same'),
    #         'name': 'test2.pdf'}
    return None


@pytest.fixture()
def json_headers():
    """JSON headers."""
    return [('Content-Type', 'application/json'),
            ('Accept', 'application/json')]


@pytest.fixture()
def oauth2_headers_user_1(app, json_headers, write_token_user_1):
    """Authentication headers (with a valid oauth2 token).

    It uses the token associated with the first user.
    """
    return fill_oauth2_headers(json_headers, write_token_user_1)


@pytest.fixture()
def oauth2_headers_user_2(app, json_headers, write_token_user_2):
    """Authentication headers (with a valid oauth2 token).

    It uses the token associated with the second user.
    """
    return fill_oauth2_headers(json_headers, write_token_user_2)


@pytest.fixture()
def script_info(app):
    """Get ScriptInfo object for testing CLI."""
    return ScriptInfo(create_app=lambda info: app)
