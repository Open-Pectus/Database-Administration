import os
import re
from typing import Any

import requests
import msal
import jwt
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route
from starlette_admin import BaseAdmin
from starlette_admin.auth import (
    AdminUser,
    AuthProvider,
    login_not_required,
)


FLOW_SESSION_KEY = "_FLOW"
REDIRECT_SESSION_KEY = "_REDIRECT"
use_auth = os.getenv("ENABLE_AZURE_AUTHENTICATION", default="").lower() == "true"
tenant_id = os.getenv("AZURE_DIRECTORY_TENANT_ID", default=None)
client_id = os.getenv("AZURE_APPLICATION_CLIENT_ID", default=None)
client_secret = os.getenv("AZURE_CLIENT_SECRET", default=None)
authority_url = f"https://login.microsoftonline.com/{tenant_id}" if tenant_id else None
jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys" if tenant_id else ""

if use_auth:
    assert tenant_id is not None, "Assign Tenant ID to environment variable AZURE_DIRECTORY_TENANT_ID"
    assert client_id is not None, "Assign Client ID to environment variable AZURE_APPLICATION_CLIENT_ID"
    assert client_secret is not None, "Assign Client Secret to environment variable AZURE_CLIENT_SECRET"

jwks_client = jwt.PyJWKClient(jwks_url)

photo_cache: dict[str, requests.Response] = dict()


def decode_token(x_identity: None | str) -> dict[str, Any] | None:
    assert authority_url
    if x_identity is None:
        return None
    try:
        return jwt.decode(
            x_identity,
            jwks_client.get_signing_key_from_jwt(x_identity).key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=authority_url+"/v2.0"
        )
    except jwt.PyJWTError:
        pass


def get_initials(user: dict[str, Any]) -> str:
    m = re.match(r"(?P<initials>.{2,4}) \((?P<name>.*?)\)", user["name"])
    if m:
        return m.groupdict()["initials"].upper()
    else:
        return user["name"]


class AzureAuthProvider(AuthProvider):
    def __init__(self, *args, **kwargs):
        self.required_roles: list[str] = kwargs.pop("required_roles", [])
        super().__init__(*args, **kwargs)

    async def is_authenticated(self, request: Request) -> bool:
        user = decode_token(request.session.get("X-Identity", None))
        return user is not None

    def get_admin_user(self, request: Request) -> AdminUser | None:
        user = decode_token(request.session.get("X-Identity", None))
        if user is None:
            return None
        user_initials = get_initials(user)
        return AdminUser(username=user_initials, photo_url=str(request.url_for(f"{self.admin.route_name}:photo")))

    async def render_login(self, request: Request, admin: BaseAdmin) -> Response:
        if "login" in request.query_params:
            login = self.msal.initiate_auth_code_flow(
                [f"{client_id}/.default",],
                redirect_uri=str(request.url_for(f"{self.admin.route_name}:msal_callback")),
            )
            request.session[FLOW_SESSION_KEY] = login
            request.session[REDIRECT_SESSION_KEY] = request.query_params.get("next", str(request.url_for(f"{self.admin.route_name}:index")))
            return RedirectResponse(login["auth_uri"])
        else:
            return admin.templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"_is_login_path": True},
            )

    async def render_logout(self, request: Request, admin: BaseAdmin) -> Response:
        del request.session["X-Identity"]
        return RedirectResponse(request.url_for(f"{self.admin.route_name}:index"))

    @login_not_required
    async def handle_auth_callback(self, request: Request) -> Response:
        login: dict[str, Any] = self.msal.acquire_token_by_auth_code_flow(
            request.session.get(FLOW_SESSION_KEY, {}),
            dict(request.query_params),
        )
        if "error" in login:
            return self.admin.templates.TemplateResponse(
                request=request,
                name="login_denied.html",
            )

        assert "id_token_claims" in login
        user: dict[str, Any] = login.get("id_token_claims", {})
        if not any(role in user.get("roles", []) for role in self.required_roles):
            user_initials = get_initials(user)
            return self.admin.templates.TemplateResponse(
                request=request,
                name="login_denied_missing_roles.html",
                context={
                    "initials": user_initials,
                    "roles": user["roles"],
                    "required_roles": self.required_roles,
                },
            )

        redirect_url = request.session.get(REDIRECT_SESSION_KEY, str(request.url_for(f"{self.admin.route_name}:index")))
        # Clear session keys used in login flow
        request.session.pop(FLOW_SESSION_KEY, None)
        request.session.pop(REDIRECT_SESSION_KEY, None)
        # Save id_token in session
        request.session["X-Identity"] = login.get("id_token")
        return RedirectResponse(redirect_url)

    async def handle_photo(self, request: Request) -> Response:
        user = self.get_admin_user(request)
        assert user
        if user.username in photo_cache:
            photo = photo_cache.get(user.username)
        else:
            token_request = self.msal.acquire_token_on_behalf_of(
                request.session["X-Identity"],
                [],  # Scopes
            )
            photo = requests.get(
                "https://graph.microsoft.com/beta/me/photos/48x48/$value",
                headers={"Authorization": f"Bearer {token_request["access_token"]}"}
            )
            photo_cache[user.username] = photo
        assert isinstance(photo, requests.Response)
        return Response(
            photo.content,
            media_type=photo.headers["content-type"]
        )

    def setup_admin(self, admin: BaseAdmin):
        super().setup_admin(admin)
        admin.routes.append(
            Route(
                "/msal",
                self.handle_auth_callback,
                methods=["GET"],
                name="msal_callback",
            )
        )
        admin.routes.append(
            Route(
                "/photo",
                self.handle_photo,
                methods=["GET"],
                name="photo",
            )
        )
        self.msal = msal.ConfidentialClientApplication(
            client_id,
            authority=authority_url,
            client_credential=client_secret,
        )
        self.admin = admin
