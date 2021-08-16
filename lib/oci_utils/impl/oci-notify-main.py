# oci-utils
#
# Copyright (c) 2020 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.


"""
This utility assists with sending messages to an Oracle Cloud Infrastructure
notification service.

The length of the message title is limited to MAX_MESSAGE_TITLE_LEN bytes. The
message file is split in CHUNK_SIZEKB chunks and send as separate messages.
The number of chunks is limited to MAX_MESSAGE_CHUNKS.
The message file can be a flat file, a url or a string.

See the manual page for more information.
"""

import argparse
import configparser
import logging
import os
import re
import shutil
import sys
import urllib
import uuid
from datetime import datetime

import oci as oci_sdk
from oci_utils import _configuration as OCIUtilsConfiguration
from oci_utils.impl.auth_helper import OCIAuthProxy
from oci_utils.metadata import InstanceMetadata

# authentication methods
DIRECT = 'direct'
PROXY = 'proxy'
IP = 'ip'
AUTO = 'auto'
NONE = 'None'


_logger = logging.getLogger('oci-utils.oci_notify')

lc_all = 'en_US.UTF8'

MAX_MESSAGE_TITLE_LEN = 128
MAX_MESSAGE_CHUNKS = 10
CHUNK_SIZE = 65536
# the default configuration directory
NOTIFY_CONFIG_DIR = os.environ.get('OCI_CONFIG_DIR', '/etc/oci-utils')
# OCI config: topic OCID etc.
OCI_CONFIG_FILE = NOTIFY_CONFIG_DIR + '/oci.conf'
# OCI API private key
OCI_API_KEY_FILE = NOTIFY_CONFIG_DIR + '/oci_api_key.pem'
# OCI SDK/CLI config
OCI_CLI_CONFIG_FILE = NOTIFY_CONFIG_DIR + '/oci_cli.conf'


def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Arguments:
     config <notification service OCID>
     message
       -t|--title <message title>
       -f|--file <file name containing the message contents>

    Returns
    -------
        The command line namespace.
    """
    _logger.debug('_parse_args')
    extra_descr = ''
    for helpline in __doc__.splitlines():
        extra_descr += '%s\n' % (helpline.replace('MAX_MESSAGE_TITLE_LEN',
                                                  str(MAX_MESSAGE_TITLE_LEN))
                                 .replace('CHUNK_SIZE', str(CHUNK_SIZE))
                                 .replace('MAX_MESSAGE_CHUNKS', str(MAX_MESSAGE_CHUNKS)))
    parser = argparse.ArgumentParser(description='%s' % extra_descr)
    sub_parser = parser.add_subparsers(dest='mode')
    config_parser = sub_parser.add_parser('config', help='Configure the notification server.')
    message_parser = sub_parser.add_parser('message', help='Send a message.')
    config_parser.add_argument(action='store',
                               dest='notification_ocid',
                               type=str,
                               help='The ocid of the notification topic.')
    message_parser.add_argument('-t', '--title',
                                action='store',
                                dest='message_title',
                                required=True,
                                type=str,
                                help='The subject of the message.')
    message_parser.add_argument('-f', '--file',
                                action='store',
                                dest='message_file',
                                required=True,
                                type=str,
                                help='The message data.')
    return parser


def is_root():
    """
    Verify is operator is the root user.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    return bool(os.getuid() == 0)


def config_notification_service_wrap(config_args):
    """
    Wrapper for writing or updating the oci notification config file.

    Parameters
    ----------
    config_args:
        The command line arguments.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('_config_notification_service_wrap: %s', config_args.notification_ocid)
    cfg = NotificationConfig(config_args.notification_ocid, OCI_CONFIG_FILE)
    cfg_title, cfg_message = cfg.config_notification_service(config_args.notification_ocid)
    cfg_res = handle_message(cfg_title, cfg_message)
    _logger.debug('Config res: %s', cfg_res)
    return True


def handle_message_wrap(message_args):
    """
    Wrapper for sending a notification message.

    Parameters:
    ----------
    message_args:
        The command line paramaters.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('_handle_message_wrap: %s', message_args)
    message_title = message_args.message_title
    message_file = message_args.message_file
    try:
        res = handle_message(message_title, message_file)
        return res
    except Exception as e:
        _logger.debug('%s', str(e), stack_info=True, exc_info=True)
        raise NotificationException(str(e))


def handle_message(title, message):
    """
    Handle the message to send to the notification service.

    Parameters
    ----------
    title: str
        The message subject.
    message: str
        The file, url or string to send.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('_handle_message')
    _logger.debug('title %s', title)
    _logger.debug('message %s', message)
    try:
        msg = NotificationMessage(title, message, oci_config_profile='DEFAULT')
        msg_send_res = msg.send_notification()
        _logger.debug('Message result: %s', msg_send_res)
    except Exception as e:
        _logger.debug('Failed to send message %s: %s', title, str(e))
        _logger.error(str(e))
    return True


class NotificationException(Exception):
    """Class of exception during notification handling
    """
    def __init__(self, message=None):
        """
        Initialisation of the Oci Migrate Exception.

        Parameters
        ----------
        message: str
            The exception message.
        """
        self._message = message
        assert (self._message is not None), 'No exception message given'

        if self._message is None:
            self._message = 'An exception occurred, no further information'

    def __str__(self):
        """
        Get this OCISDKError representation.

        Returns
        -------
        str
            The error message.
        """
        return str(self._message)


class NotificationConfig:
    """Class to manage /etc/oci-utils/config, the oci-notify config file
    """

    def __init__(self, topic=None, config_file=OCI_CONFIG_FILE):
        """
        Initialisation of the oci-notification configuration.

        Parameters
        ----------
        topic: str
            The oci-notification topic.
        config_file: str
            The full path to the oci-notify config file.
        """
        self._topic = topic
        self._config_file = config_file
        self._instance_name = InstanceMetadata().refresh()['instance']['displayName']

    def get_notification_topic(self):
        """
        Read the notification topic from the oci notification config file.

        Returns
        -------
            str: the notification topic.
        """
        _logger.debug('_Collect the notification topic.')
        if not os.path.exists(self._config_file):
            raise NotificationException('Configuration for oci-notify not found.')

        notify_config_parser = configparser.ConfigParser()
        try:
            _ = notify_config_parser.read(self._config_file)
            # notification_topic = notify_config_parser.get('NOTIFICATION', 'topic')
            # return notification_topic
        except configparser.MissingSectionHeaderError as e:
            _logger.debug('Not a configparser file: %s', str(e))
            #
            # try to convert
            if self.convert_oci_config():
                _logger.debug('Successfully converted %s', self._config_file)
                #
                # re-read the configuration file
                notify_config_parser = configparser.ConfigParser()
                cfg = notify_config_parser.read(self._config_file)
            else:
                _logger.error('Failed to convert %s, exiting.', self._config_file)
                raise NotificationException('Failed to convert %s' % self._config_file) from e
        except Exception as e:
            _logger.error('Failed to retrieve the oci notification topic: %s', str(e))
            raise NotificationException('Failed to retrieve the oci notification topic') from e

        notification_topic = notify_config_parser.get('NOTIFICATION', 'topic')
        return notification_topic

    def convert_oci_config(self):
        """
        Convert oci_config from bash shell script to configuration file, for compatibility.

        Returns
        -------
            bool: True on success, False otherwise.
        """
        _logger.debug('_convert_oci_config_file: %s', self._config_file)
        #
        # backup file
        configfile_bck = self._config_file + '_backup_' + datetime.today().strftime('%Y-%m-%d-%H%M%S')
        shutil.move(self._config_file, configfile_bck)
        #
        # read and parse config file
        notification_ocid = None
        with open(configfile_bck, 'r') as cfg:
            for line in cfg:
                if line.startswith('topic=\"ocid') and 'onstopic' in line:
                    notification_ocid = line.strip().split('=')[1].strip('\"')
                    _logger.debug('Found notification topic %s', notification_ocid)
                    break
        if bool(notification_ocid):
            self.config_notification_service(notification_ocid)
            return True

        _logger.debug('Failed to convert %s, restoring', self._config_file)
        shutil.move(configfile_bck, self._config_file)
        return False

    def config_notification_service(self, notification_ocid):
        """
        Sets the Oracle Cloud Infrastructure notification service topic.

        Parameters
        ----------
        notification_ocid: str
            The ocid of the OCI notification topic.

        Returns
        -------
            tuple: config title, config message
        """
        _logger.debug('_config_notification_service: %s', notification_ocid)
        try:
            ocid_check = re.compile(r'^ocid[0-9]\.onstopic\.')
        except Exception as e:
            raise NotificationException('Failed to find notification topic in %s' % notification_ocid)

        if ocid_check.match(notification_ocid):
            _logger.debug('%s is a valid notification topic id.', notification_ocid)
        else:
            _logger.debug('%s is a not valid notification topic id.', notification_ocid)
            raise NotificationException('%s is a not valid notification topic id.' % notification_ocid)

        _logger.debug('Set notification service topic to %s.', notification_ocid)
        config_title = 'oci-utils: Notification enabled on instance %s' % self._instance_name
        config_message = 'Configured OCI notification service topic OCID on instance %s: %s' \
                         % (self._instance_name, notification_ocid)
        #
        # write notification topic, create file if necessary.
        # [NOTIFICATION]
        #    topic = <topic>
        notify_config_parse = configparser.ConfigParser()
        try:
            _ = notify_config_parse.read(self._config_file)
        except configparser.MissingSectionHeaderError:
            #
            # file exists but is not an configuration file;
            # suppose it is bash configuration script, trying to convert, restore the original if this fails
            _logger.debug('Found config file %s but is not a configuration file, trying to convert.', self._config_file)
            if self.convert_oci_config():
                _logger.debug('Successfully converted %s', self._config_file)
                #
                # re-read the configuration file
                notify_config_parse = configparser.ConfigParser()
                _ = notify_config_parse.read(self._config_file)
                return config_title, config_message

            _logger.debug('Failed to convert %s, exiting.', self._config_file)
            raise NotificationException('Failed to convert %s, exiting.' % self._config_file)
        #
        # read the config file if necessary
        try:
            #
            # file exists and is a valid config file or does not exist
            if not notify_config_parse.has_section('NOTIFICATION'):
                #
                # adding section NOTIFICATION
                notify_config_parse.add_section('NOTIFICATION')
            notify_config_parse.set('NOTIFICATION', 'topic', notification_ocid)
            with open(self._config_file, 'w') as cfgfile:
                notify_config_parse.write(cfgfile)
            #
            # todo:
            # 1. run test if notification topic is valid
            _logger.info('Configured OCI notification service topic OCID.')
            return config_title, config_message
        except Exception as e:
            # file exist and is not a valid config file, leave here with a message.
            _logger.error('An error occurred while setting up the Oracle Cloud Infrastructure notification service '
                          'topic: %s', str(e))
            raise Exception('An error occurred while setting up the Oracle Cloud Infrastructure notification service '
                            'topic') from e


class NotificationMessage():
    """ Class to send a message to an OCI notification service.
    """

    def __init__(self, title, message,
                 oci_config_file='~/.oci/config', oci_config_profile='DEFAULT', authentication_method=None):
        """
        Initialisation sending the message.

        Parameters
        ----------
        title: str
            The message subject.
        message: str
            The file or url containing the message.
        oci_config_file: str
            The full or relative path to the oci config file, for direct authentication.
        oci_config_profile: str
            The profile used for direct authentication.
        authentication_method: str
            The authentication method: NONE, DIRECT, IP, PROXY, AUTO
        """
        self._title = title
        if len(title) > MAX_MESSAGE_TITLE_LEN:
            self._title = title[:MAX_MESSAGE_TITLE_LEN]
            _logger.info("Cutting title to '[%s]'", self._title)
        self._message = message
        self._subject = ''
        # self._topic = self.get_notification_topic()
        self._topic = None
        self._oci_config_file = oci_config_file
        self._oci_config_profile = oci_config_profile
        self._oci_authentication = authentication_method
        self._message_type_str = False
        self._signer = None
        self._ons_client = None
        self._identity_client = None
        self._oci_config = None
        self._instance_name = InstanceMetadata().refresh()['instance']['displayName']
        self._auth_method = self.get_auth_method()

    @staticmethod
    def _read_oci_config(fname, profile='DEFAULT'):
        """
        Read the OCI config file.

        Parameters
        ----------
        fname : str
            The OCI configuration file name.
            # the file name should be ~/<fname> ?
        profile : str
            The user profile.

        Returns
        -------
        dictionary
            The oci configuration.

        Raises
        ------
        Exception
            If the configuration file does not exist or is not readable.
        """
        _logger.debug('_read_oci_config')
        full_fname = os.path.expanduser(fname)
        try:
            oci_config = oci_sdk.config.from_file(full_fname, profile)
            return oci_config
        except oci_sdk.exceptions.ConfigFileNotFound as e:
            _logger.debug("Unable to read OCI config file: %s", str(e))
            raise Exception('Unable to read OCI config file') from e

    def get_auth_method(self, authentication_method=None):
        """
        Determine how (or if) we can authenticate. If auth_method is
        provided, and is not AUTO then test if the given auth_method works.
        Return one of oci_api.DIRECT, oci_api.PROXY, oci_api.IP or
        oci_api.NONE (IP is instance principals).

        Parameters
        ----------
        authentication_method : [NONE | DIRECT | PROXY | AUTO | IP]
            if specified, the authentication method to be tested.

        Returns
        -------
        One of the oci_api.DIRECT, oci_api.PROXY, oci_api.IP or oci_api.NONE,
        the authentication method which passed or NONE.
            [NONE | DIRECT | PROXY | AUTO | IP]
        """
        _logger.debug('_get_auth_method')
        if authentication_method is None:
            auth_method = OCIUtilsConfiguration.get('auth', 'auth_method')
        else:
            auth_method = authentication_method

        _logger.debug('auth method retrieved from conf: %s', auth_method)

        # order matters
        _auth_mechanisms = {
            DIRECT: self._direct_authenticate,
            IP: self._ip_authenticate,
            PROXY: self._proxy_authenticate}

        if auth_method in _auth_mechanisms.keys():
            # user specified something, respect that choice
            try:
                _logger.debug('Trying %s auth', auth_method)
                _auth_mechanisms[auth_method]()
                _logger.debug('%s auth ok', auth_method)
                return auth_method
            except Exception as e:
                _logger.debug(' %s auth has failed: %s', auth_method, str(e))
                return NONE

        _logger.debug('Nothing specified trying to find an auth method')
        for method in _auth_mechanisms:
            try:
                _logger.debug('Trying %s auth', method)
                _auth_mechanisms[method]()
                _logger.debug('%s auth ok', method)
                return method
            except Exception as e:
                _logger.debug('%s auth has failed: %s', method, str(e))

        # no options left
        return NONE

    def _proxy_authenticate(self):
        """
        Use the auth helper to get config settings and keys
        Return True for success, False for failure

        Returns
        -------
        None

        Raises
        ------
        Exception
            The authentication using direct mode is noit possible
        """
        _logger.debug('_proxy_authenticate')
        if os.geteuid() != 0:
            raise Exception("Must be root to use Proxy authentication")

        sdk_user = OCIUtilsConfiguration.get('auth', 'oci_sdk_user')
        try:
            proxy = OCIAuthProxy(sdk_user)
            self._oci_config = proxy.get_config()
            self._identity_client = oci_sdk.identity.IdentityClient(self._oci_config)
            self._ons_client = oci_sdk.ons.NotificationDataPlaneClient(config=self._oci_config)
        except Exception as e:
            _logger.debug("Proxy authentication failed: %s", str(e))
            raise Exception("Proxy authentication failed") from e

    def _direct_authenticate(self):
        """
        Authenticate with the OCI SDK.

        Returns
        -------
        None

        Raises
        ------
        Exception
            The authentication using direct mode is not possible
        """
        _logger.debug('_direct_authenticate')
        try:
            self._oci_config = self._read_oci_config(fname=self._oci_config_file, profile=self._oci_config_profile)
            self._identity_client = oci_sdk.identity.IdentityClient(self._oci_config)
            self._ons_client = oci_sdk.ons.NotificationDataPlaneClient(config=self._oci_config)
        except Exception as e:
            _logger.debug('Direct authentication failed: %s', str(e))
            raise Exception("Direct authentication failed") from e

    def _ip_authenticate(self):
        """
        Authenticate with the OCI SDK using instance principal .

        Returns
        -------
        None

        Raises
        ------
        Exception
            If IP authentication fails.
        """
        _logger.debug('_ip_authenticate')
        try:
            self._signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
            self._identity_client = oci_sdk.identity.IdentityClient(config={}, signer=self._signer)
            self._ons_client = oci_sdk.ons.NotificationDataPlaneClient(config={}, signer=self._signer)
        except Exception as e:
            _logger.debug('Instance Principals authentication failed: %s', str(e))
            raise Exception('Instance Principals authentication failed') from e

    def _get_topic(self):
        """
        Retrieve the notification topic ocid.
        Returns
        -------
            bool: True on success, raises an exception otherwise.
        """
        _logger.debug('_get_topic')
        try:
            config_data = NotificationConfig()
            self._topic = config_data.get_notification_topic()
            return True
        except Exception as e:
            _logger.debug('Failed to get notification topic: %s', str(e))
            raise NotificationException('Failed to get notification topic.')

    def _message_title(self):
        """
        Handle the message subject, truncate if necessary.

        Returns
        -------
            str: the message subject.
        """
        _logger.debug('_message_title')
        subject = self._message[:MAX_MESSAGE_TITLE_LEN]
        _logger.debug('_Message subject: %s', subject)
        return subject

    def _message_data(self):
        """
        Determine the message type, flat file or url
        if flat file, verify if it exist and is readable.
        if url, verify if it is accessible.

        Returns
        -------
            tuple: (str: message type, bool: accessible, int: size)

        """
        def file_message(message):
            """
            Collect data about a FILE message.

            Parameters
            ----------
            message: str
                The path of the file.

            Returns
            -------
                tuple: (bool: accessible, int: size, str: path to local file)
            """
            _logger.debug('_file %s', message)
            msg_access = False
            msg_size = -1
            if os.path.isfile(self._message) and os.access(message, os.R_OK):
                _logger.debug('%s exist and is readable', message)
                msg_access = True
                msg_size = os.stat(message).st_size
            else:
                _logger.error('%s is not accessible.', message)
            return msg_access, msg_size, message

        def url_message(message):
            """
            Collect data about a URL message.
            (we do not care if the url contains data which is not 'downloadable..)

            Parameters
            ----------
            message: str
                The url.

            Returns
            -------
                tuple: (bool: accessible, int: size, str: path to local file)
            """
            _logger.debug('_url %s', message)
            msg_access = False
            msg_size = -1
            msg_fn = None
            try:
                msg_fn, url_head = urllib.request.urlretrieve(message)
                msg_access = True
                msg_size = os.stat(msg_fn).st_size
            except Exception as e:
                _logger.error('%s is not accessible.', message)
                _logger.error('%s', str(e))
            return msg_access, msg_size, msg_fn

        _logger.debug('_message_data')
        _logger.debug('Testing message type %s', self._message)

        url_check = re.compile('^(https?|ftp|file)://')
        if url_check.match(self._message):
            _logger.debug('Message is URL')
            message_type = 'URL'
            message_access, message_size, message_fn = url_message(self._message)
            _logger.debug('url: %s %s %s %d %s', self._message, message_type, message_access, message_size, message_fn)
        elif os.path.exists(self._message):
            _logger.debug('Message is a flat file.')
            message_type = 'FILE'
            message_access, message_size, message_fn = file_message(self._message)
            _logger.debug('file: %s %s %s %d %s', self._message, message_type, message_access, message_size, message_fn)
        else:
            _logger.debug('Message is a string.')
            message_type = 'TEXT'
            message_access = True
            message_size = len(self._message)
            message_fn = 'text message'

        return message_type, message_access, message_size, message_fn

    def send_notification(self):
        """
        Send a notification.

        Returns
        -------
            bool: True on success, raises an exception otherwise.
        """
        _logger.debug('_send_notification')
        try:
            self._get_topic()
        except Exception as e:
            _logger.debug('Failed to get notification topic: %s', str(e))
            raise NotificationException('Failed to get notification topic.') from e

        try:
            m_type, m_access, m_size, m_fn = self._message_data()
            if m_access:
                # accessible
                if m_type == 'TEXT':
                    _logger.debug('Sending string %s', self._message)
                    self.send_message_chunk(self._message, 1, 1)
                    return True
                with open(m_fn, 'rb') as m_fb:
                    msg_cnt = 0
                    msg_cnt_tot_tuple = divmod(m_size, CHUNK_SIZE)
                    msg_cnt_tot = msg_cnt_tot_tuple[0] + 1 if msg_cnt_tot_tuple[1] != 0 else msg_cnt_tot_tuple[0]
                    while True:
                        msg_chunk = m_fb.read(CHUNK_SIZE).decode('utf-8')
                        if not msg_chunk:
                            break
                        msg_cnt += 1
                        _logger.debug('Sending %d/%d', msg_cnt, msg_cnt_tot)
                        self.send_message_chunk(msg_chunk, msg_cnt, msg_cnt_tot)
                        if msg_cnt >= MAX_MESSAGE_CHUNKS:
                            _logger.info('Maximum of %d chunks exceeded.', MAX_MESSAGE_CHUNKS)
                            break
            return True
        except Exception as e:
            _logger.debug('Failed to send %s: %s', m_fn, str(e))
            raise NotificationException('Failed to send %s' % m_fn) from e

    def send_message_chunk(self, chunk, nb, nbtot):
        """
        Send notification message fragment.

        Parameters
        ----------
        chunk: str
            The fragment.
        nb: int
            The number of the fragment.
        nbtot: int
            The total number of fragments

        Returns
        -------
            bool: True on success, raises an exception otherwise.
        """
        _logger.debug('_send_message_chunk')
        try:
            _logger.debug('_Send chunk %d of %d', nb, nbtot)
            if nbtot <= 1:
                _logger.info("Publishing message '%s: %s'", self._instance_name, self._title)
            else:
                _logger.info("Publishing message '[%d/%d] %s: %s'", nb, nbtot, self._instance_name, self._title)
            _message_details = oci_sdk.ons.models.MessageDetails(body=chunk, title=self._instance_name
                                                                                   + ':'
                                                                                   + 'self._title)
            request_id = uuid.uuid4().hex
            _logger.debug('Message request id: %s', request_id)
            publish_message_response = self._ons_client.publish_message(topic_id=self._topic,
                                                                        message_details=_message_details,
                                                                        opc_request_id=request_id,
                                                                        message_type="RAW_TEXT")
            if nbtot <= 1:
                _logger.info("Published message '%s: %s'", self._instance_name, self._title)
            else:
                _logger.info("Published message '[%d/%d] %s: %s'", nb, nbtot, self._instance_name, self._title)
            _logger.debug('Published response: %s', publish_message_response.data)
            return True
        except Exception as e:
            err_msg = e.message if hasattr(e, 'message') else e.code
            _logger.debug('Failed to publish %s: %s', self._title, e.args)
            _logger.error('Failed to publish %s: %s', self._title, err_msg)
            raise NotificationException('Failed to publish %s' % self._title) from e


def main():
    """

    Returns
    -------

    """
    #
    # locale
    os.environ['LC_ALL'] = "%s" % lc_all

    if not is_root():
        _logger.error('This program needs to be run with root privileges.')
        sys.exit(1)

    sub_commands = {'config': config_notification_service_wrap,
                    'message': handle_message_wrap}

    parser = parse_args()
    args = parser.parse_args()
    if args.mode is None:
        parser.print_help()
        sys.exit(0)

    try:
        res = sub_commands[args.mode](args)
        if not res:
            raise NotificationException('Failed to execute %s' % sub_commands[args.mode])
    except Exception as e:
        _logger.debug('*** ERROR *** %s', str(e), stack_info=True, exc_info=True)
        _logger.error('*** ERROR *** %s', str(e))
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
