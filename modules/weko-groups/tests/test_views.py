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
# WEKO3 is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WEKO3; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.


"""Test groups data models."""

import pytest
from mock import patch, MagicMock
from flask import Flask, json, jsonify, session, url_for
from invenio_accounts.models import User

from weko_groups.models import Group
from weko_groups.views import (
    get_group_name,
    sanitize_html_group,
    groupcount,
    _has_admin_access,
    index,
    requests,
    invitations,
    new,
    manage,
    delete,
    members,
    leave,
    approve,
    remove,
    accept,
    reject,
    new_member,
    remove_csrf,
    dbsession_clean
)

# def sanitize_html_group(value):
def test_sanitize_html_group(app):
    value = "value"
    assert sanitize_html_group(value=value) != None
# .tox/c1/bin/pytest -W ignore --cov=weko_groups tests/test_views.py::test_get_group_name -v -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-groups/.tox/c1/tmp

def test_get_group_name(app_2,users):
    from invenio_db import db
    group = Group.create(name="name")
    db.session.commit()
    res = get_group_name(1)
    assert res == "name"

    res = get_group_name(2)
    assert res == None

# def groupcount():
def test_groupcount(app_2):
    def members_count():
        return 1

    def get_id():
        return 1

    group = MagicMock()
    group.members_count = members_count
    group.get_id = get_id

    with app_2.app_context():
        with app_2.test_client() as client:
            # with patch("flask_login.utils._get_user", return_value=user):
            with patch("weko_groups.views.Group.query_by_user", return_value=[group]):
                group = Group()
                res = client.get(url_for('weko_groups.groupcount'))
                assert res.status_code == 200


# def _has_admin_access():
def test__has_admin_access(app):
    with app.app_context():
        user = MagicMock()
        user.is_authenticated = True
        with patch("flask_login.utils._get_user", return_value=user):
            with patch("weko_groups.views.current_admin") as current_admin_mock:
                permission = MagicMock()
                permission.can.return_value = False
                current_admin_mock.permission_factory = MagicMock(return_value=permission)
                assert _has_admin_access() is False


# def index():
def test_index(app_2, users):
    # "Encountered unknown tag 'assets'. Jinja was looking for the following tags: 'endblock'. The innermost block that needs to be closed is 'block'.",
    # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/index" there is no problem
    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user",
                       side_effect=lambda: User.query.get(users[3]["id"])):
                res = client.get(
                    url_for('weko_groups.index'),
                    query_string={
                        "q": "q",
                    }
                )
                assert res.status_code == 200
                assert b"List of groups" in res.data

                res = client.get(
                    url_for('weko_groups.index'),
                    query_string={}
                )
                assert res.status_code == 200
                assert b"List of groups" in res.data


# def requests():
def test_requests(app_2, users):
    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                res = client.get(url_for('weko_groups.requests'),
                                 query_string={'page': 1, 'per_page': 5})
                assert res.status_code == 200


# def invitations():
def test_invitations(app_2, users):
    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                res = client.get(url_for('weko_groups.invitations'),
                                 query_string={'page': 1, 'per_page': 5})
                assert res.status_code == 200


# def new():
# .tox/c1/bin/pytest --cov=weko_groups tests/test_views.py::test_new -v -W ignore -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-groups/.tox/c1/tmp

def test_new(app_2, users,mocker):
    from sqlalchemy.exc import IntegrityError
    mocker.patch("weko_groups.views.db.session.remove")
    def validate_on_submit_True():
        return True

    def validate_on_submit_False():
        return False

    form = MagicMock()
    form.validate_on_submit = validate_on_submit_False
    form.data = {'name': 'group_name'}
    group = MagicMock()
    group.name = "group_name"
    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.GroupForm", return_value=form):
                    # "Encountered unknown tag 'assets'. Jinja was looking for the following tags: 'endblock'. The innermost block that needs to be closed is 'block'.",
                    # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/new" there is no problem
                    res = client.get(url_for('weko_groups.new'))
                    assert res.status_code == 200

                form.validate_on_submit = validate_on_submit_True
                with patch("weko_groups.views.GroupForm", return_value=form):
                    with patch("weko_groups.views.Group.create", return_value=group):
                        res = client.get(url_for('weko_groups.new'))
                        assert res.status_code == 302

                    with patch(
                        "weko_groups.views.Group.create",
                        side_effect=IntegrityError(
                            "INSERT INTO accounts_group ...",
                            {"name": "group_name"},
                            Exception("test integrityerror"),
                        ),
                    ):
                        mocke_render = mocker.patch("weko_groups.views.render_template", return_value="render_template")
                        res = client.get(url_for('weko_groups.new'))
                        assert res.status_code == 200

                    with patch("weko_groups.views.Group.create", side_effect=Exception('test error')):
                        mocke_render = mocker.patch("weko_groups.views.render_template", return_value="render_template")
                        res = client.get(url_for('weko_groups.new'))
                        assert res.status_code == 200



# def manage(group_id):
def test_manage(app_2, users,mocker):
    mocker.patch("weko_groups.views.db.session.remove")
    def validate_on_submit_True():
        return True
    def validate_on_submit_False():
        return False


    form = MagicMock()
    form.validate_on_submit = validate_on_submit_True
    group = MagicMock()
    group.can_edit.return_value = False
    group.update.return_value = True
    group.name = "name"
    group.escape_name = "name"
    group.id = 1
    mock_query = MagicMock()
    mock_query.get_or_404.return_value = group

    with app_2.test_request_context():
        with app_2.test_client() as client:
            # "Encountered unknown tag 'assets'. Jinja was looking for the following tags: 'endblock'. The innermost block that needs to be closed is 'block'.",
            # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/1" there is no problem
            # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/1/manage" there is no problem
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    with patch("weko_groups.views.GroupForm", return_value=form):
                        res = client.get(url_for('weko_groups.manage', group_id=1))
                        assert res.status_code == 200

                        group.can_edit.return_value = True

                        with patch("weko_groups.views.Group.query", mock_query):
                            with patch("weko_groups.views.remove_csrf",side_effect=Exception('test error')):
                                mocke_render = mocker.patch("weko_groups.views.render_template", return_value="render_template")
                                res = client.get(url_for('weko_groups.manage', group_id=1))
                                assert res.status_code == 200


                    form.validate_on_submit = validate_on_submit_False
                    with patch("weko_groups.views.GroupForm", return_value=form):
                        mocke_render = mocker.patch("weko_groups.views.render_template", return_value="render_template")
                        res = client.get(url_for('weko_groups.manage', group_id=1))
                        assert res.status_code == 200



def test_manage_2(app_2, users):
    def validate_on_submit_True():
        return True

    form = MagicMock()
    form.validate_on_submit = validate_on_submit_True

    with app_2.test_request_context():
        # "Encountered unknown tag 'assets'. Jinja was looking for the following tags: 'endblock'. The innermost block that needs to be closed is 'block'.",
        # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/1" there is no problem
        # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/1/manage" there is no problem
        group = Group.create(name="name")
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.GroupForm", return_value=form):
                    res = client.get(url_for('weko_groups.manage', group_id=group.id))
                    assert res.status_code == 200


# def delete(group_id):
def test_delete(app_2, users, mocker):
    mocker.patch("weko_groups.views.db.session.remove")

    group = MagicMock()
    group.can_edit.return_value = False
    group.delete.return_value = True
    mock_query = MagicMock()
    mock_query.get_or_404.return_value = group
    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.post(url_for('weko_groups.delete', group_id=1))
                    assert res.status_code == 302

                group.can_edit.return_value = True
                group.delete.side_effect = Exception("test error")
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.post(url_for('weko_groups.delete', group_id=1))
                    assert res.status_code == 302


def test_delete_2(app_2, users):
    with app_2.test_request_context():
        group = Group.create(name="name")
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                res = client.post(url_for('weko_groups.delete', group_id=group.id))
                assert res.status_code == 302


# def members(group_id):
def test_members(app_2, users):
    def can_edit_True(item):
        return True

    def can_edit_False(item):
        return False

    def delete_func():
        return True

    group = MagicMock()
    group.id = 1
    group.name = "group_name"
    group.escape_name = "group_name"
    group.query = MagicMock()
    group.query.get_or_404 = MagicMock()
    group.query.get_or_404.can_edit = can_edit_False
    group.query.get_or_404.delete = delete_func

    mock_query = MagicMock()
    mock_query.get_or_404.return_value = group

    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.post(
                        url_for('weko_groups.members', group_id=1),
                        query_string={
                            "q": "q",
                            "s": "s",
                        }
                    )
                    assert res.status_code == 200
                    assert b"group_name" in res.data


def test_members_2(app_2, users):
    with app_2.test_request_context():
        group = Group.create(name="name")

        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                res = client.post(url_for('weko_groups.members', group_id=group.id))
                assert res.status_code == 302


# def leave(group_id):
def test_leave(app_2, users,mocker):
    mocker.patch("weko_groups.views.db.session.remove")

    # Case 1: can_leave returns True and remove_member succeeds
    group = MagicMock()
    group.can_leave.return_value = True
    group.remove_member.return_value = None

    mock_query = MagicMock()
    mock_query.get_or_404.return_value = group

    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.post(url_for('weko_groups.leave', group_id=1))
                    assert res.status_code == 302
                    group.remove_member.assert_called_once()

            # Case 2: can_leave returns True but remove_member raises Exception
            group.reset_mock()
            group.can_leave.return_value = True
            group.remove_member.side_effect = Exception("test error")

            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.post(url_for('weko_groups.leave', group_id=1))
                    assert res.status_code == 302

def test_leave_2(app_2, users):
    with app_2.test_request_context():
        group = Group.create(name="name")
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                res = client.post(url_for('weko_groups.leave', group_id=group.id))
                assert res.status_code == 302

# .tox/c1/bin/pytest -W ignore --cov=weko_groups tests/test_views.py::test_approve -v -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-groups/.tox/c1/tmp

# def approve(group_id, user_id):
def test_approve(app_2, users,mocker):
    mocker.patch("weko_groups.views.db.session.remove")

    # Case 1: can_edit returns True and accept succeeds
    membership = MagicMock()
    membership.group.can_edit.return_value = True
    membership.accept.return_value = None
    membership.user.email = "test@example.com"
    membership.group.name = "test_group"

    mock_query = MagicMock()
    mock_query.get_or_404.return_value = membership

    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Membership.query", mock_query):
                    res = client.post(url_for('weko_groups.approve', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302
                    membership.accept.assert_called_once()

            # Case 2: can_edit returns True but accept raises Exception
            membership.reset_mock()
            membership.group.can_edit.return_value = True
            membership.accept.side_effect = Exception("test error")
            membership.group.id = 1

            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Membership.query", mock_query):
                    res = client.post(url_for('weko_groups.approve', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302

            # Case 3: can_edit returns False (no permission)
            membership.reset_mock()
            membership.group.can_edit.return_value = False
            membership.group.name = "test_group"

            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Membership.query", mock_query):
                    res = client.post(url_for('weko_groups.approve', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302

def test_approve_2(app_2, users):
    with app_2.test_request_context():
        group = Group.create(name="name")
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                res = client.post(url_for('weko_groups.approve', group_id=group.id, user_id=users[3]["obj"].id))
                assert res.status_code == 404


# def remove(group_id, user_id):
def test_remove(app_2, users, mocker):
    mocker.patch("weko_groups.views.db.session.remove")

    group = MagicMock()
    group.can_edit.return_value = True
    mock_query = MagicMock()
    mock_query.get_or_404.return_value = group
    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.post(url_for('weko_groups.remove', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302
                group.remove_member.side_effect=Exception("test error")
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.post(url_for('weko_groups.remove', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302


def test_remove_2(app_2, users):
    with app_2.test_request_context():
        group = Group.create(name="name")
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                res = client.post(url_for('weko_groups.remove', group_id=group.id, user_id=users[3]["obj"].id))
                assert res.status_code == 302


# def accept(group_id):
def test_accept(app_2, users,mocker):
    mocker.patch("weko_groups.views.db.session.remove")

    membership = MagicMock()
    membership.group.can_edit.return_value = True
    membership.accept.return_value = True
    mock_query = MagicMock()
    mock_query.get_or_404.return_value = membership
    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Membership.query", mock_query):
                    res = client.post(url_for('weko_groups.accept', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302
                membership.accept.side_effect=Exception("test error")
                with patch("weko_groups.views.Membership.query", mock_query):
                    res = client.post(url_for('weko_groups.accept', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302

# .tox/c1/bin/pytest -W ignore --cov=weko_groups tests/test_views.py::test_reject -v -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-groups/.tox/c1/tmp
# def reject(group_id):
def test_reject(app_2, users, mocker):
    mocker.patch("weko_groups.views.db.session.remove")

    membership = MagicMock()
    membership.group.can_edit.return_value = True
    membership.reject.return_value = True
    mock_query = MagicMock()
    mock_query.get_or_404.return_value = membership

    with app_2.test_request_context():
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Membership.query", mock_query):
                    res = client.post(url_for('weko_groups.reject', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302

                membership.reject.side_effect=Exception("test error")
                with patch("weko_groups.views.Membership.query", mock_query):
                    res = client.post(url_for('weko_groups.reject', group_id=1, user_id=users[3]["obj"].id))
                    assert res.status_code == 302

# def new_member(group_id):
def test_new_member(app_2, users,mocker):
    mocker.patch("weko_groups.views.db.session.remove")

    def validate_on_submit_True():
        return True

    form = MagicMock()
    form.validate_on_submit = validate_on_submit_True
    group = MagicMock()
    group.can_invite_others.return_value = True
    group.invite_by_emails.return_value = True
    group.name = "group_name"
    group.escape_name = "group_name"
    group.id = 1
    form.data = {"emails": "test@example.com"}

    mock_query = MagicMock()
    mock_query.get_or_404.return_value = group

    with app_2.test_request_context():
        # "Encountered unknown tag 'assets'. Jinja was looking for the following tags: 'endblock'. The innermost block that needs to be closed is 'block'."
        # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/1/members/new" there is no problem
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    with patch("weko_groups.views.NewMemberForm", return_value=form):
                        res = client.get(url_for('weko_groups.new_member', group_id=1))
                        assert res.status_code == 302
                        group.invite_by_emails.assert_called_once()
                        assert list(group.invite_by_emails.call_args[0][0]) == ["test@example.com"]
                    res = client.get(url_for('weko_groups.new_member', group_id=1))
                    assert res.status_code == 200
                    assert b"Specifies email addresses" in res.data


# def new_member(group_id):
def test_new_member_2(app_2, users):
    def validate_on_submit_True():
        return True

    def can_invite_others(item):
        return True

    def invite_by_emails(item):
        return True

    form = MagicMock()
    form.validate_on_submit = validate_on_submit_True
    group = MagicMock()
    group.id = 1
    group.name = "group_name"
    group.escape_name = "group_name"
    group.query.get_or_404.can_invite_others = can_invite_others
    group.query.get_or_404.invite_by_emails = invite_by_emails
    group.name = "group_name"

    mock_query = MagicMock()
    mock_query.get_or_404.return_value = group

    with app_2.test_request_context():
        # "Encountered unknown tag 'assets'. Jinja was looking for the following tags: 'endblock'. The innermost block that needs to be closed is 'block'."
        # But upon testing on the actual url on the browser "https://localhost/accounts/settings/groups/1/members/new" there is no problem
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[3]["obj"]):
                with patch("weko_groups.views.Group.query", mock_query):
                    res = client.get(url_for('weko_groups.new_member', group_id=1))
                    assert res.status_code == 200
                    assert b"Specifies email addresses" in res.data


def test_new_member_3(app_2, users):
    with app_2.test_request_context():
        group = Group.create(name="name", is_managed=True)
        with app_2.test_client() as client:
            with patch("flask_login.utils._get_user", return_value=users[7]["obj"]):
                res = client.get(url_for('weko_groups.new_member', group_id=group.id))
                assert res.status_code == 302


# def remove_csrf(form):
def test_remove_csrf(app):
    form = MagicMock()
    form.data = {
        "not_csrf_token_key": "not_csrf_token_value"
    }

    assert remove_csrf(form=form) != None

    form = MagicMock()
    form.data = {
        "csrf_token": "1223dsfiejfpa"
    }

    assert remove_csrf(form=form) == {}

