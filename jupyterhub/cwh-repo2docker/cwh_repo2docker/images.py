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

    def render_template(self, name, **ns):
        template_ns = {}
        template_ns.update(self.template_namespace)
        template_ns.update(ns)
        template = self.settings['jinja2_env'].get_template(name)
        return template.render_async(**template_ns)

    @property
    def template_namespace(self):
        user = self.current_user
        ns = dict(
            base_url=self.settings['base_url'],
            prefix=self.settings['base_url'],
            user=user,
            #login_url=self.settings['login_url'],
            #login_service=self.authenticator.login_service,
            #logout_url=self.settings['logout_url'],
            static_url=self.static_url,
            #version_hash=self.version_hash,
            #services=self.get_accessible_services(user),
            #parsed_scopes=self.parsed_scopes,
            #expanded_scopes=self.expanded_scopes,
            service_prefix=self.settings['service_prefix']
        )
        return ns

