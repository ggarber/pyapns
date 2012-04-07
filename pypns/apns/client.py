import json
import struct
import binascii
from twisted.python import log
from StringIO import StringIO as _StringIO
from OpenSSL import SSL, crypto
from twisted.internet import reactor, defer
from twisted.internet.protocol import (
    ReconnectingClientFactory, ClientFactory, Protocol)
from twisted.internet.ssl import ClientContextFactory
from twisted.application import service
from twisted.protocols.basic import LineReceiver
from zope.interface import Interface, implements
from pypns.base import IPNSService

APNS_SERVER_SANDBOX_HOSTNAME = "gateway.sandbox.push.apple.com"
APNS_SERVER_HOSTNAME = "gateway.push.apple.com"
APNS_SERVER_PORT = 2195
FEEDBACK_SERVER_SANDBOX_HOSTNAME = "feedback.sandbox.push.apple.com"
FEEDBACK_SERVER_HOSTNAME = "feedback.push.apple.com"
FEEDBACK_SERVER_PORT = 2196

class StringIO(_StringIO):
    """Add context management protocol to StringIO
        ie: http://bugs.python.org/issue1286
    """

    def __enter__(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self

    def __exit__(self, exc, value, tb):
        self.close()

class APNSClientContextFactory(ClientContextFactory):
    def __init__(self, ssl_cert_file):
        if 'BEGIN CERTIFICATE' not in ssl_cert_file:
            log.msg('APNSClientContextFactory ssl_cert_file=%s' % ssl_cert_file)
        else:
            log.msg('APNSClientContextFactory ssl_cert_file={FROM_STRING}')
        self.ctx = SSL.Context(SSL.SSLv3_METHOD)
        if 'BEGIN CERTIFICATE' in ssl_cert_file:
            cer = crypto.load_certificate(crypto.FILETYPE_PEM, ssl_cert_file)
            pkey = crypto.load_privatekey(crypto.FILETYPE_PEM, ssl_cert_file)
            self.ctx.use_certificate(cer)
            self.ctx.use_privatekey(pkey)
        else:
            self.ctx.use_certificate_file(ssl_cert_file)
            self.ctx.use_privatekey_file(ssl_cert_file)

    def getContext(self):
        return self.ctx


class APNSProtocol(Protocol):
    def connectionMade(self):
        log.msg('APNSProtocol connectionMade')
        self.factory.addClient(self)

    def sendMessage(self, msg):
        log.msg('APNSProtocol sendMessage msg=%s' % binascii.hexlify(msg))
        return self.transport.write(msg)

    def connectionLost(self, reason):
        log.msg('APNSProtocol connectionLost')
        self.factory.removeClient(self)


class APNSFeedbackHandler(LineReceiver):
    MAX_LENGTH = 1024*1024

    def connectionMade(self):
        log.msg('feedbackHandler connectionMade')

    def rawDataReceived(self, data):
        log.msg('feedbackHandler rawDataReceived %s' % binascii.hexlify(data))
        self.io.write(data)

    def lineReceived(self, data):
        log.msg('feedbackHandler lineReceived %s' % binascii.hexlify(data))
        self.io.write(data)

    def connectionLost(self, reason):
        log.msg('feedbackHandler connectionLost %s' % reason)
        self.deferred.callback(self.io.getvalue())
        self.io.close()


class APNSFeedbackClientFactory(ClientFactory):
    protocol = APNSFeedbackHandler

    def __init__(self):
        self.deferred = defer.Deferred()

    def buildProtocol(self, addr):
        p = self.protocol()
        p.factory = self
        p.deferred = self.deferred
        p.io = StringIO()
        p.setRawMode()
        return p

    def startedConnecting(self, connector):
        log.msg('APNSFeedbackClientFactory startedConnecting')

    def clientConnectionLost(self, connector, reason):
        log.msg('APNSFeedbackClientFactory clientConnectionLost reason=%s' % reason)
        ClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        log.msg('APNSFeedbackClientFactory clientConnectionFailed reason=%s' % reason)
        ClientFactory.clientConnectionLost(self, connector, reason)


class APNSClientFactory(ReconnectingClientFactory):
    protocol = APNSProtocol

    def __init__(self):
        self.clientProtocol = None
        self.deferred = defer.Deferred()
        self.deferred.addErrback(log_errback('APNSClientFactory __init__'))

    def addClient(self, p):
        log.msg('APNSClientFactory addClient %s' % p)

        self.clientProtocol = p
        self.deferred.callback(p)

    def removeClient(self, p):
        log.msg('APNSClientFactory removeClient %s' % p)

        self.clientProtocol = None
        self.deferred = defer.Deferred()
        self.deferred.addErrback(log_errback('APNSClientFactory removeClient'))

    def startedConnecting(self, connector):
        log.msg('APNSClientFactory startedConnecting')

    def buildProtocol(self, addr):
        self.resetDelay()
        p = self.protocol()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        log.msg('APNSClientFactory clientConnectionLost reason=%s' % reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        log.msg('APNSClientFactory clientConnectionFailed reason=%s' % reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)


class APNSService(service.Service):
    """ A Service that sends notifications and receives
    feedback from the Apple Push Notification Service
    """

    implements(IPNSService)
    clientProtocolFactory = APNSClientFactory
    feedbackProtocolFactory = APNSFeedbackClientFactory

    def __init__(self, cert, environment, timeout=15):
        self.factory = None
        self.environment = environment
        self.cert_path = cert
        self.raw_mode = False
        self.timeout = timeout

    def getContextFactory(self):
        return APNSClientContextFactory(self.cert_path)

    def notify(self, token_or_token_list, payload):
        "Connect to the APNS service and send notifications"
        notifications = encode_notifications(
            [t.replace(' ', '') for t in token_or_token_list]
            if (type(token_or_token_list) is list)
            else token_or_token_list.replace(' ', ''),
            payload)

        if not self.factory:
            log.msg('APNSService write (connecting)')
            server, port = ((APNS_SERVER_SANDBOX_HOSTNAME
                             if self.environment == 'sandbox'
                             else APNS_SERVER_HOSTNAME), APNS_SERVER_PORT)
            self.factory = self.clientProtocolFactory()
            context = self.getContextFactory()
            reactor.connectSSL(server, port, self.factory, context)

        client = self.factory.clientProtocol
        if client:
            return client.sendMessage(notifications)
        else:
            log.msg('APNSService waiting for connection')
            d = self.factory.deferred
            timeout = reactor.callLater(self.timeout,
                lambda: d.called or d.errback(
                    Exception('Notification timed out after %i seconds' % self.timeout)))
            def cancel_timeout(r):
                try: timeout.cancel()
                except: pass
                return r

            def connected(protocol):
                log.msg('APNSService connected, retrying sending')
                protocol.sendMessage(notifications)
                return protocol

            d.addCallback(connected)
            d.addErrback(log_errback('apns-service-write'))
            d.addBoth(cancel_timeout)
            return d

    def feedback(self):
        "Connect to the feedback service and read all data."
        log.msg('APNSService feedback (connecting)')
        try:
            server, port = ((FEEDBACK_SERVER_SANDBOX_HOSTNAME
                             if self.environment == 'sandbox'
                             else FEEDBACK_SERVER_HOSTNAME), FEEDBACK_SERVER_PORT)
            factory = self.feedbackProtocolFactory()
            context = self.getContextFactory()
            reactor.connectSSL(server, port, factory, context)
            factory.deferred.addErrback(log_errback('apns-feedback-read'))

            timeout = reactor.callLater(self.timeout,
                lambda: factory.deferred.called or factory.deferred.errback(
                    Exception('Feedback fetch timed out after %i seconds' % self.timeout)))
            def cancel_timeout(r):
                try: timeout.cancel()
                except: pass
                return r

            factory.deferred.addBoth(cancel_timeout)
        except Exception, e:
            log.msg('APNService feedback error initializing: %s' % str(e))
            raise
        return factory.deferred

def encode_notifications(tokens, notifications):
    """ Returns the encoded bytes of tokens and notifications

          tokens          a list of tokens or a string of only one token
          notifications   a list of notifications or a dictionary of only one
    """

    fmt = "!BH32sH%ds"
    structify = lambda t, p: struct.pack(fmt % len(p), 0, 32, t, len(p), p)
    binaryify = lambda t: t.decode('hex')
    if type(notifications) is dict and type(tokens) in (str, unicode):
        tokens, notifications = ([tokens], [notifications])
    if type(notifications) is list and type(tokens) is list:
        return ''.join(map(lambda y: structify(*y), ((binaryify(t), json.dumps(p, separators=(',',':')))
        for t, p in zip(tokens, notifications))))

def log_errback(name):
    def _log_errback(err, *args):
        log.msg('errback in %s : %s' % (name, str(err)))
        return err
    return _log_errback