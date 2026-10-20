# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016-2019 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Module tests."""

import hashlib
import json

from flask import url_for
from flask_security import login_user
from invenio_accounts.testutils import login_user_via_session
from invenio_db import db
from invenio_deposit.api import Deposit
from io import BytesIO
from sqlalchemy.orm import object_session


def test_created_by_population(api, users, location):
    """Test created_by gets populated correctly."""
    record = {
        'title': 'fuu'
    }

    deposit = Deposit.create(record)
    assert 'created_by' not in deposit['_deposit']

    with api.test_request_context():
        datastore = api.extensions['security'].datastore
        login_user(datastore.find_user(email=users[0]['email']))
        deposit = Deposit.create(record)
        assert deposit['_deposit']['created_by'] == users[0]['id']

# .tox/c1/bin/pytest --cov=invenio_deposit tests/test_views_rest_files.py::test_files_get -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/invenio-deposit/.tox/c1/tmp
def test_files_get(api, deposit, files, users):
    """Test rest files get."""
    with api.test_request_context():
        # the user is the owner
        url = url_for('invenio_deposit_rest.depid_files', pid_value=deposit['_deposit']['id'])
    with api.test_client() as client:
        # get resources without login
        res = client.get(url)
        assert res.status_code == 401
        # login
        login_user_via_session(client, email=users[0]['email'])
        # get resources
        res = client.get(
           url,
            headers=[('Content-Type', 'application/json'),
                    ('Accept', 'application/json')]
        )

        assert res.status_code == 200
        data = json.loads(res.data.decode('utf-8'))
        assert data[0]['checksum'] == files[0]['checksum']
        assert data[0]['filename'] == files[0]["key"]
        assert data[0]['filesize'] == files[0]["size"]

    # the user is NOT the owner
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[1]['email'])
        # get resources
        res = client.get(url)
        assert res.status_code == 403


def test_files_get_oauth2(api, deposit, users, write_token_user_1,
                          oauth2_headers_user_1, files):
    """Test rest files get a deposit with oauth2."""
    with api.test_request_context():
        url = url_for('invenio_deposit_rest.depid_files', pid_value=deposit['_deposit']['id'])
    with api.test_client() as client:
        # get resources
        res = client.get(url, headers=oauth2_headers_user_1)
        assert res.status_code == 200
        data = json.loads(res.data.decode('utf-8'))
        data = json.loads(res.data.decode('utf-8'))
        assert data[0]['checksum'] == files[0]['checksum']
        assert data[0]['filename'] == files[0]['key']
        assert data[0]['filesize'] == files[0]['size']


def test_files_get_without_files(api, deposit, users):
    """Test rest files get a deposit without files."""
    with api.test_request_context():
        url = url_for('invenio_deposit_rest.depid_files', pid_value=deposit['_deposit']['id'])
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[0]['email'])
        # get resources
        res = client.get(url )
        assert res.status_code == 200
        data = json.loads(res.data.decode('utf-8'))
        assert data == []


def test_files_post_oauth2(api, deposit, files, users,
                           write_token_user_1):
    """Test rest files get + oauth2."""
    real_filename = 'real_test.json'
    content = b'### Testing textfile ###'
    access_token = write_token_user_1.access_token
    #  digest = 'sha256:{0}'.format(hashlib.sha256(content).hexdigest())
    filename = 'test.json'
    with api.test_request_context():
        url = url_for('invenio_deposit_rest.depid_files', pid_value=deposit['_deposit']['id'])
    with api.test_client() as client:
        # get resources
        file_to_upload = (BytesIO(content), filename)
        res = client.post(
            url,
            data={'file': file_to_upload, 'name': real_filename},
            content_type='multipart/form-data',
            headers=[
                ('Authorization',
                    'Bearer {0}'.format(access_token))
            ]
        )
        assert res.status_code == 201
        data = json.loads(res.data.decode('utf-8'))
        assert data['filename'] == real_filename


def test_files_post(api, deposit, users):
    """Post a deposit file."""
    real_filename = 'real_test.json'
    content = b'### Testing textfile ###'
    digest = 'sha256:{0}'.format(hashlib.sha256(content).hexdigest())
    filename = 'test.json'
    deposit_id = deposit.id
    with api.test_request_context():
        # the user is the owner
        url = url_for('invenio_deposit_rest.depid_files', pid_value=deposit['_deposit']['id'])
    with api.test_client() as client:
        # test post without login
        file_to_upload = (BytesIO(content), filename)
        res = client.post(
            url,
            data={'file': file_to_upload, 'name': real_filename},
            content_type='multipart/form-data'
        )
        assert res.status_code == 401
        # login
        login_user_via_session(client, email=users[0]['email'])
        # test empty post
        res = client.post(
            url,
            data={'name': real_filename},
            content_type='multipart/form-data'
        )
        assert res.status_code == 400
        # test post
        file_to_upload = (BytesIO(content), filename)
        res = client.post(
            url,
            data={'file': file_to_upload, 'name': real_filename},
            content_type='multipart/form-data'
        )
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        files = list(deposit.files)
        assert res.status_code == 201
        assert real_filename == files[0]['key']
        assert digest == files[0]['checksum']
        data = json.loads(res.data.decode('utf-8'))
        obj = files[0]
        assert data['filename'] == obj['key']
        assert data['checksum'] == obj['checksum']
        assert data['id'] == str(obj['file_id'])

    # the user is NOT the owner
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[1]['email'])
        # test post
        file_to_upload = (BytesIO(content), filename)
        res = client.post(
            url,
            data={'file': file_to_upload, 'name': real_filename},
            content_type='multipart/form-data'
        )
        assert res.status_code == 403


def test_files_put_oauth2(api, deposit, files, users,
                          write_token_user_1):
    """Test put deposit files with oauth2."""
    deposit_id = deposit.id
    with api.test_request_context():
        with api.test_client() as client:
            # fixture
            content = b'### Testing textfile 2 ###'
            stream = BytesIO(content)
            key = 'world.txt'
            deposit.files[key] = stream
            deposit.commit()
            db.session.commit()
            deposit = Deposit.get_record(deposit_id)
            assert deposit['_files'][0]['key'] == files[0]['key']
            assert deposit['_files'][1]['key'] == key
            assert len(deposit.files) == 2
            assert len(deposit['_files']) == 2

            file_ids = [f.file_id for f in deposit.files]
            # order files
            res = client.put(
                url_for('invenio_deposit_rest.depid_files',
                        pid_value=deposit['_deposit']['id']),
                data=json.dumps([
                    {'id': str(file_ids[1])},
                    {'id': str(file_ids[0])}
                ]),
                headers=[
                    ('Authorization',
                     'Bearer {0}'.format(write_token_user_1.access_token))
                ]
            )
            assert res.status_code == 200
            data = json.loads(res.data.decode('utf-8'))
            if object_session(deposit.model):
                db.session.expunge(deposit.model)
            deposit = Deposit.get_record(deposit_id)
            assert deposit['_files'][0]['key'] == data[0]['filename']
            assert deposit['_files'][1]['key'] == data[1]['filename']
            assert data[0]['id'] == str(file_ids[1])
            assert data[1]['id'] == str(file_ids[0])
            assert len(deposit.files) == 2
            assert len(deposit['_files']) == 2
            assert len(data) == 2


def test_files_put(api, deposit, files, users):
    """Test put deposit files."""
    deposit_id = deposit.id
    with api.test_request_context():
        # the user is the owner
        url = url_for('invenio_deposit_rest.depid_files', pid_value=deposit['_deposit']['id'])
    with api.test_client() as client:
        # fixture
        content = b'### Testing textfile 2 ###'
        stream = BytesIO(content)
        key = 'world.txt'
        deposit = Deposit.get_record(deposit_id)
        deposit.files[key] = stream
        deposit.commit()
        db.session.commit()
        file_ids = [f.file_id for f in deposit.files]
        assert deposit['_files'][0]['key'] == files[0]['key']
        assert deposit['_files'][1]['key'] == key
        assert len(deposit.files) == 2
        assert len(deposit['_files']) == 2
        # add new file (without login)
        res = client.put(
            url,
            data=json.dumps([
                {'id': str(file_ids[1])},
                {'id': str(file_ids[0])}
            ])
        )
        assert res.status_code == 401
        # login
        login_user_via_session(client, email=users[0]['email'])
        # order files
        res = client.put(
            url,
            data=json.dumps([
                {'id': str(file_ids[1])},
                {'id': str(file_ids[0])}
            ])
        )
        data = json.loads(res.data.decode('utf-8'))
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        assert deposit['_files'][0]['key'] == data[0]['filename']
        assert deposit['_files'][1]['key'] == data[1]['filename']
        assert data[0]['id'] == str(file_ids[1])
        assert data[1]['id'] == str(file_ids[0])
        assert len(deposit.files) == 2
        assert len(deposit['_files']) == 2
        assert len(data) == 2

        # the user is NOT the owner
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[1]['email'])
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        order = [f.key for f in deposit.files]
        # test files post
        res = client.put(
            url,
            data=json.dumps([
                {'id': str(file_ids[1])},
                {'id': str(file_ids[0])}
            ])
        )
        assert res.status_code == 403
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        assert deposit['_files'][0]['key'] == order[0]
        assert deposit['_files'][1]['key'] == order[1]


def test_file_get(api, deposit, files, users):
    """Test get file."""
    with api.test_request_context():
        # the user is the owner
        url = url_for('invenio_deposit_rest.depid_file', pid_value=deposit['_deposit']['id'], key=files[0]['key'])
    with api.test_client() as client:
        # get resource without login
        res = client.get(url)
        assert res.status_code == 401
        # login
        login_user_via_session(client, email=users[0]['email'])
        # get resource
        res = client.get(url)
        assert res.status_code == 200
        data = json.loads(res.data.decode('utf-8'))
        obj = files[0]
        assert data['filename'] == obj['key']
        assert data['checksum'] == obj['checksum']
        assert data['id'] == str(obj['file_id'])

    # the user is NOT the owner
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[1]['email'])
        # get resource
        res = client.get(url)
        assert res.status_code == 403


def test_file_get_not_found(api, deposit, users):
    """Test get file."""
    with api.test_request_context():
        url = url_for('invenio_deposit_rest.depid_file', pid_value=deposit['_deposit']['id'], key='not_found')
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[0]['email'])
        # get resource
        res = client.get(url)

        assert res.status_code == 404


def test_file_delete_oauth2(api, deposit, files, users,
                            write_token_user_1):
    """Test delete file with oauth2."""
    deposit_id = deposit.id
    with api.test_request_context():
        url = url_for('invenio_deposit_rest.depid_file', pid_value=deposit['_deposit']['id'], key=files[0]['key'])
    with api.test_client() as client:
        # delete resource
        res = client.delete(
            url,
            headers=[
                ('Authorization',
                    'Bearer {0}'.format(write_token_user_1.access_token))
            ]
        )
        assert res.status_code == 204
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        assert files[0]['key'] not in deposit.files


def test_file_delete(api, deposit, files, users):
    """Test delete file."""
    deposit_id = deposit.id
    with api.test_request_context():
        # the user is the owner
        url = url_for('invenio_deposit_rest.depid_file', pid_value=deposit['_deposit']['id'], key=files[0]['key'])
    with api.test_client() as client:
        res = client.delete(url)
        assert res.status_code == 401
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        assert files[0]['key'] in deposit.files
        assert deposit.files[files[0]['key']] is not None
        # login
        login_user_via_session(client, email=users[0]['email'])
        # delete resource
        res = client.delete(url_for(
            'invenio_deposit_rest.depid_file',
            pid_value=deposit['_deposit']['id'],
            key=files[0]['key']
        ))
        assert res.status_code == 204
        assert res.data == b''
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        assert files[0]['key'] not in deposit.files

    # the user is NOT the owner
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[1]['email'])
        # delete resource
        res = client.delete(url)
        assert res.status_code == 403


def test_file_put_not_found_bucket_not_exist(api, deposit_without_bucket, users):
    """Test put file and bucket doesn't exist."""
    with api.test_request_context():
        url = url_for('invenio_deposit_rest.depid_file',
                      pid_value=deposit_without_bucket['_deposit']['id'],
                      key='not_found')
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[0]['email'])
        res = client.put(url,
            data=json.dumps({'filename': 'foobar'})
        )
        assert res.status_code == 404


def test_file_put_not_found_file_not_exist(api, deposit, files, users):
    """Test put file and file doesn't exist."""
    with api.test_request_context():
        url = url_for('invenio_deposit_rest.depid_file', pid_value=deposit['_deposit']['id'], key='not_found')
    with api.test_client() as client:
        # login
        login_user_via_session(client, email=users[0]['email'])
        res = client.put(url,
            data=json.dumps({'filename': 'foobar'})
        )
        assert res.status_code == 404


def test_file_put_oauth2(api, deposit, files, users,
                         write_token_user_1):
    """PUT a deposit file with oauth2."""
    deposit_id = deposit.id
    with api.test_request_context():
        old_file_id = files[0]['file_id']
        old_filename = files[0]['key']
        url = url_for('invenio_deposit_rest.depid_file', pid_value=deposit['_deposit']['id'], key=old_filename)
    with api.test_client() as client:
        new_filename = '{0}-new-name'.format(old_filename)
        # test rename file
        res = client.put(
            url,
            data=json.dumps({'filename': new_filename}),
            headers=[
                ('Authorization',
                    'Bearer {0}'.format(write_token_user_1.access_token))
            ]
        )
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        files = list(deposit.files)
        assert res.status_code == 200
        assert new_filename == files[0]['key']
        assert old_file_id == files[0]['file_id']
        data = json.loads(res.data.decode('utf-8'))
        obj = files[0]
        assert data['filename'] == obj['key']
        assert data['checksum'] == obj['checksum']
        assert data['id'] == str(obj['file_id'])


def test_file_put(api, deposit, files, users):
    """PUT a deposit file."""
    deposit_id = deposit.id
    with api.test_request_context():
        old_file_id = files[0]['file_id']
        old_filename = files[0]['key']
        url = url_for('invenio_deposit_rest.depid_file', pid_value=deposit['_deposit']['id'], key=old_filename)
    with api.test_client() as client:
        new_filename = '{0}-new-name'.format(old_filename)
        # test rename file (without login)
        res = client.put(
            url,
            data=json.dumps({'filename': new_filename}))
        assert res.status_code == 401
        # login
        login_user_via_session(client, email=users[0]['email'])
        # test rename file
        res = client.put(
            url,
            data=json.dumps({'filename': new_filename}))
        if object_session(deposit.model):
            db.session.expunge(deposit.model)
        deposit = Deposit.get_record(deposit_id)
        files = list(deposit.files)
        assert res.status_code == 200
        assert new_filename == files[0]['key']
        assert old_file_id == files[0]['file_id']
        data = json.loads(res.data.decode('utf-8'))
        obj = files[0]
        assert data['filename'] == obj['key']
        assert data['checksum'] == obj['checksum']
        assert data['id'] == str(obj['file_id'])
