from twisted.python import log
from zope.interface import Interface

class IPNSService(Interface):
    """ Interface for PNS """

    def notify(self, token_or_token_list, payload):
        """ Write the notification to PNS """

    def feedback(self):
        """ Read from the feedback service """

factories = {}
services = {}

def register_factory(provider, factory):
    log.msg('register_factory {0}'.format(provider))

    factories[provider] = factory

def create_service(app_id, provider, **kwargs):
    log.msg('create_service {0} for app {1}'.format(provider, app_id))

    if not provider in factories:
        raise Exception('Unknown provider')

    service = factories[provider](**kwargs)
    _add_service(app_id, provider, service)

def get_service(app_id, provider):
    if app_id not in services or provider not in services[app_id]:
        raise Exception('service not found')
    return services[app_id][provider]

def _add_service(app_id, provider, service):
    if not app_id in services:
        services[app_id] = {}
    services[app_id][provider] = service