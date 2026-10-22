# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016-2019 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.


"""Pytest configuration."""

import os
import shutil
import tempfile
import uuid
from zipfile import ZipFile

import pytest
from flask import Flask
from flask_webpackext import current_webpack, WebpackBundleProject
from invenio_accounts import InvenioAccounts
from invenio_app import InvenioApp
from invenio_assets import InvenioAssets
from invenio_communities import InvenioCommunities
from invenio_communities.views.ui import blueprint as invenio_communities_blueprint
from invenio_config import InvenioConfigDefault
from invenio_db import InvenioDB
from invenio_files_rest import InvenioFilesREST
from invenio_files_rest.models import Location, ObjectVersion
from invenio_formatter import InvenioFormatter
from invenio_i18n import Babel
from invenio_pidstore.providers.recordid import RecordIdProvider
from invenio_records import InvenioRecords
from invenio_records_files.api import Record
from invenio_records_ui import InvenioRecordsUI
from invenio_records_ui.views import create_blueprint_from_app
from invenio_theme.webpack import theme
from invenio_db import db as db_
from io import BytesIO
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Mapper, Session
from sqlalchemy_continuum import versioning_manager
from sqlalchemy_utils.functions import create_database, drop_database

from invenio_previewer import InvenioPreviewer
from invenio_previewer.webpack import previewer as previewer_bundle

@pytest.yield_fixture(scope='session', autouse=True)
def app(versioning_listeners):
    """Flask application fixture with database initialization."""
    instance_path = tempfile.mkdtemp()
    database_created = False
    try:
        database_url = make_url(os.environ['SQLALCHEMY_DATABASE_URI']).set(
            database='previewer_ut_' + uuid.uuid4().hex)
        create_database(database_url)
        database_created = True

        app_ = Flask(
            'testapp', static_folder=instance_path, instance_path=instance_path)
        app_.config.update(
            TESTING=True,
            APP_THEME=["bootstrap3"],
            SQLALCHEMY_DATABASE_URI=database_url.render_as_string(hide_password=False),
            SQLALCHEMY_TRACK_MODIFICATIONS=True,
            RECORDS_UI_DEFAULT_PERMISSION_FACTORY=None,
            RECORDS_UI_ENDPOINTS=dict(
                recid=dict(
                    pid_type='recid',
                    route='/records/<pid_value>',
                    template='invenio_records_ui/detail.html',
                ),
                recid_previewer=dict(
                    pid_type='recid',
                    route='/records/<pid_value>/preview/<filename>',
                    view_imp='invenio_previewer.views:preview',
                    record_class='invenio_records_files.api:Record',
                ),
                recid_files=dict(
                    pid_type='recid',
                    route='/record/<pid_value>/files/<filename>',
                    view_imp='invenio_records_files.utils.file_download_ui',
                    record_class='invenio_records_files.api:Record',
                ),
                recid_file_preview=dict(
                    pid_type='recid',
                    route='/record/<pid_value>/file_preview/<path:filename>',
                    view_imp='weko_records_ui.fd.file_preview_ui',
                    record_class='weko_deposit.api:WekoRecord',
                    permission_factory_imp='weko_records_ui.permissions'
                                        ':page_permission_factory',
                ),
            ),
            SERVER_NAME='localhost',
            SECRET_KEY="SECRET_KEY",
            WEKO_THEME_INSTANCE_DATA_DIR="data",
            WEBPACKEXT_PROJECT=WebpackBundleProject(
                'invenio_assets.webpack', project_folder='assets',
                config_path='build/config.json', bundles=[theme, previewer_bundle]),
        )
        Babel(app_)
        assets_ext = InvenioAssets(app_)
        InvenioDB(app_)
        InvenioRecords(app_)
        previewer = InvenioPreviewer(app_)._state
        InvenioRecordsUI(app_)
        InvenioFilesREST(app_)
        InvenioAccounts(app_)

        app_.register_blueprint(create_blueprint_from_app(app_))
        InvenioCommunities(app_)
        app_.register_blueprint(invenio_communities_blueprint)

        # Add base assets bundles for jQuery and Bootstrap
        # Note: These bundles aren't included by default since package consumers
        # should handle assets and their dependencies manually.
        # assets_ext.env.register(previewer.js_bundles[0], previewer_base_js)
        # assets_ext.env.register(previewer.css_bundles[0], previewer_base_css)

        with app_.app_context():
            try:
                yield app_
            finally:
                db_.session.remove()
                db_.engine.dispose()
    finally:
        try:
            if database_created:
                drop_database(database_url)
        finally:
            shutil.rmtree(instance_path)


@pytest.fixture(scope='session')
def versioning_listeners():
    registrations = [
        (target, name, listener)
        for target, listeners in (
            (Session, versioning_manager.session_listeners),
            (Mapper, versioning_manager.mapper_listeners),
            (Mapper, versioning_manager.class_config_listeners))
        for name, listener in listeners.items()]
    registrations.extend([
        (Engine, 'before_execute', versioning_manager.track_association_operations),
        (Engine, 'rollback', versioning_manager.clear_connection),
        (Engine, 'set_connection_execution_options', versioning_manager.track_cloned_connections)])
    existing = [event.contains(*registration) for registration in registrations]
    try:
        yield
    finally:
        for registration, present in zip(registrations, existing):
            if not present and event.contains(*registration):
                event.remove(*registration)


@pytest.fixture(autouse=True)
def restore_config(app):
    original = app.config.copy()
    try:
        yield
    finally:
        app.config.clear()
        app.config.update(original)


@pytest.fixture(scope="module")
def app_config(app_config):
    """Flask application fixture with database initialization."""
    app_config.update(
        RECORDS_UI_DEFAULT_PERMISSION_FACTORY=None,
        RECORDS_UI_ENDPOINTS=dict(
            recid=dict(
                pid_type="recid",
                route="/records/<pid_value>",
                template="invenio_records_ui/detail.html",
            ),
            recid_previewer=dict(
                pid_type="recid",
                route="/records/<pid_value>/preview",
                view_imp="invenio_previewer.views:preview",
                record_class="invenio_records_files.api:Record",
            ),
            recid_files=dict(
                pid_type="recid",
                route="/record/<pid_value>/files/<filename>",
                view_imp="invenio_records_files.utils.file_download_ui",
                record_class="invenio_records_files.api:Record",
            ),
        ),
        SERVER_NAME="localhost",
    )
    return app_config


@pytest.fixture(scope="module")
def create_app(instance_path):
    """Application factory fixture for use with pytest-invenio."""

    def _create_app(**config):
        app_ = Flask(
            __name__,
            instance_path=instance_path,
        )
        app_.config.update(config)
        Babel(app_)
        InvenioApp(app_)
        InvenioAssets(app_)
        InvenioDB(app_)
        InvenioRecords(app_)
        InvenioConfigDefault(app_)
        InvenioFormatter(app_)
        InvenioPreviewer(app_)._state
        InvenioRecordsUI(app_)
        app_.register_blueprint(create_blueprint_from_app(app_))
        InvenioFilesREST(app_)
        return app_

    return _create_app


@pytest.fixture(scope="module")
def testapp(app):
    """Application with just a database.

    Pytest-Invenio also initialise search with the app fixture.
    """
    yield app


@pytest.fixture(scope="module")
def webassets(testapp):
    """Flask application fixture with assets."""
    initial_dir = os.getcwd()
    theme_bundle = current_webpack.project.bundles[0]
    original_aliases = theme_bundle.aliases.copy()
    try:
        os.chdir(testapp.instance_path)

        # The theme.config file has been moved from `invenio-theme` to cookiecutter
        # To solve this, a fake config file is created on the fly
        THEME_CONFIG_PATH = "less/theme.config"
        # force theme.config alias pointing to less/invenio_theme/theme.config.example
        theme_bundle.aliases["../../theme.config"] = THEME_CONFIG_PATH

        current_webpack.project.create()
        current_webpack.project.install("--no-audit", "--no-fund", "--prefer-offline")

        if testapp.config["APP_THEME"] == ["bootstrap3"]:
            scss_dir = os.path.join(testapp.instance_path, testapp.config['WEKO_THEME_INSTANCE_DATA_DIR'])
            os.makedirs(scss_dir, exist_ok=True)
            scss_file = os.path.join(scss_dir, '_variables.scss')
            with open(scss_file, "w") as f:
                f.write("$body-bg: #ffff;\n$panel-bg: #ffff;\n$footer-default-bg: #0d5f89;\n$navbar-default-bg: #0d5f89;\n$panel-default-border: #dddddd;\n$input-bg-transparent: rgba(255, 255, 255, 0);")
        else:
            # create a fake theme config file from the example one
            # theme.config.example only exists for semantic-ui theme
            _assets = os.path.join(testapp.instance_path, "assets")
            example = os.path.join(_assets, "less", "invenio_theme", "theme.config.example")
            with open(example, "r") as fi:
                with open(os.path.join(_assets, THEME_CONFIG_PATH), "w") as fo:
                    for line in fi:
                        if line.startswith("@siteFolder"):
                            # use default theme as site theme instead of `my-site/site` as
                            # in `invenio-theme`
                            fo.write("@siteFolder: 'default';")
                        else:
                            fo.write(line)

        current_webpack.project.build()

        yield testapp
    finally:
        theme_bundle.aliases.clear()
        theme_bundle.aliases.update(original_aliases)
        os.chdir(initial_dir)


@pytest.fixture()
def location(db):
    """File system location."""
    tmppath = tempfile.mkdtemp()
    try:
        loc = Location(name="testloc", uri=tmppath, default=True)
        db.session.add(loc)
        db.session.commit()
        yield loc
    finally:
        shutil.rmtree(tmppath)


@pytest.fixture()
def record(db, location):
    """Record fixture."""
    rec_uuid = uuid.uuid4()
    provider = RecordIdProvider.create(object_type="rec", object_uuid=rec_uuid)
    record = Record.create(
        {
            "control_number": provider.pid.pid_value,
            "title": "TestDefault",
        },
        id_=rec_uuid,
    )
    db.session.commit()
    return record


@pytest.fixture()
def record_with_file(db, record, location):
    """Record with a test file."""
    testfile = ObjectVersion.create(record.bucket, "testfile", stream=BytesIO(b"atest"))
    record.update(
        dict(
            _files=[
                dict(
                    bucket=str(testfile.bucket_id),
                    key=testfile.key,
                    size=testfile.file.size,
                    checksum=str(testfile.file.checksum),
                    version_id=str(testfile.version_id),
                ),
            ]
        )
    )
    record.commit()
    db.session.commit()
    return record, testfile


@pytest.fixture()
def zip_fp(db):
    """ZIP file stream."""
    fp = BytesIO()

    zipf = ZipFile(fp, "w")
    zipf.writestr("Example.txt", "This is an example".encode("utf-8"))
    zipf.writestr("Lé UTF8 test.txt", "This is an example".encode("utf-8"))
    zipf.close()

    fp.seek(0)
    return fp

@pytest.yield_fixture()
def db(app):
    """Database fixture."""
    try:
        db_.create_all()
        yield db_
    finally:
        db_.session.remove()
        db_.drop_all()
