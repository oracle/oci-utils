# oci-utils
#
# Copyright (c) 2019. 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.


"""
This utility assists with configuring iscsi storage on Oracle Cloud
Infrastructure instances.  See the manual page for more information.
"""

import argparse
import logging
import subprocess
import sys
import termios
import time
import tty
from datetime import timedelta

import oci_utils.oci_api
from oci_utils import MAX_VOLUMES_LIMIT
from oci_utils import OCI_VOLUME_SIZE_FMT
from oci_utils import __chap_password_file
from oci_utils import __ignore_file, iscsiadm, lsblk, is_root_user
from oci_utils import _configuration as OCIUtilsConfiguration
from oci_utils import where_am_i
from oci_utils.cache import load_cache, write_cache
from oci_utils.cache import load_cache_11876, write_cache_11876
from oci_utils.impl.row_printer import get_row_printer_impl
from oci_utils.impl.row_printer_helpers import get_value_data
from oci_utils.impl.row_printer_helpers import initialise_column_lengths
from oci_utils.impl.row_printer_helpers import print_data
from oci_utils.metadata import InstanceMetadata

_logger = logging.getLogger("oci-utils.oci-iscsi-config")

oci_volume_tag = 'ocid1.volume.'
iqn_tag = 'iqn.'
cache_loop = 3
cache_delay = 65


class IscsiConfigException(Exception):
    """Class of exceptions during notification handling
    """
    def __init__(self, message=None):
        """
        Initialisation of the Oci NetworkConfig Exception.

        Parameters
        ----------
        message: str
            The exception message.
        """
        super().__init__()
        self._message = message
        assert (self._message is not None), 'No exception message given, no further information.'

    def __str__(self):
        """
        Get this OCISDKError representation.

        Returns
        -------
        str
            The error message.
        """
        return str(self._message)


def def_usage_parser(s_parser):
    """
    Define the usage parser.

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the usage subcommand parser.
    """
    usage_parser = s_parser.add_parser('usage',
                                       description='Displays usage',
                                       help='Displays usage'
                                       )
    # for compatibility mode
    usage_parser.add_argument('--compat',
                              action='store_true',
                              default=False,
                              help=argparse.SUPPRESS
                              )
    return usage_parser


def def_sync_parser(s_parser):
    """
    Define the sync subparser.

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the sync subcommand parser.
    """
    sync_parser = s_parser.add_parser('sync',
                                      description='Try to attach available block devices.',
                                      help='Try to attach available block devices.'
                                      )
    sync_parser.add_argument('-a', '--apply',
                             action='store_true',
                             default=False,
                             help='Perform sync operations.'
                             )
    sync_parser.add_argument('-y', '--yes',
                             action='store_true',
                             help='Assume yes.'
                             )
    # kept for compatibility reason. keep it hidden
    sync_parser.add_argument('-i', '--interactive',
                             action='store_true',
                             default=False,
                             help=argparse.SUPPRESS
                             )
    return sync_parser


def def_show_all_parser(s_parser):
    """
    Define the show-all parser

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the show-all subcommand parser.

    """
    #
    # show all volumes all details
    show_all_parser = s_parser.add_parser('show-all',
                                          description='Show all volumes with details in this availability domain.',
                                          help='Show all volumes with details in this availability domain.'
                                          )
    show_all_parser.add_argument('-t', '--truncate',
                                 action='store_true',
                                 help=argparse.SUPPRESS
                                 )
    show_all_parser.add_argument('--output-mode',
                                 choices=('parsable', 'table', 'json', 'text'),
                                 help='Set output mode.',
                                 default='table'
                                 )
    return show_all_parser


def def_show_parser(s_parser):
    """
    Define the show parser

    Parameters
    ----------
    s_parser: subparsers.

    Returns
    -------
        ArgumentParser: the show subcommand parser.
    """
    show_parser = s_parser.add_parser('show',
                                      description='Show block volumes and iSCSI information.',
                                      help='Show block volumes and iSCSI information.'
                                      )
    show_parser.add_argument('-C', '--compartments',
                             metavar='COMP',
                             default=(),
                             type=lambda s: [ocid.strip() for ocid in s.split(',') if ocid],
                             help='Display iSCSI devices in the given comparment(s) '
                                  'or all compartments if COMP is  "all".'
                             )
    show_parser.add_argument('-A', '--all',
                             action='store_true',
                             default=False,
                             help='Display all iSCSI devices. By default only devices that are not attached '
                                  'to an instance are listed.')
    show_parser.add_argument('--output-mode',
                             choices=('parsable', 'table', 'json', 'text'),
                             help='Set output mode.',
                             default='table'
                             )
    show_parser.add_argument('--details',
                             action='store_true',
                             default=False,
                             help='Display detailed information.'
                             )
    show_parser.add_argument('--no-truncate',
                             action='store_true',
                             default=False,
                             help='Do not truncate value during output.'
                             )
    show_parser.add_argument('--compat',
                             action='store_true',
                             default=False,
                             help=argparse.SUPPRESS
                             )
    return show_parser


def def_create_parser(s_parser):
    """
    Define the create parser

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the create subcommand parser
    """
    create_parser = s_parser.add_parser('create',
                                        description='Creates a block volume.',
                                        help='Creates a block volume.'
                                        )
    create_parser.add_argument('-S', '--size',
                               type=volume_size_validator,
                               required=True,
                               help='Size of the block volume to create in GB, mandatory.'
                               )
    create_parser.add_argument('-v', '--volume-name',
                               help='Name of the block volume to create.')
    create_parser.add_argument('--attach-volume',
                               action='store_true',
                               help='Once created, should the volume be attached?'
                               )
    create_parser.add_argument('-c', '--chap',
                               action='store_true',
                               default=False,
                               help='Attach the device with the Require Chap Credentials flag.'
                               )
    create_parser.add_argument('--compat',
                               action='store_true',
                               default=False,
                               help=argparse.SUPPRESS
                               )
    return create_parser


def def_attach_parser(s_parser):
    """
    Define the attach parser.

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the attach subcommand parser
    """
    attach_parser = s_parser.add_parser('attach',
                                        description='Attach a block volume to this instance '
                                                    'and make it available to the system.',
                                        help='Attach a block volume to this instance '
                                             'and make it available to the system.'
                                        )
    ocidiqn = attach_parser.add_mutually_exclusive_group(required=True)
    ocidiqn.add_argument('-I', '--iqns',
                         type=attachable_iqn_list_validator,
                         help='Comma separated list of IQN(s) or OCID(s) of the iSCSI devices to be attached.'
                         )
    ocidiqn.add_argument('-O', '--ocids',
                         type=attachable_iqn_list_validator,
                         help='Comma separated list of OCID(s) or IQN(s) of the iSCSI devices to be attached.'
                         )
    attach_parser.add_argument('-u', '--username',
                               metavar='USER',
                               action='store',
                               help='Use USER as the user name when attaching a device that requires CHAP '
                                    'authentication.'
                               )
    attach_parser.add_argument('-p', '--password',
                               metavar='PASSWD',
                               action='store',
                               help='Use PASSWD as the password when attaching a device that requires CHAP '
                                    'authentication.'
                               )
    attach_parser.add_argument('-c', '--chap',
                               action='store_true',
                               default=False,
                               help='Attach the device with the Require Chap Credentials flag.'
                               )
    attach_parser.add_argument('--compat',
                               action='store_true',
                               default=False,
                               help=argparse.SUPPRESS
                               )
    return attach_parser


def def_detach_parser(s_parser):
    """
    Define the detach subcommand parser.

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the detach subcommand parser
    """
    detach_parser = s_parser.add_parser('detach',
                                        description='Detach a block volume',
                                        help='Detach a block volume'
                                        )
    detach_parser.add_argument('-I', '--iqns',
                               required=True,
                               type=detachable_iqn_list_validator,
                               help='Comma separated list of IQN(s) of the iSCSI devices to be detached.'
                               )
    detach_parser.add_argument('-f', '--force',
                               action='store_true',
                               help='Continue detaching even if device cannot be unmounted.'
                               )
    detach_parser.add_argument('-i', '--interactive',
                               action='store_true',
                               help=argparse.SUPPRESS
                               )
    detach_parser.add_argument('--compat',
                               action='store_true',
                               default=False,
                               help=argparse.SUPPRESS
                               )
    return detach_parser


def def_destroy_parser(s_parser):
    """
    Define the destroy subcommand parser.

    Parameters
    ----------
    s_parser: subparsers

    Returns
    -------
        ArgumentParser: the destroy subcommand parser
    """
    destroy_parser = s_parser.add_parser('destroy',
                                         description='Destroy a block volume.',
                                         help='Destroy a block volume.'
                                         )
    destroy_parser.add_argument('-O', '--ocids',
                                required=True,
                                type=volume_oci_list_validator,
                                help='OCID(s) of volumes to be destroyed.'
                                )
    destroy_parser.add_argument('-y', '--yes',
                                action='store_true',
                                help='Assume yes, otherwise be interactive.'
                                )
    # kept for compatibility reason. keep it hidden
    destroy_parser.add_argument('-i', '--interactive',
                                action='store_true',
                                help=argparse.SUPPRESS
                                )
    destroy_parser.add_argument('--compat',
                                action='store_true',
                                default=False,
                                help=argparse.SUPPRESS
                                )
    return destroy_parser


def get_args_parser():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The commandline argparse namespace.
    """
    parser = argparse.ArgumentParser(prog='oci-iscsi-config',
                                     description='Utility for listing or configuring iSCSI devices on an OCI instance.'
                                     )
    subparser = parser.add_subparsers(dest='command')
    #
    # usage
    _ = def_usage_parser(subparser)
    #
    # sync
    _ = def_sync_parser(subparser)
    #
    # show-all
    _ = def_show_all_parser(subparser)
    #
    # show
    _ = def_show_parser(subparser)
    #
    # create
    _ = def_create_parser(subparser)
    #
    # attach
    _ = def_attach_parser(subparser)
    #
    # detach
    _ = def_detach_parser(subparser)
    #
    # destroy
    _ = def_destroy_parser(subparser)

    return parser


def volume_size_validator(value):
    """
    Validate than value passed is an int and greater than 50 (GB).

    Parameters
    ----------
        value: str
           Size in GB.

    Returns
    -------
        int: size in GB on success.
    """
    _logger.debug('%s', where_am_i())
    _i_value = 0
    try:
        _i_value = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("Block volume size must be a int") from e

    if _i_value < 50:
        raise argparse.ArgumentTypeError("Volume size must be at least 50GBs")
    return _i_value


def attachable_iqn_list_validator(value):
    """
    Validate that value passed is a list of iqn and/or ocid.

    Parameters
    ----------
        value: str
           A comma separated list of iqn's.

    Returns
    -------
        list: a list of iqn's.
    """
    _logger.debug('%s', where_am_i())
    _iqns = [iqn.strip() for iqn in value.split(',') if iqn]
    for iqn in _iqns:
        if not iqn.startswith(iqn_tag) and not iqn.startswith(oci_volume_tag):
            raise argparse.ArgumentTypeError('Invalid IQN %s' % iqn)
    return _iqns


def detachable_iqn_list_validator(value):
    """
    Validate the value passed is a list of iqn and does not contain boot volume.

    Parameters
    ----------
        value: str
           A comma separated list of iqn's.

    Returns
    -------
        list: a list of iqn's.
    """
    _logger.debug('%s', where_am_i())
    _iqns = [iqn.strip() for iqn in value.split(',') if iqn]
    for iqn in _iqns:
        if not iqn.startswith(iqn_tag):
            raise argparse.ArgumentTypeError('Invalid IQN %s' % iqn)
        if 'boot:uefi' in iqn:
            raise argparse.ArgumentTypeError('Cannot detach boot volume IQN %s' % iqn)
    return _iqns


def volume_oci_list_validator(value):
    """
    Validate than value passed is a list of volume ocid's.

    Parameters
    ----------
        value: str
            A comma separated list of ocid's.

    Returns
    -------
        list: a list of ocid's
    """
    _logger.debug('%s', where_am_i())
    _ocids = [ocid.strip() for ocid in value.split(',') if ocid]
    for ocid in _ocids:
        if not ocid.startswith(oci_volume_tag):
            raise argparse.ArgumentTypeError('Invalid volume OCID %s' % ocid)
    return _ocids


def _getch():
    """
    Read a single keypress from stdin.

    Returns
    -------
        The resulting character.
    """
    _logger.debug('%s', where_am_i())
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def _read_yn(prompt, yn=True, waitenter=False, suppose_yes=False, default_yn=False):
    """
    Read yes or no form stdin, No being the default.

    Parameters
    ----------
        prompt: str
            The message.
        yn: bool
            Add (y/N) to the prompt if True.
        waitenter: bool
            Wait for the enter key pressed if True, proceed immediately
            otherwise.
        suppose_yes: bool
            if True, consider the answer is yes.
        default_yn: bool
            The default answer.
    Returns
    -------
        bool: True on yes, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    yn_prompt = prompt + ' '
    #
    # if yes is supposed, write prompt and return True.
    if suppose_yes:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        return True
    #
    # add y/N to prompt if necessary.
    if yn:
        if default_yn:
            yn_prompt += ' (Y/n)'
            yn = 'Y'
        else:
            yn_prompt += ' (y/N) '
            yn = 'N'
    #
    # if wait is set, wait for return key.
    if waitenter:
        resp_len = 0
        while resp_len == 0:
            resp = input(yn_prompt).lstrip()
            resp_len = len(resp)
        yn_i = list(resp)[0].rstrip()
    #
    # if wait is not set, proceed on any key pressed.
    else:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        yn_i = _getch().rstrip()

    sys.stdout.write('\n')
    if bool(yn_i):
        yn = yn_i
    return bool(yn.upper() == 'Y')


def ask_yes_no(question):
    """
    Ask the user a question and enforce a yes/no answer.

    Parameters
    ----------
    question : str
        The question.

    Returns
    -------
        bool
            True for yes, False for no.
    """
    _logger.debug('%s', where_am_i())
    while True:
        print(question)
        ans = input().lower()
        if ans in ['y', 'yes']:
            return True
        if ans in ['n', 'no']:
            return False
        print("Invalid answer, please answer with yes or no")


def compat_info_message(compat_msg=None, gen_msg=None, mode='gen'):
    """
    Differentiate message for compat and generic mode.

    Parameters:
    ----------
        compat_msg: str
            Message for mode 'compat'.
        gen_msg: str
            Message for other modes.

    Returns:
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    if bool(compat_msg):
        if mode == 'compat':
            _logger.info(compat_msg)
    if bool(gen_msg):
        if mode != 'compat':
            _logger.info(gen_msg)


def show_usage(usage_args):
    """
    Wrapper for showing usage info.

    Parameters
    ----------
    usage_args:
        The command line arguments.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    return True


def get_iscsiadm_session():
    """
    Find the attached block volumes, except the boot volume.

    Returns
    -------
        dict: the attached block volumes and their data.
    """
    _logger.debug('%s', where_am_i())
    all_volumes = iscsiadm.session()
    iscsiadmsession = dict((iqn, all_volumes[iqn]) for iqn in all_volumes if 'boot:uefi' not in iqn)
    return iscsiadmsession


def get_columns(details, mode, column_lengths):
    """
    Set the column lenghts.

    Parameters
    ----------
    details: bool
        If True, include the 'details'
    mode: str
        The output mode.
    column_lengths: list
        The column lengths.

    Returns
    -------
        list: the columns lenghts.
    """
    _logger.debug('%s', where_am_i())
    columns = list()
    if details:
        columns.append(['Target', column_lengths['target']+2, 'target'])
    columns.append(['Volume Name', column_lengths['name']+2, 'name'])
    if details:
        columns.append(['Volume OCID', column_lengths['ocid']+2, 'ocid'])
        columns.append(['Persistent Portal', column_lengths['p_portal']+2, 'p_portal'])
        columns.append(['Current Portal', column_lengths['c_portal']+2, 'c_portal'])
        columns.append(['Session State', column_lengths['s_state']+2, 's_state'])
    columns.append(['Attached Device', column_lengths['dev']+2, 'dev'])
    columns.append(['Size', column_lengths['size']+2, 'size'])
    if details or mode in ['text', 'parsable']:
        columns.append(['Mountpoint', column_lengths['mountpoint']+2, 'mountpoint'])
        columns.append(['Filesystem', column_lengths['fstype']+2, 'fstype'])
    return columns


def get_volume_by_iqn(sess, iqn):
    """
    Gets a volume by given IQN

    Parameters
    ----------
    sess: OCISession
        The OCISEssion instance.
    iqn: str
        The iSCSI qualified name.

    Returns
    -------
       OCIVolume : the found volume or None
    """
    _logger.debug('%s: %s', where_am_i(), iqn)
    try:
        if bool(sess):
            get_volume_by_iqn.all_this_instance_volume = sess.this_instance().all_volumes()
            for volume in get_volume_by_iqn.all_this_instance_volume:
                if volume.get_iqn() == iqn:
                    _logger.debug('Found %s', str(volume))
                    return volume
        else:
            _logger.info('Unable to get volume ocid and display name for iqn [%s], ', iqn)
    except Exception as e:
        _logger.debug('Failed to get volume data for iqn [%s]: %s', iqn, str(e), stack_info=True, exc_info=True)
        _logger.error('Failed to get volume data for iqn [%s]', iqn)
    return None


def collect_volumes_data(oci_session, iscsi_session, disks, col_lengths):
    """
    Collect data from volumes with respect to display.

    Parameters
    ----------
    oci_session: OCISession
        An oci api session.
    iscsi_session: list
        The list of iscsi devices.
    disks: dict
        Volume and partition data.
    col_lengths: list
        The max lengths of the volume paramter values and the headers.

    Returns
    -------
        tuple: (dict, list)
            (The volume data, The max lenghts)
    """
    volumes_data = list()
    for iqn in list(iscsi_session.keys()):
        # _item = {}
        _vol_data = dict()
        # target
        _vol_data['target'] = iqn
        col_lengths['target'] = max(len(iqn), col_lengths['target'])
        #
        oci_vol = get_volume_by_iqn(oci_session, iqn)
        if oci_vol is not None:
            # name
            _vol_data['name'] = oci_vol.get_display_name()
            col_lengths['name'] = max(len(_vol_data['name']), col_lengths['name'])
            # ocid
            _vol_data['ocid'] = oci_vol.get_ocid()
            col_lengths['ocid'] = max(len(_vol_data['ocid']), col_lengths['ocid'])
        # persistent portal
        _vol_data['p_portal'] = "%s:%s" \
                                % (iscsi_session[iqn]['persistent_portal_ip'],
                                   iscsi_session[iqn]['persistent_portal_port'])
        col_lengths['p_portal'] = max(len(_vol_data['p_portal']), col_lengths['p_portal'])
        # current portal
        _vol_data['c_portal'] = "%s:%s" \
                                % (iscsi_session[iqn]['current_portal_ip'],
                                   iscsi_session[iqn]['current_portal_port'])
        col_lengths['c_portal'] = max(len(_vol_data['c_portal']), col_lengths['c_portal'])
        # session state
        _vol_data['s_state'] = iscsi_session[iqn].get('session_state', 'n/a')
        col_lengths['s_state'] = max(len(_vol_data['s_state']), col_lengths['s_state'])
        # device
        device = iscsi_session[iqn].get('device', None)
        if device is None:
            _vol_data['dev'] = '(not attached)'
        else:
            _vol_data['dev'] = device
            if device in disks:
                # size
                _vol_data['size'] = disks[device]['size']
                col_lengths['size'] = max(len(_vol_data['size']), col_lengths['size'])
                # mountpoint
                _vol_data['mountpoint'] = disks[device]['mountpoint'] if disks[device]['mountpoint'] != '' else '-'
                col_lengths['mountpoint'] = max(len(_vol_data['mountpoint']), col_lengths['mountpoint'])
                # fstype
                _vol_data['fstype'] = disks[device]['fstype'] if disks[device]['fstype'] != '' else '-'
                col_lengths['fstype'] = max(len(_vol_data['fstype']), col_lengths['fstype'])
        _vol_dev_len = len(_vol_data['dev'])
        col_lengths['dev'] = max(_vol_dev_len, col_lengths['dev'])
        volumes_data.append(_vol_data)

    return volumes_data, col_lengths


def _display_oci_volume_list(volumes, args):
    """
    Display information about list of block volumes.

    Parameters
    ----------
        volumes: list
            List of OCIVOlumes
        args: namespace
            the command line
    """

    def _get_displayable_size(_, volume):
        """
        Get the volume sizes.

        Parameters
        ----------
        _
        volume: OCIVolume
            volume object

        Returns
        -------
            str: the volume size.
        """
        return volume.get_size(format_str=OCI_VOLUME_SIZE_FMT.HUMAN.name)

    def _get_attached_instance_name(_, volume):
        """
        Get the instance name the volume is attached to.

        Parameters
        ----------
        _
        volume: OCIVolume
            volume object

        Returns
        -------
            str: instance display name
        """
        global _this_instance_ocid
        if not volume.is_attached():
            return '-'
        _vol_instance_attach_to = volume.get_instance()

        if _vol_instance_attach_to.get_ocid() == _this_instance_ocid:
            return "this instance"
        pip = _vol_instance_attach_to.get_public_ip()
        if pip:
            return "%s (%s)" % (_vol_instance_attach_to.get_display_name(), _vol_instance_attach_to.get_public_ip())
        return _vol_instance_attach_to.get_display_name()

    def _get_comp_name(_, volume):
        """
        Get the compartment name.

        Parameters
        ----------
        _
        volume: OCIVolume
            volume object

        Returns
        -------
            str: the compartment name
        """
        _map = getattr(_get_comp_name, 'c_id_to_name', {})
        if volume.get_compartment_id() not in _map:
            _map[volume.get_compartment_id()] = volume.get_compartment().get_display_name()
        setattr(_get_comp_name, 'c_id_to_name', _map)
        return _map[volume.get_compartment_id()]

    def _get_vol_data_iqn(_, volume):
        """
        Get the iqn of the volume.

        Parameters
        ----------
        _
        volume: OCIVolume
            volume object

        Returns
        -------
            str: the iqn of the volume.
        """
        iqn = volume.get_iqn()
        return iqn if iqn is not None else '-'

    _logger.debug('%s', where_am_i())

    _data_struct = {
        'name':       {'head': 'Name',        'func': 'get_display_name', 'type': 'str', 'collen': 8},
        'size':       {'head': 'Size',        'func': 'get_size',         'type': 'str', 'collen': 6},
        'attachedto': {'head': 'Attached to', 'attrib': 'attachedto',     'type': 'str', 'collen': 15},
        'ocid':       {'head': 'OCID',        'func': 'get_ocid',         'type': 'str', 'collen': 32},
        }
    _data_struct_detail = {
        'iqn':         {'head': 'iqn',                 'func': 'get_iqn',                               'type': 'str', 'collen': 32},
        'compartment': {'head': 'Compartment',         'func': ['get_compartment', 'get_display_name'], 'type': 'str', 'collen': 14},
        'availdomain': {'head': 'Availability Domain', 'func': 'get_availability_domain_name',          'type': 'str', 'collen': 19},
        }
    #
    # add details information
    if args.details:
        _data_struct.update(_data_struct_detail)
    #
    # initialise the column widths if no-truncate is set
    if args.no_truncate:
        _data_struct = initialise_column_lengths(_data_struct)

    if len(volumes) == 0:
        print('No other volumes found.')
    else:
        volumes_data = list()
        for vol in volumes:
            vol.attachedto = _get_attached_instance_name(None, vol)
            vol.compartment = _get_comp_name(None, vol)
            vol.iqn = _get_vol_data_iqn(None, vol)

            _vol_data = dict()
            for key, _ in _data_struct.items():
                value_data = get_value_data(vol, _data_struct[key])
                _vol_data[key] = value_data[0]
                val_length = value_data[1]
                if args.no_truncate:
                    _data_struct[key]['collen'] = max(val_length, _data_struct[key]['collen'])
            volumes_data.append(_vol_data)

        _title = 'Block volumes information:'

        if args.output_mode == 'compat':
            title = 'Other available storage volumes:'
        else:
            title = 'Other available storage volumes'
        print_data(title,
                   _data_struct, volumes_data,
                   mode=args.output_mode,
                   truncate=not args.no_truncate)

        return True


def display_attached_volumes(oci_sess, iscsiadm_session, disks, args):
    """
    Display the attached iSCSI devices.

    Parameters
    ----------
    oci_sess: OCISession
        An OCI session
    iscsiadm_session: dict
        An iscsiadm session (as returned by oci_utils.iscsiadm.session())
    disks: dict
        List of disk to be displayed. Information about disks in the system,
        as returned by lsblk.list_blk_dev()
    args: nomespace
        The command line arguments.

    Returns
    -------
       No return value.
    """
    #
    # todo: handle the None ocisession more elegantly.
    oci_vols = list()
    try:
        if bool(oci_sess):
            oci_vols = sorted(oci_sess.this_instance().all_volumes())
    except Exception as e:
        _logger.debug('Cannot get all volumes of this instance : %s', str(e))

    if not iscsiadm_session and len(oci_vols) > 0:
        #
        # iscsiadm does not show volumes, oci_api.session does, attached volumes but not connected.
        print("Local iSCSI info not available.")
        print("List info from Cloud instead(No boot volume).")
        print("")
        _display_oci_volume_list(oci_vols, args)
        return

    _cols = ['Target',
             'Volume Name',
             'Volume OCID',
             'Persistent Portal',
             'Current Portal',
             'Session State',
             'Attached Device',
             'Size',
             'Mountpoint',
             'Filesystem']
    _col_name = ['target',
                 'name',
                 'ocid',
                 'p_portal',
                 'c_portal',
                 's_state',
                 'dev',
                 'size',
                 'mountpoint',
                 'fstype']
    _cols_len = list()
    for col in _cols:
        _cols_len.append(len(col))

    volumes_data, _collen = collect_volumes_data(oci_sess, iscsiadm_session, disks, dict(zip(_col_name, _cols_len)))

    if not args.no_truncate:
        _collen = {'target': 32,
                   'name': 13,
                   'ocid': 32,
                   'p_portal': 20,
                   'c_portal': 20,
                   's_state': 13,
                   'dev': 15,
                   'size': 6,
                   'mountpoint': 12,
                   'fstype': 12}

    _columns = get_columns(args.details, args.output_mode, _collen)

    # this is only to be used in compatibility mode, text mode or parsable mode, for now.
    partitionPrinter = get_row_printer_impl(args.output_mode)(title='\nPartitions:\n',
                                                              columns=(['Device', 8, 'dev_name'],
                                                                       ['Size', 6, 'size'],
                                                                       ['Filesystem', 12, 'fstype'],
                                                                       ['Mountpoint', 12, 'mountpoint']))

    iscsi_dev_printer = None
    if len(volumes_data) == 0:
        print('No iSCSI devices attached.')
    else:
        _title = 'Currently attached iSCSI devices:'
        iscsi_dev_printer = get_row_printer_impl(args.output_mode)(title=_title,
                                                                   columns=_columns,
                                                                   text_truncate=args.no_truncate)
    if bool(iscsi_dev_printer):
        iscsi_dev_printer.printHeader()
        for _item in volumes_data:
            iscsi_dev_printer.printRow(_item)
            if args.output_mode in ['compat', 'text', 'parsable']:
                if 'partitions' not in disks[_item['dev']]:
                    #
                    fstype = disks[_item['dev']]['fstype'] \
                        if bool(disks[_item['dev']]['fstype']) \
                        else 'Unknown'
                    iscsi_dev_printer.printKeyValue('File system type', fstype)
                    mntpoint = disks[_item['dev']]['mountpoint'] \
                        if bool(disks[_item['dev']]['mountpoint']) \
                        else 'Not mounted'
                    iscsi_dev_printer.printKeyValue('Mountpoint', mntpoint)
                else:
                    partitions = disks[_item['dev']]['partitions']
                    partitionPrinter.printHeader()
                    for part in sorted(list(partitions.keys())):
                        # add it as we need it during the print
                        partitions[part]['dev_name'] = part
                        partitionPrinter.printRow(partitions[part])
                        partitionPrinter.rowBreak()
                    partitionPrinter.printFooter()
                    if not args.output_mode == 'parsable':
                        partitionPrinter.finish()
            iscsi_dev_printer.rowBreak()
        iscsi_dev_printer.printFooter()
        iscsi_dev_printer.finish()
    return


def api_display_available_block_volumes(sess, args):
    """
    Display the available devices for the compartments specified.

    Parameters
    ----------
    sess: OCISession
        The OCISession instance.
    args: namespace
        The command line.

    Returns
    -------
        No return value.
    """
    _logger.debug('%s', where_am_i())
    _title = "Other available storage volumes:"
    if sess is None:
        _logger.info("Failed to create session, unable to show available volumes.")
        return

    vols = []
    compartments = args.compartments
    if len(compartments) > 0:
        #
        # -C/--compartment option used
        for cspec in compartments:
            try:
                if cspec == 'all':
                    vols = sess.all_volumes()
                    break
                if cspec.startswith('ocid1.compartment.oc1..'):
                    # compartment specified with its ocid
                    comp = sess.get_compartment(ocid=cspec)
                    if comp is None:
                        _logger.error("Compartment not found: %s", cspec)
                    else:
                        cvols = comp.all_volumes()
                        vols += cvols
                else:
                    # compartment specified with display name regexp
                    comps = sess.find_compartments(display_name=cspec)
                    if len(comps) == 0:
                        _logger.error("No compartments matching '%s' found", cspec)
                    else:
                        for comp in comps:
                            cvols = comp.all_volumes()
                            vols += cvols
            except Exception as e:
                _logger.error('Failed to get data for compartment %s: %s', cspec, str(e))
    else:
        #
        # -C/--compartment option wasn't used, default to the instance's own
        # compartment
        try:
            comp = sess.this_compartment()
            avail_domain = sess.this_availability_domain()
            if comp is not None:
                vols = comp.all_volumes(availability_domain=avail_domain)
                _title = "Other available storage volumes %s/%s:" % (comp.get_display_name(), avail_domain)
            else:
                _logger.error("Compartment for this instance not found")
        except Exception as e:
            _logger.error('Failed to get data for this compartment: %s', str(e))

    if len(vols) == 0:
        _logger.info("No additional storage volumes found.")
        return

    _vols_to_be_displayed = []
    for v in vols:
        if v.is_attached() and not args.all:
            continue
        # display also the attached ones
        _vols_to_be_displayed.append(v)
    _vols_to_be_displayed.sort()
    _display_oci_volume_list(_vols_to_be_displayed, args)


def show_volumes(oci_session, iscsiadm_session, system_disks, args):
    """
    Show iscsi volumes.

    Parameters
    ----------
    oci_session: OCISession
        The oci session.
    iscsiadm_session: dict
        The iscsiadm session.
    system_disks: dict
        The attached volumes.
    args: namespace
        The command line arguments.

    Returns
    -------
        bool: True
    """
    _logger.debug('%s', where_am_i())
    #
    # set the compatibility parameters, if necessary
    compatibility_mode, args.output_mode, args.details = get_compatibility_mode(args)

    display_attached_volumes(oci_session,
                             iscsiadm_session,
                             system_disks,
                             args)
    if len(args.compartments) > 0 or args.all:
        api_display_available_block_volumes(oci_session, args)

    return True


def get_instance_ocid():
    """
    Gets the instance OCID; fetch in the instance InstanceMetadata the
    ID of the current instance

    Returns
    -------
        str
            The instance id or '<instance OCID>' if not found.
    """
    return InstanceMetadata().refresh()['instance']['id']


def get_this_instance_ocid(session):
    """
    Get the ocid of the current instance, via the api or via the metadata.

    Parameters
    ----------
    session: OCISession
        The oci session.

    Returns
    -------
        str: the ocid
    """
    _logger.debug('%s', where_am_i())
    if bool(session):
        if bool(session.this_instance()):
            return session.this_instance().get_ocid()
        _logger.error('Failed to retrieve instance information.')
        sys.exit(1)
    else:
        return get_instance_ocid()


def do_show(args):
    """
    Show iscsi block volumes.

    Parameters
    ----------
    args: namespace
        The commandline.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    global _this_instance_ocid
    #
    _logger.debug('%s', where_am_i())
    # create an oci api session
    oci_sess = get_oci_api_session()
    # collect iscsi volume information
    system_disks = lsblk.list_blk_dev()
    # we are not touching boot volume in iscsi config
    iscsiadm_session = iscsiadm.session()
    # get the ocid of this instance
    _this_instance_ocid = get_this_instance_ocid(session=oci_sess)

    try:
        _ = show_volumes(oci_session=oci_sess,
                         iscsiadm_session=iscsiadm_session,
                         system_disks=system_disks,
                         args=args)
    except Exception as e:
        _logger.debug('Failed to show block volumes: %s', str(e), stack_info=True)
        return False
    return True


def do_show_all(args):
    """
    Show all iscsi block volumes.

    Parameters
    ----------
    args: namespace
        The commandline.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    args.all = True
    # args.output_mode = 'table'
    args.no_truncate = not args.truncate
    args.compartments = ()
    args.details = True
    return do_show(args)


def get_oci_api_session():
    """
    Ensure the OCI SDK is available if the option is not None.

    Returns
    -------
        OCISession
            The session or None if we cannot get one
    """
    _logger.debug('%s', where_am_i())
    session_cache = getattr(get_oci_api_session, "_session", None)
    if session_cache:
        return session_cache

    sess = None

    try:
        _logger.debug('Creating session')
        sess = oci_utils.oci_api.OCISession()
        # it seems that having a client is not enough, we may not be able to query anything on it.
        # workaround:
        # try a dummy call to be sure that we can use this session
        if not bool(sess.this_instance()):
            _logger.debug('Returning None session')
            return None
        setattr(get_oci_api_session, "_session", sess)
    except Exception as e:
        _logger.error("Failed to access OCI services: %s", str(e))
        _logger.error("Unable to authenticate correctly. Verify the Instance Principals "
                      "or Direct Authentication configuration.")
    _logger.debug('Returning session')
    return sess

def display_iscsi_device(vol):
    """
    Print the data for iscsi device identified by iqn.
    Parameters
    ----------
    vol: list
        The volume data.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    print('%s %s %s:%s [%s]' % (vol['name'], vol['iqn'], vol['portal_ip'], vol['portal_port'], vol['ocid']))
    return True


def get_volume_data_from_(somekey, sess):
    """
    Collect the data of an iscsi volume based on the iqn, the ocid or the display name.

    Parameters
    ----------
    somekey: str
        The iSCSI qualified name, the ocid or the display name.
    sess: OCISession
        An oci sdk session.

    Returns
    -------
        dict: The volume data if exist and is unique, False otherwise
    """
    _logger.debug('%s: %s', where_am_i(), somekey)
    this_compartment = sess.this_compartment()
    this_availability_domain = sess.this_availability_domain()
    all_volumes = this_compartment.all_volumes(this_availability_domain)
    those_vols = list()
    this_vol = dict()
    found = False
    for vol in all_volumes:
        try:
            if somekey.startswith(oci_volume_tag):
                # key is an ocid
                this_ocid = vol.get_ocid()
                if this_ocid == somekey:
                    this_vol['ocid'] = this_ocid
                    this_vol['iqn'] = vol.get_iqn()
                    this_vol['name'] = vol.get_display_name()
                    found = True
                _logger.debug('%s is an ocid.', somekey)
            elif somekey.startswith(iqn_tag):
                # key is an iqn
                this_iqn = vol.get_iqn()
                if this_iqn == somekey:
                    this_vol['iqn'] = this_iqn
                    this_vol['ocid'] = vol.get_ocid()
                    this_vol['name'] = vol.get_display_name()
                    found = True
                _logger.debug('%s is an iqn.', somekey)
            else:
                this_name = vol.get_display_name()
                # key is a display name, might not be unique, first one found is returned.
                if this_name == somekey:
                    this_vol['name'] = this_name
                    this_vol['iqn'] = vol.get_iqn()
                    this_vol['ocid'] = vol.get_ocid()
                    found = True
                _logger.debug('%s is a display name.', somekey)
            if found:
                _logger.debug('Found volume with key = %s', somekey)
                this_vol['portal_ip'] = vol.get_portal_ip()
                this_vol['portal_port'] = vol.get_portal_port()
                this_vol['chap_user'] = vol.get_user()
                this_vol['chap_pw'] = vol.get_password()
                this_vol['attachement_state'] = vol.get_attachment_state()
                this_vol['availability_domain'] = this_availability_domain
                this_vol['compartment'] = this_compartment.get_display_name()
                this_vol['compartment_id'] = vol.get_compartment_id()
                this_vol['attached_to'] = vol.get_instance().get_display_name()
                this_vol['size'] = vol.get_size(OCI_VOLUME_SIZE_FMT.HUMAN.name)
                this_vol['state'] = vol.get_state()
                _logger.debug('Volume data: %s', this_vol)
                those_vols.append(this_vol)
                found = False
        except Exception as e:
            _logger.debug('Get volume data for %s failed: %s', somekey, str(e))
            continue
    if len(those_vols) == 0:
        _logger.debug('Volume with key %s not found.', somekey)
        return False
    if len(those_vols) > 1:
        _logger.debug('Volume with key %s is not unique.', somekey)
    else:
        _logger.debug('Volume with key %s exists and is unique.', somekey)
    _logger.debug('Found volumes: %s', those_vols)
    return those_vols[0]


def sync_detached_devices(oci_session, detached_volumes, targets, apply=False, interactive=False, apply_yes=False):
    """
    Try to attach volumes in the detached volumes list.

    Parameters
    ----------
    oci_session: OCISession
        The oci api session.
    detached_volumes: list
        The iqn's of the detached volumes.
    targets: dict
        The targets.
    apply: bool
        Try to attach if True.
    interactive: bool
        Compatiblity flag, Try to attach if True.
    apply_yes: bool
        Assume yes if True.

    Returns
    -------
        tuple: (bool, int)
            Something changed/[0,1]
    """
    _logger.debug('%s', where_am_i())
    did_something = False
    retval = 0
    for iqn in detached_volumes:
        # display_detached_iscsi_device(iqn, targets)
        this_volume_data = get_volume_data_from_(iqn, oci_session)
        if not this_volume_data:
            _logger.error('Volume with iqn %s does not exist.', iqn)
            # if invalid iqn in detached volume list, clean up
            if apply or interactive:
                if apply_yes:
                    ans = True
                else:
                    ans = _read_yn('Would you like to remove %s from detached volume list?' % iqn,
                                   yn=True,
                                   waitenter=True,
                                   suppose_yes=False,
                                   default_yn=False)
                if ans:
                    detached_volumes.remove(iqn)
                    write_cache_11876(cache_content=list(set(detached_volumes)),
                                      cache_fname=iscsiadm.IGNOREIQNS_CACHE,
                                      cache_fname_11876=__ignore_file)
        else:
            _ = display_iscsi_device(this_volume_data)
            if apply or interactive:
                if apply_yes:
                    ans = True
                else:
                    ans = _read_yn('Would you like to attach this device?',
                                   yn=True,
                                   waitenter=True,
                                   suppose_yes=False,
                                   default_yn=False)
                if ans:
                    try:
                        chap = True if this_volume_data['chap_user'] is not None else False
                        attach_data = do_oci_vol_attach_ocid(oci_session, 'gen', this_volume_data['ocid'], chap)
                        # _do_iscsiadm_attach(this_volume_data['iqn'],
                        #                    targets,
                        #                    user=this_volume_data['chap_user'],
                        #                    passwd=this_volume_data['chap_pw'],
                        #                    iscsi_portal_ip=this_volume_data['portal_ip'])
                        detached_volumes.remove(this_volume_data['iqn'])
                        write_cache_11876(cache_content=list(set(detached_volumes)),
                                          cache_fname=iscsiadm.IGNOREIQNS_CACHE,
                                          cache_fname_11876=__ignore_file)
                        did_something = True
                    except Exception as e:
                        _logger.error('[%s] attachment failed: %s', iqn, str(e))
                        retval = 1
    return did_something, retval


def get_chap_secret(iqn):
    """
    Look for a saved (user,password) pair for iqn in the chap secrets file.

    Parameters
    ----------
    iqn: str
        The iSCSI qualified name.

    Returns
    -------
        tuple
            The (timestamp, password) on success, (None,None) otherwise.

    """
    # _, chap_passwords = load_cache(__chap_password_file)
    _logger.debug('%s', where_am_i())
    _, chap_passwords = load_cache_11876(global_file=iscsiadm.CHAPSECRETS_CACHE,
                                         global_file_11876=__chap_password_file)
    if chap_passwords is None:
        return None, None
    if iqn in chap_passwords:
        return chap_passwords[iqn]
    return None, None


def sync_failed_attached(oci_session, failed_volumes, targets, apply=False, interactive=False, apply_yes=False):
    """
    Try to attach volumes in the failed attached volumes list.
    Parameters
    ----------
    oci_session: OCISession
        The oci api session.
    failed_volumes: list
        The iqn's of volumes failed attachment.
    targets: list
        The targets.
    apply: bool
        Try to attach if True.
    interactive: bool
        Compatiblity flag, Try to attach if True.
    apply_yes: bool
        Assume yes if True.

    Returns
    -------
        tuple: (bool, int)
            Something changed/[0,1]
    """
    _logger.debug('%s', where_am_i())
    did_something = False
    retval = 0
    for iqn in list(failed_volumes.keys()):
        # display_detached_iscsi_device(iqn, targets, attach_failed)
        this_volume_data = get_volume_data_from_(iqn, oci_session)
        if this_volume_data:
            _ = display_iscsi_device(this_volume_data)
            _attach_user_name = None
            _attach_user_passwd = None
            _give_it_a_try = False
            if apply or interactive:
                if failed_volumes[iqn] != 24:
                    # not authentication error
                    # if args.yes or ask_yes_no("Would you like to retry attaching this device?"):
                    if _read_yn('Would you like to retry attaching this device?',
                                yn=True,
                                waitenter=True,
                                suppose_yes=False,
                                default_yn=False):
                        _give_it_a_try = True
                else:
                    _logger.debug('%s in failed list because of authorisation failure.', iqn)
                    # authentication error
                    # if args.yes or ask_yes_no("Would you like to configure this device?"):
                    if apply_yes or _read_yn('Would you like to configure this device?',
                                             yn=True,
                                             waitenter=True,
                                             suppose_yes=False,
                                             default_yn=False):
                        _give_it_a_try = True
                        if oci_session is not None:
                            this_volume_data = get_volume_data_from_(iqn, oci_session)
                            _attach_user_name = this_volume_data['chap_user']
                            _attach_user_passwd = this_volume_data['chap_pw']
                        else:
                            (_attach_user_name, _attach_user_passwd) = get_chap_secret(iqn)
                            if _attach_user_name is None:
                                _logger.error('Cannot retreive chap credentials')
                                _give_it_a_try = False
                if _give_it_a_try:
                    try:
                        chap = True if this_volume_data['chap_user'] is not None else False
                        attach_data = do_oci_vol_attach_ocid(oci_session, 'gen', this_volume_data['ocid'], chap)
                        failed_volumes = {key:failed_volumes[key]
                                          for key in failed_volumes if key != this_volume_data['iqn']}
                        write_cache(cache_content=[targets, failed_volumes],
                                    cache_fname=oci_utils.iscsiadm.ISCSIADM_CACHE)
                        did_something = True
                    except Exception as e:
                        _logger.error("Failed to configure device [%s]: %s", this_volume_data['iqn'], str(e))
                        retval = 1
        else:
            _logger.error('Volume [%s] not found.', iqn)
    return did_something, retval


def ocid_refresh(wait=False):
    """
    Refresh OCID cached information; it runs
    /usr/libexec/ocid command line with --refresh option

    Parameters
    ----------
    wait: bool
       Flag, wait until completion if set.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    _cmd = ['/usr/libexec/ocid', '--refresh', 'iscsi']
    if wait:
        _cmd.append('--no-daemon')
    try:
        _logger.debug('Executing %s', _cmd)
        output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug('Ocid run output: %s', str(output))
        return True
    except subprocess.CalledProcessError as e:
        _logger.debug('Launch of ocid failed : %s', str(e))
        return False


def load_iscsi_admin_cache():
    """
    Load the iscsiadm cache.

    Returns
    -------
        tuple: targets, timestamp
    """
    _logger.debug('%s', where_am_i())
    ocid_cache = load_cache(global_file=iscsiadm.ISCSIADM_CACHE, max_age=timedelta(minutes=2))[1]
    if ocid_cache is None:
        _logger.debug('Updating the cache')
        # run ocid once, to update the cache
        ocid_refresh(wait=True)
        # now try to load again
        ocid_cache = load_cache(global_file=iscsiadm.ISCSIADM_CACHE, max_age=timedelta(minutes=2))[1]
    if ocid_cache is None:
        targets, attach_failed = None, None
    else:
        targets, attach_failed = ocid_cache
    _logger.debug('iSCSI targets: %s', targets)
    _logger.debug('Attach failed: %s', attach_failed)
    return targets, attach_failed


def load_detached_volumes_cache():
    """
    Load the iqns of the detached volumes from the cache.

    Returns
    -------
        list: the iqns of the detached volumes.
    """
    # detached_vol_iqns = load_cache(__ignore_file)[1]
    _logger.debug('%s', where_am_i())
    detached_vol_iqns = load_cache_11876(global_file=iscsiadm.IGNOREIQNS_CACHE, global_file_11876=__ignore_file)[1]
    if detached_vol_iqns is None:
        detached_vol_iqns = []
    _logger.debug('Detached volumes: %s', detached_vol_iqns)
    return detached_vol_iqns


def do_sync(args):
    """
    Syncronise iscsi block volumes.

    Parameters
    ----------
    args: namespace
        The commandline.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    #
    # load iscsiadm-cache
    targets, attach_failed = load_iscsi_admin_cache()
    #
    # load detached volumes cache
    detached_volume_iqns = load_detached_volumes_cache()
    #
    if not detached_volume_iqns and not attach_failed:
        # nothing to do, stop here
        print("All known devices are attached.")
        return True
    #
    # we still have volume not attached, process them.
    # this one is as good as obsolete, ocid takes care of executing iscsiadm attach commands.
    # and detached volume iqns contains volumes which are detached from oci instance
    #
    # create an oci_api session
    oci_sess = get_oci_api_session()
    #
    return_value_d = 0
    synced_f = False
    if detached_volume_iqns:
        _logger.info("Detached devices:")
        synced_d, return_value_d = sync_detached_devices(oci_sess,
                                                         detached_volume_iqns,
                                                         targets,
                                                         apply=args.apply,
                                                         interactive=args.interactive,
                                                         apply_yes=args.yes)
    return_value_f = 0
    synced_d = False
    if attach_failed:
        _logger.info("Devices that could not be attached automatically:")
        synced_f, return_value_f = sync_failed_attached(oci_sess,
                                                        attach_failed,
                                                        targets,
                                                        apply=args.apply,
                                                        interactive=args.interactive,
                                                        apply_yes=args.yes)

    ocid_refresh(wait=True)
    return True if return_value_d + return_value_f == 0 else False


def get_compatibility_mode(args):
    """
    Get the compatibility mode, compat = 0.11.

    Parameters
    ----------
    args: namespace
        The command line

    Returns
    -------
        tuple: compat mode, output mode, details flag
    """
    _logger.debug('%s', where_am_i())
    if 'compat' in args and args.compat is True:
        # Display information as version 0.11 for compatibility reasons for few settings.
        output_mode = 'compat'
        details = True
        compat_mode = 'compat'
    else:
        compat_mode = 'gen'
        output_mode = args.output_mode if 'output_mode' in args else None
        details = args.details if 'details' in args else None
    _logger.debug('Compatibility mode: %s', compat_mode)
    return compat_mode, output_mode, details


def get_max_volumes():
    """
    Evaluate the number of configured volumes.

    Returns
    -------
        int: the max number of volumes.
    """
    _logger.debug('%s', where_am_i())
    max_vol = OCIUtilsConfiguration.getint('iscsi', 'max_volumes')
    if max_vol > MAX_VOLUMES_LIMIT:
        _logger.error("Your configured max_volumes(%s) is over the limit(%s)", max_vol, MAX_VOLUMES_LIMIT)
        max_vol = MAX_VOLUMES_LIMIT
    return max_vol


def do_create_volume(sess, size, display_name, attach_it, detached, chap_credentials, mode):
    """
    Create a new OCI volume and attach it to this instance.

    Parameters
    ----------
    sess: OCISession
        The OCISession instance.
    size: int
        The volume size in GB.
    display_name: str
        The volume display name.
    attach_it: boolean
        Do we attach the newly created volume.
    detached: list
        The list of detached volumes.
    chap_credentials: boolean
        Use Chap Credentials Required if True
    mode: str
        Show output in 0.11 compatibility mode is set to 'compat'

    Returns
    -------
       No return value
    Raises
    ------
       Exception if something went wrong
    """
    _logger.debug('%s', where_am_i())
    try:
        _logger.info("Creating a new %d GB volume %s", size, display_name)
        inst = sess.this_instance()
        if inst is None:
            raise Exception("OCI SDK error: couldn't get instance info")
        _logger.debug('\n availability_domain %s\n compartment_id %s',
                      inst.get_availability_domain_name(), inst.get_compartment_id())
        #
        vol = sess.create_volume(sess.this_compartment().get_ocid(),
                                 inst.get_availability_domain_name(),
                                 size=size,
                                 display_name=display_name,
                                 wait=True)
    except Exception as e:
        _logger.debug("Failed to create volume", exc_info=True)
        raise Exception("Failed to create volume") from e

    _logger.info("Volume [%s] created", vol.get_display_name())
    _logger.debug("Volume [%s - %s] created", vol.get_display_name(), vol.get_ocid())

    if not attach_it:
        return

    compat_info_message(gen_msg="Attaching the volume to this instance", mode=mode)
    try:
        if chap_credentials:
            _logger.debug('Attaching with chap secrets.')
            vol = vol.attach_to(instance_id=inst.get_ocid(), use_chap=True)
        else:
            _logger.debug('Attaching without chap secrets.')
            vol = vol.attach_to(instance_id=inst.get_ocid(), use_chap=False)
    except Exception as e:
        _logger.debug('Cannot attach block volume', exc_info=True)
        vol.destroy()
        raise Exception('Cannot attach block volume') from e
    #
    # attach using iscsiadm commands
    compat_info_message(gen_msg="Attaching iSCSI device.", mode=mode)

    vol_portal_ip = vol.get_portal_ip()
    vol_portal_port = vol.get_portal_port()
    vol_iqn = vol.get_iqn()
    vol_username = vol.get_user()
    vol_password = vol.get_password()
    retval = iscsiadm.attach(ipaddr=vol_portal_ip,
                             port=vol_portal_port,
                             iqn=vol_iqn,
                             username=vol_username,
                             password=vol_password,
                             auto_startup=True)
    compat_info_message(compat_msg="iscsiadm attach Result: %s" % iscsiadm.error_message_from_code(retval),
                        gen_msg="Volume [%s] is attached." % vol.get_display_name(), mode=mode)
    if retval == 0:
        _logger.debug('Attachment successful')
        if chap_credentials:
            _logger.debug('Attachment OK: saving chap credentials.')
            add_chap_secret(vol_iqn, vol_username, vol_password)
        #
        # is a new volume, should not be in detached list
        if vol_iqn in detached:
            _logger.debug('Volume %s should not be in detached volumes list.', vol_iqn)
        #
        ocid_refresh(wait=True)
        #
        return
    #
    # Something wrong if passing here.
    try:
        _logger.debug('Trying to destroy the volume')
        vol.destroy()
    except Exception as e:
        _logger.debug("Failed to destroy volume", exc_info=True)
        _logger.error("Failed to destroy volume: %s", str(e))

    raise Exception('Failed to attach created volume: %s' % iscsiadm.error_message_from_code(retval))


def do_create(args):
    """
    Create an iscsi block volume.

    Parameters
    ----------
    args: namespace
        The commandline.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    #
    # evaluate the number of volumes
    max_volumes = get_max_volumes()
    #
    # collect iscsi volume information
    system_disks = lsblk.list_blk_dev()
    #
    # try to create an oci api session
    oci_sess = get_oci_api_session()
    #
    # load detached volumes cache
    detached_volume_iqns = load_detached_volumes_cache()
    #
    # set the compatibility parameters, if necessary
    compatibility_mode, args.output_mode, args.details = get_compatibility_mode(args)
    #
    if len(system_disks) > max_volumes:
        _logger.error("This instance reached the max_volumes(%s)", max_volumes)
        return 1
    try:
        if bool(oci_sess):
            do_create_volume(oci_sess,
                             size=args.size,
                             display_name=args.volume_name,
                             attach_it=args.attach_volume,
                             detached=detached_volume_iqns,
                             chap_credentials=args.chap,
                             mode=compatibility_mode)
        else:
            _logger.info('Unable to create volume, failed to create a session.')
            return False
    except Exception as e:
        _logger.debug('Volume creation has failed: %s', str(e), stack_info=True, exc_info=True)
        _logger.error('Volume creation has failed: %s', str(e))
        return False

    ocid_refresh(wait=True)
    return True


def get_iqn_from_ocid(sess, ocid):
    """
    Try to get the value for the iqn for a volume identified by an ocid, if any.

    Parameters
    ----------
    sess: OCISession
        The OCISession instance.
    ocid: str
        The ocid.

    Returns
    -------
        str: the iqn.
    """
    _logger.debug('%s: %s', where_am_i(), ocid)
    this_compartment = sess.this_compartment()
    this_availability_domain = sess.this_availability_domain()
    all_volumes = this_compartment.all_volumes(this_availability_domain)
    for vol in all_volumes:
        try:
            if vol.get_ocid() == ocid:
                return vol.get_iqn()
        except Exception as e:
            _logger.debug('Failed to find the iqn for[%s]: %s', ocid, str(e))
            continue
    return None


def do_destroy_volume(sess, ocid):
    """
    Destroy the volume with the given ocid.
    The volume must be detached.  This is just an added measure to
    prevent accidentally destroying the wrong volume.

    Add root privilege requirement to be the same as create_volumerequirement.

    Parameters
    ----------
    sess: OCISession
        The OCI service session.
    ocid: str
        The OCID.

    Returns
    -------
        None
    Raise
    -----
        Exception : when destroy has failed
    """
    _logger.debug('%s: %s', where_am_i(), ocid)
    try:
        vol = sess.get_volume(ocid)
    except Exception as e:
        _logger.debug("Failed to retrieve Volume details", exc_info=True)
        raise Exception("Failed to retrieve Volume details: %s" % ocid) from e

    if vol is None:
        raise Exception("Volume not found: %s" % ocid)

    if vol.is_attached():
        raise Exception("Cannot destroy an attached volume")

    try:
        _logger.debug('destroying volume %s:%s', vol.get_display_name(), vol.get_ocid())
        vol.destroy()
    except Exception as e:
        _logger.debug("Failed to destroy volume %s", ocid, exc_info=True)
        raise Exception("Failed to destroy volume") from e


def do_destroy(args):
    """
    Destroy an iscsi block volume.

    Parameters
    ----------
    args: namespace
        The commandline.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    #
    # try to create an oci api session
    oci_sess = get_oci_api_session()
    #
    # load detached volumes cache
    detached_volume_iqns = load_detached_volumes_cache()
    retval = True
    if not args.yes:
        for ocid in args.ocids:
            _logger.info("Volume : [%s]", ocid)
        if not _read_yn('WARNING: the volume(s) will be destroyed.  This is irreversible.  Continue?',
                        yn=True,
                        waitenter=True,
                        suppose_yes=False,
                        default_yn=False):
            return True
    for ocid in args.ocids:
        try:
            if bool(oci_sess):
                _logger.debug('Destroying [%s]', ocid)
                #
                # try to get the iqn from a detached volume
                _iqn = get_iqn_from_ocid(oci_sess, ocid)
                do_destroy_volume(oci_sess, ocid)
                _ = remove_chap_secret(ocid)
                _logger.info("Volume [%s] is destroyed", ocid)
                #
                # remove iqn from ignore list.
                if bool(_iqn):
                    if _iqn in detached_volume_iqns:
                        detached_volume_iqns.remove(_iqn)
                        write_cache_11876(cache_content=list(set(detached_volume_iqns)),
                                          cache_fname=iscsiadm.IGNOREIQNS_CACHE,
                                          cache_fname_11876=__ignore_file)
                        _logger.debug('%s removed from cache.', _iqn)
            else:
                _logger.info('Unable to destroy volume, failed to create a session.')
                retval = False
        except Exception as e:
            _logger.debug('Volume [%s] deletion has failed: %s', ocid, str(e), stack_info=True, exc_info=True)
            _logger.error('Volume [%s] deletion has failed: %s', ocid, str(e))
            retval = False

    return retval


def add_chap_secret(iqn, user, password):
    """
    Save the login information for the given iqn in the chap secrets file.

    Parameters
    ----------
    iqn: str
        The iSCSI qualified name.
    user: str
        The iscsiadm username.
    password: str
        The iscsiadm password.

    Returns
    -------
        No return value.
    """
    # _, chap_passwords = load_cache(__chap_password_file)
    _logger.debug('%s', where_am_i())
    _, chap_passwords = load_cache_11876(global_file=iscsiadm.CHAPSECRETS_CACHE,
                                         global_file_11876=__chap_password_file)
    if chap_passwords is None:
        chap_passwords = {}
    chap_passwords[iqn] = (user, password)
    # write_cache(cache_content=chap_passwords, cache_fname=__chap_password_file, mode=0o600)
    write_cache_11876(cache_content=chap_passwords,
                      cache_fname=iscsiadm.CHAPSECRETS_CACHE,
                      cache_fname_11876=__chap_password_file,
                      mode=0o600)


def get_iqn_from_chap_secrets_cache(ocid):
    """
    Try to retrieve iqn and pw for volume ocid from chap secrets cache.

    Parameters
    ----------
    ocid: str
        The ocid/username of the volume.

    Returns
    -------
        tuple: (iqn, password) if found, (None, None) otherwise
    """
    # _, chap_passwords = load_cache(__chap_password_file)
    _logger.debug('%s', where_am_i())
    _, chap_passwords = load_cache_11876(global_file=iscsiadm.CHAPSECRETS_CACHE,
                                         global_file_11876=__chap_password_file)
    if chap_passwords is None:
        return None, None
    for iqn, unpw in chap_passwords.items():
        if ocid == unpw[0]:
            return iqn, unpw[1]
    return None, None


def remove_chap_secret(iqn_ocid):
    """
    Remove the login information for a given iqn from the chap secrets file.

    Parameters
    ----------
    iqn_ocid: str
        The iSCSI qualified name

    Returns
    -------
        str: cache file timestamp on success, None otherwise
    """
    _logger.debug('%s: %s', where_am_i(), iqn_ocid)
    ret_value = None
    # _, chap_passwords = load_cache(__chap_password_file)
    _, chap_passwords = load_cache_11876(global_file=iscsiadm.CHAPSECRETS_CACHE,
                                         global_file_11876=__chap_password_file)
    if not bool(chap_passwords):
        return ret_value

    iqn, _ = get_iqn_from_chap_secrets_cache(iqn_ocid)[0] if iqn_ocid.startswith(oci_volume_tag) else iqn_ocid, None

    if iqn in chap_passwords.keys():
        removed_values = chap_passwords.pop(iqn)
        # ret_value = write_cache(cache_content=chap_passwords, cache_fname=__chap_password_file, mode=0o600)
        ret_value = write_cache_11876(cache_content=chap_passwords,
                                      cache_fname=iscsiadm.CHAPSECRETS_CACHE,
                                      cache_fname_11876=__chap_password_file,
                                      mode=0o600)
    return ret_value


def get_portal_ip_from_iscsiadm_cache(iqn_x):
    """
    Try to retrieve the portal ip from the iscsiadm cache.

    Parameters
    ----------
    iqn_x: str
       The iqn

    Returns
    -------
       str: the portal ip if found, None otherwise
    """
    _logger.debug('%s', where_am_i())
    _, iscsi_cache = load_cache(global_file=iscsiadm.ISCSIADM_CACHE)
    for portal in iscsi_cache:
        for p_ip, iqn_list in portal.items():
            if iqn_x in iqn_list:
                return p_ip
    return None


def do_oci_vol_attach_ocid(oci_session, compatibility_mode, volume_iqn, use_chap_secrets):
    """
    Collect data for attaching an iSCSI volume to this instance based on an ocid.

    Parameters
    ----------
    oci_session: OCISession
        The oci_api session.
    compatibility_mode: str
        The compatibility mode for the messages, 'compat' or 'gen'
    volume_iqn: str
        The ocid of the volume.
    use_chap_secrets: bool
        Use chap username and password.

    Returns
    -------
        dict: the attachment data.
    """
    _logger.debug('%s', where_am_i())
    bs_volume = None
    try:
        if bool(oci_session):
            compat_info_message(compat_msg="Attaching iSCSI device.", mode=compatibility_mode)
            #
            # verify if volume is in the chap secrets cache
            this_iqn, this_pw = get_iqn_from_chap_secrets_cache(volume_iqn)
            _logger.debug('The cache: iqn %s pw %s', this_iqn, this_pw)
            if this_iqn is not None or use_chap_secrets:
                _logger.debug('Using chap secret')
                bs_volume = _do_attach_oci_block_volume(oci_session, volume_iqn, chap=True)
            else:
                _logger.debug('Not using chap secret.')
                bs_volume = _do_attach_oci_block_volume(oci_session, volume_iqn, chap=False)
            compat_info_message(gen_msg='Volume [%s] is attached' % volume_iqn,
                                compat_msg='Result: command executed successfully',
                                mode=compatibility_mode)
            # user/pass coming from volume itself
            attach_data = dict()
            attach_data['attachment_username'] = bs_volume.get_user()
            attach_data['attachment_password'] = bs_volume.get_password()
            attach_data['iscsi_portal_ip'] = bs_volume.get_portal_ip()
            attach_data['iqn_to_use'] = bs_volume.get_iqn()
            attach_data['save_chap_cred'] = bool(use_chap_secrets)
            _logger.debug('Attach data: %s', attach_data)
            return attach_data

        _logger.info('Unable to attach volume, failed to create a session.')
        return False
    except Exception as e:
        _logger.debug('Failed to attach volume [%s]: %s', volume_iqn, str(e),
                      stack_info=True,
                      exc_info=True)
        _logger.error('Failed to attach volume [%s]: %s', volume_iqn, str(e))
        return False


def _is_iqn_attached(sess, iqn):
    """
    Verify if oci volume with iqn is attached to this instance.

    Parameters
    ----------
    sess: OCISession
        The OCISession instance.
    iqn: str
        The iSCSI qualified name.

    Returns
    -------
        str: the ocid
    """
    _logger.debug('%s: %s', where_am_i(), iqn)
    volume_data = get_volume_by_iqn(sess, iqn)
    if volume_data is None:
        return None
    if volume_data.is_attached():
        return volume_data.get_ocid()
    return None


def _do_attach_oci_block_volume(sess, ocid, chap=False):
    """
    Make API calls to attach a volume with the given OCID to this instance.

    Parameters
    ----------
    sess : OCISession
        An OCISession instance
    ocid : str
        The volume OCID
    chap: bool
        Set the Require Chap Credentials flag if True
    Returns
    -------
        OCIVolume
    Raise:
        Exception if attachment failed
    """
    _logger.debug('%s: %s', where_am_i(), ocid)
    vol = sess.get_volume(ocid)
    if vol is None:
        raise Exception('Volume [%s] not found' % ocid)

    if vol.is_attached():
        if vol.get_instance().get_ocid() == sess.this_instance().get_ocid():
            _msg = 'Volume [%s] already attached to this instance' % ocid
        else:
            _msg = 'Volume [%s] already attached to instance %s [%s]' % (ocid,
                                                                         vol.get_instance().get_ocid(),
                                                                         vol.get_instance().get_display_name())
        raise Exception(_msg)

    _logger.info('Attaching OCI Volume [%s] to this instance.', ocid)
    # vol = vol.attach_to(instance_id=sess.this_instance().get_ocid(), wait=True)
    vol = vol.attach_to(instance_id=sess.this_instance().get_ocid(), use_chap=chap, wait=True)
    _logger.debug("Volume [%s] attached", ocid)

    return vol


def do_oci_vol_attach_iqn(oci_session, iscsiadm_session, volume_iqn, chap_username, chap_password):
    """
    Collect data for attaching an iSCSI volume to this instance based on an iqn.

    Parameters
    ----------
    oci_session: OCISession
        The oci_api session.
    iscsiadm_session: dict
        The iscsi adm session.
    volume_iqn: str
        The iSCSI qualified name of the volume.
    chap_username: str
        The chap username.
    chap_password: str
        The chap password.

    Returns
    -------
        dict: the attachment data.
    """
    #
    # iqn is not in iscsiadm session ... might also not be in this_instance volume list..
    _logger.debug('%s', where_am_i())
    this_ocid = _is_iqn_attached(oci_session, volume_iqn)
    if not this_ocid:
        #
        # volume is not attached to oci, giving up for now instead of letting it timeout for 90 sec
        _logger.error('A volume with iqn [%s] is not in this instance list '
                      'of attached block volumes, attach it using the ocid.', volume_iqn)
        return False

    portal_ip_candidate = get_portal_ip_from_iscsiadm_cache(volume_iqn)
    attach_data = dict()
    if chap_username is not None and chap_password is not None:
        attach_data['attachment_username'] = chap_username
        attach_data['attachment_password'] = chap_password
    else:
        # user/pass not provided , looking in the cache
        (attach_data['attachment_username'], attach_data['attachment_password']) = get_chap_secret(volume_iqn)
    _logger.debug('Chap secrets: %s %s', attach_data['attachment_username'], attach_data['attachment_password'])
    #
    # in fact not necessary but for the sake of completeness.
    attach_data['save_chap_cred'] = False
    if attach_data['attachment_username'] is not None and attach_data['attachment_password'] is not None:
        attach_data['save_chap_cred'] = True

    if volume_iqn in iscsiadm_session:
        attach_data['iscsi_portal_ip'] = iscsiadm_session[volume_iqn]['current_portal_ip']
        _logger.debug('Portal ip for [%s] is [%s]', volume_iqn, attach_data['iscsi_portal_ip'])
    elif portal_ip_candidate is not None:
        attach_data['iscsi_portal_ip'] = portal_ip_candidate
    else:
        _logger.info('Invalid argument, iqn [%s] not found', volume_iqn)
        return False
    return attach_data


def _do_iscsiadm_attach(iqn, targets, user=None, passwd=None, iscsi_portal_ip=None):
    """
    Attach an iSCSI device.

    Parameters
    ----------
    iqn: str
        The iSCSI qualified name.
    targets: dict
        The targets,
    user: str
        The iscsiadm username.
    passwd: str
        The iscsiadm user password.
    iscsi_portal_ip: str
        portal IP
    Returns
    -------
        None
    Raise
    -----
    Exception in case of error
    """
    _logger.debug('%s', where_am_i())
    if not iscsi_portal_ip:
        portal_ip = None
        if targets is None:
            raise Exception("Ocid service must be running to determine the portal IP address for this device.")

        for ipaddr in list(targets.keys()):
            if iqn in targets[ipaddr]:
                portal_ip = ipaddr
        if portal_ip is None:
            #
            # this shouldn't really happen, but just in case
            raise Exception("Can't find portal IP address")
    else:
        portal_ip = iscsi_portal_ip

    _logger.debug('Portal: ip %s; iqn: %s; user %s; passwd: %s', portal_ip, iqn, user, passwd)
    retval = iscsiadm.attach(portal_ip, 3260, iqn, user, passwd, auto_startup=True)

    if retval != 0:
        _logger.info("Result: %s", iscsiadm.error_message_from_code(retval))
        raise Exception('iSCSI attachment failed: %s' % iscsiadm.error_message_from_code(retval))


def do_attach(args):
    """
    Attach an iscsi block volume.

    Parameters
    ----------
    args: namespace
        The commandline.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    #
    # collect iscsi volume information
    system_disks = lsblk.list_blk_dev()
    #
    # evaluate the number of volumes
    max_volumes = get_max_volumes()
    #
    # we are not touching boot volume in iscsi config
    iscsiadm_session = iscsiadm.session()
    #
    # try to create an oci api session
    oci_sess = get_oci_api_session()
    #
    # set the compatibility parameters, if necessary
    compatibility_mode, args.output_mode, args.details = get_compatibility_mode(args)
    #
    # load iscsiadm-cache
    targets, attach_failed = load_iscsi_admin_cache()
    #
    # load detached volumes cache
    detached_volume_iqns = load_detached_volumes_cache()
    #
    # maximum number of volumes reached
    if len(system_disks) > max_volumes:
        _logger.error("This instance reached the maximum number of volumes attached (%s)", max_volumes)
        return False

    if bool(args.ocids):
        iqnocid = args.ocids
    elif bool(args.iqns):
        iqnocid = args.iqns
    else:
        # should be trapped by argparse, one of those is required.
        _logger.error('Missing iqns or ocids')
        return False

    retval = True
    for iqnorocid in iqnocid:
        _save_chap_cred = False
        if iqnorocid in iscsiadm_session:
            _logger.info("Target [%s] is already attached.", iqnorocid)
            continue

        if iqnorocid.startswith(oci_volume_tag):
            #
            # ocid
            _logger.debug('Given IQN [%s] is probably an ocid, attaching it', iqnorocid)

            attach_data = do_oci_vol_attach_ocid(oci_sess, compatibility_mode, iqnorocid, args.chap)
            if not bool(attach_data):
                retval = False
                continue
        elif iqnorocid.startswith(iqn_tag):
            #
            # iqn
            _logger.debug('Given IQN [%s] is probably an iqn, attaching it', iqnorocid)

            attach_data = do_oci_vol_attach_iqn(oci_sess, iscsiadm_session, iqnorocid, args.username, args.password)
            if not bool(attach_data):
                retval = False
                continue
        else:
            #
            # invalid parameter
            _logger.info('Invalid argument, given IQN [%s] is not an iqn nor an ocid.', iqnorocid)
            retval = False
            continue
        #
        _logger.debug('Attaching [%s] to iSCSI session', iqnorocid)
        try:
            _do_iscsiadm_attach(attach_data['iqn_to_use'],
                                targets,
                                user=attach_data['attachment_username'],
                                passwd=attach_data['attachment_password'],
                                iscsi_portal_ip=attach_data['iscsi_portal_ip'])
            _logger.debug('Attachment of %s succeeded.', iqnorocid)
            if attach_data['iqn_to_use'] in detached_volume_iqns:
                _logger.debug('Volume %s was detached, remove from detached list.', iqnorocid)
                detached_volume_iqns.remove(attach_data['iqn_to_use'])
                write_cache_11876(cache_content=list(set(detached_volume_iqns)),
                                  cache_fname=iscsiadm.IGNOREIQNS_CACHE,
                                  cache_fname_11876=__ignore_file)
            if args.chap:
                _logger.debug('Attachment OK: saving chap credentials.')
                add_chap_secret(iqnorocid, attach_data['attachment_username'], attach_data['attachment_password'])
        except Exception as e:
            _logger.debug("Failed to attach target [%s]: %s", iqnorocid, str(e), exc_info=True, stack_info=True)
            _logger.error("Failed to attach target [%s]: %s", iqnorocid, str(e))
            _save_chap_cred = False
            retval = False
            continue

    if retval:
        _logger.debug('Trigger ocid refresh.')
        ocid_refresh(wait=True)

    return retval


def _wait_for_detached_cache(iqn):
    """
    Waiting loop for iqn disappearing from detached volumes cache.

    Parameters
    ----------
    iqn: str
        The iqn.

    Returns
    -------
        bool: True on success, False otherwise
    """
    _logger.debug('%s', where_am_i())
    for _ in range(cache_loop):
        detachedvolumecache = load_detached_volumes_cache()
        if iqn in detachedvolumecache:
            _logger.debug('%s is still in detached volumes list, '
                          'wait for ocid refresh to complete and give it another try.', iqn)
            time.sleep(cache_delay)
        else:
            return True
    return False


def do_detach_volume(oci_session, iscsiadm_session, iqn, mode):
    """
    Detach the volume with given IQN

    Parameters
    ----------
    oci_session: OCISession
        The oci session.
    iscsiadm_session:
        iscsiadm session
    iqn: str
        The IQN.
    mode: str
        Show output in 0.11 compatibility mode is set to 'compat'

    Returns
    -------
        None
    Raise
    -----
        Exception : when destroy has failed
    """
    _logger.debug('%s', where_am_i())
    _volume = get_volume_by_iqn(oci_session, iqn)
    if _volume is None:
        raise Exception("Volume with IQN [%s] not found" % iqn)
    try:
        compat_info_message(compat_msg="Detaching volume",
                            gen_msg="Detaching volume %s [%s]" % (_volume.get_display_name(),
                                                                  _volume.get_iqn()), mode=mode)
        _volume.detach()
    except Exception as e:
        _logger.debug("Failed to disconnect volume", exc_info=True)
        _logger.error('%s', str(e))
        raise Exception("Failed to disconnect volume %s" % iqn) from e

    _logger.debug('Volume detached, detaching it from iSCSI session')
    if not iscsiadm.detach(iscsiadm_session[iqn]['persistent_portal_ip'],
                           iscsiadm_session[iqn]['persistent_portal_port'],
                           iqn):
        raise Exception("Failed to detach target %s" % iqn)


def do_umount(mountpoint):
    """
    Unmount the given mountpoint.

    Parameters
    ----------
    mountpoint: str
        The mountpoint.
    Returns
    -------
        bool
            True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    try:
        _logger.info("Unmounting %s", mountpoint)
        subprocess.check_output(['/usr/bin/umount', mountpoint], stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        _logger.error("Failed to unmount [%s]: %s", mountpoint, e.output)
        return False


def unmount_device(session, iqn, disks):
    """
    Unmount the partitions of the device with the specified iqn, if they are mounted.

    Parameters
    ----------
    session: iscsiadm session
        iscsiadm.session()
    iqn: str
        The iSCSI qualified name.
    disks: dict
        List of block devices.

    Returns
    -------
        bool
            True for success or the device is not mounted.
            False if the device is mount and unmounting failed.
    """
    _logger.debug('%s: %s', where_am_i(), iqn)
    retval = True
    #
    # find mountpoints
    _logger.debug('')
    device = session[iqn]['device']
    if device not in disks:
        return True
    if not bool(disks[device]['partitions']):
        #
        # no partitions, maybe device mounted.
        if bool(disks[device]['mountpoint']):
            #
            # volume has no partitions and is currently mounted
            if not do_umount(disks[device]['mountpoint']):
                retval = False
        else:
            _logger.debug('Volume %s not mounted', iqn)
    else:
        #
        # partitions
        partitions = disks[device]['partitions']
        for part in list(partitions.keys()):
            if bool(partitions[part]['mountpoint']):
                # the partition is mounted
                _logger.debug('Volume %s mounted', partitions[part]['mountpoint'])
                if not do_umount(partitions[part]['mountpoint']):
                    retval = False
            else:
                _logger.debug('Volume %s not mounted', partitions[part]['mountpoint'])
    return retval


def do_detach(args):
    """
    Detach an iscsi block volume.

    Parameters
    ----------
    args: namespace
        The commandline.

    Returns
    -------
        bool: True on success, False otherwise.
    """
    _logger.debug('%s', where_am_i())
    #
    # we are not touching boot volume in iscsi config
    iscsiadm_session = iscsiadm.session()
    #
    # collect iscsi volume information
    system_disks = lsblk.list_blk_dev()
    #
    # try to create an oci api session
    oci_sess = get_oci_api_session()
    #
    # set the compatibility parameters, if necessary
    compatibility_mode, args.output_mode, args.details = get_compatibility_mode(args)
    #
    # load detached volumes cache
    detached_volume_iqns = load_detached_volumes_cache()
    #
    return_value = True
    for iqn in args.iqns:
        retval = True
        if not _wait_for_detached_cache(iqn):
            _logger.error("Target [%s] is already detached", iqn)
            retval = False
            # continue
        if iqn not in iscsiadm_session or 'device' not in iscsiadm_session[iqn]:
            _logger.error("Target [%s] not found", iqn)
            retval = False
            # continue
        if retval:
            _logger.debug('Unmounting the block volume')
            if not unmount_device(iscsiadm_session, iqn, system_disks):
                _logger.debug('Unmounting has failed')
                if not args.force:
                    # if not ask_yes_no("Failed to unmount volume, Continue detaching anyway?"):
                    if not _read_yn('Failed to unmount volume, Continue detaching anyway?',
                                    yn=True,
                                    waitenter=True,
                                    suppose_yes=False,
                                    default_yn=False):
                        continue
                else:
                    _logger.info('Unmount failed, force option selected,continue anyway.')
            try:
                if bool(oci_sess):
                    _logger.debug('Detaching [%s]', iqn)
                    do_detach_volume(oci_sess, iscsiadm_session, iqn, mode=compatibility_mode)
                    compat_info_message(gen_msg="Volume [%s] is detached." % iqn, mode=compatibility_mode)
                    detached_volume_iqns.append(iqn)
                    write_cache_11876(cache_content=list(set(detached_volume_iqns)),
                                      cache_fname=iscsiadm.IGNOREIQNS_CACHE,
                                      cache_fname_11876=__ignore_file)
                else:
                    _logger.info('Unable to detach volume, failed to create a session.')
                    retval = False
            except Exception as e:
                _logger.debug('Volume [%s] detach has failed: %s', iqn, str(e), stack_info=True, exc_info=True)
                _logger.error('Volume [%s] detach has failed: %s', iqn, str(e))
                retval = 1

        if retval:
            pass
        else:
            return_value = retval

    _logger.debug('Trigger ocid refresh')
    ocid_refresh(wait=True)
    return return_value


_this_instance_ocid = None


def main():
    """
    Main.

    Returns
    -------
        int
            0 on success
            1 on failure
    """
    sub_commands = {'usage': show_usage,
                    'show': do_show,
                    'show-all': do_show_all,
                    'sync': do_sync,
                    'create': do_create,
                    'destroy': do_destroy,
                    'attach': do_attach,
                    'detach': do_detach
                    }

    # global _this_instance_ocid
    #
    # command line
    parser = get_args_parser()
    args = parser.parse_args()
    _logger.debug('Command line: %s', args)

    # no arguments defaults to 'sync' command
    if args.command is None:
        args.command = "sync"
        args.apply = False
        args.interactive = False
        args.yes = False

    if args.command == 'usage':
        parser.print_help()
        return 0
    #
    # operator needs to have root priviliges.
    if not is_root_user():
        _logger.error('This program needs to be run with root privileges.')
        return 1

    try:
        res = sub_commands[args.command](args)
        if not res:
            raise IscsiConfigException('Failed to complete %s.' % sub_commands[args.command].__name__)
        return 0
    except Exception as e:
        _logger.error('*** ERROR *** %s', str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
