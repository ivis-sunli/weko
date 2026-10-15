# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015-2018 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.


"""Pytest configuration."""

import os
import shutil
import tempfile
from uuid import uuid4

import pytest
from celery import Celery, current_app as current_celery_app
from flask import Flask
from flask_admin import Admin
from flask_celeryext import FlaskCeleryExt
from flask_mail import Mail
from flask_webpackext.manifest import (
    JinjaManifest,
    JinjaManifestEntry,
    JinjaManifestLoader,
)
from invenio_assets import InvenioAssets
from invenio_access import InvenioAccess
from invenio_access.models import ActionRoles, ActionUsers
from invenio_db import InvenioDB, db
from invenio_i18n import Babel, InvenioI18N
from invenio_rest import InvenioREST
from invenio_theme import InvenioTheme
from simplekv.memory.redisstore import RedisStore
from sqlalchemy.engine.url import make_url
from weko_records_ui.config import WEKO_PERMISSION_SUPER_ROLE_USER
from weko_accounts.config import WEKO_ACCOUNTS_GAKUNIN_GROUP_PATTERN_DICT
from sqlalchemy_utils.functions import create_database, database_exists, drop_database
from webargs import fields
from werkzeug.exceptions import NotFound

from invenio_accounts import InvenioAccounts, InvenioAccountsREST
from invenio_accounts.admin import role_adminview, session_adminview, user_adminview
from invenio_accounts.models import Role
from invenio_accounts.testutils import create_test_user
from invenio_accounts.views.rest import RegisterView, create_rest_blueprint, use_kwargs
from invenio_accounts.views.settings import create_settings_blueprint


#
# Mock the webpack manifest to avoid having to compile the full assets.
#
class MockJinjaManifest(JinjaManifest):
    """Mock manifest."""

    def __getitem__(self, key):
        """Get a manifest entry."""
        return JinjaManifestEntry(key, [key])

    def __getattr__(self, name):
        """Get a manifest entry."""
        return JinjaManifestEntry(name, [name])


class MockManifestLoader(JinjaManifestLoader):
    """Manifest loader creating a mocked manifest."""

    def load(self, filepath):
        """Load the manifest."""
        return MockJinjaManifest()


def _app_factory(config=None):
    """Application factory."""
    # TODO use the fixtures from pytest-invenio instead
    instance_path = tempfile.mkdtemp()
    app = Flask("testapp", instance_path=instance_path)
    icons = {
        "semantic-ui": {
            "key": "key icon",
            "link": "linkify icon",
            "shield": "shield alternate icon",
            "user": "user icon",
            "codepen": "codepen icon",
            "cogs": "cogs icon",
            "*": "{} icon",
        },
        "bootstrap3": {
            "key": "fa fa-key fa-fw",
            "link": "fa fa-link fa-fw",
            "shield": "fa fa-shield fa-fw",
            "user": "fa fa-user fa-fw",
            "codepen": "fa fa-codepen fa-fw",
            "cogs": "fa fa-cogs fa-fw",
            "*": "fa fa-{} fa-fw",
        },
    }

    database_url = make_url(os.environ["SQLALCHEMY_DATABASE_URI"]).set(
        database="accounts_ut_" + uuid4().hex
    )
    app.config.update(
        ACCOUNTS_USE_CELERY=False,
        ACCOUNTS_LOCAL_LOGIN_ENABLED=True,
        APP_THEME=["semantic-ui"],
        THEME_ICONS=icons,
        CELERY_ALWAYS_EAGER=True,
        CELERY_CACHE_BACKEND="memory",
        CELERY_EAGER_PROPAGATES=True,
        CELERY_RESULT_BACKEND="cache",
        LOGIN_DISABLED=False,
        MAIL_SUPPRESS_SEND=True,
        SECRET_KEY="CHANGE_ME",
        # SECURITY_PASSWORD_SALT="CHANGE_ME_ALSO",
        SECURITY_CONFIRM_EMAIL_WITHIN="2 seconds",
        SECURITY_RESET_PASSWORD_WITHIN="2 seconds",
        SECURITY_CHANGEABLE=True,
        SECURITY_RECOVERABLE=True,
        SECURITY_REGISTERABLE=True,
        #SQLALCHEMY_DATABASE_URI=os.environ.get(
        #    "SQLALCHEMY_DATABASE_URI", "sqlite:///test.db"
        #),
        SQLALCHEMY_DATABASE_URI=database_url,
        DB_VERSIONING=False,
        DB_VERSIONING_USER_MODEL=None,
        SERVER_NAME="example.com",
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        ACCOUNTS_SITENAME="invenio",
        ACCOUNTS_BASE_TEMPLATE="invenio_accounts/base.html",
        ACCOUNTS_SETTINGS_TEMPLATE="invenio_accounts/settings/base.html",
        ACCOUNTS_COVER_TEMPLATE="invenio_accounts/base_cover.html",
        WEBPACKEXT_MANIFEST_LOADER=MockManifestLoader,
        ACCOUNTS_JWT_ALOGORITHM = 'HS256',
        ACCOUNTS_JWT_SECRET_KEY = 'None',
        WEKO_PERMISSION_SUPER_ROLE_USER = WEKO_PERMISSION_SUPER_ROLE_USER,
        WEKO_ACCOUNTS_GAKUNIN_GROUP_PATTERN_DICT=WEKO_ACCOUNTS_GAKUNIN_GROUP_PATTERN_DICT.copy(),
    )

    app.config.update(config or {})
    Babel(app)
    Mail(app)
    InvenioDB(app)
    InvenioI18N(app)
    InvenioAssets(app)
    InvenioTheme(app)

    # it overrides the custom error handler set by InvenioTheme, by setting it
    # back to the default 404 error handler.
    app.register_error_handler(404, NotFound)

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

@pytest.fixture(autouse=True)
def app_context(request):
    if "app" in request.fixturenames:
        app = request.getfixturevalue("app")
        with app.test_request_context():
            yield
    else:
        yield

def _database_setup(app, request):
    """Set up the database."""
    def teardown():
        try:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
                if database_exists(db.engine.url):
                    drop_database(db.engine.url)
                # The Redis service is owned exclusively by this test run.
                if hasattr(app, "kvsession_store") and isinstance(
                    app.kvsession_store, RedisStore
                ):
                    for key in app.kvsession_store.keys():
                        app.kvsession_store.delete(key)
        finally:
            shutil.rmtree(app.instance_path)

    request.addfinalizer(teardown)
    with app.app_context():
        create_database(db.engine.url)
        db.create_all()
    return app


@pytest.fixture()
def base_app(request):
    """Flask application fixture."""
    app = _app_factory()
    _database_setup(app, request)
    yield app

# TODO
@pytest.fixture()
def app(request):
    """Flask application fixture with Invenio Accounts."""
    app = _app_factory()
    app.config.update(ACCOUNTS_USERINFO_HEADERS=True)
    InvenioAccess(app)
    InvenioAccounts(app)

    app.register_blueprint(create_settings_blueprint(app))

    _database_setup(app, request)
    yield app


@pytest.fixture()
def api(request):
    """Flask application fixture."""
    api_app = _app_factory(
        dict(
            #SQLALCHEMY_DATABASE_URI=os.environ.get(
            #    "SQLALCHEMY_DATABASE_URI", "sqlite:///test.db"
            #),
            SERVER_NAME="localhost",
            TESTING=True,
        )
    )

    InvenioREST(api_app)
    InvenioAccountsREST(api_app)
    api_app.register_blueprint(create_rest_blueprint(api_app))

    _database_setup(api_app, request)

    yield api_app


@pytest.fixture()
def app_with_redis_url(request):
    """Flask application fixture with Invenio Accounts."""
    app = _app_factory(dict(ACCOUNTS_SESSION_REDIS_URL=os.environ["ACCOUNTS_SESSION_REDIS_URL"]))
    app.config.update(ACCOUNTS_USERINFO_HEADERS=True)
    InvenioAccounts(app)

    app.register_blueprint(create_settings_blueprint(app))

    _database_setup(app, request)
    yield app


@pytest.fixture()
def app_with_flexible_registration(request):
    """Flask application fixture with Invenio Accounts."""

    class MyRegisterView(RegisterView):
        post_args = {**RegisterView.post_args, "active": fields.Boolean(required=True)}

        @use_kwargs(post_args)
        def post(self, **kwargs):
            """Register a user."""
            return super(MyRegisterView, self).post(**kwargs)

    api_app = _app_factory()
    InvenioREST(api_app)
    InvenioAccountsREST(api_app)

    api_app.config["ACCOUNTS_REST_AUTH_VIEWS"]["register"] = MyRegisterView

    api_app.register_blueprint(create_rest_blueprint(api_app))

    _database_setup(api_app, request)
    yield api_app


@pytest.fixture
def task_app(request):
    """Flask application with Celery enabled."""
    app = _app_factory(
        dict(
            ACCOUNTS_USE_CELERY=True,
            MAIL_SUPPRESS_SEND=True,
        )
    )
    previous_celery = current_celery_app._get_current_object()
    celery = Celery("invenio-accounts-tests", set_as_current=False)
    celery.set_current()

    def cleanup_celery():
        previous_celery.set_current()
        celery.close()

    request.addfinalizer(cleanup_celery)
    FlaskCeleryExt(app)
    InvenioAccounts(app)
    _database_setup(app, request)
    return app


@pytest.fixture
def cookie_app(app):
    """Use the same application and database as the users fixture."""
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_DOMAIN="example.com",
    )
    return app


@pytest.fixture
def admin_view(app):
    """Admin view fixture."""
    assert isinstance(role_adminview, dict)
    assert isinstance(user_adminview, dict)
    assert isinstance(session_adminview, dict)

    assert "model" in role_adminview
    assert "modelview" in role_adminview
    assert "model" in user_adminview
    assert "modelview" in user_adminview
    assert "model" in session_adminview
    assert "modelview" in session_adminview

    admin = Admin(app, name="Test")

    user_adminview_copy = dict(user_adminview)
    user_model = user_adminview_copy.pop("model")
    user_view = user_adminview_copy.pop("modelview")
    admin.add_view(user_view(user_model, db.session, **user_adminview_copy))

    admin.add_view(
        session_adminview["modelview"](
            session_adminview["model"],
            db.session,
            category=session_adminview["category"],
        )
    )


@pytest.fixture()
def users(app):
    """Create users."""
    with app.app_context():
        user1 = create_test_user(email="INFO@inveniosoftware.org", password="tester")
        user2 = create_test_user(email="info2@invenioSOFTWARE.org", password="tester2")
        user3 = create_test_user(email="admin1@inveniosoftware.org",password="tester3")
        
        ds = app.extensions["invenio-accounts"].datastore
        role_count = Role.query.filter_by(name="System Administrator").count()
        if role_count != 1:
            sysadmin_role = ds.create_role(name="System Administrator")
        else:
            sysadmin_role = Role.query.filter_by(name="System Administrator").first()
        
        # Assign access authorization
        with db.session.begin_nested():
            action_users = [
                ActionUsers(action="superuser-access", user=user3),
            ]
            db.session.add_all(action_users)
            action_roles = [
                ActionRoles(action="superuser-access", role=sysadmin_role)
            ]
            db.session.add_all(action_roles)
            ds.add_role_to_user(user3, sysadmin_role)
        db.session.commit()

        return [
            {
                "email": user1.email,
                "id": user1.id,
                "password": user1.password_plaintext,
                "obj": user1,
            },
            {
                "email": user2.email,
                "id": user2.id,
                "password": user2.password_plaintext,
                "obj": user2,
            },
            {
                "email": user3.email,
                "id": user3.id,
                "password": user3.password_plaintext,
                "obj": user3
            }
        ]
