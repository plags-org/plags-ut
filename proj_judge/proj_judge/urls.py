"""proj_judge URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# from django.contrib import admin
from django.urls import path, include

from app_judge.api.exercise_concrete.exists import api_exercise_concrete_exists
from app_judge.api.exercise_concrete.upload import api_exercise_concrete_upload
from app_judge.api.exercise_concrete.setting.validate import api_exercise_concrete_setting_validate
from app_judge.api.submission.submit import api_submission_submit
from app_judge.api.submission.result import api_submission_result


urlpatterns = [
    # System Management
    # path('admin/', admin.site.urls),
    path('django-rq/', include('django_rq.urls')),

    # API
    path('api/exercise_concrete/exists/', api_exercise_concrete_exists),
    path('api/exercise_concrete/upload/', api_exercise_concrete_upload),
    path('api/exercise_concrete/setting/validate/', api_exercise_concrete_setting_validate),

    # Submission / Result getting
    path('api/submission/submit/', api_submission_submit),
    path('api/submission/result/', api_submission_result),
]
