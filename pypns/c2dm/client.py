import urllib
from twisted.python import log
from twisted.internet import reactor
from twisted.application import service
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from zope.interface import implements
from pypns.base import IPNSService, register_factory

CLIENT_LOGIN_URL = 'https://www.google.com/accounts/ClientLogin'
C2DM_URL = 'https://android.apis.google.com/c2dm/send'

class C2DMService(service.Service):
    """ A Service that sends notifications to the C2DM Service
    """

    implements(IPNSService)

    def __init__(self, email, passwd, environment, timeout=15):
        log.msg('C2DMService __init__')
        self.agent = Agent(reactor)
        self.token = None
        self.environment = environment
        self.email = email
        self.passwd = passwd
        self.timeout = timeout

    def notify(self, registration_id, payload):
        "Connect to the C2DM service and send notifications"
        if not self.token:
            return self.get_token().addCallback(lambda: self.send_notify(registration_id, payload))

        return self.send_notify(registration_id, payload)

    def send_notify(self, registration_id, payload):
        log.msg('C2DMService.send_notify %s' % registration_id)

        values = {
            'collapse_key' : '',
            'registration_id' : registration_id,
            }
        d = self.agent.request(
            'POST',
            C2DM_URL,
            Headers({
                'Authorization': 'GoogleLogin auth=' + self.token,
                'Content-Type': 'application/x-www-form-urlencoded'}),
            urllib.urlencode(values))
        d.addCallback(self)
        d.addErrback(log_errback('c2dm-service-write'))
        return d

    def get_token(self):
        log.msg('C2DMService.get_token')

        values = {
            'accountType' : 'HOSTED_OR_GOOGLE',
            'Email' : self.email,
            'Passwd' : self.passwd,
            'source' : 'C2DMVALIDACCOUNT-C2DM-1',
            'service' : 'c2dm'
        }
        d = self.agent.request(
            'POST',
            CLIENT_LOGIN_URL,
            Headers({
                'Content-Type': 'application/x-www-form-urlencoded'
            }),
            urllib.urlencode(values))
        d.addCallback(self.parse_token)
        d.addErrback(log_errback('c2dm-service-write'))
        return d

    def parse_token(self, response):
        return response.deliverBody(BeginningPrinter(finished))

        responseAsList = response.split('\n')
        self._token = responseAsList[2].split('=')[1]
        self.token =  None

def log_errback(name):
    def _log_errback(err, *args):
        log.msg('errback in %s : %s' % (name, str(err)))
        return err
    return _log_errback
