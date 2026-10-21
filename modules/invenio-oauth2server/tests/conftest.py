# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015-2018 CERN.
# Copyright (C) 2024 Graz University of Technology.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.


"""Pytest configuration."""

import invenio_oauth2server._compat  # noqa isort:skip
import os
import pytest
import shutil
import tempfile
import uuid

from flask import Flask, url_for
from flask.cli import ScriptInfo
from flask.views import MethodView
from flask_mail import Mail
from flask_menu import Menu
from unittest.mock import MagicMock
from invenio_accounts import InvenioAccountsREST, InvenioAccountsUI
from invenio_accounts.models import User
from invenio_accounts.views.settings import (
    create_settings_blueprint as create_accounts_blueprint,
)
from invenio_db import InvenioDB, db
from invenio_i18n import InvenioI18N
from invenio_oauth2server import InvenioOAuth2Server, InvenioOAuth2ServerREST
from invenio_oauth2server.decorators import require_api_auth, require_oauth_scopes
from invenio_oauth2server.models import Client, Scope, Token
from invenio_oauth2server.views import server_blueprint, settings_blueprint
from sqlalchemy_utils.functions import create_database, database_exists, drop_database
from sqlalchemy.engine.url import make_url


from .helpers import create_oauth_client, patch_request

try:
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
except ImportError:
    from werkzeug.wsgi import DispatcherMiddleware


@pytest.fixture()
def versioning_listeners():
    """Release only global versioning listeners installed by these apps."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Mapper, Session
    from sqlalchemy_continuum import versioning_manager

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
        (Engine, "before_execute", versioning_manager.track_association_operations),
        (Engine, "rollback", versioning_manager.clear_connection),
        (Engine, "set_connection_execution_options", versioning_manager.track_cloned_connections),
    ])
    owned = [registration for registration in registrations
             if not event.contains(*registration)]

    def release_owned():
        for registration in reversed(owned):
            if event.contains(*registration):
                event.remove(*registration)

    try:
        yield release_owned
    finally:
        release_owned()


@pytest.fixture()
def app(request, versioning_listeners):
    """Flask application fixture."""
    database_url = make_url(os.environ["SQLALCHEMY_DATABASE_URI"]).set(
        database="oauth2server_ut_{}".format(uuid.uuid4().hex))
    instance_path = tempfile.mkdtemp()
    initialized_apps = []
    database_owned = False

    def teardown():
        try:
            for initialized_app in reversed(initialized_apps):
                with initialized_app.app_context():
                    db.session.remove()
                    db.engine.dispose()
            if database_owned:
                drop_database(database_url)
        finally:
            shutil.rmtree(instance_path)

    request.addfinalizer(teardown)

    def init_app(app):
        app.config.update(
            DB_VERSIONING=True,
            LOGIN_DISABLED=False,
            MAIL_SUPPRESS_SEND=True,
            OAUTH2_CACHE_TYPE="simple",
            OAUTHLIB_INSECURE_TRANSPORT=True,
            SECRET_KEY="CHANGE_ME",
            SECURITY_DEPRECATED_PASSWORD_SCHEMES=[],
            SECURITY_PASSWORD_HASH="plaintext",
            SECURITY_PASSWORD_SINGLE_HASH=["plaintext"],
            SECURITY_PASSWORD_SALT="CHANGE_ME_ALSO",
            SECURITY_PASSWORD_SCHEMES=["plaintext"],
            SQLALCHEMY_DATABASE_URI=database_url,
            SQLALCHEMY_TRACK_MODIFICATIONS=True,
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            APP_THEME="semantic-ui",
            THEME_ICONS={
                "semantic-ui": {
                    "key": "key icon",
                    "link": "linkify icon",
                    "shield": "shield alternate icon",
                    "user": "user icon",
                    "codepen": "codepen icon",
                    "cogs": "cogs icon",
                    # Special catch all:
                    "*": "{} icon",
                }
            },
            ACCOUNTS_COVER_TEMPLATE="invenio_accounts/base_cover.html",
            ACCOUNTS_BASE_TEMPLATE="invenio_accounts/base.html",
        )
        InvenioI18N(app)
        Mail(app)
        Menu(app)
        # UI and API share the global manager. Keep one live registration set
        # while each real InvenioDB initialization installs its listeners.
        versioning_listeners()
        InvenioDB(app)
        initialized_apps.append(app)
        InvenioOAuth2Server(app)
        InvenioI18N(app)

    api_app = Flask("testapiapp", instance_path=instance_path)
    api_app.config.update(APPLICATION_ROOT="/api", ACCOUNTS_REGISTER_BLUEPRINT=True)
    init_app(api_app)
    InvenioAccountsREST(api_app)
    InvenioOAuth2ServerREST(api_app)

    app = Flask("testapp", instance_path=instance_path)
    init_app(app)
    InvenioAccountsUI(app)
    app.register_blueprint(create_accounts_blueprint(app))
    app.register_blueprint(server_blueprint)
    app.register_blueprint(settings_blueprint)

    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/api": api_app.wsgi_app})

    with app.app_context():
        if database_exists(database_url):
            raise RuntimeError("Test database must be newly owned by this fixture")
        create_database(database_url)
        database_owned = True
        db.create_all()

    def delete_user_from_cache(exception):
        """Delete user from `flask.g` when the request is tearing down.

        Flask-login==0.6.2 changed the way the user is saved i.e uses `flask.g`.
        Flask.g is pointing to the application context which is initialized per
        request. That said, `pytest-flask` is pushing an application context on each
        test initialization that causes problems as subsequent requests during a test
        are detecting the active application request and not popping it when the
        sub-request is tearing down. That causes the logged in user to remain cached
        for the whole duration of the test. To fix this, we add an explicit teardown
        handler that will pop out the logged in user in each request and it will force
        the user to be loaded each time.
        """
        from flask import g

        if "_login_user" in g:
            del g._login_user

    app.teardown_request(delete_user_from_cache)

    return app


@pytest.fixture()
def api_app(app):
    """Retrieve the REST API application."""
    return getattr(app.wsgi_app.mounts["/api"], "__self__", None)


@pytest.fixture()
def api_app_with_test_view(api_app):
    """Add a test view URL."""
    api_app.add_url_rule("/test", "test", view_func=lambda: "OK")
    return api_app


@pytest.fixture
def script_info(app):
    """Get ScriptInfo object for testing CLI."""
    return ScriptInfo(create_app=lambda: app)


@pytest.fixture
def settings_fixture(app):
    """Fixture for testing settings views."""
    from invenio_oauth2server.proxies import current_oauth2server

    with app.app_context():
        with db.session.begin_nested():
            datastore = app.extensions["security"].datastore
            datastore.create_user(email="info@inveniosoftware.org", password="tester")
        db.session.commit()
        current_oauth2server.register_scope(Scope("test:scope"))
        current_oauth2server.register_scope(Scope("test:scope2"))
    return app


@pytest.fixture
def developer_app_fixture(settings_fixture):
    """Fixture for testing developer application use cases."""
    settings_app = settings_fixture
    with settings_app.app_context():
        with db.session.begin_nested():
            datastore = settings_app.extensions["security"].datastore
            dev_user = datastore.create_user(
                email="dev@inveniosoftware.org", password="dev", active=True
            )

            dev_client = Client(
                client_id="dev",
                client_secret="dev",
                name="Test name",
                description="Test description",
                is_confidential=False,
                user=dev_user,
                website="http://inveniosoftware.org",
                _redirect_uris="",
                _default_scopes="test:scope",
            )

            user = datastore.get_user("info@inveniosoftware.org")
            user_token = Token(
                client=dev_client,
                user=user,
                token_type="bearer",
                access_token="dev_access_1",
                refresh_token="dev_refresh_1",
                expires=None,
                is_personal=False,
                is_internal=False,
                _scopes="test:scope",
            )

            db.session.add(dev_client)
            db.session.add(user_token)
        db.session.commit()
    return settings_app


@pytest.fixture
def models_fixture(app):
    """Fixture that contains the test data for models tests."""
    from invenio_oauth2server.proxies import current_oauth2server

    with app.app_context():
        # Register a test scope
        current_oauth2server.register_scope(Scope("test:scope1"))
        current_oauth2server.register_scope(Scope("test:scope2", internal=True))
        datastore = app.extensions["security"].datastore
        with db.session.begin_nested():
            test_user = datastore.create_user(
                email="info@inveniosoftware.org",
                password="tester",
            )
            resource_owner = datastore.create_user(
                email="resource_owner@inveniosoftware.org", password="test"
            )
            consumer = datastore.create_user(
                email="consumer@inveniosoftware.org", password="test"
            )

            # create resource_owner -> client_1
            u1c1 = Client(
                client_id="client_test_u1c1",
                client_secret="client_test_u1c1",
                name="client_test_u1c1",
                description="",
                is_confidential=False,
                user=resource_owner,
                _redirect_uris="",
                _default_scopes="",
            )
            # create resource_owner -> client_1 / resource_owner -> token_1

            u1c1u1t1 = Token(
                client=u1c1,
                user=resource_owner,
                token_type="u",
                access_token="dev_access_1",
                refresh_token="dev_refresh_1",
                expires=None,
                is_personal=False,
                is_internal=False,
                _scopes="",
            )

            # create consumer -> client_1 / resource_owner -> token_2

            u1c1u2t2 = Token(
                client=u1c1,
                user=consumer,
                token_type="u",
                access_token="dev_access_2",
                refresh_token="dev_refresh_2",
                expires=None,
                is_personal=False,
                is_internal=False,
                _scopes="",
            )
            db.session.add(u1c1)
            db.session.add(u1c1u1t1)
            db.session.add(u1c1u2t2)
        db.session.commit()
        test_user_id = test_user.get_id()
        app.test_user = lambda: User.query.get(test_user_id)
        app.resource_owner_id = resource_owner.get_id()
        app.consumer_id = consumer.get_id()
        app.u1c1_id = u1c1.client_id
        app.u1c1u1t1_id = u1c1u1t1.id
        app.u1c1u2t2_id = u1c1u2t2.id
    return app


@pytest.fixture
def provider_fixture(app):
    """Fixture that contains test data for provider tests."""
    from invenio_oauth2server.proxies import current_oauth2server

    # Mock the oauth client calls to prevent them from going online.
    oauth_client = create_oauth_client(app, "oauth2test")
    oauth_client.http_request = MagicMock(side_effect=patch_request(app))
    datastore = app.extensions["security"].datastore
    with app.test_request_context():
        with db.session.begin_nested():
            current_oauth2server.register_scope(Scope("test:scope"))

            user1 = datastore.create_user(
                email="info@inveniosoftware.org",
                password="tester",
                active=True,
            )
            datastore.create_user(
                email="abuse@inveniosoftware.org", password="tester2", active=True
            )
            user3 = datastore.create_user(
                email="inactive@inveniosoftware.org", password="tester3", active=False
            )

            c1 = Client(
                client_id="dev",
                client_secret="dev",
                name="dev",
                description="",
                is_confidential=False,
                user=user1,
                _redirect_uris=url_for("oauth2test.authorized", _external=True),
                _default_scopes="test:scope",
            )
            c2 = Client(
                client_id="confidential",
                client_secret="confidential",
                name="confidential",
                description="",
                is_confidential=True,
                user=user1,
                _redirect_uris=url_for("oauth2test.authorized", _external=True),
                _default_scopes="test:scope",
            )
            # Same as 'c2' but user belonging to a user that's inactive
            c3 = Client(client_id='confidential-user-inactive',
                        client_secret='confidential-user-inactive',
                        name='confidential-user-inactive',
                        description='',
                        is_confidential=True,
                        user=user3,
                        _redirect_uris=url_for(
                            'oauth2test.authorized', _external=True
                        ),
                        _default_scopes='test:scope'
                        )
            c4 = Client(client_id='confidential-email',
                        client_secret='confidential-email',
                        name='confidential-email',
                        description='',
                        is_confidential=True,
                        user=user1,
                        _redirect_uris=url_for(
                            'oauth2test.authorized', _external=True
                        ),
                        _default_scopes='email')
            c5 = Client(client_id='no-scopes',
                        client_secret='no-scopes',
                        name='no-scopes',
                        description='',
                        is_confidential=False,
                        user=user1,
                        _redirect_uris=url_for(
                            'oauth2test.authorized', _external=True
                        ))
            db.session.add(c1)
            db.session.add(c2)
            db.session.add(c3)
            db.session.add(c4)
            db.session.add(c5)
        personal_token = Token.create_personal('test-personal',
                                               user1.id,
                                               scopes=[],
                                               is_internal=True)

        personal_token3 = Token.create_personal(
            "test-personal", user3.id, scopes=[], is_internal=True
        )
        db.session.commit()

        app.user1_id = user1.id
        app.user3_id = user3.id
        app.personal_token = personal_token.access_token
        app.personal_token3 = personal_token3.access_token
    return app


@pytest.fixture
def resource_fixture(app, api_app):
    """Fixture that contains the test data for models tests."""
    from flask import g, request

    from invenio_oauth2server.proxies import current_oauth2server

    # Setup API resources
    class Test0Resource(MethodView):
        def get(self):
            app.identity = g.identity
            return "success", 200

    class Test1Resource(MethodView):
        # NOTE: Method decorators are applied in reverse order
        decorators = [
            require_oauth_scopes("test:testscope"),
            require_api_auth(),
        ]

        def get(self):
            assert request.oauth.access_token
            app.identity = g.identity
            return "success", 200

        def post(self):
            assert request.oauth.access_token
            return "success", 200

    class Test2Resource(MethodView):
        @require_api_auth()
        @require_oauth_scopes("test:testscope")
        def get(self):
            assert request.oauth.access_token
            return "success", 200

        @require_api_auth()
        @require_oauth_scopes("test:testscope")
        def post(self):
            assert request.oauth.access_token
            return "success", 200

    class Test3Resource(MethodView):
        @require_api_auth()
        def post(self):
            return "success", 200

    class Test4Resource(MethodView):
        @require_api_auth(allow_anonymous=True)
        def get(self):
            from flask_login import current_user

            return str(current_user.get_id()), 200

        def post(self):
            from flask_login import current_user

            return str(current_user.get_id()), 200

    # Register API resources
    api_app.add_url_rule(
        "/test0/identitytestcase/",
        view_func=Test0Resource.as_view("test0resource"),
    )
    api_app.add_url_rule(
        "/test1/decoratorstestcase/",
        view_func=Test1Resource.as_view("test1resource"),
    )
    api_app.add_url_rule(
        "/test2/decoratorstestcase/",
        view_func=Test2Resource.as_view("test2resource"),
    )
    # This one is a UI resource using login_required
    api_app.add_url_rule(
        "/test3/loginrequiredstestcase/",
        view_func=Test3Resource.as_view("test3resource"),
    )
    api_app.add_url_rule(
        "/test4/allowanonymous/",
        view_func=Test4Resource.as_view("test4resource"),
    )

    datastore = app.extensions["security"].datastore
    with app.app_context():
        # Register a test scope
        current_oauth2server.register_scope(
            Scope("test:testscope", group="Test", help_text="Test scope")
        )
        with db.session.begin_nested():
            app.user = datastore.create_user(
                email="info@inveniosoftware.org",
                password="tester",
                active=True,
            )

        # Create tokens
        app.user_id = app.user.id
        app.token = Token.create_personal(
            "test-", app.user.id, scopes=["test:testscope"], is_internal=True
        ).access_token
        app.token_noscope = Token.create_personal(
            "test-", app.user.id, scopes=[], is_internal=True
        ).access_token
        db.session.commit()

    with api_app.test_request_context():
        app.url_for_test3resource = url_for("test3resource")

    with api_app.test_request_context():
        app.url_for_test0resource = url_for("test0resource")
        app.url_for_test1resource = url_for("test1resource")
        app.url_for_test2resource = url_for("test2resource")
        app.url_for_test4resource = url_for("test4resource")
        app.url_for_test0resource_token = url_for(
            "test0resource", access_token=app.token
        )
        app.url_for_test1resource_token = url_for(
            "test1resource", access_token=app.token
        )
        app.url_for_test2resource_token = url_for(
            "test2resource", access_token=app.token
        )
        app.url_for_test1resource_token_noscope = url_for(
            "test1resource", access_token=app.token_noscope
        )
        app.url_for_test2resource_token_noscope = url_for(
            "test2resource", access_token=app.token_noscope
        )
        app.url_for_test4resource_token = url_for(
            "test4resource", access_token=app.token
        )

    return app
