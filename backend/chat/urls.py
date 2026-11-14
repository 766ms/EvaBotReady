from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/csrf/", views.csrf, name="csrf"),
    path("api/setup/", views.setup, name="setup"),
    path("api/upload/", views.upload_file, name="upload"),
    path("api/chat/", views.chat, name="chat"),
    path("api/reset/", views.reset, name="reset"),
    path("api/transcribe/", views.transcribe, name="transcribe"),
    path("api/tts/", views.speak, name="speak"),
    path("api/live/token/", views.live_token, name="live_token"),
    path("api/live/save/", views.live_save, name="live_save"),
]
