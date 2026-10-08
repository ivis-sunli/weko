
import os
import calendar
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, patch

import pytest

from celery import Celery
from flask import current_app
from requests.models import Response

from invenio_oaiserver.models import OAISet
from weko_admin.models import AdminSettings
from weko_admin.tasks import (
    send_all_reports,
    _get_start_end_date,
    check_send_all_reports,
    send_feedback_mail,
    _due_to_run,
    _is_end_of_month,
    check_send_site_access_report,
    clean_temp_info
)
from weko_admin.models import AdminSettings
from weko_admin.tasks import is_reindex_running, reindex

# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp

# def send_all_reports(report_type=None, year=None, month=None):
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_send_all_reports -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp
def test_send_all_reports(app, users, statistic_email_addrs, mocker):
    current_app.config.update(
        WEKO_ADMIN_REPORT_EMAIL_TEMPLATE='weko_admin/email_templates/report.html'
    )
    class MockZip():
        def getvalue(self):
            return "test_value"

    mocker.patch("weko_admin.tasks.render_template",return_value="test_html")

    now = datetime.now()

    # report_type is None, frequency is daily
    start_date = now - timedelta(days=2)
    end_date = now - timedelta(days=2)
    subject = "{} Log report.".format(start_date.strftime("%Y-%m-%d"))
    target_email=[email.email_address for email in statistic_email_addrs]
    schedule = {"details": "", "enabled": True, "frequency": "daily"}
    with patch("weko_admin.tasks.get_reports") as mock_get_reports, \
            patch("weko_admin.tasks.package_reports", return_value=MockZip()) as mock_package_reports, \
            patch("weko_admin.tasks.send_mail") as mock_mail:

        send_all_reports(schedule=schedule)

    args, kwargs = mock_get_reports.call_args
    assert args == ("all",)
    assert kwargs["start_date"].strftime("%Y-%m-%d") == start_date.strftime("%Y-%m-%d")
    assert kwargs["end_date"].strftime("%Y-%m-%d") == end_date.strftime("%Y-%m-%d")
    args, kwargs = mock_package_reports.call_args
    assert args == (ANY,)
    assert kwargs["report_date"] == start_date.strftime("%Y-%m-%d")
    args, kwargs = mock_mail.call_args
    assert args == (subject, target_email)
    assert kwargs["html"] == "test_html"

    # report_type is not None, frequency is weekly
    start_date = now - timedelta(days=8)
    end_date = now - timedelta(days=2)
    subject = "{} Log report.".format(start_date.strftime("%Y-%m-%d") + "_" + end_date.strftime("%Y-%m-%d"))
    schedule = {"details": str(now.weekday()), "enabled": True, "frequency": "weekly"}
    with patch("weko_admin.tasks.get_reports") as mock_get_reports, \
            patch("weko_admin.tasks.package_reports", return_value=MockZip()) as mock_package_reports, \
            patch("weko_admin.tasks.send_mail") as mock_mail:

        send_all_reports("fiile_download", schedule=schedule)

    args, kwargs = mock_get_reports.call_args
    assert args == ("fiile_download",)
    assert kwargs["start_date"].strftime("%Y-%m-%d") == start_date.strftime("%Y-%m-%d")
    assert kwargs["end_date"].strftime("%Y-%m-%d") == end_date.strftime("%Y-%m-%d")
    args, kwargs = mock_package_reports.call_args
    assert args == (ANY,)
    assert kwargs["report_date"] == f'{start_date.strftime("%Y-%m-%d")}_{end_date.strftime("%Y-%m-%d")}'
    args, kwargs = mock_mail.call_args
    assert args == (subject, target_email)
    assert kwargs["html"] == "test_html"

    # frequency is monthly
    end_date = now.replace(day=1) - timedelta(days=1)
    start_date = end_date.replace(day=1)
    subject = "{} Log report.".format(start_date.strftime("%Y-%m"))
    schedule = {"details": "2", "enabled": True, "frequency": "monthly"}
    with patch("weko_admin.tasks.get_reports") as mock_get_reports, \
            patch("weko_admin.tasks.package_reports", return_value=MockZip()) as mock_package_reports, \
            patch("weko_admin.tasks.send_mail") as mock_mail:

        send_all_reports("fiile_download", schedule=schedule)

    args, kwargs = mock_get_reports.call_args
    assert args == ("fiile_download",)
    assert kwargs["start_date"].strftime("%Y-%m-%d") == start_date.strftime("%Y-%m-%d")
    assert kwargs["end_date"].strftime("%Y-%m-%d") == end_date.strftime("%Y-%m-%d")
    args, kwargs = mock_package_reports.call_args
    assert args == (ANY, start_date.year, start_date.month)
    assert not kwargs
    args, kwargs = mock_mail.call_args
    assert args == (subject, target_email)
    assert kwargs["html"] == "test_html"

    # raise Exception
    mock_mail = mocker.patch("weko_admin.tasks.send_mail", side_effect=Exception("test_error"))
    mocker.patch("weko_admin.tasks.package_reports", return_value=MockZip())
    send_all_reports("file_download", schedule=schedule)
    args, kwargs = mock_mail.call_args
    assert args == (subject, target_email)
    assert kwargs["html"] == "test_html"

# def _get_start_end_date(dt, frequency):
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test__get_start_end_date -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp
def test__get_start_end_date():
    dt = datetime(year=2024, month=2, day=15, tzinfo=timezone.utc)

    # frequency is daily, start_date and end_date are 2 days ago
    start_date, end_date = _get_start_end_date(dt, 'daily')
    assert start_date == datetime(year=2024, month=2, day=13, tzinfo=timezone.utc)
    assert end_date == datetime(year=2024, month=2, day=13, tzinfo=timezone.utc)

    # frequency is weekly, a week ago ending 2 days ago
    start_date, end_date = _get_start_end_date(dt, 'weekly')
    assert start_date == datetime(year=2024, month=2, day=7, tzinfo=timezone.utc)
    assert end_date == datetime(year=2024, month=2, day=13, tzinfo=timezone.utc)

    # frequency is monthly, last month
    start_date, end_date = _get_start_end_date(dt, 'monthly')
    assert start_date == datetime(year=2024, month=1, day=1, tzinfo=timezone.utc)
    assert end_date == datetime(year=2024, month=1, day=31, tzinfo=timezone.utc)

    # leap year, frequency is monthly
    dt = datetime(year=2024, month=3, day=15, tzinfo=timezone.utc)
    start_date, end_date = _get_start_end_date(dt, 'monthly')
    assert start_date == datetime(year=2024, month=2, day=1, tzinfo=timezone.utc)
    assert end_date == datetime(year=2024, month=2, day=29, tzinfo=timezone.utc)


# def check_send_all_reports():
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_check_send_all_reports -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp
def test_check_send_all_reports(app, admin_settings, mocker):
    AdminSettings.update("report_email_schedule_settings", {})
    mock_send = mocker.patch("weko_admin.tasks.send_all_reports.delay")
    check_send_all_reports()
    mock_send.assert_not_called()

    AdminSettings.update("report_email_schedule_settings", {"Root Index": {"details":"","enabled":True,"frequency":"daily"}})
    mock_send = mocker.patch("weko_admin.tasks.send_all_reports.delay")
    check_send_all_reports()
    mock_send.assert_called()
    args, kwargs = mock_send.call_args
    assert kwargs["repository_id"] == "Root Index"

    AdminSettings.update("report_email_schedule_settings", {"Root Index": {"details":"","enabled":False,"frequency":"daily"}})
    mock_send = mocker.patch("weko_admin.tasks.send_all_reports.delay")
    check_send_all_reports()
    mock_send.assert_not_called()


# def send_feedback_mail():
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_send_feedback_mail -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp
def test_send_feedback_mail(app, mocker):
    mock_send = mocker.patch("weko_admin.tasks.StatisticMail.send_mail_to_all")
    setting = mocker.Mock()
    setting.is_sending_feedback=True
    mocker.patch("weko_admin.models.FeedbackMailSetting.get_feedback_email_setting_by_repo",return_value=[setting])
    send_feedback_mail()
    mock_send.assert_called()


# def _due_to_run(schedule):
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_due_to_run -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp
def test_due_to_run(mocker):
    schedule = {"details":"","enabled":False,"frequency":"daily"}
    result = _due_to_run(schedule)
    assert result == False

    schedule = {"details":"","enabled":True,"frequency":"daily"}
    result = _due_to_run(schedule)
    assert result == True

    today = datetime.now(tz=timezone.utc)
    weekday = today.weekday()

    schedule = {"details":f"{weekday}","enabled":False,"frequency":"weekly"}
    result = _due_to_run(schedule)
    assert result == False

    schedule = {"details":f"{weekday}","enabled":True,"frequency":"weekly"}
    result = _due_to_run(schedule)
    assert result == True

    schedule = {"details":f"{weekday + 1}","enabled":True,"frequency":"weekly"}
    result = _due_to_run(schedule)
    assert result == False

    day = today.day

    schedule = {"details":f"{day}","enabled":False,"frequency":"monthly"}
    result = _due_to_run(schedule)
    assert result == False

    schedule = {"details":f"{day}","enabled":True,"frequency":"monthly"}
    result = _due_to_run(schedule)
    assert result == True

    schedule = {"details":f"{day + 1}","enabled":True,"frequency":"monthly"}
    result = _due_to_run(schedule)
    assert result == False

    mocker.patch("weko_admin.tasks._is_end_of_month", return_value=True)
    schedule = {"details":"-1","enabled":True,"frequency":"monthly"}
    result = _due_to_run(schedule)
    assert result == True

    mocker.patch("weko_admin.tasks._is_end_of_month", return_value=False)
    schedule = {"details":"-1","enabled":True,"frequency":"monthly"}
    result = _due_to_run(schedule)
    assert result == False

    schedule = {"details":"1","enabled":True,"frequency":"unknown"}
    result = _due_to_run(schedule)
    assert result == False

# def _is_end_of_month(dt):
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_is_end_of_month_match -vv -s --cov-branch --cov-report=term
@pytest.mark.parametrize("month", [i for i in range(1, 13)], ids=list(calendar.month_abbr)[1:])
def test_is_end_of_month_match(month):
    dt = datetime(year=2025, month=month, day=calendar.mdays[month], tzinfo=timezone.utc)
    assert _is_end_of_month(dt) == True

# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_is_end_of_month_not_match -vv -s --cov-branch --cov-report=term
@pytest.mark.parametrize("month", [i for i in range(1, 13)], ids=list(calendar.month_abbr)[1:])
def test_is_end_of_month_not_match(month):
    dt = datetime(year=2025, month=month, day=(calendar.mdays[month] - 1), tzinfo=timezone.utc)
    assert _is_end_of_month(dt) == False

# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_is_end_of_month_leap_year -vv -s --cov-branch --cov-report=term
def test_is_end_of_month_leap_year():
    dt = datetime(year=2024, month=2, day=28, tzinfo=timezone.utc)
    assert _is_end_of_month(dt) == False

    dt = datetime(year=2024, month=2, day=29, tzinfo=timezone.utc)
    assert _is_end_of_month(dt) == True

# def check_send_site_access_report():
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_check_send_site_access_report -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp
def test_check_send_site_access_report(client, admin_settings, mocker):

    # site_license_mail_setting.auto_send_flag is False
    check_send_site_access_report()

    # site_license_mail_setting.auto_send_flag is True
    AdminSettings.update("site_license_mail_settings", {"Root Index": {"auto_send_flag": True}})
    mock_send = mocker.patch("weko_admin.tasks.handle_site_license_mail")
    check_send_site_access_report()
    mock_send.assert_called()

# def clean_temp_info():
# .tox/c1/bin/pytest --cov=weko_admin tests/test_tasks.py::test_clean_temp_info -vv -s --cov-branch --cov-report=term --basetemp=/code/modules/weko-admin/.tox/c1/tmp
def test_clean_temp_info(instance_path):
    #/tmp
    now = datetime.now()
    dir_not_expire = os.path.join(instance_path,"not_expire")
    dir_expire_after_now = os.path.join(instance_path,"expire_after_now")
    dir_expire_before_now = os.path.join(instance_path,"expire_before_now")
    dir_export_tmp = os.path.join(instance_path,"export_tmp")
    os.makedirs(dir_not_expire, exist_ok=True)
    os.makedirs(dir_expire_after_now, exist_ok=True)
    os.makedirs(dir_expire_before_now, exist_ok=True)
    os.makedirs(dir_export_tmp, exist_ok=True)
    data = {"test_key":{
        "/not_exist_path": {},# not exist path
        dir_not_expire: {},
        dir_expire_after_now: {"expire":(now+timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")},
        dir_expire_before_now: {"expire":(now+timedelta(days=-10)).strftime("%Y-%m-%d %H:%M:%S")},
        dir_export_tmp: {"expire":(now+timedelta(days=-10)).strftime("%Y-%m-%d %H:%M:%S"), "is_export": True}
    }}
    class MockTempDirInfo():
        def __init__(self):
            self.key = "test_key"
            self.data = data
        def get_all(self):
            result = {}
            for idx, val in self.data.get(self.key).items():
                path = idx
                result[path] = val
            return result
        def delete(self, path):
            self.data[self.key].pop(path)
    mock_temp_dir_info = MockTempDirInfo()
    with patch("weko_admin.tasks.TempDirInfo", return_value=mock_temp_dir_info):
        with patch("weko_search_ui.utils.delete_exported",return_value=True) as mock_delete_exported:

            clean_temp_info()
            result = mock_temp_dir_info.get_all()
            assert list(result.keys()) == [dir_not_expire, dir_expire_after_now]
            assert os.path.exists(dir_expire_before_now) is False
            mock_delete_exported.assert_called_with(dir_export_tmp,
                {"expire":(now+timedelta(days=-10)).strftime("%Y-%m-%d %H:%M:%S"), "is_export": True})


INSPECT_RETURN_VALUE={'celery@d852e7dcb4da': [{'id': '0789eb75-2d50-45ba-b132-e85a70e71524', 'name': 'weko_admin.tasks.reindex', 'args': [False], 'kwargs': {}, 'type': 'weko_admin.tasks.reindex', 'hostname': 'celery@d852e7dcb4da', 'time_start': 1671494657.8838153, 'acknowledged': True, 'delivery_info': {'exchange': '', 'routing_key': 'celery', 'priority': 0, 'redelivered': False}, 'worker_pid': 264}]}

def test_is_reindex_running_not_running(i18n_app, mocker):
    mocker.patch("weko_admin.tasks.check_celery_is_run", return_value=False)

    assert not is_reindex_running()

def test_is_reindex_running_active(i18n_app, mocker):
    mocker.patch("weko_admin.tasks.check_celery_is_run", return_value=True)
    mock_celery = mocker.MagicMock(spec=Celery)
    mock_celery.control.inspect.return_value.active.return_value = INSPECT_RETURN_VALUE
    mock_celery.control.inspect.return_value.reserved.return_value = []
    mocker.patch("weko_admin.tasks.current_celery_app", new=mock_celery)

    assert is_reindex_running()

def test_is_reindex_running_reserved(i18n_app, mocker):
    mocker.patch("weko_admin.tasks.check_celery_is_run", return_value=True)
    mock_celery = mocker.MagicMock(spec=Celery)
    mock_celery.control.inspect.return_value.active.return_value = []
    mock_celery.control.inspect.return_value.reserved.return_value = INSPECT_RETURN_VALUE
    mocker.patch("weko_admin.tasks.current_celery_app", new=mock_celery)

    assert is_reindex_running()

def test_is_reindex_running_waiting(i18n_app, mocker):
    mocker.patch("weko_admin.tasks.check_celery_is_run", return_value=True)
    mock_celery = mocker.MagicMock(spec=Celery)
    mock_celery.control.inspect.return_value.active.return_value = []
    mock_celery.control.inspect.return_value.reserved.return_value = []
    mocker.patch("weko_admin.tasks.current_celery_app", new=mock_celery)

    assert not is_reindex_running()


def test_reindex_EStoES(i18n_app,admin_settings, mocker):

    return_value = mocker.Mock(spec=Response)
    return_value.text = "test_mock"
    return_value.status_code = 200

    mocker.patch("weko_admin.utils.requests.head", return_value=return_value)
    with patch("weko_admin.utils.requests.put" , return_value=return_value):
        with patch("weko_admin.utils.requests.post" , return_value=return_value):
            with patch("weko_admin.utils.requests.delete" , return_value=return_value):
                with patch("weko_admin.utils.requests.get" , return_value=return_value):
                    assert 'completed' == reindex(False)


def test_reindex_DBtoES(i18n_app,admin_settings,reindex_settings, mocker):

    return_value = mocker.Mock(spec=Response)
    return_value.text = "test_mock"
    return_value.status_code = 200

    mocker.patch("weko_admin.utils.requests.head", return_value=return_value)
    with patch("weko_admin.utils.requests.put" , return_value=return_value):
        with patch("weko_admin.utils.requests.post" , return_value=return_value):
            with patch("weko_admin.utils.requests.delete" , return_value=return_value):
                with patch("weko_admin.utils.requests.get" , return_value=return_value):
                    with patch("invenio_oaiserver.receivers._new_percolator", return_value=""):

                        retVal1= OAISet(spec="1669370353014",name="index name" ,search_pattern="path[1669370353014]",system_created=False)
                        retVal2= OAISet(spec="1669959650594",name="index name" ,search_pattern="path[1669959650594]",system_created=False)
                        reindex_settings.session.add(retVal1)
                        reindex_settings.session.add(retVal2)
                        reindex_settings.session.commit()

                        assert 'completed' == reindex(True)

def test_reindex_raise(i18n_app,admin_settings):
    with patch("weko_admin.tasks.search_reindex" , side_effect=BaseException("test_error")):
        with pytest.raises(BaseException, match="test_error"):
            reindex(True)

    admin_setting = AdminSettings.get("elastic_reindex_settings", False)
    assert True == admin_setting.get('has_errored')
