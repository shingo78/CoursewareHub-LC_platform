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
            f'{url}{name}/manifests/{ref}',
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
            f'{url}{name}/manifests/{ref}',
            json=manifest,
            headers=headers) as resp:
        return await resp.json()


async def _get_tags(session, url, repo):
    async with session.get(f'{url}{repo}/tags/list') as resp:
        return await resp.json()


async def _get_repos(session, url):
    async with session.get(f'{url}_catalog') as resp:
        return await resp.json()


async def _get_blob(session, url, repo, digest):
    async with session.get(
            f'{url}{repo}/blobs/{digest}') as resp:
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
    async with session.delete(f'{url}{repo}/blobs/{digest}') as resp:
        await resp.read()


def split_image_name(image_name, default_tag='latest'):
    parts = image_name.rsplit(':', 1)
    if len(parts) == 2:
        name, tag = parts
    else:
        name, tag = (parts[0], default_tag)
    return (name, tag)


def _short_id(id):
    sep = id.find(':')
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

    def get_registry_url(self):
        scheme = 'https' if not self.insecure else 'http'
        return f'{scheme}://{self.host}/v2/'

    def _get_auth(self):
        return aiohttp.BasicAuth(self.username, self.password)

    def get_default_course_image(self):
        host = self.host
        name = self.default_course_image
        return f'{host}/{name}'

    def get_initial_course_image(self):
        host = self.host
        name = self.initial_course_image
        return f'{host}/{name}'

    async def list_images(self):
        async with aiohttp.ClientSession(auth=self._get_auth()) as session:
            url = self.get_registry_url()
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

            self.log.debug('found images: %s', [f"{c['name']}:{c['reference']}" for c in configs])

            default_course_image = None
            initial_course_image = None
            images = []
            for config in configs:
                labels = config['data'].get('config', {}).get('Labels', {})
                name = config['name']
                ref = config['reference']
                image_name_ref = f'{name}:{ref}'
                if self.default_course_image == image_name_ref:
                    self.log.debug('found default course image: %s labels=%s', image_name_ref, labels)
                    default_course_image = config['digest']
                elif self.initial_course_image == image_name_ref:
                    self.log.debug('found initial course image: %s labels=%s', image_name_ref, labels)
                    initial_course_image = {
                        "repo": '-',
                        "ref": '-',
                        "image_name": name,
                        "display_name": 'initial',
                        "image_id": config['digest'],
                        "short_image_id": _short_id(config['digest']),
                        "status": "-",
                        "default_course_image": False,
                        "initial_course_image": True,
                    }
                elif ('cwh_repo2docker.image_name' in labels and
                        image_name_ref == labels['cwh_repo2docker.image_name']):
                    self.log.debug('found repo2docker course image: %s labels=%s', image_name_ref, labels)
                    images.append({
                        "repo": labels["repo2docker.repo"],
                        "ref": labels["repo2docker.ref"],
                        "image_name": labels["cwh_repo2docker.image_name"],
                        "display_name": labels["cwh_repo2docker.display_name"],
                        "image_id": config['digest'],
                        "short_image_id": _short_id(config['digest']),
                        "status": "built",
                        "default_course_image": False,
                        "initial_course_image": False,
                    })
                else:
                    self.log.debug('not course image: %s labels=%s', image_name_ref, labels)


            if default_course_image:
                for image in images:
                    if image['image_id'] == default_course_image:
                        image['default_course_image'] = True

            if initial_course_image:
                images.append(initial_course_image)

            return images

    async def inspect_image(self, name, ref):
        async with aiohttp.ClientSession(auth=self._get_auth()) as session:
            url = self.get_registry_url()

            manifest = await _get_manifest(session, url, name, ref)

            return await _get_config(session, url, name, ref, manifest)

    async def delete(self, name, ref):
        async with aiohttp.ClientSession(auth=self._get_auth()) as session:
            url = self.get_registry_url()

            manifest = await _get_manifest(session, url, name, ref)
            manifest_digest = manifest['digest']

            async with session.delete(
                    f'{url}{name}/manifests/{manifest_digest}') as resp:
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
        new_name, new_ref = split_image_name(self.default_course_image)
        return await self.set_name_tag(
            new_name, new_ref, name, ref)

    async def set_name_tag(self, new_name, new_tag, src_name, src_tag):
        async with aiohttp.ClientSession(auth=self._get_auth()) as session:
            url = self.get_registry_url()

            manifest = await _get_manifest(session, url, src_name, src_tag)

            return await _put_manifest(
                session,
                url,
                new_name, new_tag,
                manifest['manifest'])
