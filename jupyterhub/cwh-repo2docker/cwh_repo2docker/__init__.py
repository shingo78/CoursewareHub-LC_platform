import os

from coursewareuserspawner import CoursewareUserSpawner
from jinja2 import Environment, BaseLoader
from jupyterhub.handlers.static import CacheControlStaticFilesHandler
from traitlets import Unicode

from .builder import BuildHandler
from .registry import get_registry, split_image_name
from .images import ImagesHandler, DefaultCouseImageHandler
from .logs import LogsHandler


class Repo2DockerSpawner(CoursewareUserSpawner):
    """
    A custom spawner for using Docker images built with cwh-repo2docker.
    """
    
    image_form_template = Unicode(
        """
        <style>
            #image-list {
                max-height: 600px;
                overflow: auto;
            }
            .image-info {
                font-weight: normal;
            }
        </style>
        <div class='form-group' id='image-list'>
        {% for image in image_list %}
        <label for='image-item-{{ loop.index0 }}' class='form-control input-group'>
            <div class='col-md-1'>
                <input type='radio' name='image' id='image-item-{{ loop.index0 }}' value='{{ registry_host }}/{{ image.image_name }}' />
            </div>
            <div class='col-md-11'>
                <strong>{{ image.display_name }}</strong>
                <div class='row image-info'>
                    <div class='col-md-4'>
                        Repository:
                    </div>
                    <div class='col-md-8'>
                        <a href="{{ image.repo }}" target="_blank">{{ image.repo }}</a>
                    </div>
                </div>
                <div class='row image-info'>
                    <div class='col-md-4'>
                        Reference:
                    </div>
                    <div class='col-md-8'>
                        <a href="{{ image.repo }}/tree/{{ image.ref }}" target="_blank">{{ image.ref }}</a>
                    </div>
                </div>
            </div>
        </label>
        {% endfor %}
        </div>
        """,
        config=True,
        help="""
        Jinja2 template for constructing the list of images shown to the user.
        """,
    )

    async def get_options_form(self):
        """
        Override the default form to handle the case when there is only one image.
        """
        registry = get_registry(parent=self)
        images = await registry.list_images()

        if not self.user.admin:
            self._use_default_course_image(images)
            return ''

        if len(images) <= 1:
            self._use_initial_course_image(images)
            return ''

        image_form_template = Environment(loader=BaseLoader).from_string(
            self.image_form_template
        )
        return image_form_template.render(image_list=images, registry_host=registry.host)

    def _use_default_course_image(self, images):
        registry = get_registry(parent=self)

        self.image = registry.get_default_course_image()

        default_course_images = [i for i in images if i['default_course_image']]
        if not default_course_images:
            self._use_initial_course_image(images)
            return
        self.cmd = default_course_images[0]['cmd']

    def _use_initial_course_image(self, images):
        registry = get_registry(parent=self)

        self.image = registry.get_initial_course_image()

        initial_course_images = [i for i in images if i['initial_course_image']]
        if not initial_course_images:
            raise RuntimeError("Initial course image NOT found")
        self.cmd = initial_course_images[0]['cmd']

    async def get_command(self):
        """get command from registry instead of local image."""

        if self.cmd:
            cmd = self.cmd
        else:
            parts = self.image.split('/', 1)
            if len(parts) == 2:
                host, image_name = parts
            else:
                host, image_name = ('', parts[0])

            registry = get_registry(parent=self)
            if host == registry.host:
                name, ref = split_image_name(image_name)
                config = await registry.inspect_image(name, ref)
                cmd = config['data']['config']['Cmd']
            else:
                image_info = await self.docker("inspect_image", self.image)
                cmd = image_info["Config"]["Cmd"]
        return cmd + self.get_args()

    async def create_object(self, *args, **kwargs):
        registry = get_registry(parent=self)
        self.docker(
            'login',
            username=registry.username,
            password=registry.password,
            registry=registry.get_registry_url())
        return await super().create_object(*args, **kwargs)



def cwh_repo2docker_jupyterhub_config(c):
    # hub
    c.JupyterHub.spawner_class = Repo2DockerSpawner

    # add extra templates for the service UI
    c.JupyterHub.template_paths.insert(
        0, os.path.join(os.path.dirname(__file__), "templates")
    )

    # register the handlers to manage the user images
    c.JupyterHub.extra_handlers.extend(
        [
            (r"environments", ImagesHandler),
            (r"api/environments", BuildHandler),
            (r"api/environments/default-course-image", DefaultCouseImageHandler),
            (r"api/environments/([^/]+)/logs", LogsHandler),
            (
                r"environments-static/(.*)",
                CacheControlStaticFilesHandler,
                {"path": os.path.join(os.path.dirname(__file__), "static")},
            ),
        ]
    )

