from django.db import models


class Conversation(models.Model):
    """Una conversación = una sesión de chat. Sin usuario ni datos personales."""
    subject = models.CharField(max_length=120, blank=True)
    topic = models.CharField(max_length=120, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    context_text = models.TextField(blank=True)   # texto extraído del adjunto
    image_b64 = models.TextField(blank=True)      # imagen adjunta en base64
    image_type = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class Message(models.Model):
    ROLES = [("user", "user"), ("assistant", "assistant")]
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
