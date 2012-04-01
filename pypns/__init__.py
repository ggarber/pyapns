from base import register_factoryfrom apns.client import APNSServicefrom c2dm.client import C2DMServicedef apns_factory(**kwargs):    return APNSService(**kwargs)def c2dm_factory(**kwargs):    return C2DMService(**kwargs)register_factory('apns', apns_factory)register_factory('c2dm', c2dm_factory)