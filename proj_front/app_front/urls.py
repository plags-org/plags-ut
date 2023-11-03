# pylint: disable=line-too-long
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView
from django.contrib.staticfiles.views import serve as serve_static
from django.urls import include, path
from django.views.decorators.cache import never_cache
from django.views.generic import RedirectView

# isort: off
# fmt: off
from app_front.views.home import HomeView
from app_front.views.not_available import view_not_available

from app_front.views.administration.data_migration import AdministrationDataMigrationView
from app_front.views.administration.system_email_setting import AdministrationEmailSettingView
from app_front.views.administration.send_mail_bulk import AdministrationSendMailBulkView
from app_front.views.administration.system_settings import view_administration_system_settings
from app_front.views.administration.version import AdministrationVersionView

from app_front.views.accounts.login import DefaultLoginView
from app_front.views.accounts.login_google_auth import LoginGoogleAuthView
from app_front.views.accounts.login_password_auth import LoginPasswordAuthView
from app_front.views.accounts.user_profile import AccountsProfileView
from app_front.views.accounts.loggedout import view_accounts_loggedout
from app_front.views.accounts.update_email import view_accounts_update_email
from app_front.views.accounts.update_password import AccountsPasswordUpdateView

from app_front.views.register.activate import RegisterActivateView

from app_front.views.transitory_user.list import TransitoryUserListView

from app_front.views.user.create import UserCreateView
from app_front.views.user.list import UserListView
from app_front.views.user.list_export_file import UserListExportFileView
from app_front.views.user.user_profile import UserProfileView
from app_front.views.user.reset_password_form import UserResetPasswordFormView
from app_front.views.user.reset_password_confirm import UserResetPasswordConfirmView
from app_front.views.user.update_email import UpdateEmailView

from app_front.views.organization.create import OrganizationCreateView
from app_front.views.organization.list import OrganizationListView
from app_front.views.organization.top import OrganizationTopView
from app_front.views.organization.course_edit import OrganizationCourseEditView
from app_front.views.organization.course_delete import OrganizationCourseDeleteView
from app_front.views.organization.course_user_list import OrganizationCourseUserListView
from app_front.views.organization.course_user_export import OrganizationCourseUserExportView

from app_front.views.organization_user.add_faculty import OrganizationUserAddFacultyView
from app_front.views.organization_user.change import OrganizationFacultyUserChangeView
from app_front.views.organization_user.kickout import OrganizationUserKickoutView

from app_front.views.course.create import CreateCourseView
from app_front.views.course.edit import EditCourseView, EditCourseDescriptionView
from app_front.views.course.top import CourseTopView
from app_front.views.course.register import CourseRegisterView

from app_front.views.course_top_notice_by_organization.list import CourseTopNoticeByOrganizationListView
from app_front.views.course_top_notice_by_organization.edit import CourseTopNoticeByOrganizationEditView

from app_front.views.course_user.add_faculty import CourseFacultyUserAddView
from app_front.views.course_user.add_student import CourseStudentUserAddView
from app_front.views.course_user.change import CourseFacultyUserChangeView, CourseStudentUserChangeView
from app_front.views.course_user.kickout import CourseUserKickoutView
from app_front.views.course_user.manage import CourseUserManageView
from app_front.views.course_user.lms_diff import CourseUserLMSDiffView
from app_front.views.course_user.export import view_course_user_export

from app_front.views.exercise.view import ExerciseViewView
from app_front.views.exercise.edit import ExerciseEditView

from app_front.views.submission_parcel.list import view_submission_parcel_list
from app_front.views.submission_parcel.view import SubmissionParcelView
from app_front.views.submission_parcel.download import view_submission_parcel_download

from app_front.views.submission.bulk_review import BulkReviewSubmissionView
from app_front.views.submission.dashboard import SubmissionDashboardView
from app_front.views.submission.list import ListSubmissionView
from app_front.views.submission.list_export import ListExportSubmissionView
from app_front.views.submission.list_export_file import ListExportFileSubmissionView
from app_front.views.submission.view import ViewSubmissionView
from app_front.views.submission.full_export import SubmissionFullExportView

from app_front.views.async_job.list import CourseAsyncJobListView
from app_front.views.operation_log.list import CourseFacultyOperationLogListView

from app_front.api.v0.course.get import api_course_get
from app_front.api.v0.exercise.get import api_exercise_get
from app_front.api.v0.submission.bulk_confirm import api_submission_bulk_confirm
from app_front.api.v0.submission.bulk_rejudge import api_submission_bulk_rejudge
from app_front.api.v0.submission.bulk_review import api_submission_bulk_review
from app_front.api.v0.submission.get import api_submission_get
from app_front.api.v0.submission.list_count import api_submission_list_count
from app_front.api.v0.submission_parcel.get import api_submission_parcel_get

from app_front.judge_reply.main import judge_reply_main

# for things that should be defined
import app_front.core.login_history     # noqa:F401 # pylint:disable=unused-import
import app_front.utils.template_util    # noqa:F401 # pylint:disable=unused-import
# isort: on

URL_PATTERNS = [
    path('', RedirectView.as_view(pattern_name='profile', permanent=False)),
    path('home/', HomeView.as_view(), name='home'),
    path('not_available/', view_not_available, name='not_available'),

    path('administration/data_migration/', AdministrationDataMigrationView.as_view(), name='administration/data_migration'),
    path('administration/system_email_setting/', AdministrationEmailSettingView.as_view(), name='administration/system_email_setting'),
    path('administration/send_mail_bulk/', AdministrationSendMailBulkView.as_view(), name='administration/send_mail_bulk'),
    path('administration/system_settings/', view_administration_system_settings, name='administration/system_settings'),
    path('administration/version/', AdministrationVersionView.as_view(), name='administration/version'),

    # path('plags_ut_admin/', admin.site.urls),
    path('accounts/login/', DefaultLoginView.as_view(), name='login'),
    path('accounts/login_google_auth/', LoginGoogleAuthView.as_view(), name='login_google_auth'),
    path('accounts/login_password_auth/', LoginPasswordAuthView.as_view(), name='login_password_auth'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    path('accounts/profile/', AccountsProfileView.as_view(), name='profile'),
    path('accounts/loggedout/', view_accounts_loggedout, name='loggedout'),
    path('accounts/update_email/', view_accounts_update_email, name='update_email'),
    path('accounts/update_password/', AccountsPasswordUpdateView.as_view(), name='update_password'),

    # user registration
    path('register/activate/', RegisterActivateView.as_view(), name='register/activate'),

    path('register/instructions/', RedirectView.as_view(pattern_name='profile', permanent=False)),
    path('register/instructions/o/<str:o_name>/c/<str:c_name>/', RedirectView.as_view(pattern_name='profile', permanent=False)),
    path('register/form/', RedirectView.as_view(pattern_name='profile', permanent=False)),
    path('register/form/o/<str:o_name>/c/<str:c_name>/', RedirectView.as_view(pattern_name='profile', permanent=False)),
    path('register/complete/', RedirectView.as_view(pattern_name='profile', permanent=False)),
    path('register/complete/o/<str:o_name>/c/<str:c_name>/', RedirectView.as_view(pattern_name='profile', permanent=False)),

    # transitory user
    path('list/transitory_user/', TransitoryUserListView.as_view(), name='transitory_user/list'),
    path('list/o/<str:o_name>/transitory_user/', TransitoryUserListView.as_view(), name='organization_manager/transitory_user/list'),

    # user
    path('create/user/', UserCreateView.as_view(), name='user/create'),
    path('create/o/<str:o_name>/user/', UserCreateView.as_view(), name='organization_manager/user/create'),
    path('activate/user/', RedirectView.as_view(pattern_name='register/activate', permanent=False), name='user/activate'),
    path('deactivate/user/', RedirectView.as_view(pattern_name='profile', permanent=False)),
    path('list/user/', UserListView.as_view(), name='user/list'),
    path('list_export_file/user/', UserListExportFileView.as_view(), name='user/list_export_file'),
    path('profile/u/<str:u_name>/user/', UserProfileView.as_view(), name='user/profile'),
    path('reset_password/form/user/', UserResetPasswordFormView.as_view(), name='user/reset_password/form'),
    path('reset_password/confirm/user/', UserResetPasswordConfirmView.as_view(), name='user/reset_password/confirm'),
    path('update_email/user/', UpdateEmailView.as_view(), name='user/update_email'),

    # organization
    path('create/organization/', OrganizationCreateView.as_view(), name='organization/create'),
    path('list/organization/', OrganizationListView.as_view(), name='organization/list'),
    path('top/o/<str:o_name>/organization/', OrganizationTopView.as_view(), name='organization/top'),
    path('o/<str:o_name>/course/edit', OrganizationCourseEditView.as_view(), name='organization/course/edit'),
    path('o/<str:o_name>/course/delete', OrganizationCourseDeleteView.as_view(), name='organization/course/delete'),
    path('o/<str:o_name>/course_user/list', OrganizationCourseUserListView.as_view(), name='organization/course_user/list'),
    path('o/<str:o_name>/course_user/export', OrganizationCourseUserExportView.as_view(), name='organization/course_user/export'),

    # organization + attribute
    path('add_faculty/o/<str:o_name>/organization_user/', OrganizationUserAddFacultyView.as_view(), name='organization_user/add_faculty'),
    path('change_faculty/o/<str:o_name>/organization_user/', OrganizationFacultyUserChangeView.as_view(), name='organization_user/change_faculty'),
    path('kickout/o/<str:o_name>/organization_user/', OrganizationUserKickoutView.as_view(), name='organization_user/kickout'),
    # path('list/o/<str:o_name>/organization_user/', view_organization_user_list, name='organization_user/list'),

    # course_concrete
    path('view/o/<str:o_name>/cc/<str:cc_name>/ch/<str:cc_hash>/', view_not_available, name='course_concrete/view'),

    # exercise_concrete
    path('view/o/<str:o_name>/ec/<str:ec_name>/eh/<str:ec_hash>/', view_not_available, name='exercise_concrete/view'),

    # course
    path('create/o/<str:o_name>/course/', CreateCourseView.as_view(), name='course/create'),
    path('edit/o/<str:o_name>/c/<str:c_name>/course/', EditCourseView.as_view(), name='course/edit'),
    path('edit/o/<str:o_name>/c/<str:c_name>/course/description/', EditCourseDescriptionView.as_view(), name='course/description_edit'),
    path('top/o/<str:o_name>/c/<str:c_name>/course/', CourseTopView.as_view(), name='course/top'),
    path('register/o/<str:o_name>/c/<str:c_name>/course/', CourseRegisterView.as_view(), name='course/register'),

    path('o/<str:o_name>/course_top_notice/list', CourseTopNoticeByOrganizationListView.as_view(), name='course_top_notice_by_organization/list'),
    path('o/<str:o_name>/course_top_notice/edit/<int:ctno_id>', CourseTopNoticeByOrganizationEditView.as_view(), name='course_top_notice_by_organization/edit'),

    # course + attribute
    path('add_student/o/<str:o_name>/c/<str:c_name>/course_user/', CourseStudentUserAddView.as_view(), name='course_user/add_student'),
    path('add_faculty/o/<str:o_name>/c/<str:c_name>/course_user/', CourseFacultyUserAddView.as_view(), name='course_user/add_faculty'),
    path('change_faculty/o/<str:o_name>/c/<str:c_name>/course_user/', CourseFacultyUserChangeView.as_view(), name='course_user/change_faculty'),
    path('change_student/o/<str:o_name>/c/<str:c_name>/course_user/', CourseStudentUserChangeView.as_view(), name='course_user/change_student'),
    path('kickout/o/<str:o_name>/c/<str:c_name>/course_user/', CourseUserKickoutView.as_view(), name='course_user/kickout'),
    path('manage/o/<str:o_name>/c/<str:c_name>/course_user/', CourseUserManageView.as_view(), name='course_user/manage'),
    path('lms_diff/o/<str:o_name>/c/<str:c_name>/course_user/', CourseUserLMSDiffView.as_view(), name='course_user/lms_diff'),
    path('export/o/<str:o_name>/c/<str:c_name>/course_user/', view_course_user_export, name='course_user/export'),

    # exercise
    path('crate/o/<str:o_name>/c/<str:c_name>/exercise/', view_not_available, name='exercise/create'),
    path('view/o/<str:o_name>/c/<str:c_name>/e/<str:e_name>/exercise/', ExerciseViewView.as_view(), name='exercise/view'),
    path('edit/o/<str:o_name>/c/<str:c_name>/e/<str:e_name>/exercise/', ExerciseEditView.as_view(), name='exercise/edit'),

    # submission parcel
    path('list/o/<str:o_name>/c/<str:c_name>/submission_parcel/', view_submission_parcel_list, name='submission_parcel/list'),
    path('view/o/<str:o_name>/c/<str:c_name>/sp/<str:sp_eb64>/submission_parcel/', SubmissionParcelView.as_view(), name='submission_parcel/view'),
    path('download/o/<str:o_name>/c/<str:c_name>/sp/<str:sp_eb64>/submission_parcel/', view_submission_parcel_download, name='submission_parcel/download'),

    # submission
    path('bulk_review/o/<str:o_name>/c/<str:c_name>/submission/', BulkReviewSubmissionView.as_view(), name='submission/bulk_review'),
    path('dashboard/o/<str:o_name>/c/<str:c_name>/submission/', SubmissionDashboardView.as_view(), name='submission/dashboard'),
    path('list/o/<str:o_name>/c/<str:c_name>/submission/', ListSubmissionView.as_view(), name='submission/list'),
    path('list_export/o/<str:o_name>/c/<str:c_name>/submission/', ListExportSubmissionView.as_view(), name='submission/list_export'),
    path('list_export_file/o/<str:o_name>/c/<str:c_name>/submission/', ListExportFileSubmissionView.as_view(), name='submission/list_export_file'),
    path('view/o/<str:o_name>/c/<str:c_name>/s/<str:s_eb64>/submission/', ViewSubmissionView.as_view(), name='submission/view'),
    path('full_export/o/<str:o_name>/c/<str:c_name>/e/<str:e_name>/submission/', SubmissionFullExportView.as_view(), name='submission/full_export'),

    path('list/o/<str:o_name>/c/<str:c_name>/operation_log/course_faculty/', CourseFacultyOperationLogListView.as_view(), name='operation_log/course_faculty/list'),
    path('list/o/<str:o_name>/c/<str:c_name>/course/async_job/', CourseAsyncJobListView.as_view(), name='course/async_job/list'),

    # path('extension/ex/<str:x_name>/o/<str:o_name>/organization/', view_not_available, name='extension/organization'),
    # path('extension/ex/<str:x_name>/o/<str:o_name>/c/<str:c_name>/course/', view_extension_of_course, name='extension/course'),
    # path('extension/ex/<str:x_name>/o/<str:o_name>/c/<str:c_name>/e/<str:e_name>/exercise/', view_extension_of_exercise, name='extension/exercise'),

    # Web API for web clients
    path('api/v0/o/<str:o_name>/c/<str:c_name>/course/get/', api_course_get),
    path('api/v0/o/<str:o_name>/c/<str:c_name>/exercise/get/', api_exercise_get),
    path('api/v0/o/<str:o_name>/c/<str:c_name>/submission/bulk_confirm/', api_submission_bulk_confirm),
    path('api/v0/o/<str:o_name>/c/<str:c_name>/submission/bulk_rejudge/', api_submission_bulk_rejudge),
    path('api/v0/o/<str:o_name>/c/<str:c_name>/submission/bulk_review/', api_submission_bulk_review),
    path('api/v0/o/<str:o_name>/c/<str:c_name>/submission/get/', api_submission_get),
    path('api/v0/o/<str:o_name>/c/<str:c_name>/submission/list_count/', api_submission_list_count),
    path('api/v0/o/<str:o_name>/c/<str:c_name>/submission_parcel/get/', api_submission_parcel_get),

    # HTTP API for judge reply
    path('judge_reply/v0/', judge_reply_main),
]
# fmt: on

# static files (necessary when deploying with uvicorn + asgi)
# cf. <https://stackoverflow.com/questions/61770551/how-to-run-django-with-uvicorn-webserver>
if settings.DEBUG:
    static_url_patterns = static(
        settings.STATIC_URL,
        # NOTE ローカルでキャッシュされると *.(css|js) への変更が即反映されなくて辛い
        view=never_cache(serve_static),
        # document_root=settings.STATIC_ROOT,
    )
    assert static_url_patterns
    URL_PATTERNS.append(static_url_patterns[0])


DEBUG_URL_PATTERNS = []

if settings.DEBUG:
    import debug_toolbar

    DEBUG_URL_PATTERNS = [
        path("/", include(debug_toolbar.urls)),
    ]
