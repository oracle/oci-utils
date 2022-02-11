# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import re
import subprocess
import time
import unittest
import uuid
from tools.oci_test_case import OciTestCase
from tools.decorators import (skipUnlessOCI, skipUnlessRoot)
from oci_utils import oci_api

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

def _show_res(head, msg):
    """
    Prints a list line by line.

    Parameters
    ----------
    head: str
        Title
    msg: list
        The data
    Returns
    -------
        No return value.
    """
    print('\n%s' % head)
    print('-'*len(head))
    print('\n'.join(msg))
    print('-'*len(head))


class TestCliOciIscsiConfig(OciTestCase):
    """ oci-iscsi-config tests.
    """

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.

        Raises
        ------
        unittest.SkipTest
            If the ISCSI_CONFIG file does not exist.
        """
        super().setUp()
        self.iscsi_config_path = self.properties.get_property('oci-iscsi-config')
        self.iscsiadm_path = '/sbin/iscsiadm'
        if not os.path.exists(self.iscsi_config_path):
            raise unittest.SkipTest("%s not present" % self.iscsi_config_path)
        try:
            self.vol_name_prefix = self.properties.get_property('volume-name-prefix')
        except Exception:
            self.vol_name_prefix = 'auto-'
        self.volume_name = self.vol_name_prefix + uuid.uuid4().hex
        try:
            self.waittime = int(self.properties.get_property('waittime'))
        except Exception:
            self.waittime = 20
        try:
            self.volume_size = self.properties.get_property('volume-size')
        except Exception:
            self.volume_size = '53'
        try:
            self.compartment_name = self.properties.get_property('compartment-name')
        except Exception as e:
            self.compartment_name = 'ImageDev'
        self._volumes_created = list()
        self.oci_session = oci_api.OCISession()

    def _get_iscsi_show(self, all_vol=True):
        """
        Get the iscsi vol data.


        Parameters
        ----------
        all_vol: bool
            Get all volumes if True, only attached if False.
        Returns
        -------
            dict: the volname with ocid and iqn.
        """
        get_volumes = [self.iscsi_config_path, 'show', '--detail', '--no-truncate', '--output-mode', 'text']
        if all_vol:
            get_volumes.append('--all')
        return subprocess.check_output(get_volumes).decode('utf-8').splitlines()

    def _get_ocid_from_volume_name(self, volume_name):
        """
        Try to get the value for the ocid for a volume identified by an volume_name, if any.

        Parameters
        ----------
            volume_name: str
                The display_name.

        Returns
        -------
            str: the iqn.
        """
        this_compartment = self.oci_session.this_compartment()
        this_availability_domain = self.oci_session.this_availability_domain()
        all_volumes = this_compartment.all_volumes(this_availability_domain)
        for vol in all_volumes:
            try:
                disp_name = vol.get_display_name()
                if disp_name == volume_name:
                    return vol.get_ocid()
            except Exception as e:
                continue
        return None

    def _get_iqn_from_volume_name(self, volume_name):
        """
        Try to get the value for the ocid for a volume identified by an volume_name, if any.

        Parameters
        ----------
            volume_name: str
                The display_name.

        Returns
        -------
            str: the iqn.
        """
        this_compartment = self.oci_session.this_compartment()
        this_availability_domain = self.oci_session.this_availability_domain()
        all_volumes = this_compartment.all_volumes(this_availability_domain)
        for vol in all_volumes:
            try:
                disp_name = vol.get_display_name()
                if disp_name == volume_name:
                    return vol.get_iqn()
            except Exception as e:
                continue
        return None

    def _get_volume_data_from_name(self, volume_name):
       """
       Try to get the value for the ocid for a volume identified by an volume_name, if any.

       Parameters
       ---------
           volume_name: str
               The display_name.

       Returns
       -------
           str: the iqn.
       """
       this_compartment = self.oci_session.this_compartment()
       this_availability_domain = self.oci_session.this_availability_domain()
       all_volumes = this_compartment.all_volumes(this_availability_domain)
       for vol in all_volumes:
           try:
               disp_name = vol.get_display_name()
               if disp_name == volume_name:
                   try:
                       this_ocid = vol.get_ocid()
                   except Exception as e:
                       this_ocid = None
                   try:
                       this_iqn = vol.get_iqn()
                   except Exception as e:
                       this_iqn = None
                   try:
                       this_ip = vol.get_portal_ip()
                   except Exception as e:
                       this_ip = None
                   try:
                       this_port = vol.get_portal_port()
                   except Exception as e:
                       this_port = None
                   return this_ocid, this_iqn, this_ip, this_port
           except Exception as e:
               continue
       return None


    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_createattach_detach_attach_detach_destroy(self):
        """
        Test block volume creation attach and destruction.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create
            volume_name_a = self.vol_name_prefix + uuid.uuid4().hex
            cmd_c = [self.iscsi_config_path, 'create', '--size', self.volume_size, '--volume-name', volume_name_a, '--attach-volume']
            create_volume_data = subprocess.check_output(cmd_c).decode('utf-8').splitlines()
            _show_res('Create Volume', create_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            new_ocid = self._get_ocid_from_volume_name(volume_name_a)
            self._volumes_created.append({'display_name': volume_name_a, 'ocid': new_ocid})
            #
            # detach
            new_iqn = self._get_iqn_from_volume_name(volume_name_a)
            cmd_d = [self.iscsi_config_path, 'detach', '--iqns', new_iqn]
            detach_volume_data = subprocess.check_output(cmd_d).decode('utf-8').splitlines()
            _show_res('Detach Volume', detach_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            #
            # attach
            new_ocid = self._get_ocid_from_volume_name(volume_name_a)
            cmd_e = [self.iscsi_config_path, 'attach', '--ocids', new_ocid]
            attach_volume_data = subprocess.check_output(cmd_e).decode('utf-8').splitlines()
            _show_res('Attach Volume', attach_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            #
            # detach
            new_iqn = self._get_iqn_from_volume_name(volume_name_a)
            cmd_d = [self.iscsi_config_path, 'detach', '--iqns', new_iqn]
            detach_volume_data = subprocess.check_output(cmd_d).decode('utf-8').splitlines()
            _show_res('Detach Volume', detach_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            #
            # destroy
            # _show_res('Volume data', volume_data)
            _show_res('Volume ocid', [new_ocid])
            cmd_d = [self.iscsi_config_path, 'destroy', '--ocids', new_ocid, '--yes']
            destroy_volume_data = subprocess.check_output(cmd_d).decode('utf-8').splitlines()
            _show_res('Destroy volume', destroy_volume_data)
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('oci-iscsi-config createattach/detach/destroy has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_createattach_detach_attach_detach_destroy_comp(self):
        """
        Test block volume creation attach and destruction.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create
            volume_name_a = self.vol_name_prefix + uuid.uuid4().hex
            cmd_c = [self.iscsi_config_path, '-c', self.volume_size, '--volume-name', volume_name_a]
            create_volume_data = subprocess.check_output(cmd_c).decode('utf-8').splitlines()
            _show_res('Create Volume', create_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            new_ocid = self._get_ocid_from_volume_name(volume_name_a)
            self._volumes_created.append({'display_name': volume_name_a, 'ocid': new_ocid})
            #
            # detach
            new_iqn = self._get_iqn_from_volume_name(volume_name_a)
            cmd_d = [self.iscsi_config_path, '-d', new_iqn]
            detach_volume_data = subprocess.check_output(cmd_d).decode('utf-8').splitlines()
            _show_res('Detach Volume', detach_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            #
            # attach
            new_ocid = self._get_ocid_from_volume_name(volume_name_a)
            cmd_e = [self.iscsi_config_path, 'attach', '--ocids', new_ocid]
            attach_volume_data = subprocess.check_output(cmd_e).decode('utf-8').splitlines()
            _show_res('Attach Volume', attach_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            #
            # detach
            new_iqn = self._get_iqn_from_volume_name(volume_name_a)
            cmd_d = [self.iscsi_config_path, '-d', new_iqn]
            detach_volume_data = subprocess.check_output(cmd_d).decode('utf-8').splitlines()
            _show_res('Detach Volume', detach_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            #
            # destroy
            # _show_res('Volume data', volume_data)
            _show_res('Volume ocid', [new_ocid])
            cmd_d = [self.iscsi_config_path, 'destroy', '--ocids', new_ocid, '--yes']
            destroy_volume_data = subprocess.check_output(cmd_d).decode('utf-8').splitlines()
            _show_res('Destroy volume', destroy_volume_data)
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('oci-iscsi-config createattach/detach/destroy has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciIscsiConfig)
    unittest.TextTestRunner().run(suite)
