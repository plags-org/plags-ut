"""
ASGI config for proj_front project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/asgi/

---

- usage:
  - (pre-condition): `source ../venv_proj_front/.venv/bin/activate`
  - production: `python -m uvicorn proj_front.asgi:application`
  - development: `python -m uvicorn proj_front.asgi:application --port 8041 --reload`
  - development (docker): `python -m uvicorn proj_front.asgi:application --host 0.0.0.0 --port 8041 --reload`
"""  # noqa:E501
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings
from django.core.asgi import get_asgi_application
from django.urls import re_path
from strawberry.channels import GraphQLHTTPConsumer, GraphQLWSConsumer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "proj_front.settings")

_django_application = get_asgi_application()

# Import your Strawberry schema after creating the django ASGI application
# This ensures django.setup() has been called before any ORM models are imported
# for the schema.
# cf. <https://strawberry.rocks/docs/integrations/channels>
# pylint:disable=wrong-import-position
from app_front.graphql.main import schema as graphql_schema  # noqa:E402

_graphql_ws_consumer = GraphQLWSConsumer.as_asgi(schema=graphql_schema)
_websocket_urlpatterns = [
    re_path(r"graphql", _graphql_ws_consumer),
]

_graphql_http_consumer = AuthMiddlewareStack(
    GraphQLHTTPConsumer.as_asgi(schema=graphql_schema, graphiql=settings.DEBUG)
)
application = ProtocolTypeRouter(
    {
        "http": URLRouter(
            [
                re_path("^graphql", _graphql_http_consumer),
                re_path("^", _django_application),
            ]
        ),
        "websocket": AuthMiddlewareStack(URLRouter(_websocket_urlpatterns)),
    }
)
