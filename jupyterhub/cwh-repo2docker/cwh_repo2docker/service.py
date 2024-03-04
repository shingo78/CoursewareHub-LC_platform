import json
import os
from urllib.parse import urlparse

from tornado import web
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

from traitlets import Unicode
from traitlets.config import Application, catch_config_error

from jupyterhub.services.auth import HubOAuthCallbackHandler, HubOAuthenticated
from jupyterhub.utils import url_path_join
from jupyterhub.handlers.static import CacheControlStaticFilesHandler
from jupyterhub._data import DATA_FILES_PATH

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PrefixLoader

from .builder import BuildHandler, DefaultCourseImageHandler
from .registry import get_registry, split_image_name
from .images import ImagesHandler
from .logs import LogsHandler


class CwhRepo2DockerApplication(Application):

    config_file = Unicode(
        '/srv/jupyterhub/cwh_repo2docker_config.py',
        help="The config file to load").tag(
        config=True
    )
    aliases = {
        "config-file": "CwhRepo2DockerApplication.config_file"
    }

    @catch_config_error
    async def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)

        self.load_config_file(self.config_file)

    async def start(self):
        self.io_loop = loop = IOLoop.current()

        base_url = os.environ['JUPYTERHUB_BASE_URL']

        jupyterhub_template_path = os.path.join(DATA_FILES_PATH, 'templates')
        template_path = os.path.join(os.path.dirname(__file__), "templates")
        jupyterhub_static_path = os.path.join(DATA_FILES_PATH, 'static')
        static_path = os.path.join(os.path.dirname(__file__), "static")

        template_paths = [
            jupyterhub_template_path,
            template_path
        ]

        jinja_options = dict(autoescape=True, enable_async=True)
        loader = ChoiceLoader(
            [
                PrefixLoader({'templates': FileSystemLoader([jupyterhub_template_path])}, '/'),
                FileSystemLoader(template_paths),
            ]
        )
        jinja_env = Environment(loader=loader, **jinja_options)

        service_prefix = os.environ['JUPYTERHUB_SERVICE_PREFIX']

        self.tornado_settings = {
            'config': self.config,
            'base_url': base_url,
            'jinja2_env': jinja_env,
            'static_path': jupyterhub_static_path,
            'static_url_prefix': url_path_join(base_url, 'static/'),
            'service_prefix': service_prefix,
        }

        self.tornado_application = web.Application(
            [
                (service_prefix, ImagesHandler),
                (url_path_join(service_prefix, 'oauth_callback'),
                    HubOAuthCallbackHandler),
                (url_path_join(service_prefix, 'api/environments'),
                    BuildHandler),
                (url_path_join(
                    service_prefix, 'api/environments/default-course-image'),
                    DefaultCourseImageHandler),
                (url_path_join(
                    service_prefix, r'api/environments/([^/]+)/logs'),
                    LogsHandler),
                (url_path_join(service_prefix, r"static/(.*)"),
                    web.StaticFileHandler,
                    {
                        "path": os.path.join(os.path.dirname(__file__), "static")
                    }
                 )
            ],
            self.tornado_settings,
            cookie_secret=os.urandom(32),
        )

        self.http_server = HTTPServer(self.tornade_application)

        url = urlparse(os.environ['JUPYTERHUB_SERVICE_URL'])
        self.http_server.listen(url.port, url.hostname)

    def stop(self):
        if not self.io_loop:
            return
        if self.http_server:
            self.http_server.stop()

    async def launch_instance_async(self, argv=None):
        try:
            await self.initialize(argv)
            await self.start()
        except Exception as e:
            self.log.exception("")
            self.exit(1)


def main():
    app = CwhRepo2DockerApplication()

    loop = IOLoop(make_current=False)

    try:
        loop.run_sync(app.launch_instance_async)
    except Exception:
        loop.close()
        raise

    try:
        loop.start()
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        loop.stop()
        loop.close()


if __name__ == '__main__':
    main()
