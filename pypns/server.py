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

  def xmlrpc_notify(self, app_id, provider, token_or_token_list, aps_dict_or_list):
    """ Sends push notifications to the PNS server. Multiple 
    notifications can be sent by sending pairing the token/notification
    arguments in lists [token1, token2], [notification1, notification2].

      Arguments:
          app_id                provisioned app_id to send to
          token_or_token_list   token to send the notification or a list of tokens
          aps_dict_or_list      notification dicts or a list of notifications
      Returns:
          None
    """
    d = get_service(app_id, provider).notify(token_or_token_list, aps_dict_or_list)
    if d:
      def _finish_err(r):
        # so far, the only error that could really become of this
        # request is a timeout, since PNS simply terminates connectons
        # that are made unsuccessfully, which twisted will try endlessly
        # to reconnect to, we timeout and notifify the client
        raise xmlrpc.Fault(500, 'Connection to the PNS server could not be made.')
      return d.addCallbacks(lambda r: None, _finish_err)

  def xmlrpc_feedback(self, app_id, provider):
    """ Queries the Apple APNS feedback server for inactive app tokens. Returns
    a list of tuples as (datetime_went_dark, token_str).

      Arguments:
          app_id   the app_id to query
      Returns:
          Feedback tuples like (datetime_expired, token_str)
    """

    return get_service(app_id, provider).feedback().addCallback(
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
