from django.urls import re_path
from sabil.views import TableauConsumer
from sabil.views import BroadcastConsumer

websocket_urlpatterns = [
    re_path(
        r'ws/tableau/(?P<classe_id>[^/]+)/(?P<seance_id>[^/]+)/$',
        TableauConsumer.as_asgi()
    ),
    re_path(
        r'ws/session/(?P<channel>[\w-]+)/(?P<classe_id>[^/]+)/(?P<seance_id>[^/]+)/$',
        BroadcastConsumer.as_asgi()
    ),
]
