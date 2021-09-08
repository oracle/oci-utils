# oci-utils
#
# Copyright (c) 2019. 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.


"""
This utility assists with configuring iscsi storage on Oracle Cloud
Infrastructure instances.  See the manual page for more information.
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import timedelta
import termios
import tty

import oci_utils.oci_api
from oci_utils import __ignore_file, iscsiadm, lsblk
from oci_utils import _configuration as OCIUtilsConfiguration
from oci_utils import OCI_VOLUME_SIZE_FMT
from oci_utils.cache import load_cache, write_cache
from oci_utils.metadata import InstanceMetadata

from oci_utils.impl.row_printer import get_row_printer_impl

_logger = logging.getLogger("oci-utils.oci-iscsi-config")

oci_volume_tag = 'ocid1.volume.'
iqn_tag = 'iqn.'


def volume_size_validator(value):
    """
    Validate than value passed is an int and greater then 50 (GB).

    Parameters
    ----------
        value: str
           Size in GB.

    Returns
    -------
        int: size in GB on success.
    """
    _i_value = 0
    try:
        _i_value = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("block volume size must be a int") from e

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
    _ocids = [ocid.strip() for ocid in value.split(',') if ocid]
    for ocid in _ocids:
        if not ocid.startswith(oci_volume_tag):
            raise argparse.ArgumentTypeError('Invalid volume OCID %s' % ocid)
    return _ocids


def get_args_parser():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The commandline argparse namespace.
    """
    parser = argparse.ArgumentParser(description='Utility for listing or configuring iSCSI devices on an OCI instance.')
    subparser = parser.add_subparsers(dest='command')
    #
    # sync
    sync_parser = subparser.add_parser('sync',
                                       description='Try to attach available block devices.')
    sync_parser.add_argument('-a', '--apply',
                             action='store_true',
                             help='Perform sync operations.')
    sync_parser.add_argument('-y', '--yes',
                             action='store_true',
                             help='Assume yes.')
    # kept for compatibility reason. keep it hidden
    sync_parser.add_argument('-i', '--interactive',
                             action='store_true',
                             help=argparse.SUPPRESS)
    #
    # usage
    usage_parser = subparser.add_parser('usage',
                         description='Displays usage.')
    # for compatibility mode
    usage_parser.add_argument('--compat',
                             action='store_true',
                             default=False,
                             help=argparse.SUPPRESS)
    #
    # show
    show_parser = subparser.add_parser('show',
                                       description='Show block volumes and iSCSI information.')
    show_parser.add_argument('-C', '--compartments',
                             metavar='COMP',
                             default=(),
                             type=lambda s: [ocid.strip() for ocid in s.split(',') if ocid],
                             help='Display iSCSI devices in the given comparment(s) '
                                  'or all compartments if COMP is  "all".')
    show_parser.add_argument('-A', '--all',
                             action='store_true',
                             default=False,
                             help='Display all iSCSI devices. By default only devices that are not attached '
                                  'to an instance are listed.')
    show_parser.add_argument('--output-mode',
                             choices=('parsable', 'table', 'json', 'text'),
                             help='Set output mode.',
                             default='table')
    show_parser.add_argument('--details',
                             action='store_true',
                             default=False,
                             help='Display detailed information.')
    show_parser.add_argument('--no-truncate',
                             action='store_true',
                             default=False,
                             help='Do not truncate value during output ')
    show_parser.add_argument('--compat',
                             action='store_true',
                             default=False,
                             help=argparse.SUPPRESS)
    #
    # create
    create_parser = subparser.add_parser('create',
                                         description='Creates a block volume.')
    create_parser.add_argument('-S', '--size',
                               type=volume_size_validator,
                               required=True,
                               help='Size of the block volume to create in GB, mandatory.')
    create_parser.add_argument('-v', '--volume-name',
                               help='Name of the block volume to create.')
    create_parser.add_argument('--attach-volume',
                               action='store_true',
                               help='Once created, should the volume be attached?')
    create_parser.add_argument('-c', '--chap',
                               action='store_true',
                               default=False,
                               help='Attach the device with the Require Chap Credentials flag.')
    create_parser.add_argument('--compat',
                               action='store_true',
                               default=False,
                               help=argparse.SUPPRESS)
    #
    # attach
    attach_parser = subparser.add_parser('attach',
                                         description='Attach a block volume to this instance and make it '
                                                     'available to the system.')
    ocidiqn = attach_parser.add_mutually_exclusive_group(required=True)
    ocidiqn.add_argument('-I', '--iqns',
                               type=attachable_iqn_list_validator,
                               help='Comma separated list of IQN(s) or OCID(s) of the iSCSI devices to be attached.')
    ocidiqn.add_argument('-O', '--ocids',
                               type=attachable_iqn_list_validator,
                               help='Comma separated list of OCID(s) or IQN(s) of the iSCSI devices to be attached.')
    # attach_parser.add_argument('-I', '--iqns',
    #                            required=True,
    #                            type=attachable_iqn_list_validator,
    #                            help='Comma separated list of IQN(s) or OCID(s) of the iSCSI devices to be attached.')
    # attach_parser.add_argument('-O', '--ocids',
    #                            required=True,
    #                            type=attachable_iqn_list_validator,
    #                            help='Comma separated list of OCID(s) or IQN(s) of the iSCSI devices to be attached.')
    attach_parser.add_argument('-u', '--username',
                               metavar='USER',
                               action='store',
                               help='Use USER as the user name when attaching a device that requires CHAP '
                                    'authentication.')
    attach_parser.add_argument('-p', '--password',
                               metavar='PASSWD',
                               action='store',
                               help='Use PASSWD as the password when attaching a device that requires CHAP '
                                    'authentication.')
    attach_parser.add_argument('-c', '--chap',
                               action='store_true',
                               default=False,
                               help='Attach the device with the Require Chap Credentials flag.')
    attach_parser.add_argument('--compat',
                               action='store_true',
                               default=False,
                               help=argparse.SUPPRESS)
    #
    # detach
    detach_parser = subparser.add_parser('detach',
                                         description='Detach a block volume')
    detach_parser.add_argument('-I', '--iqns',
                               required=True,
                               type=detachable_iqn_list_validator,
                               help='Comma separated list of IQN(s) of the iSCSI devices to be detached.')
    detach_parser.add_argument('-f', '--force',
                               action='store_true',
                               help='Continue detaching even if device cannot be unmounted.')
    detach_parser.add_argument('-i', '--interactive',
                               action='store_true',
                               help=argparse.SUPPRESS)
    detach_parser.add_argument('--compat',
                               action='store_true',
                               default=False,
                               help=argparse.SUPPRESS)
    #
    # destroy
    destroy_parser = subparser.add_parser('destroy',
                                          description='Destroy a block volume.')
    destroy_parser.add_argument('-O', '--ocids',
                                required=True,
                                type=volume_oci_list_validator,
                                help='OCID(s) of volumes to be destroyed.')
    destroy_parser.add_argument('-y', '--yes',
                                action='store_true',
                                help='Assume yes, otherwise be interactive.')
    # kept for compatibility reason. keep it hidden
    destroy_parser.add_argument('-i', '--interactive',
                                action='store_true',
                                help=argparse.SUPPRESS)
    destroy_parser.add_argument('--compat',
                               action='store_true',
                               default=False,
                               help=argparse.SUPPRESS)
    return parser


def _getch():
    """
    Read a single keypress from stdin.

    Returns
    -------
        The resulting character.
    """
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
    if bool(compat_msg):
        if mode == 'compat':
            _logger.info(compat_msg)
    if bool(gen_msg):
        if mode != 'compat':
            _logger.info(gen_msg)


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


def _display_oci_volume_list(volumes, output_mode, details, truncate):
    """
    Display information about list of block volumes.

    Parameters
    ----------
        volumes: list
            List of OCIVOlumes
        output_mode: str
            Output mode
        details: bool
            Display details information if True
        truncate: bool
            Truncate text if False
    """

    def _get_displayable_size(_, volume):
        return volume.get_size(format_str=OCI_VOLUME_SIZE_FMT.HUMAN.name)

    def _get_attached_instance_name(_, volume):
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
        """ keep track of compartment per ID as it may be expensive info to fetch """
        _map = getattr(_get_comp_name, 'c_id_to_name', {})
        if volume.get_compartment_id() not in _map:
            _map[volume.get_compartment_id()] = volume.get_compartment().get_display_name()
        setattr(_get_comp_name, 'c_id_to_name', _map)
        return _map[volume.get_compartment_id()]

    if len(volumes) == 0:
        print('No other volumes found.')
    else:
        _title = 'Block volumes information'
        _columns = [['Name', 32, 'get_display_name'],
                    ['Size', 6, _get_displayable_size],
                    ['Attached to', 32, _get_attached_instance_name],
                    ['OCID', 32, 'get_ocid']]
        if details:
            _columns.extend((['IQN', 14, 'get_iqn'],
                             ['Compartment', 14, _get_comp_name],
                             ['Availability domain', 19, 'get_availability_domain_name']))
        if output_mode == 'compat':
            printerKlass = get_row_printer_impl('text')
        else:
            printerKlass = get_row_printer_impl(output_mode)

        printer = printerKlass(title=_title, columns=_columns, text_truncate=truncate)
        printer.printHeader()
        for vol in volumes:
            printer.printRow(vol)
            printer.rowBreak()
        printer.printFooter()
        printer.finish()


def get_oci_api_session():
    """
    Ensure the OCI SDK is available if the option is not None.

    Returns
    -------
        OCISession
            The session or None if cannot get one
    """
    session_cache = getattr(get_oci_api_session, "_session", None)
    if session_cache:
        return session_cache

    sess = None

    try:
        _logger.debug('Creating session')
        sess = oci_utils.oci_api.OCISession()
        # it seems that having a client is not enough, we may not be able to query anything on it
        # workaround :
        # try a dummy call to be sure that we can use this session
        if not bool(sess.this_instance()):
            _logger.debug('Returning None session')
            return None
        setattr(get_oci_api_session, "_session", sess)
    except Exception as e:
        _logger.error("Failed to access OCI services: %s", str(e))
    _logger.debug('Returning session')
    return sess


def display_attached_volumes(oci_sess, iscsiadm_session, disks, output_mode, details, truncate):
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
        as returned by lsblk.list()
    output_mode : the output mode as str (text,json,parsable)
    details : display detailed information ?
    truncate: truncate text?

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
        print("Local iSCSI info not available. ")
        print("List info from Cloud instead(No boot volume).")
        print("")
        _display_oci_volume_list(oci_vols, output_mode, details, truncate)

    _columns = []
    if details:
        _columns.append(['Target', 32, 'target'])
    _columns.append(['Volume name', 32, 'name'])
    if details:
        _columns.append(['Volume OCID', 32, 'ocid'])
        _columns.append(['Persistent portal', 20, 'p_portal'])
        _columns.append(['Current portal', 20, 'c_portal'])
        _columns.append(['Session State', 13, 's_state'])
    _columns.append(['Attached device', 15, 'dev'])
    _columns.append(['Size', 6, 'size'])

    # this is only used in compatibility mode i.e using 'text'
    partitionPrinter = get_row_printer_impl('text')(title='Partitions',
                                                    columns=(['Device', 8, 'dev_name'],
                                                             ['Size', 6, 'size'],
                                                             ['Filesystem', 12, 'fstype'],
                                                             ['Mountpoint', 12, 'mountpoint']))
    _items = []
    for iqn in list(iscsiadm_session.keys()):
        _item = {}
        oci_vol = get_volume_by_iqn(oci_sess, iqn)
        _item['target'] = iqn
        if oci_vol is not None:
            _item['name'] = oci_vol.get_display_name()
            _item['ocid'] = oci_vol.get_ocid()
        _item['p_portal'] = "%s:%s" % (iscsiadm_session[iqn]['persistent_portal_ip'],
                                       iscsiadm_session[iqn]['persistent_portal_port'])
        _item['c_portal'] = "%s:%s" % (iscsiadm_session[iqn]['current_portal_ip'],
                                       iscsiadm_session[iqn]['current_portal_port'])
        _item['s_state'] = iscsiadm_session[iqn].get('session_state', 'n/a')
        device = iscsiadm_session[iqn].get('device', None)
        if device is None:
            _item['dev'] = '(not attached)'
        else:
            _item['dev'] = device
            if device in disks:
                _item['size'] = disks[device]['size']

        _items.append(_item)

    iscsi_dev_printer = None
    if len(_items) == 0:
        print('No iSCSI devices attached.')
    elif output_mode == 'compat':
        iscsi_dev_printer = get_row_printer_impl('text')(
            title='Currently attached iSCSI devices', columns=_columns, text_truncate=truncate)
    else:
        iscsi_dev_printer = get_row_printer_impl(output_mode)(
            title='Currently attached iSCSI devices', columns=_columns, text_truncate=truncate)
    if bool(iscsi_dev_printer):
        iscsi_dev_printer.printHeader()
        for _item in _items:
            iscsi_dev_printer.printRow(_item)
            if output_mode == 'compat':
                if 'partitions' not in disks[_item['dev']]:
                    #
                    # iscsi_dev_printer.printKeyValue('File system type', disks[_item['dev']]['fstype'])
                    # iscsi_dev_printer.printKeyValue('Mountpoint', disks[_item['dev']]['mountpoint'])
                    fstype = disks[_item['dev']]['fstype'] if bool(disks[_item['dev']]['fstype']) else 'Unknown'
                    iscsi_dev_printer.printKeyValue('File system type', fstype)
                    mntpoint = disks[_item['dev']]['mountpoint'] if bool(disks[_item['dev']]['mountpoint']) else 'Not mounted'
                    iscsi_dev_printer.printKeyValue('Mountpoint', mntpoint)
                else:
                    partitions = disks[device]['partitions']
                    partitionPrinter.printHeader()
                    for part in sorted(list(partitions.keys())):
                        # add it as we need it during the print
                        partitions[part]['dev_name'] = part
                        partitionPrinter.printRow(partitions[part])
                        partitionPrinter.rowBreak()
                    partitionPrinter.printFooter()
                    partitionPrinter.finish()
            iscsi_dev_printer.rowBreak()
        iscsi_dev_printer.printFooter()
        iscsi_dev_printer.finish()


# def display_detached_iscsi_device(iqn, targets, attach_failed=()):
#     """
#     Display the iSCSI devices
#
#     Parameters
#     ----------
#     iqn: str
#         The iSCSI qualified name.
#     targets: dict
#         The targets.
#     attach_failed: dict
#         The devices for which attachment failed.
#     """
#     devicePrinter = get_row_printer_impl('table')(title="Target %s" % iqn,
#                                                   text_truncate=False,
#                                                   columns=(['Portal', 20, 'portal'], ['State', 65, 'state']))
#     devicePrinter.printHeader()
#     _item = {}
#     for ipaddr in list(targets.keys()):
#         _item['portal'] = "%s:3260" % ipaddr
#         if iqn in attach_failed:
#             _item['state'] = iscsiadm.error_message_from_code(attach_failed[iqn])
#         else:
#             _item['state'] = "Detached"
#         devicePrinter.printRow(_item)
#         devicePrinter.rowBreak()
#     devicePrinter.printFooter()
#     devicePrinter.finish()

def display_iscsi_device(iqn, sess):
    """
    Print the data for iscsi device identified by iqn.
    Parameters
    ----------
    iqn: str
        The iSCSI qualified name.
    sess: OCISession
        An oci sdk session.
    Returns
    -------
        bool: True on success, False otherwise.
    """
    this_compartment = sess.this_compartment()
    this_availability_domain = sess.this_availability_domain()
    all_volumes = this_compartment.all_volumes(this_availability_domain)
    for vol in all_volumes:
        try:
            this_iqn = vol.get_iqn()
        except Exception as e:
            continue
        try:
            if this_iqn == iqn:
                this_name = vol.get_display_name()
                this_ocid = vol.get_ocid()
                this_ip = vol.get_portal_ip()
                this_port = vol.get_portal_port()
                print('%s %s %s:%s [%s]' % (this_name, iqn, this_ip, this_port, this_ocid))
                return True
        except Exception as e:
            return False


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
    if not iscsi_portal_ip:
        portal_ip = None
        if targets is None:
            raise Exception("Ocid must be running to determine the portal IP address for this device.")

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


def do_detach_volume(oci_session, iscsiadm_session, iqn, mode):
    """
    Detach the volume with given IQN

    Parameters
    ----------
    oci_session: OCISession
        The iscsiadm session.
    iscsiadm_session:
        iscsiadm.session()
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


def do_destroy_volume(sess, ocid):
    """
    Destroy the volume with the given ocid.
    The volume must be detached.  This is just an added measure to
    prevent accidentally destroying the wrong volume.

    Add root privilege requirement to be the same as create's requirement.

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
    _logger.debug("Destroying volume [%s]", ocid)
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


def api_display_available_block_volumes(sess, compartments, show_all, output_mode, details, truncate):
    """
    Display the available devices.

    Parameters
    ----------
    sess: OCISession
        The OCISession instance.
    compartments: list of str
        compartement ocid(s)
    show_all: bool
        display all volumes. By default display only not-attached  ones
    output_mode : information display mode
    details : display detailed information ?
    truncate: truncate text?

    Returns
    -------
        No return value.
    """

    _title = "Other available storage volumes"
    if sess is None:
        _logger.info("Failed to create session, unable to show available volumes.")
        return

    vols = []
    if len(compartments) > 0:
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
                _title = "Other available storage volumes %s/%s" % (comp.get_display_name(), avail_domain)
            else:
                _logger.error("Compartment for this instance not found")
        except Exception as e:
            _logger.error('Failed to get data for this compartment: %s', str(e))

    if len(vols) == 0:
        _logger.info("No additional storage volumes found.")
        return

    _vols_to_be_displayed = []
    for v in vols:
        if v.is_attached() and not show_all:
            continue
        # display also the attached ones
        _vols_to_be_displayed.append(v)
    _vols_to_be_displayed.sort()
    _display_oci_volume_list(_vols_to_be_displayed, output_mode, details, truncate)


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
    _logger.debug('Attaching volume [%s]', ocid)
    vol = sess.get_volume(ocid)
    if vol is None:
        raise Exception('Volume [%s] not found' % ocid)

    if vol.is_attached():
        if vol.get_instance().get_ocid() == sess.this_instance().get_ocid():
            # attached to this instance already
            _msg = 'Volume [%s] already attached to this instance' % ocid
        else:
            _msg = 'Volume [%s] already attached to instance %s [%s]' % (ocid,
                                                                       vol.get_instance().get_ocid(),
                                                                       vol.get_instance().get_display_name())
        raise Exception(_msg)

    _logger.info('Attaching OCI Volume [%s] to this instance.' % ocid)
    # vol = vol.attach_to(instance_id=sess.this_instance().get_ocid(), wait=True)
    vol = vol.attach_to(instance_id=sess.this_instance().get_ocid(), use_chap=chap, wait=True)
    _logger.debug("Volume [%s] attached", ocid)

    return vol


def get_volume_by_iqn(sess, iqn):
    """
    Gets a volume by given IQN

    Parameters
    ----------
    sess: OCISession
        The OCISEssion instance..
    iqn: str
        The iSCSI qualified name.

    Returns
    -------
       OCIVolume : the found volume or None
    """
    _logger.debug('Looking for volume with IQN == %s', iqn)
    #
    # _GT_
    # if not hasattr(get_volume_by_iqn, 'all_this_instance_volume'):
    #    _logger.debug('_GT_ attr A %s', sess.this_instance().all_volumes())
    #    get_volume_by_iqn.all_this_instance_volume = sess.this_instance().all_volumes()
    # else:
    #    _logger.debug('_GT_ attr B %s', get_volume_by_iqn.all_this_instance_volume)
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


def _get_iqn_from_ocid(sess, ocid):
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
    _logger.debug('Trying to find the iqn for volume [%s]', ocid)
    this_compartment = sess.this_compartment()
    this_availability_domain = sess.this_availability_domain()
    all_volumes = this_compartment.all_volumes(this_availability_domain)
    for vol in all_volumes:
        try:
            if vol.get_ocid() == ocid:
                return vol.get_iqn()
        except Exception as e:
            continue
    return None


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
    _logger.debug('Verifying if [%s] is attached to this instance.')
    volume_data = get_volume_by_iqn(sess, iqn)
    if volume_data is None:
        return None
    if volume_data.is_attached():
        return volume_data.get_ocid()
    return None


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
    retval = True
    # find mountpoints
    device = session[iqn]['device']
    if device not in disks:
        return True
    if 'partitions' not in disks[device]:
        if disks[device]['mountpoint'] != '':
            # volume has no partitions and is currently mounted
            if not do_umount(disks[device]['mountpoint']):
                retval = False
        else:
            _logger.debug('Volume %s not mounted', disks[device]['mountpoint'])
    else:
        partitions = disks[device]['partitions']
        for part in list(partitions.keys()):
            if partitions[part]['mountpoint'] != '':
                # the partition is mounted
                _logger.debug('Volume %s mounted', partitions[part]['mountpoint'])
                if not do_umount(partitions[part]['mountpoint']):
                    retval = False
            else:
                _logger.debug('Volume %s not mounted', partitions[part]['mountpoint'])
    return retval


def do_create_volume(sess, size, display_name, attach_it, chap_credentials, mode):
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
    chap_credentials: boolean
        Use Chap Credentials Required if True
    mode: str
        Show output in 0.11 compatibility mode is set to 'compat'

    Returns
    -------
       nothing
    Raises
    ------
       Exception if something went wrong
    """

    try:
        _logger.info("Creating a new %d GB volume %s", size, display_name)
        inst = sess.this_instance()
        if inst is None:
            raise Exception("OCI SDK error: couldn't get instance info")
        _logger.debug('\n availability_domain %s\n compartment_id %s',
                      inst.get_availability_domain_name(), inst.get_compartment_id())
        #
        # GT
        # vol = sess.create_volume(inst.get_compartment_id(),
        vol = sess.create_volume(sess.this_compartment().get_ocid(),
                                 inst.get_availability_domain_name(),
                                 size=size,
                                 display_name=display_name,
                                 wait=True)
    except Exception as e:
        _logger.debug("Failed to create volume", exc_info=True)
        raise Exception("Failed to create volume") from e

    _logger.info("Volume [%s] created", vol.get_display_name())

    if not attach_it:
        return

    compat_info_message(gen_msg="Attaching the volume to this instance", mode=mode)
    try:
        if chap_credentials:
            vol = vol.attach_to(instance_id=inst.get_ocid(), use_chap=True)
        else:
            vol = vol.attach_to(instance_id=inst.get_ocid(), use_chap=False)
    except Exception as e:
        _logger.debug('Cannot attach BV', exc_info=True)
        vol.destroy()
        raise Exception('Cannot attach BV') from e
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
        _logger.debug('Creation successful')
        if chap_credentials:
            _logger.debug('Attachment OK: saving chap credentials.')
            add_chap_secret(vol_iqn, vol_username, vol_password)
        return

    # here because of error case
    try:
        _logger.debug('Destroying the volume')
        vol.destroy()
    except Exception as e:
        _logger.debug("Failed to destroy volume", exc_info=True)
        _logger.error("Failed to destroy volume: %s", str(e))

    raise Exception('Failed to attach created volume: %s' % iscsiadm.error_message_from_code(retval))


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
    _, chap_passwords = load_cache(oci_utils.__chap_password_file)
    if chap_passwords is None:
        chap_passwords = {}
    chap_passwords[iqn] = (user, password)
    write_cache(cache_content=chap_passwords, cache_fname=oci_utils.__chap_password_file, mode=0o600)


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
    _logger.debug('Remove %s from chap secret cache', iqn_ocid)
    ret_value = None
    _, chap_passwords = load_cache(oci_utils.__chap_password_file)
    if not bool(chap_passwords):
        return ret_value

    iqn, _ = get_iqn_from_chap_secrets_cache(iqn_ocid)[0] if iqn_ocid.startswith(oci_volume_tag) else iqn_ocid, _

    if iqn in chap_passwords.keys():
        removed_values = chap_passwords.pop(iqn)
        ret_value = write_cache(cache_content=chap_passwords,
                                cache_fname=oci_utils.__chap_password_file,
                                mode=0o600)
    return ret_value


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
    _, chap_passwords = load_cache(oci_utils.__chap_password_file)
    if chap_passwords is None:
        return None, None
    if iqn in chap_passwords:
        return chap_passwords[iqn]
    return None, None


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
    _, iscsi_cache = load_cache(iscsiadm.ISCSIADM_CACHE)
    for portal in iscsi_cache:
        for p_ip, iqn_list in portal.items():
            if iqn_x in iqn_list:
                return p_ip
    return None


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
    _, chap_passwords = load_cache(oci_utils.__chap_password_file)
    if chap_passwords is None:
        return None, None
    for iqn, unpw in chap_passwords.items():
        if ocid == unpw[0]:
            return iqn, unpw[1]
    return None, None


_this_instance_ocid = None


def main():
    """
    Main.

    Returns
    -------
        int
            Return value of the operation, if any.
            0 otherwise.
    """
    global _this_instance_ocid

    parser = get_args_parser()
    args = parser.parse_args()
    _logger.debug('Command line: %s', args)
    if args.command is None:
        # default to 'sync' command
        args.command = "sync"

    if args.command == 'usage':
        parser.print_help()
        sys.exit(0)

    oci_sess = get_oci_api_session()

    # we need this at many places, grab it once
    if bool(oci_sess):
        if bool(oci_sess.this_instance()):
            _this_instance_ocid = oci_sess.this_instance().get_ocid()
    else:
        _this_instance_ocid = get_instance_ocid()

    if 'compat' in args and args.compat is True:
        # Display information as version 0.11 for compatibility reasons for few settings.
        args.output_mode = 'compat'
        args.details = True
        compat_mode = 'compat'
    else:
        compat_mode = 'gen'
    _logger.debug('Compatibility mode: %s', compat_mode)

    system_disks = lsblk.list()
    iscsiadm_session = iscsiadm.session()

    # starting from here, nothing works if we are not root
    _user_euid = os.geteuid()
    if _user_euid != 0:
        _logger.error("This program needs to be run with root privileges.")
        return 1

    if args.command == 'show':
        display_attached_volumes(oci_sess, iscsiadm_session, system_disks,
                                 args.output_mode, args.details, not args.no_truncate)
        if len(args.compartments) > 0 or args.all:
            api_display_available_block_volumes(oci_sess, args.compartments, args.all,
                                                args.output_mode, args.details, not args.no_truncate)

        return 0

    max_volumes = OCIUtilsConfiguration.getint('iscsi', 'max_volumes')
    if max_volumes > oci_utils._MAX_VOLUMES_LIMIT:
        _logger.error("Your configured max_volumes(%s) is over the limit(%s)",
                      max_volumes, oci_utils._MAX_VOLUMES_LIMIT)
        max_volumes = oci_utils._MAX_VOLUMES_LIMIT
    #
    # load iscsiadm-cache
    ocid_cache = load_cache(iscsiadm.ISCSIADM_CACHE, max_age=timedelta(minutes=2))[1]
    if ocid_cache is None:
        _logger.debug('Updating the cache')
        # run ocid once, to update the cache
        ocid_refresh(wait=True)
        # now try to load again
        ocid_cache = load_cache(iscsiadm.ISCSIADM_CACHE, max_age=timedelta(minutes=2))[1]
    if ocid_cache is None:
        targets, attach_failed = None, None
    else:
        targets, attach_failed = ocid_cache
    #
    # load detached volumes cache
    _logger.debug('iSCSI targets: %s', targets)
    detached_volume_iqns = load_cache(__ignore_file)[1]
    if detached_volume_iqns is None:
        detached_volume_iqns = []

    if args.command == 'sync' and not detached_volume_iqns and not attach_failed:
        # nothing to do, stop here
        print("All known devices are attached.")

    if args.command == 'sync':
        #
        # we still have volume not attached, process them.
        # this one is as good as obsolete, ocid takes care of execting iscsiadm attach commands.
        # and detached volume iqns contains volumes which are detached from ociinstance
        retval = 0
        _did_something = False
        # if detached_volume_iqns:
        #     print()
        #     print("Detached devices:")
        #     for iqn in detached_volume_iqns:
        #         # display_detached_iscsi_device(iqn, targets)
        #         display_iscsi_device(iqn, oci_sess)
        #         if args.apply or args.interactive:
        #             if args.yes:
        #                 ans = True
        #             else:
        #                 ans = _read_yn('Would you like to attach this device?',
        #                               yn=True,
        #                                waitenter=True,
        #                                suppose_yes=False,
        #                                default_yn=False)
        #                 # ans = ask_yes_no("Would you like to attach this device?")
        #            if ans:
        #                  try:
        #                     _do_iscsiadm_attach(iqn, targets)
        #                     _did_something = True
        #                 except Exception as e:
        #                     _logger.error('[%s] attachment failed: %s', iqn, str(e))
        #                    retval = 1

        if attach_failed:
            _logger.info("Devices that could not be attached automatically:")
            for iqn in list(attach_failed.keys()):
                # display_detached_iscsi_device(iqn, targets, attach_failed)
                display_iscsi_device(iqn, oci_sess)
                _attach_user_name = None
                _attach_user_passwd = None
                _give_it_a_try = False
                if args.apply or args.interactive:
                    if attach_failed[iqn] != 24:
                        # not authentication error
                        # if args.yes or ask_yes_no("Would you like to retry attaching this device?"):
                        if _read_yn('Would you like to retry attaching this device?',
                                    yn=True,
                                    waitenter=True,
                                    suppose_yes=False,
                                    default_yn=False):
                            _give_it_a_try = True
                    else:
                        # authentication error
                        # if args.yes or ask_yes_no("Would you like to configure this device?"):
                        if args.yes or _read_yn('Would you like to configure this device?',
                                                yn=True,
                                                waitenter=True,
                                                suppose_yes=False,
                                                default_yn=False):
                            _give_it_a_try = True
                            if oci_sess is not None:
                                oci_vols = oci_sess.find_volumes(iqn=iqn)
                                if len(oci_vols) != 1:
                                    _logger.error('volume [%s] not found', iqn)
                                    _give_it_a_try = False
                                _attach_user_name = oci_vols[0].get_user()
                                _attach_user_passwd = oci_vols[0].get_password()
                            else:
                                (_attach_user_name, _attach_user_passwd) = get_chap_secret(iqn)
                                if _attach_user_name is None:
                                    _logger.error('Cannot retreive chap credentials')
                                    _give_it_a_try = False
                    if _give_it_a_try:
                        try:
                            _do_iscsiadm_attach(iqn, targets, _attach_user_name, _attach_user_passwd)
                            _did_something = True
                        except Exception as e:
                            _logger.error("Failed to configure device automatically: %s", str(e))
                            retval = 1

        if _did_something:
            ocid_refresh()
        return retval

    if args.command == 'create':
        if len(system_disks) > max_volumes:
            _logger.error("This instance reached the max_volumes(%s)", max_volumes)
            return 1
        try:
            if bool(oci_sess):
                do_create_volume(oci_sess,
                                 size=args.size,
                                 display_name=args.volume_name,
                                 attach_it=args.attach_volume,
                                 chap_credentials=args.chap,
                                 mode=compat_mode)
            else:
                _logger.info('Unable to create volume, failed to create a session.')
                return 1
        except Exception as e:
            _logger.debug('Volume creation has failed: %s', str(e), stack_info=True, exc_info=True)
            _logger.error('Volume creation has failed: %s', str(e))
            return 1

        ocid_refresh()
        return 0

    if args.command == 'destroy':
        # destroy command used to be for only one volume
        # changed the behavior to be more aligned with attach/dettach commands
        # i.e : taking more than one ocid and doing best effort
        retval = 0
        if not args.yes:
            for ocid in args.ocids:
                _logger.info("Volume : [%s]", ocid)
            # if not ask_yes_no("WARNING: the volume(s) will be destroyed.  This is irreversible.  Continue?"):
            if not _read_yn('WARNING: the volume(s) will be destroyed.  This is irreversible.  Continue?',
                            yn=True,
                            waitenter=True,
                            suppose_yes=False,
                            default_yn=False):
                return 0
        for ocid in args.ocids:
            try:
                if bool(oci_sess):
                    _logger.debug('Destroying [%s]', ocid)
                    #
                    # try to get the iqn from a detached volume
                    _iqn = _get_iqn_from_ocid(oci_sess, ocid)
                    do_destroy_volume(oci_sess, ocid)
                    _ = remove_chap_secret(ocid)
                    _logger.info("Volume [%s] is destroyed", ocid)
                    #
                    # remove iqn from ignore list.
                    if bool(_iqn):
                        if _iqn in detached_volume_iqns:
                            detached_volume_iqns.remove(_iqn)
                            write_cache(cache_content=detached_volume_iqns, cache_fname=__ignore_file)
                            _logger.debug('%s removed from cache.', _iqn)
                else:
                    _logger.info('Unable to destroy volume, failed to create a session.')
                    retval = 1
            except Exception as e:
                _logger.debug('Volume [%s] deletion has failed: %s', ocid, str(e), stack_info=True, exc_info=True)
                _logger.error('Volume [%s] deletion has failed: %s', ocid, str(e))
                retval = 1

        return retval

    if args.command == 'detach':
        retval = 0
        for iqn in args.iqns:
            if iqn in detached_volume_iqns:
                _logger.error("Target [%s] is already detached", iqn)
                retval = 1
                continue
            if iqn not in iscsiadm_session or 'device' not in iscsiadm_session[iqn]:
                _logger.error("Target [%s] not found", iqn)
                retval = 1
                continue

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
                    do_detach_volume(oci_sess, iscsiadm_session, iqn, mode=compat_mode)
                    compat_info_message(gen_msg="Volume [%s] is detached." % iqn, mode=compat_mode)
                    detached_volume_iqns.append(iqn)
                else:
                    _logger.info('Unable to detach volume, failed to create a session.')
                    retval = 1
            except Exception as e:
                _logger.debug('Volume [%s] detach has failed: %s', iqn, str(e), stack_info=True, exc_info=True)
                _logger.error('Volume [%s] detach has failed: %s', iqn, str(e))
                retval = 1

        if retval == 0:
            # compat_info_message(gen_msg="Updating detached volume cache file: remove %s" % iqn, mode=compat_mode)
            # compat_info_message(gen_msg="Volume [%s] successfully detached." % iqn, mode=compat_mode)
            write_cache(cache_content=detached_volume_iqns, cache_fname=__ignore_file)

        _logger.debug('Trigger ocid refresh')
        ocid_refresh()

        return retval

    if args.command == 'attach':
        if len(system_disks) > max_volumes:
            _logger.error("This instance reached the maximum number of volumes attached (%s)", max_volumes)
            return 1

        if bool(args.ocids):
            iqnocid = args.ocids
        elif bool(args.iqns):
            iqnocid = args.iqns
        else:
            # should be trapped by argparse, one of those is required.
            _logger.error('Missing iqns or ocids')
            sys.exit(1)

        retval = 0
        for iqn in iqnocid:
            _iqn_to_use = iqn
            _save_chap_cred = False
            if iqn in iscsiadm_session:
                _logger.info("Target [%s] is already attached.", iqn)
                continue

            if _iqn_to_use.startswith(oci_volume_tag):
                #
                # ocid
                _logger.debug('Given IQN [%s] is probably an ocid, attaching it', _iqn_to_use)
                bs_volume = None
                try:
                    if bool(oci_sess):
                        compat_info_message(compat_msg="Attaching iSCSI device.", mode=compat_mode)
                        #
                        # verify if volume is in the chap secrets cache
                        this_iqn, this_pw = get_iqn_from_chap_secrets_cache(_iqn_to_use)
                        _logger.debug('The cache: iqn %s pw %s', this_iqn, this_pw)
                        if this_iqn is not None or args.chap:
                            _logger.debug('Using chap secret')
                            bs_volume = _do_attach_oci_block_volume(oci_sess, _iqn_to_use, chap=True)
                        else:
                            _logger.debug('Not using chap secret.')
                            bs_volume = _do_attach_oci_block_volume(oci_sess, _iqn_to_use, chap=False)
                        compat_info_message(gen_msg='Volume [%s] is attached' % _iqn_to_use,
                                            compat_msg='Result: command executed successfully',
                                            mode=compat_mode)
                        # user/pass coming from volume itself
                        _attachment_username = bs_volume.get_user()
                        _attachment_password = bs_volume.get_password()
                        _iscsi_portal_ip = bs_volume.get_portal_ip()
                        _iqn_to_use = bs_volume.get_iqn()
                        if args.chap:
                            _save_chap_cred = True
                    else:
                        _logger.info('Unable to attach volume, failed to create a session.')
                        retval = 1
                except Exception as e:
                    _logger.debug('Failed to attach volume [%s]: %s', _iqn_to_use, str(e),
                                                                      stack_info=True,
                                                                      exc_info=True)
                    _logger.error('Failed to attach volume [%s]: %s', _iqn_to_use, str(e))
                    retval = 1
                    continue
            elif _iqn_to_use.startswith(iqn_tag):
                #
                # iqn
                _logger.debug('Given IQN [%s] is probably an iqn, attaching it', _iqn_to_use)
                #
                # iqn is not in iscsiadm session ... might also not be in this_instance volume list..
                this_ocid = _is_iqn_attached(oci_sess, _iqn_to_use)
                if not this_ocid:
                    #
                    # volume is not attached to oci, giving up for now instead of letting it timeout for 90 sec
                    _logger.error('A volume with iqn [%s] is not in this instance list '
                                  'of attached block volumes, attach it using the ocid.', _iqn_to_use)
                    retval = 1
                    continue

                pip_cand = get_portal_ip_from_iscsiadm_cache(_iqn_to_use)
                if args.username is not None and args.password is not None:
                    _attachment_username = args.username
                    _attachment_password = args.password
                else:
                    # user/pass not provided , looking in the cache
                    (_attachment_username, _attachment_password) = get_chap_secret(iqn)
                #
                # in fact not necessary but for the sake of completeness.
                if _attachment_username is not None and _attachment_password is not None:
                    _save_chap_cred = True

                if _iqn_to_use in iscsiadm_session:
                    _iscsi_portal_ip = iscsiadm_session[_iqn_to_use]['current_portal_ip']
                    _logger.debug('Portal ip for [%s] is [%s]', _iqn_to_use, _iscsi_portal_ip)
                elif pip_cand is not None:
                    _iscsi_portal_ip = pip_cand
                else:
                    _logger.info('Invalid argument, iqn [%s] not found', _iqn_to_use)
                    retval = 1
                    continue
            else:
                #
                # invalid parameter
                _logger.info('Invalid argument, given IQN [%s] is not an iqn nor an ocid.', _iqn_to_use)
                retval = 1
                continue

            _logger.debug('Attaching [%s] to iSCSI session', _iqn_to_use)
            try:
                _do_iscsiadm_attach(_iqn_to_use,
                                    targets,
                                    user=_attachment_username,
                                    passwd=_attachment_password,
                                    iscsi_portal_ip=_iscsi_portal_ip)
                _logger.debug('Attachment of %s succeeded.', _iqn_to_use)
                if _iqn_to_use in detached_volume_iqns:
                    detached_volume_iqns.remove(_iqn_to_use)
            except Exception as e:
                _logger.debug("Failed to attach target [%s]: %s", _iqn_to_use, str(e), exc_info=True, stack_info=True)
                _logger.error("Failed to attach target [%s]: %s", _iqn_to_use, str(e))
                _save_chap_cred = False
                retval = 1
                continue

            if _save_chap_cred:
                _logger.debug('Attachment OK: saving chap credentials.')
                add_chap_secret(_iqn_to_use, _attachment_username, _attachment_password)

        if retval == 0:
            # compat_info_message(gen_msg="Volume [%s] successfully attached." % _iqn_to_use)
            #
            # update detached volume cache
            # compat_info_message(gen_msg="Updating detached volume cache file: remove %s if necessary."
            #                             % _iqn_to_use, mode=compat_mode)
            write_cache(cache_content=detached_volume_iqns, cache_fname=__ignore_file)
            #
            # run ocid.refresh
            _logger.debug('Trigger ocid refresh.')
            ocid_refresh()

        return retval

    if not attach_failed and not detached_volume_iqns:
        print("All known devices are attached.")
        print("Use the -s, --show or show option for details.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
