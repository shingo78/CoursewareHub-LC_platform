from inspect import isawaitable
from jupyterhub.services.auth import HubOAuthenticated
from jupyterhub.scopes import needs_scope
from tornado import web
from tornado.log import app_log
import json

from .docker import list_containers
from .registry import get_registry
from .base import BaseHandler


class ImagesHandler(HubOAuthenticated, BaseHandler):
    """
    Handler to show the list of environments as Docker images
    """

    @web.authenticated
    #@needs_scope('admin-ui')
    async def get(self):
        app_log.debug("tornado settings=%s", self.settings)
        registry = get_registry(config=self.settings['config'])
        images = await registry.list_images()
        containers = await list_containers()
        result = self.render_template(
            "images.html",
            images=images + containers
        )
        self.write(await result)

