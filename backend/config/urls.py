from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("", include("chat.urls")),
]

if settings.DEBUG:  # sirve CSS y fuentes en desarrollo (con uvicorn)
    urlpatterns += staticfiles_urlpatterns()
