# -*- coding: utf-8 -*-
#
# This file is part of WEKO3.
# Copyright (C) 2017 National Institute of Informatics.
#
# WEKO3 is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# WEKO3 is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WEKO3; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.

"""Pytest for weko-accounts configuration."""

import os, sys
import shutil
import tempfile
import uuid

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Mapper, Session
from sqlalchemy_continuum import versioning_manager
from invenio_base.signals import app_loaded
from datetime import datetime, timedelta

import pytest
from flask import Flask
from flask_babel import Babel
from flask_menu import Menu
from flask_mail import Mail
from sqlalchemy_utils.functions import create_database, database_exists, drop_database


from invenio_access import InvenioAccess
from invenio_admin import InvenioAdmin
from invenio_access.models import ActionUsers,ActionRoles
from invenio_accounts import InvenioAccounts
from invenio_accounts.models import User, Role
from invenio_accounts.testutils import create_test_user
from invenio_communities.models import Community
from invenio_db import InvenioDB, db as db_
from invenio_i18n import InvenioI18N
from invenio_oauth2server import InvenioOAuth2Server
from weko_admin import WekoAdmin
from weko_admin.models import SessionLifetime
from weko_index_tree.models import Index
from weko_records_ui import WekoRecordsUI
from weko_redis.redis import RedisConnection
from weko_search_ui import WekoSearchUI
from weko_user_profiles import WekoUserProfiles
from weko_logging.audit import WekoLoggingUserActivity

from weko_accounts import WekoAccounts, WekoAccountsREST
from weko_accounts.views import blueprint


@pytest.yield_fixture()
def instance_path():
    """Temporary instance path."""
    path = tempfile.mkdtemp()
    try:
        yield path
    finally:
        shutil.rmtree(path)


@pytest.fixture(autouse=True)
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

    def cleanup():
        for registration in reversed(owned):
            if event.contains(*registration):
                event.remove(*registration)

    try:
        yield cleanup
    finally:
        cleanup()


@pytest.fixture(autouse=True)
def app_loaded_receivers():
    """Release only pending extension callbacks registered by this test."""
    existing = set(app_loaded.receivers_for(None))
    try:
        yield
    finally:
        for receiver in set(app_loaded.receivers_for(None)) - existing:
            app_loaded.disconnect(receiver)


@pytest.fixture()
def base_app(instance_path, versioning_listeners):
    """Flask application fixture."""
    app_ = Flask('testapp', instance_path=instance_path,
                 static_folder=os.path.join(instance_path, 'static'))
    app_.config.update(
        SECRET_KEY='SECRET_KEY',
        TESTING=True,
        SERVER_NAME='test_server.localdomain',
        # SQLALCHEMY_DATABASE_URI=os.environ.get(
        #  'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db'),
        SQLALCHEMY_DATABASE_URI=make_url(os.environ['SQLALCHEMY_DATABASE_URI']).set(
            database='accounts_ut_' + uuid.uuid4().hex),
        THEME_SITEURL = 'https://localhost',
        CACHE_REDIS_URL=os.environ.get(
            "CACHE_REDIS_URL", "redis://{}:6379/0".format(os.environ["CACHE_REDIS_HOST"])
        ),
        CACHE_REDIS_DB='0',
        GROUP_INFO_REDIS_DB='4',
        CACHE_REDIS_HOST=os.environ['CACHE_REDIS_HOST'],
        CACHE_TYPE="redis",
        REDIS_PORT='6379',
        WEB_HOST_NAME='localhost',
        WEKO_ACCOUNTS_SSO_ATTRIBUTE_MAP = {
            'eppn': (False, 'shib_eppn'),
            'HTTP_WEKOSOCIETYAFFILIATION': (False, 'shib_role_authority_name'),
            'mail': (False, 'shib_mail'),
            'HTTP_WEKOID': (False, 'shib_user_name'),
        },
        WEKO_ACCOUNTS_SHIB_IDP_LOGIN_URL='{}secure/login.py',
        WEKO_ACCOUNTS_SHIB_ROLE_RELATION = {
            '管理者': 'System Administrator',
            '機関内のOrthros': 'Repository Administrator'
        }
    )
    try:
        Babel(app_)
        InvenioI18N(app_)
        InvenioDB(app_)
        Mail(app_)
        Menu(app_)
        InvenioAccounts(app_)
        InvenioAccess(app_)
        InvenioAdmin(app_)
        InvenioOAuth2Server(app_)
        WekoAccounts(app_)
        WekoRecordsUI(app_)
        WekoAdmin(app_)
        WekoUserProfiles(app_)
        app_.register_blueprint(blueprint, name='weko_accounts_unique')
        WekoAccountsREST(app_)
        WekoSearchUI(app_)
        WekoLoggingUserActivity(app_)
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
def request_context(app):
    with app.test_request_context():
        yield app
@pytest.yield_fixture()
def db(app):
    """Database fixture."""
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

@pytest.yield_fixture()
def client(app,session_time):
    """make a test client.
    Args:
        app (Flask): flask app.
    Yields:
        FlaskClient: test client
    """
    with app.test_client() as client:
        yield client


@pytest.fixture()
def users(app, db):
    """Create users."""
    ds = app.extensions['invenio-accounts'].datastore
    user_count = User.query.filter_by(email='user@test.org').count()
    if user_count != 1:
        user = create_test_user(email='user@test.org')
        contributor = create_test_user(email='contributor@test.org')
        comadmin = create_test_user(email='comadmin@test.org')
        repoadmin = create_test_user(email='repoadmin@test.org')
        sysadmin = create_test_user(email='sysadmin@test.org')
        generaluser = create_test_user(email='generaluser@test.org')
        originalroleuser = create_test_user(email='originalroleuser@test.org')
        originalroleuser2 = create_test_user(email='originalroleuser2@test.org')
        student = create_test_user(email='student@test.org')
    else:
        user = User.query.filter_by(email='user@test.org').first()
        contributor = User.query.filter_by(email='contributor@test.org').first()
        comadmin = User.query.filter_by(email='comadmin@test.org').first()
        repoadmin = User.query.filter_by(email='repoadmin@test.org').first()
        sysadmin = User.query.filter_by(email='sysadmin@test.org').first()
        generaluser = User.query.filter_by(email='generaluser@test.org')
        originalroleuser = create_test_user(email='originalroleuser@test.org')
        originalroleuser2 = create_test_user(email='originalroleuser2@test.org')
        student = User.query.filter_by(email='student@test.org').first()

    role_count = Role.query.filter_by(name='System Administrator').count()
    if role_count != 1:
        sysadmin_role = ds.create_role(name='System Administrator')
        repoadmin_role = ds.create_role(name='Repository Administrator')
        contributor_role = ds.create_role(name='Contributor')
        comadmin_role = ds.create_role(name='Community Administrator')
        general_role = ds.create_role(name='General')
        originalrole = ds.create_role(name='Original Role')
        studentrole = ds.create_role(name='Student')
    else:
        sysadmin_role = Role.query.filter_by(name='System Administrator').first()
        repoadmin_role = Role.query.filter_by(name='Repository Administrator').first()
        contributor_role = Role.query.filter_by(name='Contributor').first()
        comadmin_role = Role.query.filter_by(name='Community Administrator').first()
        general_role = Role.query.filter_by(name='General').first()
        originalrole = Role.query.filter_by(name='Original Role').first()
        studentrole = Role.query.filter_by(name='Student').first()

    ds.add_role_to_user(sysadmin, sysadmin_role)
    ds.add_role_to_user(repoadmin, repoadmin_role)
    ds.add_role_to_user(contributor, contributor_role)
    ds.add_role_to_user(comadmin, comadmin_role)
    ds.add_role_to_user(generaluser, general_role)
    ds.add_role_to_user(originalroleuser, originalrole)
    ds.add_role_to_user(originalroleuser2, originalrole)
    # ds.add_role_to_user(originalroleuser2, repoadmin_role)
    ds.add_role_to_user(student,studentrole)

    # Assign access authorization
    with db.session.begin_nested():
        action_users = [
            ActionUsers(action='superuser-access', user=sysadmin),
        ]
        db.session.add_all(action_users)
        action_roles = [
            ActionRoles(action='superuser-access', role=sysadmin_role),
            ActionRoles(action='admin-access', role=repoadmin_role),
            ActionRoles(action='schema-access', role=repoadmin_role),
            ActionRoles(action='index-tree-access', role=repoadmin_role),
            ActionRoles(action='indextree-journal-access', role=repoadmin_role),
            ActionRoles(action='item-type-access', role=repoadmin_role),
            ActionRoles(action='item-access', role=repoadmin_role),
            ActionRoles(action='files-rest-bucket-update', role=repoadmin_role),
            ActionRoles(action='files-rest-object-delete', role=repoadmin_role),
            ActionRoles(action='files-rest-object-delete-version', role=repoadmin_role),
            ActionRoles(action='files-rest-object-read', role=repoadmin_role),
            ActionRoles(action='search-access', role=repoadmin_role),
            ActionRoles(action='detail-page-acces', role=repoadmin_role),
            ActionRoles(action='download-original-pdf-access', role=repoadmin_role),
            ActionRoles(action='author-access', role=repoadmin_role),
            ActionRoles(action='items-autofill', role=repoadmin_role),
            ActionRoles(action='stats-api-access', role=repoadmin_role),
            ActionRoles(action='read-style-action', role=repoadmin_role),
            ActionRoles(action='update-style-action', role=repoadmin_role),
            ActionRoles(action='detail-page-acces', role=repoadmin_role),

            ActionRoles(action='admin-access', role=comadmin_role),
            ActionRoles(action='index-tree-access', role=comadmin_role),
            ActionRoles(action='indextree-journal-access', role=comadmin_role),
            ActionRoles(action='item-access', role=comadmin_role),
            ActionRoles(action='files-rest-bucket-update', role=comadmin_role),
            ActionRoles(action='files-rest-object-delete', role=comadmin_role),
            ActionRoles(action='files-rest-object-delete-version', role=comadmin_role),
            ActionRoles(action='files-rest-object-read', role=comadmin_role),
            ActionRoles(action='search-access', role=comadmin_role),
            ActionRoles(action='detail-page-acces', role=comadmin_role),
            ActionRoles(action='download-original-pdf-access', role=comadmin_role),
            ActionRoles(action='author-access', role=comadmin_role),
            ActionRoles(action='items-autofill', role=comadmin_role),
            ActionRoles(action='detail-page-acces', role=comadmin_role),
            ActionRoles(action='detail-page-acces', role=comadmin_role),

            ActionRoles(action='item-access', role=contributor_role),
            ActionRoles(action='files-rest-bucket-update', role=contributor_role),
            ActionRoles(action='files-rest-object-delete', role=contributor_role),
            ActionRoles(action='files-rest-object-delete-version', role=contributor_role),
            ActionRoles(action='files-rest-object-read', role=contributor_role),
            ActionRoles(action='search-access', role=contributor_role),
            ActionRoles(action='detail-page-acces', role=contributor_role),
            ActionRoles(action='download-original-pdf-access', role=contributor_role),
            ActionRoles(action='author-access', role=contributor_role),
            ActionRoles(action='items-autofill', role=contributor_role),
            ActionRoles(action='detail-page-acces', role=contributor_role),
            ActionRoles(action='detail-page-acces', role=contributor_role),
        ]
        db.session.add_all(action_roles)
    db.session.commit()
    index = Index()
    db.session.add(index)
    db.session.commit()
    comm = Community.create(community_id="comm01", role_id=sysadmin_role.id,
                            id_user=sysadmin.id, title="test community",
                            description=("this is test community"),
                            root_node_id=index.id)
    db.session.commit()
    return [
        {'email': sysadmin.email, 'id': sysadmin.id, 'obj': sysadmin},
        {'email': repoadmin.email, 'id': repoadmin.id, 'obj': repoadmin},
        {'email': comadmin.email, 'id': comadmin.id, 'obj': comadmin},
        {'email': contributor.email, 'id': contributor.id, 'obj': contributor},
        {'email': generaluser.email, 'id': generaluser.id, 'obj': generaluser},
        {'email': originalroleuser.email, 'id': originalroleuser.id, 'obj': originalroleuser},
        {'email': originalroleuser2.email, 'id': originalroleuser2.id, 'obj': originalroleuser2},
        {'email': user.email, 'id': user.id, 'obj': user},
        {'email': student.email,'id': student.id, 'obj': student}
    ]

@pytest.fixture()
def session_time(app,db):
    session_lifetime = SessionLifetime(lifetime=60,is_delete=False)

    with db.session.begin_nested():
        db.session.add(session_lifetime)

@pytest.fixture
def redis_connect(app):
    redis_connection = RedisConnection().connection(db=app.config['CACHE_REDIS_DB'], kv = True)
    keys = ('Shib-Session-1111', 'Shib-Session-session', 'Shib-Session-')
    if any(redis_connection.redis.exists(key) for key in keys):
        raise RuntimeError('Refusing to reuse an existing Shibboleth test key')
    try:
        yield redis_connection
    finally:
        redis_connection.redis.delete(*keys)
        redis_connection.redis.close()

@pytest.fixture()
def group_info_redis_connect(app):
    """Redis connection for group info."""
    redis_connection = RedisConnection().connection(db=app.config['GROUP_INFO_REDIS_DB'], kv=True)
    key = 'example_com_gakunin_groups'
    if redis_connection.redis.exists(key):
        raise RuntimeError('Refusing to reuse an existing GakuNin test key')
    try:
        yield redis_connection
    finally:
        redis_connection.redis.delete(key)
        redis_connection.redis.close()

@pytest.fixture()
def users_login(users):
    inactive_user = create_test_user(email='inactive_user@test.org', active=False)
    users.append({'email': inactive_user.email, 'id': inactive_user.id, 'obj': inactive_user})
    return users

@pytest.fixture()
def indices(db):
    """Create indices."""
    index_1 = Index(
        index_name='Index 1',
        comment='This is index 1',
        position=0,
        browsing_role='1,2,3',
        contribute_role='1,2,3',
        is_deleted=False
    )
    index_2 = Index(
        index_name='Index 2',
        comment='This is index 2',
        position=1,
        browsing_role='1,2,3',
        contribute_role='',
        is_deleted=False
    )
    index_3 = Index(
        index_name='Index 3',
        comment='This is index 3',
        position=2,
        browsing_role='',
        contribute_role='1,2,3',
        is_deleted=False
    )
    index_4 = Index(
        index_name='Index 4',
        comment='This is index 4',
        position=3,
        browsing_role='',
        contribute_role='',
        is_deleted=False
    )
    db.session.add(index_1)
    db.session.add(index_2)
    db.session.add(index_3)
    db.session.add(index_4)
    db.session.commit()
    return [index_1, index_2, index_3, index_4]

@pytest.fixture()
def weko_roles(app):
    """Create roles.

    Args:
        app (Flask): Flask application.

    Returns:
        dict: Dictionary of roles.
    """
    ds = app.extensions["invenio-accounts"].datastore
    sysadmin_role = ds.create_role(name='System Administrator')
    repoadmin_role = ds.create_role(name='Repository Administrator')
    contributor_role = ds.create_role(name='Contributor')
    comadmin_role = ds.create_role(name='Community Administrator')
    return {
        'sysadmin': sysadmin_role,
        'repoadmin': repoadmin_role,
        'contributor': contributor_role,
        'comadmin': comadmin_role
    }

@pytest.fixture()
def user_activity_log_partition_table(app, db):
    """Create user activity log partition."""
    # Create partition for current month
    now = datetime.now()
    start = now.date().replace(day=1)
    end = (start + timedelta(days=31)).replace(day=1)
    partition_name = f"user_activity_logs_{now.year}_{now.month:02d}"
    create_partition_sql = f"""
        CREATE TABLE IF NOT EXISTS {partition_name}
        PARTITION OF user_activity_logs
        FOR VALUES FROM ('{start}') TO ('{end}');
    """

    with db.session.begin_nested():
        db.session.execute(create_partition_sql)
    db.session.commit()
