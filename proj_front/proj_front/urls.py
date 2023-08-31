"""proj_front URL Configuration

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
from django.conf import settings
from django.urls import include, path

from app_front.urls import DEBUG_URL_PATTERNS as app_front_urlpatterns_debug
from app_front.urls import URL_PATTERNS as app_front_urlpatterns

urlpatterns = [
    path("", include(app_front_urlpatterns)),
] + (
    [
        path("__debug__/app_front", include(app_front_urlpatterns_debug)),
    ]
    if settings.DEBUG
    else []
)
