from tornado import web
from tornado.log import app_log


class BaseHandler(web.RequestHandler):
    @property
    def log(self):
        return self.settings.get('log', app_log)

    def render_template(self, name, **ns):
        template_ns = {}
        template_ns.update(self.template_namespace)
        template_ns["xsrf_token"] = self.xsrf_token.decode("ascii")
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
            no_spawner_check=True
        )
        return ns

