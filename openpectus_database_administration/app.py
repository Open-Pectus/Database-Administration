import os
import secrets
from unittest import mock
import inspect
import uvicorn
from argparse import ArgumentParser
import logging

from sqlalchemy import create_engine
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin.contrib.sqla import Admin, ModelView
from starlette_admin.views import CustomView
with mock.patch.dict(
        'sys.modules',
        pint=mock.MagicMock(),  # Pint is not required here
        colorlog=mock.MagicMock(),  # Colorlog is not required here
        ):
    from openpectus.aggregator.data.database import json_serialize, json_deserialize
    from openpectus.aggregator.data.models import DBModel
    from openpectus.aggregator.data import models

from openpectus_database_administration.auth_provider import AzureAuthProvider


def get_arg_parser():
    parser = ArgumentParser("Start Database Administration")
    parser.add_argument("-host", "--host", required=False, default="127.0.0.1",
                        help="Host address to bind frontend and WebSocket to. Default: 127.0.0.1")
    parser.add_argument("-p", "--port", required=False, type=int, default=4200,
                        help="Host port to bind frontend and WebSocket to. Default: 4200")
    parser.add_argument("-db", "--database", required=True, type=str,
                        help="Path to Sqlite3 database.")
    return parser


def main():
    args = get_arg_parser().parse_args()
    assert os.path.isfile(args.database), f"Database file '{args.database}' does not exist."

    def index(request: Request) -> Response:
        return RedirectResponse(request.url_for("admin:index"))

    app = Starlette(
        routes=[
            Route(
                "/",
                index,
            )
        ],
    )

    auth_provider = None
    if os.environ.get("ENABLE_AZURE_AUTHENTICATION", "") == "true":
        auth_provider = AzureAuthProvider(required_roles=["Administrator",])

    admin = Admin(
        create_engine(
            f"sqlite:///{args.database}",
            echo=False,
            connect_args={"check_same_thread": False},
            json_serializer=json_serialize,
            json_deserializer=json_deserialize,
        ),
        title="Administration Panel",
        templates_dir=os.path.join(os.path.dirname(__file__), "templates"),
        statics_dir=os.path.join(os.path.dirname(__file__), "static"),
        favicon_url="/admin/statics/favicon.ico",
        logo_url="/admin/statics/icon-72dpi.png",
        auth_provider=auth_provider,
        middlewares=[
            Middleware(
                SessionMiddleware,
                secret_key=secrets.token_urlsafe(),
            )
        ],
        index_view=CustomView(
            label="Open Pectus Administration Panel",
            name="Home",
            template_path="index.html",
            methods=["GET",],
            add_to_menu=False,
        ),
    )

    # Discover models defined in Open Pectus project
    for model in [model for model in models.__dict__.values() if inspect.isclass(model) and issubclass(model, DBModel) and model is not DBModel]:
        admin.add_view(ModelView(model))

    admin.mount_to(app)
    print(f"Serving frontend at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level=logging.WARNING, forwarded_allow_ips="*", proxy_headers=True)


if __name__ == "__main__":
    main()
