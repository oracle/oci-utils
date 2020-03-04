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

_user_euid = None

_logger = logging.getLogger("oci-utils.oci-iscsi-config")

def parse_args():
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
                                                 'instance.', add_help=False)
    parser.add_argument('-i', '--interactive', action='store_true',
                        help='Run in interactive mode')
    parser.add_argument('-s', '--show', action='store_true',
                        help='Display the current iSCSI configuration')
    parser.add_argument('-C', '--compartment', metavar='COMP',
                        action='append', dest='compartments',
                        help='Display iSCSI devices in the given comparment(s)'
                             ' or all compartments if COMP is "all".  '
                             'Requires the '
                             'OCI Python SDK')
    parser.add_argument('-A', '--all', action='store_true',
                        help='Display all iSCSI devices. By default only '
                             'devices that are not attached to an instance are '
                             'listed.  Requires the OCI Python SDK.')
    parser.add_argument('-d', '--detach', metavar='TARGET', dest='detach_iqns',
                        action='append', type=str,
                        help='Detach the iSCSI device with the specified IQN')
    parser.add_argument('-a', '--attach', metavar='TARGET', dest='attach_iqns',
                        action='append', type=str,
                        help='Attach the iSCSI device with the specified IQN '
                             'or volume OCID')
    parser.add_argument('-c', '--create-volume', metavar='SIZE', action='store',
                        type=int,
                        help='Create a new volume and attach it to this '
                             'instance. SIZE is in gigabytes.  Use '
                             '--volume-name to specify a name for the volume.')
    parser.add_argument('--volume-name', metavar='NAME', action='store',
                        type=str, help='When used with --create-volume, '
                                       'set the name of the new volume to NAME')
    # parser.add_argument('--use-chap', action='store_true',
    #                     help='Use CHAP authentication when attaching an '
    #                     'OCI volume to this instance.')
    parser.add_argument('--username', metavar='USER', action='store',
                        type=str,
                        help='Use USER as the user name when attaching a '
                             'device that requires CHAP authentication')
    parser.add_argument('--password', metavar='PASSWD', action='store',
                        type=str,
                        help='Use PASSWD as the password when attaching a '
                             'device that requires CHAP authentication')
    parser.add_argument('--destroy-volume', metavar='OCID', action='store',
                        type=str, help='Destroy the volume with the given '
                                       'OCID.  WARNING: this is irreversible.')
    parser.add_argument('--debug', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--help', action='help',
                        help='Display this help')

    args = parser.parse_args()
    return args


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
    md = InstanceMetadata().filter('instance')
    if 'instance' in md and 'id' in md['instance']:
        return md['instance']['id']
    else:
        # TODO : What the purpose of this ?
        #        How user supposed to handle this ?
        return '<instance OCID>'


# TODO : how defval can be optional ?
#        what the purpose of default value ?
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


def ocid_refresh(wait=False, debug=False):
    """
    Refresh OCID cached information; it runs
    /usr/libexec/ocid command line with --refresh option

    Parameters
    ----------
    wait: bool
       Flag, wait until completion if set.
    debug: bool
       Flag, write the result to standard error if set.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    if debug:
        debug_opt = ['--debug']
        wait = True
    else:
        debug_opt = []

    # TODO : what happen with (wait=True and debug=False) ?

    try:
        if wait:
            output = subprocess.check_output(['/usr/libexec/ocid',
                                              '--no-daemon',
                                              '--refresh',
                                              'iscsi'] + debug_opt,
                                             stderr=subprocess.STDOUT)
        else:
            output = subprocess.check_output(['/usr/libexec/ocid',
                                              '--refresh',
                                              'iscsi'] + debug_opt,
                                             stderr=subprocess.STDOUT)
        _logger.debug(str(output))
        return True
    except subprocess.CalledProcessError:
        return False


def display_current_devices(oci_sess, session, disks):
    """
    Display the attched iSCSI devices.

    Parameters
    ----------
    oci_sess: OCISession
        An OCI session
    session: dict
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
    if oci_sess is not None and oci_sdk_error is None:
        oci_vols = oci_sess.this_instance().all_volumes()

    if session:
        for iqn in list(session.keys()):
            oci_vol = None
            for vol in oci_vols:
                if vol.get_iqn() == iqn:
                    oci_vol = vol
                    break

            print()
            print("Target %s" % iqn)
            if oci_vol is not None:
                print("         Volume name:    %s" \
                      % oci_vol.get_display_name())
                print("         Volume OCID:    %s" \
                      % oci_vol.get_ocid())

            print("   Persistent portal:    %s:%s" % \
                  (session[iqn]['persistent_portal_ip'],
                   session[iqn]['persistent_portal_port']))
            print("      Current portal:    %s:%s" % \
                  (session[iqn]['current_portal_ip'],
                   session[iqn]['current_portal_port']))
            if 'session_state' in session[iqn]:
                print("               State:    %s" % \
                      session[iqn]['session_state'])
            if 'device' not in session[iqn]:
                print()
                continue
            device = session[iqn]['device']
            print("     Attached device:    %s" % device)
            if device in disks:
                print("                Size:    %s" % disks[device]['size'])
                if 'partitions' not in disks[device]:
                    print("    File system type:    %s" % \
                          nvl(disks[device]['fstype']))
                    print("          Mountpoint:    %s" % \
                          nvl(disks[device]['mountpoint'], "Not mounted"))
                else:
                    print("          Partitions:    " \
                          "Device  %6s  %10s   Mountpoint" % \
                          ("Size", "Filesystem"))
                    partitions = disks[device]['partitions']
                    plist = list(partitions.keys())
                    plist.sort()
                    for part in plist:
                        print("                         %s  %8s  %10s   %s" % \
                              (part, partitions[part]['size'],
                               nvl(partitions[part]['fstype'], "Unknown fs"),
                               nvl(partitions[part]['mountpoint'],
                                   "Not mounted")))
    else:
        print("Error: Local iSCSI info not available. ")
        print("List info from Cloud instead(No boot volume).")
        print("")
        for oci_vol in oci_vols:
            print("Target %s" % oci_vol.get_iqn())
            print("         Volume name:    %s" % oci_vol.get_display_name())
            print("         Volume OCID:    %s" % oci_vol.get_ocid())
            print("         Volume size:    %s" % \
                  oci_vol.get_size(format=oci_vol.HUMAN))

    print()


# TODO : developer of this method should add documentation
def display_attach_failed_device(iqn, targets, attach_failed):
    """
    Display the devices which could not attached automatically.

    Parameters
    ----------
    iqn: str
        The iSCSI qualified name.
    targets: dict
        The targets.
    attach_failed: dict
        The devices for which attachment failed.

    Returns
    -------
        No return value.
    """
    print()
    print("Target %s" % iqn)
    for ipaddr in list(targets.keys()):
        if iqn in targets[ipaddr]:
            print("              Portal:    %s:%s" % (ipaddr, 3260))
            print("               State:    %s" % \
                  iscsiadm.error_message_from_code(attach_failed[iqn]))


# TODO : developer of this method should add documentation
def display_detached_device(iqn, targets):
    """
    Display the detached devices.

    Parameters
    ----------
    iqn: str
        The iSCSI qualified name.
    targets: dict
        The targets.

    Returns
    -------
        No return value.
    """
    print()
    print("Target %s" % iqn)
    if targets:
        for ipaddr in list(targets.keys()):
            if iqn in targets[ipaddr]:
                print("              Portal:    %s:%s" % (ipaddr, 3260))
    else:
        print("              Portal:    unknown (need ocid to determine)")

    print("               State:    Detached")


def do_attach(oci_sess, iqn, targets, user=None, passwd=None):
    """
    Attach an iSCSI device.

    Parameters
    ----------
    oci_sess: OCISession
        The OCISession.
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
        int
            The iscsiadm attach return value on successful start, 99 otherwise.
    """
    if oci_sess is not None:
        oci_vols = oci_sess.find_volumes(iqn=iqn)
        if len(oci_vols) == 1:
            user = oci_vols[0].get_user()
            passwd = oci_vols[0].get_password()
    portal_ip = None
    if targets is None:
        print("ocid must be running to determine the portal IP address " \
              "for this device")
        return 99
    for ipaddr in list(targets.keys()):
        if iqn in targets[ipaddr]:
            portal_ip = ipaddr
    if portal_ip is None:
        # this shouldn't really happen, but just in case
        print("Can't find portal IP address")
        return 99
    retval = iscsiadm.attach(portal_ip, 3260, iqn,
                             user, passwd,
                             auto_startup=True)
    print("Result: %s" \
          % iscsiadm.error_message_from_code(retval))
    return retval


def do_destroy_volume(sess, ocid, interactive=False):
    """
    Destroy the volume with the given ocid.
    The volume must be detached.  This is just an added measure to
    prevent accidentally destroying the wrong volume.

    Add root privilege requirement to be the same as create's requirement.

    Parameters
    ----------
    sess: OCISession
        The iscsiadm session.
    ocid: str
        The OCID.
    interactive: bool
        Flag forces confirmation if set.

    Returns
    -------
    int
        0 on success, 1 on failure
        possible failure:
                * user's not root
                * OCI SDK is not installed
                * Volume with given OCID cannot be found
                * Volume with given OCID is currently attached
                * volume destruction failed
    """

    if not USE_OCI_SDK or sess is None:
        _logger.error("Need OCI Service to destroy volume.\n"
                         "Make sure to install and configure "
                         "OCI Python SDK (python-oci-sdk)\n")
        if oci_sdk_error is not None:
            _logger.error("OCI SDK error: %s\n" % oci_sdk_error)
        return 1

    vol = None
    try:
        vol = sess.get_volume(ocid)
    except Exception:
        _logger.debug("Failed to retrieve Volume details", exc_info=True)
        _logger.error("Failed to retrieve Volume details: %s" % vol)
        return 1

    if vol is None:
        _logger.error("Volume not found: %s\n" % ocid)
        return 1

    if vol.is_attached():
        _logger.error("Volume is attached: %s\n" % ocid)
        _logger.error("You must detach this volume first.\n")
        return 1

    if interactive:
        cont = ask_yes_no("WARNING: the volume will be destroyed.  This "
                          "is irreversible.  Continue?")
        if not cont:
            return 1

    try:
        vol.destroy()
    except Exception as e:
        _logger.debug("Failed to destroy volume", exc_info=True)
        _logger.error("Failed to destroy volume: %s" % e)
        return 1

    return 0


def api_display_available_devices(sess, args):
    """
    Display the available devices.

    Parameters
    ----------
    sess: OCISession
        The OCISession instance.
    args: namespace
        The commandline argparse namespace.

    Returns
    -------
        No return value.
    """
    if sess is None or not USE_OCI_SDK:
        _logger.error("Need OCI services to display available devices.\n")
        if oci_sdk_error is not None:
            _logger.error("OCI SDK error: %s\n" % oci_sdk_error)
        return

    vols = []
    if args.compartments:
        for cspec in args.compartments:
            if cspec == 'all':
                vols = sess.all_volumes()
                break
            if cspec.startswith('ocid1.compartment.oc1..'):
                # compartment specified with its ocid
                comp = sess.get_compartment(ocid=cspec)
                if comp is None:
                    _logger.error("OCI SDK Error:Compartment "
                                     "not found: %s\n" % cspec)
                else:
                    cvols = comp.all_volumes()
                    vols += cvols
            else:
                # compartment specified with display name regexp
                comps = sess.find_compartments(display_name=cspec)
                if len(comps) == 0:
                    _logger.error("OCI SDK Error:No compartments "
                                     "matching '%s' found\n" % cspec)
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
            _logger.error("OCI SDK Error:Compartment for "
                             "this instance not found\n")

    if len(vols) == 0:
        print("No additional storage volumes found.")
        return

    print("Other available storage volumes:")
    print()

    for vol in vols:
        if vol.is_attached() and not args.all:
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
        print("   size:        %s" % \
              vol.get_size(format_str=OCI_VOLUME_SIZE_FMT.HUMAN.name))
        print()


def do_attach_ocid(sess, ocid):
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
        bool
            True on success, False otherwise.
    """
    global _user_euid

    if not USE_OCI_SDK or sess is None:
        _logger.error("Need OCI Service to create volume.\n"
                         "Make sure to install and configure "
                         "OCI Python SDK (python-oci-sdk)\n")
        if oci_sdk_error is not None:
            _logger.error("OCI SDK error: %s\n" % oci_sdk_error)
        return False

    vol = sess.get_volume(ocid)
    if vol is None:
        _logger.error("Volume %s not found.\n" % ocid)
        return False

    if vol.is_attached():
        if vol.get_instance().get_ocid() == sess.this_instance().get_ocid():
            # attached to this instance already
            print("Volume %s already attached to this instance." % \
                  ocid)
            return True
        else:
            _logger.error("Volume %s\nis currently attached to "
                             "instance %s (%s)\n"
                             % (ocid, vol.get_instance().get_display_name(),
                                vol.get_instance().get_public_ip()))
            return False
    print("Attaching OCI Volume to this instance.")
    vol = vol.attach_to(instance_id=sess.this_instance().get_ocid(), wait=True)

    if _user_euid != 0:
        if vol.get_user() is not None:
            # requires CHAP auth user/password
            _logger.error("Run oci-iscsi-config with root privileges "
                             "to attach this device.\n")
            return False
        else:
            # ocid will attach it automatically
            return True

    # attach using iscsiadm commands
    print("Attaching iSCSI device")
    retval = iscsiadm.attach(ipaddr=vol.get_portal_ip(),
                             port=vol.get_portal_port(),
                             iqn=vol.get_iqn(),
                             username=vol.get_user(),
                             password=vol.get_password(),
                             auto_startup=True)
    print("Result: %s" \
          % iscsiadm.error_message_from_code(retval))
    if retval == 0:
        return True

    return False


def api_detach(sess, iqn):
    """
    Detach the given volume from the instance using OCI API calls.

    Parameters
    ----------
    sess: OCISession
        The OCISEssion instance..
    iqn: str
        The iSCSI qualified name.

    Returns
    -------
       bool
            True on success, False otherwise.
    """
    if sess is None:
        _logger.error("Need OCI Service to detach volume.\n"
                         "Make sure to install and configure "
                         "OCI Python SDK (python-oci-sdk)\n")
        return False

    for v in sess.this_instance().all_volumes():
        if v.get_iqn() == iqn:
            try:
                print("Detaching volume")
                v.detach()
                return True
            except OCISDKError as e:
                _logger.debug("Failed to disconnect volume", exc_info=True)
                _logger.error("Failed to disconnect volume %s from this instance: %s" % (iqn, e))
                return False
    _logger.error("Volume not found...\n")
    return False


def do_umount(mountpoint, warn=True):
    """
    Unmount the given mountpoint.

    Parameters
    ----------
    mountpoint: str
        The mountpoint.
    warn: bool
        # --GT-- not used yet, left in to avoid breakinf function call.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    try:
        print("Unmounting %s" % mountpoint)
        subprocess.check_output(['/usr/bin/umount',
                                 mountpoint], stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        _logger.error("Failed to unmount %s: %s\n" % (mountpoint, e.output))
        return False


def unmount_device(session, iqn, disks):
    """
    Unmount the partitions of the device with the specified iqn, if they are
    mounted.

    Parameters
    ----------
    session: OCISession
        The OCISession session instance.
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
    if iqn not in session or 'device' not in session[iqn]:
        # the device is detaching already
        return True
    device = session[iqn]['device']
    if device not in disks:
        return True
    if 'partitions' not in disks[device]:
        if disks[device]['mountpoint'] != '':
            # volume has not partitions and is currently mounted
            if not do_umount(disks[device]['mountpoint'], warn=retval):
                retval = False
    else:
        partitions = disks[device]['partitions']
        for part in list(partitions.keys()):
            if partitions[part]['mountpoint'] != '':
                # the partition is mounted
                if not do_umount(partitions[part]['mountpoint'], warn=retval):
                    retval = False
    return retval


def do_create_volume(sess, size, display_name, use_chap=False):
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
    use_chap: bool
        Flag, use chap secret when set.
        # --GT-- not used yet, left in to avoid breaking function call.

    Returns
    -------
        bool
            True on success, False otherwise.
    """
    if not USE_OCI_SDK or sess is None:
        _logger.error("Need OCI Service to create volume.\n"
                         "Make sure to install and configure "
                         "OCI Python SDK (python-oci-sdk)\n")
        if oci_sdk_error is not None:
            _logger.error("OCI SDK error: %s\n" % oci_sdk_error)
        return False

    if size < 50:
        _logger.error("Volume size must be at least 50GBs\n")
        return False

    # FIXME: use_chap, but not used yet
    # vol = None
    # inst = None
    try:
        print("Creating a new %d GB volume" % size)
        inst = sess.this_instance()
        if inst is None:
            _logger.error("OCI SDK error: couldn't get instance info.")
            return False

        vol = inst.create_volume(size=size,
                                 display_name=display_name)
    except Exception as e:
        _logger.debug("Failed to create volume", exc_info=True)
        _logger.error("Failed to create volume: %s" % e)
        return False

    print("Volume %s created" % vol.get_display_name())

    # attach using iscsiadm commands
    state = vol.get_attachment_state()
    if OCI_ATTACHMENT_STATE[state] in (
            OCI_ATTACHMENT_STATE.ATTACHED, OCI_ATTACHMENT_STATE.ATTACHING):
        print("Volume %s is %s" % (vol.get_display_name(), state))
        return True

    print("Attaching iSCSI device")
    retval = iscsiadm.attach(ipaddr=vol.get_portal_ip(),
                             port=vol.get_portal_port(),
                             iqn=vol.get_iqn(),
                             username=vol.get_user(),
                             password=vol.get_password(),
                             auto_startup=True)
    print("Result: %s" % iscsiadm.error_message_from_code(retval))
    if retval == 0:
        return True

    try:
        vol.destroy()
    except Exception as e:
        _logger.debug("Failed to destroy volume", exc_info=True)
        _logger.error("Failed to destroy volume: %s" % e)

    return False


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
    global USE_OCI_SDK
    global oci_sdk_error
    global _user_euid
    oci_sdk_error = None
    oci_sess = None

    args = parse_args()

    _user_euid = os.geteuid()

    if oci_utils.oci_api.HAVE_OCI_SDK:
        try:
            oci_sess = oci_utils.oci_api.OCISession()
            USE_OCI_SDK = True
        except Exception as e:
            oci_sdk_error = str(e)
            USE_OCI_SDK = False
            if args.debug:
                raise

    if not os.path.isfile("/var/run/ocid.pid"):
        _logger.error("Warning:\n"
                      "For full functionality of this utility the ocid "
                      "service must be running\n"
                      "The administrator can start it using this command:\n"
                      "    sudo systemctl start ocid.service\n")

    max_volumes = OCIUtilsConfiguration.getint('iscsi', 'max_volumes')
    if max_volumes > oci_utils._MAX_VOLUMES_LIMIT:
        _logger.error(
            "Your configured max_volumes(%s) is over the limit(%s)\n"
            % (max_volumes, oci_utils._MAX_VOLUMES_LIMIT))
        max_volumes = oci_utils._MAX_VOLUMES_LIMIT

    ocid_cache = load_cache(iscsiadm.ISCSIADM_CACHE,
                            max_age=timedelta(minutes=2))[1]
    if ocid_cache is None and _user_euid == 0:
        # run ocid once, to update the cache
        ocid_refresh(wait=True, debug=args.debug)
        # now try to load again
        ocid_cache = load_cache(iscsiadm.ISCSIADM_CACHE,
                                max_age=timedelta(minutes=2))[1]
    if ocid_cache is None:
        targets, attach_failed = None, None
    else:
        targets, attach_failed = ocid_cache
    disks = lsblk.list()
    session = iscsiadm.session()
    detached = load_cache(__ignore_file)[1]
    if detached is None:
        detached = []

    if args.create_volume:
        if _user_euid != 0:
            _logger.error("You must run this program with root privileges "
                             "to create and attach iSCSI devices.\n")
            return 1
        if len(disks) > max_volumes:
            _logger.error(
                "This instance reached the max_volumes(%s)\n" % max_volumes)
            return 1

        # FIXME: use_chap
        retval = do_create_volume(oci_sess, size=args.create_volume,
                                  display_name=args.volume_name)
    elif args.destroy_volume:
        if _user_euid != 0:
            _logger.error("You must run this program with root privileges "
                             "to destroy a iSCSI volume.\n")
            return 1
        retval = do_destroy_volume(oci_sess, args.destroy_volume,
                                   args.interactive)
        if retval == 0:
            print("Volume %s is destroyed." % args.destroy_volume)
        return retval

    elif args.detach_iqns:
        if _user_euid != 0:
            _logger.error("You must run this program with root privileges "
                             "to detach iSCSI devices.\n")
            return 1

        write_ignore_file = False
        retval = 0
        do_refresh = False
        for iqn in args.detach_iqns:
            if not iqn.startswith("iqn."):
                _logger.error("Invalid IQN %s\n" % iqn)
                retval = 1
                continue
            if iqn in detached:
                _logger.error("Target %s is already detached\n" % iqn)
                retval = 1
                continue
            if iqn not in session:
                _logger.error("Target %s not found\n" % iqn)
                retval = 1
                continue
            if 'boot:uefi' in iqn:
                _logger.error("IQN %s is the boot device, cannot "
                                 "detach.\n" % iqn)
                retval = 1
                continue
            if not unmount_device(session, iqn, disks):
                if args.interactive:
                    cont = ask_yes_no("Failed to unmount volume.  "
                                      "Continue detaching anyway?")
                    if not cont:
                        return 1
                else:
                    return 1

            api_detached = False

            if USE_OCI_SDK:
                api_detached = api_detach(oci_sess, iqn)

            if not iscsiadm.detach(session[iqn]['persistent_portal_ip'],
                                   session[iqn]['persistent_portal_port'],
                                   iqn):
                _logger.error("Failed to detach target %s\n" % iqn)
                retval = 1
            else:
                if not api_detached:
                    detached.append(iqn)
                    write_ignore_file = True
                    do_refresh = True
        if write_ignore_file:
            _logger.error("Updating ignore file: %s\n" % detached)
            write_cache(cache_content=detached,
                        cache_fname=__ignore_file)
        if do_refresh:
            ocid_refresh(debug=args.debug)
        return retval

    elif args.attach_iqns:
        if _user_euid != 0:
            _logger.error("You must run this program with root "
                             "privileges to attach iSCSI devices.\n")
            return 1

        if len(disks) > max_volumes:
            _logger.error(
                "This instance reached the max_volumes(%s)\n" % max_volumes)
            return 1

        retval = 0
        write_ignore_file = False
        do_refresh = False

        for iqn in args.attach_iqns:
            if iqn.startswith('ocid1.volume.oc'):
                # it's an OCID
                if not do_attach_ocid(oci_sess, iqn):
                    retval = 1
                continue
            elif not iqn.startswith("iqn."):
                _logger.error("Invalid IQN %s \n" % iqn)
                retval = 1
                continue

            if iqn in session:
                print("Target %s is already attached." % iqn)
                continue
            if iqn not in detached and iqn not in attach_failed:
                _logger.error("Target %s not found\n" % iqn)
                retval = 1
                continue
            user = args.username
            passwd = args.password
            if user is None or passwd is None:
                (user, passwd) = get_chap_secret(iqn)
            if do_attach(oci_sess, iqn, targets,
                         user=user, passwd=passwd) != 0:
                _logger.error("Failed to attach target %s\n" % iqn)
                retval = 1
            else:
                do_refresh = True
                if iqn in detached:
                    detached.remove(iqn)
                if args.username is not None:
                    save_chap_secret(iqn, args.username, args.password)
                write_ignore_file = True
        if write_ignore_file:
            write_cache(cache_content=detached,
                        cache_fname=__ignore_file)
        if do_refresh:
            ocid_refresh(debug=args.debug)

        return retval

    if args.show:
        display_current_devices(oci_sess, session, disks)
        api_display_available_devices(oci_sess, args)

    if args.create_volume or args.destroy_volume:
        return retval

    if detached:
        print()
        print("Detached devices:")

        do_refresh = False
        write_ignore_file = False
        for iqn in detached:
            display_detached_device(iqn, targets)
            if args.interactive:
                if _user_euid != 0:
                    print("You must run this program with root privileges " \
                          "to attach iSCSI devices.\n")
                    ans = False
                else:
                    ans = ask_yes_no("Would you like to attach this device?")
                if ans:
                    retval = do_attach(oci_sess, iqn, targets)
                    do_refresh = True
                    if retval == 24:
                        # authentication error
                        attach_failed[iqn] = 24
                    if iqn in detached:
                        detached.remove(iqn)
                        write_ignore_file = True
        if write_ignore_file:
            write_cache(cache_content=detached,
                        cache_fname=__ignore_file)
        if do_refresh:
            ocid_refresh(debug=args.debug)

    if attach_failed:
        print()
        print("Devices that could not be attached automatically:")

        auth_errors = 0
        for iqn in list(attach_failed.keys()):
            if attach_failed[iqn] == 24:
                auth_errors += 1

        for iqn in list(attach_failed.keys()):
            display_attach_failed_device(iqn, targets, attach_failed)
            do_refresh = False
            if args.interactive:
                if attach_failed[iqn] != 24:
                    # not authentication error
                    ans = True
                    while ans:
                        if _user_euid != 0:
                            print("You must run this program with root  " \
                                  "privileges to attach iSCSI devices.\n")
                            ans = False
                        else:
                            ans = ask_yes_no("Would you like to retry "
                                             "attaching this device?")
                        if ans:
                            retval = do_attach(oci_sess, iqn, targets)
                            if retval == 0:
                                ans = False
                                do_refresh = True
                        else:
                            ans = False
                else:
                    # authentication error
                    if _user_euid != 0:
                        print("You must run this program with root " \
                              "privileges to configure iSCSI devices.\n")
                        ans = False
                    else:
                        ans = ask_yes_no("Would you like to configure this "
                                         "device?")
                    if ans:
                        retval = 1
                        if USE_OCI_SDK:
                            # try and get the user and password from the API
                            retval = do_attach(oci_sess, iqn, targets,
                                               None, None)
                        else:
                            (user, passwd) = get_chap_secret(iqn)
                            if user is not None:
                                retval = do_attach(oci_sess, iqn, targets,
                                                   user, passwd)
                        if retval == 0:
                            print("Device configured automatically.")
                            do_refresh = True
                        else:
                            myocid = get_instance_ocid()
                            while ans:
                                print("To find the CHAP username and " \
                                      "password for this device, go to")
                                print("https://console.us-phoenix-1." \
                                      "oraclecloud.com/#/a/compute/instances" \
                                      "/%s/disks?jt=listing" % \
                                      myocid)
                                print("Select the Block Volume, then click " \
                                      "the \"iSCSI Commands & Information\" " \
                                      "button.")
                                print("CHAP username:")
                                user = input()
                                print("CHAP password:")
                                passwd = input()
                                print("Attaching iSCSI device...")
                                retval = do_attach(oci_sess, iqn, targets,
                                                   user, passwd)
                                if retval != 0:
                                    ans = ask_yes_no("Would you like to try "
                                                     "again?")
                                else:
                                    ans = False
                                    do_refresh = True
        if do_refresh:
            ocid_refresh(debug=args.debug)
        if not args.interactive and auth_errors:
            print()
            print("Use the -i or --interactive mode to configure " \
                  "devices that require authentication information")

    if not args.show and not attach_failed and not detached:
        print("All known devices are attached.")
        print("Use the -s or --show option for details.")

    return 0


USE_OCI_SDK = False

if __name__ == "__main__":
    sys.exit(main())
