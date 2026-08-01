from django.urls import re_path
from sabil.views import TableauConsumer

websocket_urlpatterns = [
    re_path(
        r'ws/tableau/(?P<classe_id>[^/]+)/(?P<seance_id>[^/]+)/$',
        TableauConsumer.as_asgi()
    ),
]