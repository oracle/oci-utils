# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
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

import oci_utils.oci_api
from oci_utils import __ignore_file, iscsiadm, lsblk
from oci_utils import _configuration as OCIUtilsConfiguration
from oci_utils import (OCI_ATTACHMENT_STATE, OCI_VOLUME_SIZE_FMT)
from oci_utils.cache import load_cache, write_cache
from oci_utils.exceptions import OCISDKError
from oci_utils.metadata import InstanceMetadata
from oci_utils.impl.oci_resources import OCIVolume


_logger = logging.getLogger("oci-utils.oci-iscsi-config")

def volume_size_validator(value):
    """
    validate than value passed is an int and greater then 50 (GB)
    """
    _i_value = 0
    try:
        _i_value = int(value)
    except ValueError as e :
        raise ValueError("block volume size must be a int") from e

    if _i_value < 50:
        raise ValueError("Volume size must be at least 50GBs")
    return _i_value

def iqn_list_validator(value):
    """
    validate than value passed is a list of iqn
    """
    _iqns =  [iqn.strip() for iqn in value.split(',')  if iqn]
    for iqn in _iqns:
        if not iqn.startswith("iqn."):
            raise ValueError('Invalid IQN %s' % iqn)
    return _iqns
def boot_iqn_list_validator(value):
    """
    validate than value passed is a list of iqn and do nto contain boot volume
    """
    _iqns =  [iqn.strip() for iqn in value.split(',')  if iqn]
    for iqn in _iqns:
        if not iqn.startswith("iqn."):
            raise ValueError('Invalid IQN %s' % iqn)
        if 'boot:uefi' in iqn:
            raise ValueError('Cannot detach boot volume IQN %s' % iqn)
    return _iqns

def get_args_parser():
    """
    Parse the command line arguments and return an object representing the
    command line (as returned by argparse's parse_args()).

    Returns
    -------
        The commandline argparse namespace.
    """
    parser = argparse.ArgumentParser(description='Utility for listing or '
                                                 'configuring iSCSI devices '
                                                 'on an OCI '
                                                 'instance.')
    subparser = parser.add_subparsers(dest='command')
    subparser.add_parser('usage',description='Displays usage')
    show_parser = subparser.add_parser('show',description='Show block volumes and iSCSI information')
    show_parser.add_argument('-C','--compartments', metavar='COMP',
                        type=lambda s: [ocid.strip() for ocid in s.split(',')  if ocid],
                        help='Display iSCSI devices in the given comparment(s)'
                             ' or all compartments if COMP is "all".')
    show_parser.add_argument('-A', '--all', action='store_true', default=False,
                        help='Display all iSCSI devices. By default only devices that are not attached to an instance are listed.')

    create_parser = subparser.add_parser('create',description='Creates a block volume')
    create_parser.add_argument('-S','--size',type=volume_size_validator, required=True, help='Size of the block volume to create in GB')
    create_parser.add_argument('-v','--volume-name',help='Name of the block volume to create')
    create_parser.add_argument('-s', '--show', action='store_true', help='Display the iSCSI configuration after the creation')

    attach_parser = subparser.add_parser('attach',description='Attach a block volume')
    attach_parser.add_argument('-i', '--interactive', action='store_true', help='Run in interactive mode')
    attach_parser.add_argument('-I','--iqns',required=True, type=iqn_list_validator,
                                 help='IQN(s) of the iSCSI devices to be attach')
    attach_parser.add_argument('-u', '--username', metavar='USER', action='store',
                               help='Use USER as the user name when attaching a device that requires CHAP authentication')
    attach_parser.add_argument('-p', '--password', metavar='PASSWD', action='store',
                               help='Use PASSWD as the password when attaching a device that requires CHAP authentication')
    attach_parser.add_argument('-s', '--show', action='store_true', help='Display the iSCSI configuration after the attach operation')

    detach_parser = subparser.add_parser('detach',description='Detach a block volume')
    detach_parser.add_argument('-i', '--interactive', action='store_true', help='Run in interactive mode')
    detach_parser.add_argument('-I','--iqns',required=True, type=boot_iqn_list_validator,
                                 help='IQN(s) of the iSCSI devices to be dettached')
    detach_parser.add_argument('-s', '--show', action='store_true', help='Display the iSCSI configuration after the detach operation')


    destroy_parser = subparser.add_parser('destroy',description='Destroy a block volume')
    destroy_parser.add_argument('-O','--ocids',required=True, type=lambda s: [ocid.strip() for ocid in s.split(',')  if ocid],
                                 help='OCID(s) of volumes to be destroyed')
    destroy_parser.add_argument('-s', '--show', action='store_true', help='Display the iSCSI configuration after the destruction')

    return parser


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


def nvl(value, defval="Unknown"):
    """
    Provide a default value for empty/NULL/None.

    Parameters
    ----------
    value: obj
        The value to verify.
    defval: obj
        The value to return if the provide value is None or empty.

    Returns
    -------
        defval if value is None or empty, otherwise return value

    """
    if value is None:
        return defval
    if not value:
        return defval
    return value


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
    _cmd = ['/usr/libexec/ocid','--refresh', 'iscsi']
    if wait:
        _cmd.append('--no-daemon')
    try:
        output = subprocess.check_output(_cmd, stderr=subprocess.STDOUT)
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug(str(output))
        return True
    except subprocess.CalledProcessError as e :
        _logger.debug('launch of ocid failed : %s',str(e))
        return False

def _display_block_volume(volume):
    """
    display information about a block volume
    argument:
        volume : OCIVOlume
    """
    assert isinstance (volume, OCIVolume) , 'Must be a OCIVolume'

    print("Volume name:    %s" % volume.get_display_name())
    print("Volume OCID:    %s" % volume.get_ocid())
    print("Volume iSCSI target %s" % volume.get_iqn())
    print("Volume size:    %s" % volume.get_size(format_str=OCI_VOLUME_SIZE_FMT.HUMAN.name))
    if volume.is_attached():
        if volume.get_instance().get_ocid() == get_instance_ocid():
            instance = "this instance"
        else:
            instance = "instance %s (%s)" % \
                           (volume.get_instance().get_display_name(),
                            volume.get_instance().get_public_ip())
            print("   attached to: %s" % instance)
    else:
        print("   attached to: (not attached)")

def display_current_devices(oci_sess, iscsiadm_session, disks):
    """
    Display the attched iSCSI devices.

    Parameters
    ----------
    oci_sess: OCISession
        An OCI session
    iscsiadm_session: dict
        An iscsiadm session (as returned by oci_utils.iscsiadm.session())
    disks: dict
        List of disk to be displayed. Information about disks in the system,
        as returned by lsblk.list()

    Returns
    -------
       No return value.
    """
    print("Currently attached iSCSI devices:")
    oci_vols = []
    try:
        oci_vols = oci_sess.this_instance().all_volumes()
    except Exception as e:
        oci_vols = []
        _logger.debug('Cannot get all volumes of this instance : %s' , str(e))

    if not iscsiadm_session and len(oci_vols) > 0:
        print("Local iSCSI info not available. ")
        print("List info from Cloud instead(No boot volume).")
        print("")
        for oci_vol in oci_vols:
            _display_block_volume(oci_vol)


    for iqn in list(iscsiadm_session.keys()):
        oci_vol = get_volume_by_iqn(oci_sess, iqn)
        if oci_vol is None:
            _logger.debug('Cannot find volume by iqn [%s]' % iqn)

        print()
        print("Target %s" % iqn)
        if oci_vol is not None:
            print("         Volume name:    %s"
                    % oci_vol.get_display_name())
            print("         Volume OCID:    %s"
                    % oci_vol.get_ocid())

        print("   Persistent portal:    %s:%s" %
                (iscsiadm_session[iqn]['persistent_portal_ip'],
                iscsiadm_session[iqn]['persistent_portal_port']))
        print("      Current portal:    %s:%s" %
                (iscsiadm_session[iqn]['current_portal_ip'],
                iscsiadm_session[iqn]['current_portal_port']))
        if 'session_state' in iscsiadm_session[iqn]:
            print("               State:    %s" %
                    iscsiadm_session[iqn]['session_state'])
        if 'device' not in iscsiadm_session[iqn]:
            print()
            continue
        device = iscsiadm_session[iqn]['device']
        print("     Attached device:    %s" % device)
        if device in disks:
            print("                Size:    %s" % disks[device]['size'])
            if 'partitions' not in disks[device]:
                print("    File system type:    %s" %
                        nvl(disks[device]['fstype']))
                print("          Mountpoint:    %s" %
                        nvl(disks[device]['mountpoint'], "Not mounted"))
            else:
                print("          Partitions:    "
                        "Device  %6s  %10s   Mountpoint" %
                        ("Size", "Filesystem"))
                partitions = disks[device]['partitions']
                plist = list(partitions.keys())
                plist.sort()
                for part in plist:
                    print("                         %s  %8s  %10s   %s" %
                            (part, partitions[part]['size'],
                            nvl(partitions[part]['fstype'], "Unknown fs"),
                            nvl(partitions[part]['mountpoint'],
                                "Not mounted")))



def display_detached_iscsi_device(iqn, targets, attach_failed=()):
    """
    Display the iSCSI devices

    Parameters
    ----------
    iqn: str
        The iSCSI qualified name.
    targets: dict
        The targets.
    attach_failed: dict
        The devices for which attachment failed.
    """
    print("Target %s" % iqn)
    for ipaddr in list(targets.keys()):
        if iqn in targets[ipaddr]:
            print("              Portal:    %s:%s" % (ipaddr, 3260))
            if iqn in attach_failed:
                print("               State:    %s" % iscsiadm.error_message_from_code(attach_failed[iqn]))
            else:
                print("               State:    Detached")


def _do_iscsiadm_attach(iqn, targets, user=None, passwd=None):
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

    Returns
    -------
        None
    Raise
    -----
    Exception in case of error
    """

    portal_ip = None
    if targets is None:
        raise Exception ("ocid must be running to determine the portal IP address for this device")

    for ipaddr in list(targets.keys()):
        if iqn in targets[ipaddr]:
            portal_ip = ipaddr
    if portal_ip is None:
        # this shouldn't really happen, but just in case
        raise Exception("Can't find portal IP address")

    retval = iscsiadm.attach(portal_ip, 3260, iqn,
                             user, passwd,
                             auto_startup=True)

    _logger.info("Result: %s" % iscsiadm.error_message_from_code(retval))


def do_detach_volume(oci_session , iscsiadm_session , iqn):
    """
    Detach the volume with given IQN

    Parameters
    ----------
    oci_session: OCISession
        The iscsiadm session.
    iscsiadm_session:
        iscsiadm.session()
    ocid: str
        The OCID.

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
        _logger.info("Detaching volume")
        _volume.detach()
    except OCISDKError as e:
        _logger.debug("Failed to disconnect volume", exc_info=True)
        raise Exception("Failed to disconnect volume %s: %s" % iqn) from e

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

    vol = None
    try:
        vol = sess.get_volume(ocid)
    except Exception as e:
        _logger.debug("Failed to retrieve Volume details", exc_info=True)
        raise Exception ("Failed to retrieve Volume details: %s" % ocid) from e

    if vol is None:
        raise Exception ("Volume not found: %s" % ocid)

    if vol.is_attached():
        raise Exception ("Cannot destroy an attached volume")

    try:
        vol.destroy()
    except Exception as e:
        _logger.debug("Failed to destroy volume %s", ocid,exc_info=True)
        raise Exception("Failed to destroy volume") from e



def api_display_available_block_volumes(sess, compartments=(),show_all=False):
    """
    Display the available devices.

    Parameters
    ----------
    sess: OCISession
        The OCISession instance.
    compartments: list of str
        compartement ocid(s)
    all: boot
        display all volumes. By default display only not-attached  ones
    Returns
    -------
        No return value.
    """

    vols = []
    if compartments and len(compartments) > 0:
        for cspec in compartments:
            if cspec == 'all':
                vols = sess.all_volumes()
                break
            if cspec.startswith('ocid1.compartment.oc1..'):
                # compartment specified with its ocid
                comp = sess.get_compartment(ocid=cspec)
                if comp is None:
                    _logger.error("Compartment not found: %s" % cspec)
                else:
                    cvols = comp.all_volumes()
                    vols += cvols
            else:
                # compartment specified with display name regexp
                comps = sess.find_compartments(display_name=cspec)
                if len(comps) == 0:
                    _logger.error("No compartments matching '%s' found" % cspec)
                else:
                    for comp in comps:
                        cvols = comp.all_volumes()
                        vols += cvols
    else:
        # -C/--compartment option wasn't used, default to the instance's own
        # compartment
        comp = sess.this_compartment()
        avail_domain = sess.this_availability_domain()
        if comp is not None:
            vols = comp.all_volumes(availability_domain=avail_domain)
        else:
            _logger.error("Compartment for this instance not found")

    if len(vols) == 0:
        _logger.info("No additional storage volumes found.")
        return

    print("Other available storage volumes:")
    print()

    for vol in vols:
        if vol.is_attached() and not show_all:
            continue
        print("Volume %s" % vol.get_display_name())
        print("   OCID:        %s" % vol.get_ocid())
        if vol.is_attached():
            if vol.get_instance().get_ocid() \
                    == sess.this_instance().get_ocid():
                instance = "this instance"
            else:
                instance = "instance %s (%s)" % \
                           (vol.get_instance().get_display_name(),
                            vol.get_instance().get_public_ip())
            print("   attached to: %s" % instance)
        else:
            print("   attached to: (not attached)")
        print("   size:        %s" %
              vol.get_size(format_str=OCI_VOLUME_SIZE_FMT.HUMAN.name))
        print()


def _do_attach_oci_block_volume(sess, ocid):
    """
    Make API calls to attach a volume with the given OCID to this instance.

    Parameters
    ----------
    sess : OCISession
        An OCISession instance
    ocid : str
        The volume OCID
    Returns
    -------
        None
    Raise:
        Exception if attachement failed
    """

    vol = sess.get_volume(ocid)
    if vol is None:
        raise Exception("Volume %s not found" % ocid)

    if vol.is_attached():
        if vol.get_instance().get_ocid() == sess.this_instance().get_ocid():
            # attached to this instance already
            _logger.info("Volume %s already attached to this instance" ,ocid)
        else:
            raise Exception("Volume %s already attached to instance %s (%s)"
                        % (ocid, vol.get_instance().get_display_name(),
                            vol.get_instance().get_public_ip()))
    else:
        _logger.info("Attaching OCI Volume to this instance.")
        vol = vol.attach_to(instance_id=sess.this_instance().get_ocid(), wait=True)
        _logger.debug("Volume attached")

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
       OCIVOlume : the found volume or None
    """
    _logger.debug('Looking for volume with IQN == %s' % iqn)
    if not hasattr(get_volume_by_iqn, 'all_this_instance_volume'):
        get_volume_by_iqn.all_this_instance_volume = sess.this_instance().all_volumes()

    for v in get_volume_by_iqn.all_this_instance_volume:
        if v.get_iqn() == iqn:
            _logger.debug('found %s', str(v))
            return v
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
        _logger.info("Unmounting %s" % mountpoint)
        subprocess.check_output(['/usr/bin/umount',
                                 mountpoint], stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        _logger.error("Failed to unmount %s: %s" ,mountpoint, e.output)
        return False


def unmount_device(session, iqn, disks):
    """
    Unmount the partitions of the device with the specified iqn, if they are
    mounted.

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
            # volume has not partitions and is currently mounted
            if not do_umount(disks[device]['mountpoint']):
                retval = False
    else:
        partitions = disks[device]['partitions']
        for part in list(partitions.keys()):
            if partitions[part]['mountpoint'] != '':
                # the partition is mounted
                if not do_umount(partitions[part]['mountpoint']):
                    retval = False
    return retval


def do_create_volume(sess, size, display_name):
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

    Returns
    -------
       nothing
    Raises
    ------
       Exception if something went wrong
    """

    try:
        _logger.info("Creating a new %d GB volume" , size)
        inst = sess.this_instance()
        if inst is None:
            raise Exception ("OCI SDK error: couldn't get instance info")

        vol = inst.create_volume(size=size,
                                 display_name=display_name)
    except Exception as e:
        _logger.debug("Failed to create volume", exc_info=True)
        raise Exception ("Failed to create volume") from e

    _logger.info("Volume %s created" , vol.get_display_name())

    # attach using iscsiadm commands
    state = vol.get_attachment_state()
    if OCI_ATTACHMENT_STATE[state] in (
            OCI_ATTACHMENT_STATE.ATTACHED, OCI_ATTACHMENT_STATE.ATTACHING):
        _logger.info("Volume %s is %s" , vol.get_display_name(), state)
        return

    _logger.info("Attaching iSCSI device")
    retval = iscsiadm.attach(ipaddr=vol.get_portal_ip(),
                             port=vol.get_portal_port(),
                             iqn=vol.get_iqn(),
                             username=vol.get_user(),
                             password=vol.get_password(),
                             auto_startup=True)
    _logger.info("iscsiadm attach Result: %s" , iscsiadm.error_message_from_code(retval))
    if retval == 0:
        _logger.debug('Creation succesful')
        return

    # here because of error case
    try:
        _logger.debug('destroying the volume')
        vol.destroy()
    except Exception as e:
        _logger.debug("Failed to destroy volume", exc_info=True)
        _logger.error("Failed to destroy volume: %s" ,str(e))

    raise Exception('Failed to attach created volume: %s' % iscsiadm.error_message_from_code(retval))




def save_chap_secret(iqn, user, password):
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
    _, chap_passwords = \
        load_cache(oci_utils.__chap_password_file)
    if chap_passwords is None:
        chap_passwords = {}
    chap_passwords[iqn] = (user, password)
    write_cache(cache_content=chap_passwords,
                cache_fname=oci_utils.__chap_password_file,
                mode=0o600)


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
    _, chap_passwords = \
        load_cache(oci_utils.__chap_password_file)
    if chap_passwords is None:
        return None, None
    if iqn in chap_passwords:
        return chap_passwords[iqn]
    return None, None


def main():
    """
    Main.

    Returns
    -------
        int
            Return value of the operation, if any.
            0 otherwise.
    """

    parser = get_args_parser()
    args = parser.parse_args()
    if args.command is None:
        # default to 'show' command
        args.command = "show"


    if args.command == 'usage':
        parser.print_help()
        sys.exit(0)

    oci_sess = None
    try:
        oci_sess = oci_utils.oci_api.OCISession()
    except Exception as e:
        _logger.debug('Cannot get OCI session: %s',str(e))

    system_disks = lsblk.list()
    iscsiadm_session = iscsiadm.session()

    if args.command == 'show':
        display_current_devices(oci_sess, iscsiadm_session, system_disks)
        if args.compartments:
            api_display_available_block_volumes(oci_sess, args.compartments, args.all)
        else:
            api_display_available_block_volumes(oci_sess, None, args.all)
        return 0

    # starting from here, nothing works if we are not root
    _user_euid = os.geteuid()
    if _user_euid != 0:
        _logger.error("You must run this program with root privileges")
        return 1

    if not os.path.isfile("/var/run/ocid.pid"):
        _logger.error("Warning:\n"
                      "For full functionality of this utility the ocid "
                      "service must be running\n"
                      "The administrator can start it using this command:\n"
                      "    sudo systemctl start ocid.service\n")

    max_volumes = OCIUtilsConfiguration.getint('iscsi', 'max_volumes')
    if max_volumes > oci_utils._MAX_VOLUMES_LIMIT:
        _logger.error(
            "Your configured max_volumes(%s) is over the limit(%s)"
            % (max_volumes, oci_utils._MAX_VOLUMES_LIMIT))
        max_volumes = oci_utils._MAX_VOLUMES_LIMIT

    ocid_cache = load_cache(iscsiadm.ISCSIADM_CACHE,
                            max_age=timedelta(minutes=2))[1]
    if ocid_cache is None:
        _logger.debug('updating the cache')
        # run ocid once, to update the cache
        ocid_refresh(wait=True)
        # now try to load again
        ocid_cache = load_cache(iscsiadm.ISCSIADM_CACHE,
                                max_age=timedelta(minutes=2))[1]
    if ocid_cache is None:
        targets, attach_failed = None, None
    else:
        targets, attach_failed = ocid_cache

    detached_volume_iqns = load_cache(__ignore_file)[1]
    if detached_volume_iqns is None:
        detached_volume_iqns = []

    if args.command == 'create':
        if len(system_disks) > max_volumes:
            _logger.error(
                "This instance reached the max_volumes(%s)" % max_volumes)
            return 1
        try:
            do_create_volume(oci_sess, size=args.size, display_name=args.volume_name)
            if args.show:
                display_current_devices(oci_sess, iscsiadm_session, system_disks)
                api_display_available_block_volumes(oci_sess)
            return 0
        except Exception as e:
            _logger.error('volume creation has failed: %s', str(e))
            return 1

    if args.command == 'destroy':
        # destroy command used to be for only one volume
        # changed the behavior to be more aligned with attach/dettach commands
        # i.e : taking more than one ocid and doing best effort
        retval = 0
        if args.interactive:
            for ocid in args.ocids:
                _logger.info("volume : %s", ocid)
            if not ask_yes_no("WARNING: the volume(s) will be destroyed.  This is irreversible.  Continue?"):
                return 0
        for ocid in args.ocids:
            try:
                _logger.debug('Destroying [%s]',ocid)
                do_destroy_volume(oci_sess, ocid)
                _logger.info("Volume [%s] is destroyed",ocid)
            except Exception as e:
                _logger.error('volume [%s] deletion has failed: %s', ocid,str(e))
                retval = 1

        if args.show:
            display_current_devices(oci_sess, iscsiadm_session, system_disks)
            api_display_available_block_volumes(oci_sess)
        return retval

    if args.command == 'detach':
        retval = 0
        for iqn in args.iqns:
            if iqn in detached_volume_iqns:
                _logger.error("Target %s is already detached" , iqn)
                retval = 1
                continue
            if iqn not in iscsiadm_session  or 'device' not in iscsiadm_session[iqn]:
                _logger.error("Target %s not found" , iqn)
                retval = 1
                continue
            _logger.debug('unmounting the block volume')
            if not unmount_device(iscsiadm_session, iqn, system_disks):
                _logger.debug('Unmounting has failed')
                if args.interactive:
                    if not  ask_yes_no("Failed to unmount volume, Continue detaching anyway?"):
                        continue
            try:
                _logger.debug('Detaching [%s]',iqn)
                do_detach_volume(oci_sess, iscsiadm_session, iqn)
                _logger.info("Volume [%s] is detached",iqn)
                detached_volume_iqns.append(iqn)
            except Exception as e:
                _logger.error('volume [%s] detach has failed: %s', iqn,str(e))
                retval = 1
        if args.show:
            display_current_devices(oci_sess, iscsiadm_session, system_disks)
            api_display_available_block_volumes(oci_sess)

        _logger.info("Updating detached volume cache file: %s" % detached_volume_iqns)
        write_cache(cache_content=detached_volume_iqns, cache_fname=__ignore_file)
        _logger.debug('trigger ocid refresh')
        ocid_refresh()

        return retval

    if args.command=='attach':
        if len(system_disks) > max_volumes:
            _logger.error(
                "This instance reached the maximum number of volumes attached (%s)" , max_volumes)
            return 1

        retval = 0

        for iqn in args.iqns:
            _save_chap_cred=False
            if iqn in iscsiadm_session:
                _logger.info("Target %s is already attached." % iqn)
                continue

            if iqn.startswith('ocid1.volume.oc'):
                _logger.debug('given IQN [%s] is an ocid, attaching it',iqn)
                bs_volume = None
                try:
                    bs_volume = _do_attach_oci_block_volume(oci_sess, iqn)
                    _logger.info("Volume [%s] is attache",iqn)
                except Exception as e:
                    _logger.error('Failed to attach volume [%s]: %s', iqn,str(e))
                    retval = 1
                # user/pass coming from volume itself
                _attachment_username = bs_volume.get_user()
                _attachment_password = bs_volume.get_password()
            else:
                if args.username is not None and  args.password is not None:
                    _attachment_username = args.username
                    _attachment_password = args.password
                else:
                    # user/pass not provided , asking for it
                    (_attachment_username,_attachment_password) =  get_chap_secret(iqn)
                    _save_chap_cred = True

            if iqn not in detached_volume_iqns:
                _logger.error("Target IQN %s not found" , iqn)
                retval = 1
                continue

            _logger.debug('attaching [%s] to iSCSI session',iqn)
            try:
                _do_iscsiadm_attach(iqn, targets,user=_attachment_username, passwd=_attachment_password)
                _logger.debug('attach ok')
                detached_volume_iqns.remove(iqn)
            except Exception as e:
                _logger.error("Failed to attach target %s: %s" % (iqn,str(e)))
                _save_chap_cred = False
                retval = 1

            if _save_chap_cred:
                _logger.debug('attachment OK: saving chap creds')
                save_chap_secret(iqn, _attachment_username, _attachment_password)

        if args.show:
            display_current_devices(oci_sess, iscsiadm_session, system_disks)
            api_display_available_block_volumes(oci_sess)

        _logger.info("Updating detached volume cache file: %s" % detached_volume_iqns)
        write_cache(cache_content=detached_volume_iqns, cache_fname=__ignore_file)
        _logger.debug('trigger ocid refresh')
        ocid_refresh()

        return retval

    # we still have volume not attached, process them.
    if detached_volume_iqns:
        print()
        print("Detached devices:")
        _did_something = False
        for iqn in detached_volume_iqns:
            display_detached_iscsi_device(iqn, targets)
            if args.interactive:
                ans = ask_yes_no("Would you like to attach this device?")
                if ans:
                    try:
                        _do_iscsiadm_attach(oci_sess, iqn, targets)
                        _did_something = True
                    except Exception as e:
                        _logger.error('[%s] attachement failed: %s' , iqn, str(e))
        if _did_something:
            ocid_refresh()

    if attach_failed:
        do_refresh = False
        _logger.info("Devices that could not be attached automatically:")
        for iqn in list(attach_failed.keys()):
            display_detached_iscsi_device(iqn, targets, attach_failed)
            _attach_user_name = None
            _attach_user_passwd = None
            _give_it_a_try = False
            if args.interactive:
                if attach_failed[iqn] != 24:
                    # not authentication error
                    if ask_yes_no("Would you like to retry attaching this device?"):
                        _give_it_a_try=True
                else:
                    # authentication error
                    if ask_yes_no("Would you like to configure this device?"):
                        _give_it_a_try=True
                        if oci_sess is not None:
                            oci_vols = oci_sess.find_volumes(iqn=iqn)
                            if len(oci_vols) != 1:
                                _logger.error('volume [%s] not found',iqn)
                                _give_it_a_try=False
                            _attach_user_name = oci_vols[0].get_user()
                            _attach_user_passwd = oci_vols[0].get_password()
                        else:
                            (_attach_user_name, _attach_user_passwd) = get_chap_secret(iqn)
                            if _attach_user_name is None:
                                _logger.error('Cannot retreive chap credentials')
                                _give_it_a_try=False
                if _give_it_a_try:
                    try:
                        _do_iscsiadm_attach(iqn, targets, _attach_user_name, _attach_user_passwd)
                        do_refresh = True
                    except Exception as e:
                        _logger.error("Failed to configure device automatically: %s", str(e))

    if do_refresh:
        ocid_refresh()


    if not args.show and not attach_failed and not detached_volume_iqns:
        print("All known devices are attached.")
        print("Use the -s or --show option for details.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
