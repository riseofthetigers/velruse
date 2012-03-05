import logging
import os

from pyramid.config import Configurator
from pyramid.exceptions import ConfigurationError
from pyramid.response import Response

from velruse.app.utils import generate_token
from velruse.app.utils import redirect_form


log = logging.getLogger(__name__)

def auth_complete_view(context, request):
    end_point = request.registry.settings.get('velruse.end_point')
    token = generate_token()
    storage = request.registry.velruse_store
    if 'birthday' in context.profile:
        context.profile['birthday'] = \
                context.profile['birthday'].strftime('%Y-%m-%d')
    result_data = {
        'profile': context.profile,
        'credentials': context.credentials,
    }
    storage.store(token, result_data, expires=300)
    form = redirect_form(end_point, token)
    return Response(body=form)

def auth_denied_view(context, request):
    end_point = request.registry.settings.get('velruse.end_point')
    token = generate_token()
    storage = request.registry.velruse_store
    error_dict = {
        'code': getattr(context, 'code', None), 
        'description': context.message, 
    }
    storage.store(token, error_dict, expires=300)
    form = redirect_form(end_point, token)
    return Response(body=form)

def auth_info_view(request):
    storage = request.registry.velruse_store
    token = request.GET['token']
    return storage.retrieve(token)

def default_setup(config):
    from pyramid.session import UnencryptedCookieSessionFactoryConfig

    log.info('Using an unencrypted cookie-based session. This can be '
             'changed by pointing the "velruse.setup" setting at a different '
             'function for configuring the session factory.')

    settings = config.registry.settings
    secret = settings.get('velruse.session.secret')
    cookie_name = settings.get('velruse.session.cookie_name',
                               'velruse.session')
    if secret is None:
        log.warn('Configuring unencrypted cookie-based session with a '
                 'random secret which will invalidate old cookies when '
                 'restarting the app.')
        secret = ''.join('%02x' % ord(x) for x in os.urandom(16))
        log.info('autogenerated session secret: %s', secret)
    factory = UnencryptedCookieSessionFactoryConfig(
        secret, cookie_name=cookie_name)
    config.set_session_factory(factory)

def includeme(config):
    """Configuration function to make a pyramid app a velruse one."""
    settings = config.registry.settings

    # setup application
    setup = settings.get('velruse.setup') or default_setup
    if setup:
        config.include(setup)

    # configure providers
    config.include('velruse')

    # setup backing storage
    store = settings.get('velruse.store')
    if store is None:
        raise ConfigurationError(
            'invalid setting velruse.store: {0}'.format(store))
    config.include(store)

    # check for required settings
    if not settings.get('velruse.end_point'):
        raise ConfigurationError(
            'missing required setting "velruse.end_point"')

    # add views
    config.add_view(
        auth_complete_view,
        context='velruse.api.AuthenticationComplete')
    config.add_view(
        auth_denied_view,
        context='velruse.exceptions.AuthenticationDenied')
    config.add_view(
        auth_info_view,
        name='auth_info',
        request_param='format=json',
        renderer='json')

def make_app(**settings):
    config = Configurator(settings=settings)
    config.include(includeme)
    return config.make_wsgi_app()

def make_velruse_app(global_conf, **settings):
    """Construct a complete WSGI app ready to serve by Paste

    Example INI file:

    .. code-block:: ini

        [server:main]
        use = egg:Paste#http
        host = 0.0.0.0
        port = 80

        [composite:main]
        use = egg:Paste#urlmap
        / = YOURAPP
        /velruse = velruse

        [app:velruse]
        use = egg:velruse

        velruse.setup = myapp.setup_velruse

        velruse.end_point = http://example.com/logged_in

        velruse.store = velruse.store.redis
        velruse.store.host = localhost
        velruse.store.port = 6379
        velruse.store.db = 0
        velruse.store.key_prefix = velruse_ustore

        velruse.providers =
            facebook
            twitter

        velruse.facebook.consumer_key = KMfXjzsA2qVUcnnRn3vpnwWZ2pwPRFZdb
        velruse.facebook.consumer_secret = ULZ6PkJbsqw2GxZWCIbOEBZdkrb9XwgXNjRy
        velruse.twitter.consumer_key = ULZ6PkJbsqw2GxZWCIbOEBZdkrb9XwgXNjRy
        velruse.twitter.consumer_secret =
            eoCrFwnpBWXjbim5dyG6EP7HzjhQzFsMAcQOEK

        [app:YOURAPP]
        use = egg:YOURAPP
        full_stack = true
        static_files = true

    """
    return make_app(**settings)