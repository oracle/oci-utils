# oci-utils
#
# Copyright (c) 2018, 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import binascii
import logging
import random
import socket

__version__ = '0.1.0'

log = logging.getLogger("oci-utils.pystun")

STUN_SERVERS = (
    'stun.stunprotocol.org',
    'stun.counterpath.net',
    'stun.voxgratia.org',
    'stun.callwithus.com',
    'stun.ekiga.net',
    'stun.ideasip.com',
    'stun.voipbuster.com',
    'stun.voiparound.com',
    'stun.voipstunt.com')

stun_servers_list = STUN_SERVERS

DEFAULTS = {
    'stun_port': 3478,
    'source_ip': '0.0.0.0',
    'source_port': 54320}

# stun attributes
MappedAddress = '0001'
ResponseAddress = '0002'
ChangeRequest = '0003'
SourceAddress = '0004'
ChangedAddress = '0005'
Username = '0006'
Password = '0007'
MessageIntegrity = '0008'
ErrorCode = '0009'
UnknownAttribute = '000A'
ReflectedFrom = '000B'
XorOnly = '0021'
XorMappedAddress = '8020'
ServerName = '8022'
SecondaryAddress = '8050'  # Non standard extension

# types for a stun message
BindRequestMsg = '0001'
BindResponseMsg = '0101'
BindErrorResponseMsg = '0111'
SharedSecretRequestMsg = '0002'
SharedSecretResponseMsg = '0102'
SharedSecretErrorResponseMsg = '0112'

dictAttrToVal = {'MappedAddress': MappedAddress,
                 'ResponseAddress': ResponseAddress,
                 'ChangeRequest': ChangeRequest,
                 'SourceAddress': SourceAddress,
                 'ChangedAddress': ChangedAddress,
                 'Username': Username,
                 'Password': Password,
                 'MessageIntegrity': MessageIntegrity,
                 'ErrorCode': ErrorCode,
                 'UnknownAttribute': UnknownAttribute,
                 'ReflectedFrom': ReflectedFrom,
                 'XorOnly': XorOnly,
                 'XorMappedAddress': XorMappedAddress,
                 'ServerName': ServerName,
                 'SecondaryAddress': SecondaryAddress}

dictMsgTypeToVal = {
    'BindRequestMsg': BindRequestMsg,
    'BindResponseMsg': BindResponseMsg,
    'BindErrorResponseMsg': BindErrorResponseMsg,
    'SharedSecretRequestMsg': SharedSecretRequestMsg,
    'SharedSecretResponseMsg': SharedSecretResponseMsg,
    'SharedSecretErrorResponseMsg': SharedSecretErrorResponseMsg}

dictValToMsgType = {}

dictValToAttr = {}

Blocked = "Blocked"
OpenInternet = "Open Internet"
FullCone = "Full Cone"
SymmetricUDPFirewall = "Symmetric UDP Firewall"
RestricNAT = "Restric NAT"
RestricPortNAT = "Restric Port NAT"
SymmetricNAT = "Symmetric NAT"
ChangedAddressError = "Meet an error, when do Test1 on Changed IP and Port"


def _initialize():
    """

    Returns
    -------
        No return value.
    """
    items = list(dictAttrToVal.items())
    for i in range(len(items)):
        dictValToAttr.update({items[i][1]: items[i][0]})
    items = list(dictMsgTypeToVal.items())
    for i in range(len(items)):
        dictValToMsgType.update({items[i][1]: items[i][0]})


def _bin_to_hexstr(b):
    if type(b) == bytes:
        return binascii.b2a_hex(b).decode('utf-8')
    return binascii.a2b_hex(b)


def gen_tran_id():
    """
    Generate a random 32byte HEX string.

    Returns
    -------
        str
            The random HEX string.
    """
    a = ''.join(random.choice('0123456789ABCDEF') for i in range(32))
    # return binascii.a2b_hex(a)
    return a


def stun_test(sock, host, port, source_ip, source_port, send_data=""):
    """
    Test.

    Parameters
    ----------
    sock: socket.pyi
        Network socket.
    host: str
        The destination IP address..
    port: int
        The IP port.
    source_ip: str
        The source IP address.
        # GT not used, left in place to avoid function call break.
    source_port: int
        The source port.
        # GT not used, left in place to avoid function call break.
    send_data: str
        Test data.

    Returns
    -------
        dict
            Test results.
    """
    ret_val = {'Resp': False, 'ExternalIP': None, 'ExternalPort': None,
               'SourceIP': None, 'SourcePort': None, 'ChangedIP': None,
               'ChangedPort': None}
    str_len = "%#04d" % (len(send_data) / 2)
    tranid = gen_tran_id()
    str_data = ''.join([BindRequestMsg, str_len, tranid, send_data])
    data = _bin_to_hexstr(str_data)
    recv_corr = False
    while not recv_corr:
        recieved = False
        count = 3
        while not recieved:
            log.debug("sendto: %s", (host, port))
            try:
                sock.sendto(data, (host, port))
            except socket.gaierror as e:
                log.debug("sendto exception: %s", e)
                ret_val['Resp'] = False
                return ret_val
            try:
                buf, addr = sock.recvfrom(2048)
                log.debug("recvfrom: %s", addr)
                recieved = True
            except Exception as e:
                log.debug("recvfrom exception: %s", e)
                recieved = False
                if count > 1:
                    count -= 1
                else:
                    ret_val['Resp'] = False
                    return ret_val
        msgtype = _bin_to_hexstr(buf[0:2])
        bind_resp_msg = dictValToMsgType[msgtype] == "BindResponseMsg"
        tranid_match = tranid.upper() == _bin_to_hexstr(buf[4:20]).upper()
        if bind_resp_msg and tranid_match:
            recv_corr = True
            ret_val['Resp'] = True
            len_message = int(_bin_to_hexstr(buf[2:4]), 16)
            len_remain = len_message
            base = 20
            while len_remain:
                attr_type = _bin_to_hexstr(buf[base:(base + 2)])
                attr_len = int(_bin_to_hexstr(buf[(base + 2):(base + 4)]), 16)
                if attr_type == MappedAddress:
                    port = int(_bin_to_hexstr(buf[base + 6:base + 8]), 16)
                    ip = ".".join(
                        [str(int(_bin_to_hexstr(buf[base + 8:base + 9]), 16)),
                         str(int(_bin_to_hexstr(buf[base + 9:base + 10]), 16)),
                         str(int(_bin_to_hexstr(buf[base + 10:base + 11]), 16)),
                         str(int(_bin_to_hexstr(buf[base + 11:base + 12]), 16))])
                    ret_val['ExternalIP'] = ip
                    ret_val['ExternalPort'] = port
                if attr_type == SourceAddress:
                    port = int(_bin_to_hexstr(buf[base + 6:base + 8]), 16)
                    ip = ".".join([
                        str(int(_bin_to_hexstr(buf[base + 8:base + 9]), 16)),
                        str(int(_bin_to_hexstr(buf[base + 9:base + 10]), 16)),
                        str(int(_bin_to_hexstr(buf[base + 10:base + 11]), 16)),
                        str(int(_bin_to_hexstr(buf[base + 11:base + 12]), 16))])
                    ret_val['SourceIP'] = ip
                    ret_val['SourcePort'] = port
                if attr_type == ChangedAddress:
                    port = int(_bin_to_hexstr(buf[base + 6:base + 8]), 16)
                    ip = ".".join([
                        str(int(_bin_to_hexstr(buf[base + 8:base + 9]), 16)),
                        str(int(_bin_to_hexstr(buf[base + 9:base + 10]), 16)),
                        str(int(_bin_to_hexstr(buf[base + 10:base + 11]), 16)),
                        str(int(_bin_to_hexstr(buf[base + 11:base + 12]), 16))])
                    ret_val['ChangedIP'] = ip
                    ret_val['ChangedPort'] = port
                # if attr_type == ServerName:
                    # serverName = buf[(base+4):(base+4+attr_len)]
                base = base + 4 + attr_len
                len_remain = len_remain - (4 + attr_len)
    # s.close()
    return ret_val


def get_nat_type(s, source_ip, source_port, stun_host=None, stun_port=3478):
    """
    Get the NAT type.

    Parameters
    ----------
    s: socket.pyi
        The socket to use.
    source_ip: str
        The source IP address.
    source_port: int
        The source port.
    stun_host: str
        The destination IP address.
    stun_port: int
        The destinatin port.

    Returns
    -------
        tuple
            The type, the test results
    """
    _initialize()
    port = stun_port
    log.debug("Do Test1")
    resp = False
    if stun_host:
        ret = stun_test(s, stun_host, port, source_ip, source_port)
        resp = ret['Resp']
    else:
        for stun_host in random.sample(stun_servers_list, 3):
            log.debug('Trying STUN host: %s', stun_host)
            ret = stun_test(s, stun_host, port, source_ip, source_port)
            resp = ret['Resp']
            if resp:
                break
    if not resp:
        return Blocked, ret
    log.debug("Result: %s", ret)
    ex_ip = ret['ExternalIP']
    ex_port = ret['ExternalPort']
    changed_ip = ret['ChangedIP']
    changed_port = ret['ChangedPort']
    if ret['ExternalIP'] == source_ip:
        change_request = ''.join([ChangeRequest, '0004', "00000006"])
        ret = stun_test(s, stun_host, port, source_ip, source_port,
                        change_request)
        if ret['Resp']:
            typ = OpenInternet
        else:
            typ = SymmetricUDPFirewall
    else:
        change_request = ''.join([ChangeRequest, '0004', "00000006"])
        log.debug("Do Test2")
        ret = stun_test(s, stun_host, port, source_ip, source_port,
                        change_request)
        log.debug("Result: %s", ret)
        if ret['Resp']:
            typ = FullCone
        else:
            log.debug("Do Test1")
            ret = stun_test(s, changed_ip, changed_port, source_ip, source_port)
            log.debug("Result: %s", ret)
            if not ret['Resp']:
                typ = ChangedAddressError
            else:
                if ex_ip == ret['ExternalIP'] and ex_port == ret['ExternalPort']:
                    changed_port_request = ''.join([ChangeRequest, '0004',
                                                    "00000002"])
                    log.debug("Do Test3")
                    ret = stun_test(s, changed_ip, port, source_ip, source_port,
                                    changed_port_request)
                    log.debug("Result: %s", ret)
                    if ret['Resp']:
                        typ = RestricNAT
                    else:
                        typ = RestricPortNAT
                else:
                    typ = SymmetricNAT
    return typ, ret


def get_ip_info(source_ip="0.0.0.0", source_port=54320, stun_host=None, stun_port=3478):
    """
    Get the IP info.

    Parameters
    ----------
    source_ip: str
        The source IP address.
    source_port: int
        The source port.
    stun_host: str
        The destination IP address.
    stun_port:
        The destination port.

    Returns
    -------
        tuple
            The nat type, the IP address, the port.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.0)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((source_ip, source_port))
    nat_type, nat = get_nat_type(s, source_ip, source_port, stun_host=stun_host, stun_port=stun_port)
    external_ip = nat['ExternalIP']
    external_port = nat['ExternalPort']
    s.close()
    return nat_type, external_ip, external_port
