import aiohttp
import asyncio
import json

from textwrap import dedent
from traitlets import (
    Unicode,
    Bool
)
from traitlets.config import SingletonConfigurable

CONTENT_TYPE_MANIFEST_V2_2 = 'application/vnd.docker.distribution.manifest.v2+json'


def get_registry(*args, **kwargs):
    return Registry.instance(*args, **kwargs)


async def _get_manifest(session, url, name, ref):
    headers = {
        'Accept': CONTENT_TYPE_MANIFEST_V2_2
    }
    async with session.get(
            f'{url}/v2/{name}/manifests/{ref}',
            headers=headers) as resp:
        manifest = await resp.json()
        return {
            'name': name,
            'reference': ref,
            'digest': resp.headers['Docker-Content-Digest'],
            'data': manifest
        }


async def _put_manifest(session, url, name, ref, manifest):
    headers = {
        'Content-Type': CONTENT_TYPE_MANIFEST_V2_2
    }
    async with session.put(
            f'{url}/v2/{name}/manifests/{ref}',
            json=manifest,
            headers=headers) as resp:
        return await resp.json()


async def _get_tags(session, url, repo):
    async with session.get(f'{url}/v2/{repo}/tags/list') as resp:
        return await resp.json()


async def _get_repos(session, url):
    async with session.get(f'{url}/v2/_catalog') as resp:
        return await resp.json()


async def _get_blob(session, url, repo, digest):
    async with session.get(
            f'{url}/v2/{repo}/blobs/{digest}') as resp:
        return await resp.read()


async def _get_config(session, url, repo, ref, manifest):
    config_digest = manifest['data']['config']['digest']
    config_blob = await _get_blob(
        session, url, repo, config_digest)
    config = json.loads(config_blob)
    return {
        'name': repo,
        'reference': ref,
        'manifest': manifest,
        'data': config,
        'digest': config_digest
    }


async def _delete_blob(session, url, repo, digest):
    async with session.delete(f'{url}/v2/{repo}/blobs/{digest}') as resp:
        await resp.read()


def _split_image_name(name, default_tag):
    sep = name.rfind(':')
    if sep < 0 or len(name) - 1 <= sep:
        return (name, default_tag)
    return (name[:sep], name[sep+1:])


def short_id(id):
    sep = id.split(':')
    return id[sep+1:sep+13]


class Registry(SingletonConfigurable):
    """
    Docker registry client to manage course images.
    """

    host = Unicode(
        config=True,
        allow_none=False,
        help=dedent(
            """
            Host name of registry server.
            e.g. `localhost:5000`
            """
        )
    )

    username = Unicode(
        config=True,
        allow_none=False,
        help=dedent(
            """
            Username of registry
            """
        )
    )

    password = Unicode(
        config=True,
        allow_none=False,
        help=dedent(
            """
            Password of registry
            """
        )
    )

    insecure = Bool(
        False,
        config=True,
        help=dedent(
            """
            Use HTTP instead of HTTPS.
            Default is False.
            """
        )
    )

    default_course_image = Unicode(
        'coursewarehub/default-course-image:latest',
        config=True,
        help="""
        Name of default course image, excluding registry host name
        """
    )

    initial_course_image = Unicode(
        'coursewarehub/initial-course-image:latest',
        config=True,
        help="""
        Name of initial course image, excluding registry host name
        """
    )

    def __init__(self, *args, **kwargs):
        super(Registry, self).__init__(*args, **kwargs)

        self.log.debug('Registry host: %s', self.host)
        self.log.debug('Registry user: %s', self.username)
        self.log.debug('default_course_image: %s',
                       self.default_course_image)
        self.log.debug('initial_course_image: %s',
                       self.initial_course_image)

    def _get_registry_url(self):
        scheme = 'https' if not self.insecure else 'http'
        return f'{scheme}://{self.host}'

    def _get_auth(self):
        return aiohttp.BasicAuth(self.username, self.password)

    def get_default_course_image(self):
        host = self.host
        name = self.default_course_image
        return f'{host}/{name}'

    def get_default_course_image_name(self):
        sep = self.default_course_image.rfind(':')
        if sep < 0:
            return self.default_course_image
        return self.default_course_image[:sep]

    def get_default_course_image_tag(self):
        sep = self.default_course_image.rfind(':')
        if sep < 0 or len(self.default_course_image) - 1 <= sep:
            return 'latest'
        return self.default_course_image[sep+1:]

    async def list_images(self):
        images = []
        async with aiohttp.ClientSession(auth=self._get_auth()) as session:
            url = self._get_registry_url()
            self.log.debug('registry host=%s, registry url=%s', self.host, url)
            repos_dict = await _get_repos(session, url)
            repo_names = repos_dict['repositories']

            tasks = []
            for name in repo_names:
                tasks.append(asyncio.ensure_future(
                    _get_tags(session, url, name)))

            taginfos = await asyncio.gather(*tasks)
            repos = []
            for taginfo in taginfos:
                name = taginfo['name']
                tags = taginfo['tags']
                for tag in tags:
                    repos.append((name, tag))

            tasks = []
            for name, tag in repos:
                tasks.append(asyncio.ensure_future(
                        _get_manifest(session, url, name, tag)))
            manifests = await asyncio.gather(*tasks)

            tasks = []
            for manifest in manifests:
                name = manifest['name']
                ref = manifest['reference']
                tasks.append(asyncio.ensure_future(
                    _get_config(session, url, name, ref, manifest)))
            configs = await asyncio.gather(*tasks)

            default_course_image = None
            initial_course_image = None
            for config in configs:
                labels = config.get('data', {}).get('Labels', {})
                if 'cwh_repo2docker.image_name' not in labels:
                    continue
                name = config['name']
                ref = config['reference']
                image_name = f'{name}:{ref}'
                if self.default_course_image == image_name:
                    default_course_image = config['digest']
                elif self.initial_course_image == image_name:
                    initial_course_image = {
                        "repo": '-',
                        "ref": '-',
                        "image_name": name,
                        "display_name": 'initial',
                        "default_course_image": False,
                        "image_id": config['digest'],
                        "short_image_id": short_id(config['digest']),
                        "status": "-"
                    }
                elif (name == labels["repo2docker.repo"] and
                        ref == labels["repo2docker.ref"]):
                    images.append({
                        "repo": labels["repo2docker.repo"],
                        "ref": labels["repo2docker.ref"],
                        "image_name": labels["cwh_repo2docker.image_name"],
                        "display_name": labels["cwh_repo2docker.display_name"],
                        "default_course_image": False,
                        "image_id": config['digest'],
                        "short_image_id": short_id(config['digest']),
                        "status": "built"
                    })

            if default_course_image:
                for image in images:
                    if image['image_id'] == default_course_image:
                        image['default_course_image'] = True

            if initial_course_image:
                images.append(initial_course_image)

            return images

    async def delete(self, name, ref):
        async with aiohttp.ClientSession(auth=self._get_auth()) as session:
            url = self._get_registry_url()

            manifest = await _get_manifest(session, url, name, ref)
            manifest_digest = manifest['digest']

            async with session.delete(
                    f'{url}/v2/{name}/manifests/{manifest_digest}') as resp:
                await resp.json()

            tasks = []
            config = manifest['config']
            tasks.append(asyncio.ensure_future(
                _delete_blob(session, url, name, config['digest'])))

            layers = manifest['layers']
            for layer in layers:
                tasks.append(asyncio.ensure_future(
                    _delete_blob(session, url, name, layer['digest'])))

            await asyncio.gather(*tasks)

    async def set_default_course_image(self, name, ref):
        new_name, new_ref = _split_image_name(self.default_course_image)
        return await self.set_name_tag(
            new_name, new_ref, name, ref)

    async def set_name_tag(self, new_name, new_tag, src_name, src_tag):
        async with aiohttp.ClientSession(auth=self._get_auth()) as session:
            url = self._get_registry_url()

            manifest = await _get_manifest(session, url, src_name, src_tag)

            return await _put_manifest(
                session,
                url,
                new_name, new_tag,
                manifest['manifest'])
