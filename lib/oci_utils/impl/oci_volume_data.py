#
# Copyright (c) 2022 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import argparse
import sys

from oci_utils import oci_api
from oci_utils import OCI_VOLUME_SIZE_FMT

oci_volume_tag = 'ocid1.volume.'
iqn_tag = 'iqn.'
none_str = '--'


def command_line():
    """
    parse the command line.

    Returns
    -------
        The commandline argparse namespace.
    """
    parser = argparse.ArgumentParser(prog='oci-volume-data',
                                     description='Tool to display the oci properties of an iscsi volume.')
    parser.add_argument('-k', '--key',
                        action='store',
                        required=True,
                        dest='key',
                        help='The key to identify the volume, an OCID, an IQN or a display name')
    parser.add_argument('-p', '--par',
                        action='store',
                        dest='par',
                        choices=['name',
                                 'iqn',
                                 'ocid',
                                 'portal',
                                 'chap',
                                 'attachestate',
                                 'avdomain',
                                 'compartment',
                                 'attached',
                                 'size',
                                 'state'],
                        default=None,
                        help='The parameter to show. If none is given, all are shown.')
    parser.add_argument('-v', '--value-only',
                        action='store_true',
                        dest='value_only',
                        help='Show only the value(s)')
    args = parser.parse_args()
    return args


def get_oci_api_session():
    """
    Ensure the OCI SDK is available if the option is not None.

    Returns
    -------
        OCISession
            The session or None if we cannot get one
    """
    session_cache = getattr(get_oci_api_session, "_session", None)
    if session_cache:
        return session_cache

    sess = None

    try:
        sess = oci_api.OCISession()
        # it seems that having a client is not enough, we may not be able to query anything on it
        # workaround :
        # try a dummy call to be sure that we can use this session
        if not bool(sess.this_instance()):
            print('Failure: returning None session')
            return None
        setattr(get_oci_api_session, "_session", sess)
    except Exception as e:
        print("Failed to access OCI services: %s", str(e))
    return sess


def get_vol_ocid(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the volume ocid
    """
    try:
        the_ocid = vol.get_ocid()
    except Exception as e:
        the_ocid = none_str
    return the_ocid


def get_vol_iqn(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the volume iqn.
    """
    try:
        the_iqn = vol.get_iqn()
    except Exception as e:
        the_iqn = none_str
    return the_iqn


def get_vol_display_name(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the volume display name.
    """
    try:
        the_name = vol.get_display_name()
    except Exception as e:
        the_name = none_str
    return the_name


def get_vol_portalip(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the iscsi portal ip
    """
    try:
        the_portal_ip = vol.get_portal_ip()
    except Exception as e:
        the_portal_ip = none_str
    return the_portal_ip


def get_vol_portal_port(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the iscsi portal port.
    """
    try:
        the_portal_port = vol.get_portal_port()
    except Exception as e:
        the_portal_port = none_str
    return the_portal_port


def get_vol_chap_user(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the chap user.
    """
    try:
        the_chap_user = vol.get_user()
    except Exception as e:
        the_chap_user = none_str
    return the_chap_user


def get_vol_chap_pw(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the chap password
    """
    try:
        the_chap_pw = vol.get_password()
    except Exception as e:
        the_chap_pw = none_str
    return the_chap_pw


def get_vol_attachement_state(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the attachment state
    """
    try:
        the_attachement_state = vol.get_attachement_state()
    except Exception as e:
        the_attachement_state = none_str
    return the_attachement_state


def get_vol_compartment_id(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the compartment ocid.
    """
    try:
        the_compartment_id = vol.get_compartment_id()
    except Exception as e:
        the_compartment_id = none_str
    return the_compartment_id


def get_vol_attached_to(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the instance the volume is attached to.
    """
    try:
        the_attached_to = vol.get_instance().get_display_name()
    except Exception as e:
        the_attached_to = none_str
    return the_attached_to


def get_vol_size(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the size.
    """
    try:
        the_size = vol.get_size(OCI_VOLUME_SIZE_FMT.HUMAN.name)
    except Exception as e:
        the_size = none_str
    return the_size


def get_vol_state(vol):
    """
    Return the volume state.

    Parameters
    ----------
    vol: OCIVolume

    Returns
    -------
        str: the state
    """
    try:
        the_state = vol.get_state()
    except Exception as e:
        the_state = none_str
    return the_state


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
                this_ocid = get_vol_ocid(vol)
                if this_ocid == somekey:
                    this_vol['ocid'] = this_ocid
                    this_vol['iqn'] = get_vol_iqn(vol)
                    this_vol['name'] = get_vol_display_name(vol)
                    found = True
            elif somekey.startswith(iqn_tag):
                # key is an iqn
                this_iqn = get_vol_iqn(vol)
                if this_iqn == somekey:
                    this_vol['iqn'] = this_iqn
                    this_vol['ocid'] = get_vol_ocid(vol)
                    this_vol['name'] = vol.get_display_name()
                    found = True
            else:
                try:
                    this_name = vol.get_display_name()
                except Exception as e:
                    this_name = none_str
                # key is a display name, might not be unique, first one found is returned.
                if this_name == somekey:
                    this_vol['name'] = this_name
                    this_vol['iqn'] = get_vol_iqn(vol)
                    this_vol['ocid'] = get_vol_ocid(vol)
                    found = True
            if found:
                this_vol['portal_ip'] = get_vol_portalip(vol)
                this_vol['portal_port'] = get_vol_portal_port(vol)
                this_vol['chap_user'] = get_vol_chap_user(vol)
                this_vol['chap_pw'] = get_vol_chap_pw(vol)
                this_vol['attachement_state'] = get_vol_attachement_state(vol)
                this_vol['availability_domain'] = this_availability_domain
                this_vol['compartment'] = this_compartment.get_display_name()
                this_vol['compartment_id'] = get_vol_compartment_id(vol)
                this_vol['attached_to'] = get_vol_attached_to(vol)
                this_vol['size'] = get_vol_size(vol)
                this_vol['state'] = get_vol_state(vol)
                those_vols.append(this_vol)
                found = False
        except Exception as e:
            print('Get volume data for %s failed: %s' % (somekey, str(e)))
            continue
    if len(those_vols) == 0:
        print('Volume with key %s not found.' % somekey)
        return False
    elif len(those_vols) > 1:
        print('Volume with key %s is not unique.' % somekey)
    # else:
    #     print('Volume with key %s exists and is unique.'% somekey)
    return those_vols


def print_value(par, tag, name, value, only):
    """
    Prints a value for an iscsi volume metadata key.

    Parameters
    ----------
    par: str
        The parameter for which the value is requested.
    tag: str
        The dictionary key.
    name: str
        The name of the parameter.
    value: str
        The parameter value.
    only: bool
        If True, do not display the name, only the value.

    Returns
    -------

    """
    if not bool(par) or par == tag:
        if not only:
            print('%25s: ' % name, end='')
        print('%s' % value)


def display_volume(volume, par=None, only=False):
    """
    Display the data for volume vol.

    Parameters
    ----------
    volume: dict
        The volume data.
    par: str
        The parameter for which the value is requested.
    only: bool
        Show only the value if True.
    Returns
    -------
        No return value.
    """
    print_value(par, 'name', 'display name', volume['name'], only)
    print_value(par, 'ocid', 'ocid', volume['ocid'], only)
    print_value(par, 'iqn', 'iqn', volume['iqn'], only)
    print_value(par, 'portal', 'portal ip', volume['portal_ip'], only)
    print_value(par, 'portal', 'portal port', volume['portal_port'], only)
    print_value(par, 'chap', 'chap user', volume['chap_user'], only)
    print_value(par, 'chap', 'chap password', volume['chap_pw'], only)
    print_value(par, 'avdomain', 'availability domain', volume['availability_domain'], only)
    print_value(par, 'compartment', 'compartment', volume['compartment'], only)
    print_value(par, 'compartment', 'compartment id', volume['compartment_id'], only)
    print_value(par, 'attached', 'attached to', volume['attached_to'], only)
    print_value(par, 'attachstate', 'attachment state', volume['attachement_state'], only)
    print_value(par, 'size', 'size', volume['size'], only)
    print_value(par, 'state', 'state', volume['state'], only)
    print('')


def main():
    """
    oci-volume-data displays metadata for an iscsi volume.

    Returns
    -------
        No return value.
    """
    args = command_line()
    oci_session = get_oci_api_session()
    if bool(oci_session):
        volumes = get_volume_data_from_(args.key, oci_session)
        if bool(volumes):
            for vol in volumes:
                display_volume(vol, args.par, args.value_only)
        else:
            print('No volumes found for [%s]' % args.key)
    else:
        print('Failed to create an oci sesion.')


if __name__ == "__main__":
    sys.exit(main())
