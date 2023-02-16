from inspect import isawaitable
from jupyterhub.handlers.base import BaseHandler
from jupyterhub.scopes import needs_scope
from tornado import web

from .docker import list_containers
from .registry import get_registry

class ImagesHandler(BaseHandler):
    """
    Handler to show the list of environments as Docker images
    """

    @web.authenticated
    @needs_scope('admin-ui')
    async def get(self):
        images = await get_registry(parent=self).list_images()
        containers = await list_containers()
        result = self.render_template(
            "images.html",
            images=images + containers
        )
        if isawaitable(result):
            self.write(await result)
        else:
            self.write(result)


class DefaultCouseImageHandler(BaseHandler):
    """
    Handler to update the default course image
    """

    @web.authenticated
    @needs_scope('admin-ui')
    async def post(self):
        repo = self.get_body_argument('repo')
        ref = self.get_body_argument('ref')

        get_registry(parent=self).set_default_course_image(repo, ref)
        

