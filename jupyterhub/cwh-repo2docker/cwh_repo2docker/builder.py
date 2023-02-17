import json
import re

from aiodocker import Docker, DockerError
from jupyterhub.apihandlers import APIHandler
from jupyterhub.scopes import needs_scope
from tornado import web

from .docker import build_image
from .registry import get_registry

IMAGE_NAME_RE = r"^[a-z0-9-_]+$"


class BuildHandler(APIHandler):
    """
    Handle requests to build user environments as Docker images
    """

    @web.authenticated
    @needs_scope('admin-ui')
    async def delete(self):
        data = self.get_json_body()
        name = data["name"]
        async with Docker() as docker:
            try:
                await docker.images.delete(name)
            except DockerError as e:
                raise web.HTTPError(e.status, e.message)

        self.set_status(200)
        self.finish(json.dumps({"status": "ok"}))

    @web.authenticated
    @needs_scope('admin-ui')
    async def post(self):
        data = self.get_json_body()
        repo = data["repo"]
        ref = data["ref"]
        name = data["name"].lower()
        buildargs = data.get("buildargs", None)
        username = data.get("username", None)
        password = data.get("password", None)

        if not repo:
            raise web.HTTPError(400, "Repository is empty")

        if name and not re.match(IMAGE_NAME_RE, name):
            raise web.HTTPError(
                400,
                f"The name of the environment is restricted to the following characters: {IMAGE_NAME_RE}",
            )

        extra_buildargs = []
        if buildargs:
            for barg in buildargs.split("\n"):
                if "=" not in barg:
                    raise web.HTTPError(
                        400,
                        "Invalid build argument format"
                    )
                extra_buildargs.append(barg)

        registry = get_registry(parent=self)

        await build_image(registry.host, repo, ref, name, username, password, extra_buildargs)

        self.set_status(200)
        self.finish(json.dumps({"status": "ok"}))