import os
import binascii
import urllib
from twisted.python import log
from twisted.internet import reactor
from twisted.internet import defer
from twisted.internet.protocol import Protocol
from twisted.application import service
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from zope.interface import implements
from pypns.base import IPNSService

CLIENT_LOGIN_URL = 'https://www.google.com/accounts/ClientLogin'
C2DM_URL = 'https://android.apis.google.com/c2dm/send'

class UnauthorizedException(Exception):
    pass

class InvalidRegistrationException(Exception):
    pass

class NotRegisteredException(Exception):
    pass

class BufferProtocol(Protocol):
    def __init__(self):
        self._buffer = ''
        self.done = defer.Deferred()

    def connectionMade(self):
        pass

    def dataReceived(self, bytes):
        self._buffer += bytes

    def connectionLost(self, reason):
        self.done.callback(self._buffer)

class BufferProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def resumeProducing(self):
        pass

    def stopProducing(self):
        pass

class C2DMService(service.Service):
    """
    A Service that sends notifications to the C2DM Service
    """
    implements(IPNSService)

    ERRORS = {
        'InvalidRegistration': InvalidRegistrationException,
        'NotRegistered': NotRegisteredException
    }

    def __init__(self, email, password, environment, timeout=15):
        log.msg('C2DMService __init__')
        self.agent = Agent(reactor)
        self.token = None
        self.environment = environment
        self.email = email
        self.password = password
        self.timeout = timeout

    @defer.inlineCallbacks
    def notify(self, registration_id, payload):
        """
        Connect to the C2DM service and send notifications
        """
        log.msg('notify %s' % registration_id)

        #TODO: Avoid making multiple get_token requests in parallel until you get the token
        if not self.token:
            self.token = yield self.get_token()

        try:
            result = yield self.send_notify(registration_id, payload)
        except UnauthorizedException:
            self.token = yield self.get_token()
            result = yield self.send_notify(registration_id, payload)

        defer.returnValue(result)

    @defer.inlineCallbacks
    def send_notify(self, registration_id, payload):
        log.msg('C2DMService.send_notify %s' % registration_id)

        values = {
            'collapse_key' : binascii.hexlify(os.urandom(16)),
            'registration_id' : registration_id,
            }
        for k,v in payload.iteritems():
            values['data.%s' % k] = v

        response = yield self.agent.request(
            'POST',
            C2DM_URL,
            Headers({
                'Authorization': ['GoogleLogin auth=' + self.token],
                'Content-Type': ['application/x-www-form-urlencoded']}),
            BufferProducer(urllib.urlencode(values)))

        if response.code == 401:
            raise UnauthorizedException()
        elif response.code != 200:
            raise Exception('Invalid response code %d' % response.code)

        protocol = BufferProtocol()
        response.deliverBody(protocol)

        response_content = yield protocol.done

        responseAsList = response_content.split('\n')
        key, val = responseAsList[0].split('=')

        if key == 'Error':
            raise self.ERRORS.get(val, Exception)('Error sending notification ' + val)

        defer.returnValue(val)

    @defer.inlineCallbacks
    def get_token(self):
        log.msg('C2DMService.get_token')

        values = {
            'accountType' : 'HOSTED_OR_GOOGLE',
            'Email' : self.email,
            'Passwd' : self.password,
            'source' : 'C2DMVALIDACCOUNT-C2DM-1',
            'service' : 'ac2dm'
        }

        response = yield self.agent.request(
            'POST',
            CLIENT_LOGIN_URL,
            Headers({
                'Content-Type': ['application/x-www-form-urlencoded']
            }),
            BufferProducer(urllib.urlencode(values)))

        token = yield self.parse_token(response)

        log.msg('token %s' % token)

        defer.returnValue(token)

    @defer.inlineCallbacks
    def parse_token(self, response):
        log.msg('parse_token')

        protocol = BufferProtocol()
        response.deliverBody(protocol)

        response_content = yield protocol.done

        log.msg('parse_token ' + response_content)

        responseAsList = response_content.split('\n')
        token = responseAsList[2].split('=')[1]

        defer.returnValue(token)

def log_errback(name):
    def _log_errback(err, *args):
        log.msg('errback in %s : %s' % (name, str(err)))
        return err
    return _log_errback
