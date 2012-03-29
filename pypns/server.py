import struct
import binascii
import datetime
from twisted.web import xmlrpc
from base import create_service, get_service

class PNSServer(xmlrpc.XMLRPC):
  def __init__(self):
    self.use_date_time = True
    self.useDateTime = True
    xmlrpc.XMLRPC.__init__(self, allowNone=True)
  
  def xmlrpc_provision(self, app_id, path_to_cert_or_cert, environment, timeout=15):
    """ Starts an APNSService for the this app_id and keeps it running
    
      Arguments:
          app_id                 the app_id to provision for APNS
          path_to_cert_or_cert   absolute path to the APNS SSL cert or a 
                                 string containing the .pem file
          environment            either 'sandbox' or 'production'
          timeout                seconds to timeout connection attempts
                                 to the APNS server
      Returns:
          None
    """
    
    if environment not in ('sandbox', 'production'):
      raise xmlrpc.Fault(401, 'Invalid environment provided `%s`. Valid '
                              'environments are `sandbox` and `production`' % (
                              environment,))

    service = create_service(app_id, 'apns', cert=path_to_cert_or_cert, environment=environment, timeout=timeout)
  
  def xmlrpc_notify(self, app_id, token_or_token_list, aps_dict_or_list):
    """ Sends push notifications to the Apple APNS server. Multiple 
    notifications can be sent by sending pairing the token/notification
    arguments in lists [token1, token2], [notification1, notification2].
    
      Arguments:
          app_id                provisioned app_id to send to
          token_or_token_list   token to send the notification or a list of tokens
          aps_dict_or_list      notification dicts or a list of notifications
      Returns:
          None
    """
    d = get_service(app_id, 'apns').notify(token_or_token_list, aps_dict_or_list)
    if d:
      def _finish_err(r):
        # so far, the only error that could really become of this
        # request is a timeout, since APNS simply terminates connectons
        # that are made unsuccessfully, which twisted will try endlessly
        # to reconnect to, we timeout and notifify the client
        raise xmlrpc.Fault(500, 'Connection to the APNS server could not be made.')
      return d.addCallbacks(lambda r: None, _finish_err)
  
  def xmlrpc_feedback(self, app_id):
    """ Queries the Apple APNS feedback server for inactive app tokens. Returns
    a list of tuples as (datetime_went_dark, token_str).
    
      Arguments:
          app_id   the app_id to query
      Returns:
          Feedback tuples like (datetime_expired, token_str)
    """
    
    return get_pns_service(app_id, 'apns').read().addCallback(
      lambda r: decode_feedback(r))

def decode_feedback(binary_tuples):
  """ Returns a list of tuples in (datetime, token_str) format 
  
        binary_tuples   the binary-encoded feedback tuples
  """
  
  fmt = '!lh32s'
  size = struct.calcsize(fmt)
  with StringIO(binary_tuples) as f:
    return [(datetime.datetime.fromtimestamp(ts), binascii.hexlify(tok))
            for ts, toklen, tok in (struct.unpack(fmt, tup) 
                              for tup in iter(lambda: f.read(size), ''))]
