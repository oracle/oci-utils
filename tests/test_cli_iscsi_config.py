# Copyright (c) 2018, 2019 Oracle and/or its affiliates. All rights reserved.
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

def _get_volume_data(volume_data):
    """
    Formats the data list retrieved from show as a dictionary.

    Parameters
    ----------
    volume_data: list

    Returns
    -------
        dict: dictionary
              { display_name : {'ocid' : OCID, 'iqn': iqn} }
    """
    singlespace = re.compile("\s*,\s*|\s+$")
    volume_data_dict = dict()
    ind = 0
    for y in volume_data:
        if y.startswith('Currently attached iSCSI'):
             break
        ind += 1
    while ind < len(volume_data) - 1:
        ind += 1
        v = volume_data[ind]
        if v.startswith('Target iqn'):
            iqn = singlespace.sub(' ', v.split(' ')[1]).strip()
            cnt = 0
            ind += 1
            for y in volume_data[ind:]:
                if 'Volume name' in y:
                    display_name = singlespace.sub(' ', y.split(': ', 1)[1]).strip()
                    cnt += 1
                elif 'Volume OCID' in y:
                    ocid = singlespace.sub(' ', y.split(': ', 1)[1]).strip()
                    cnt += 1
                if cnt == 2:
                    volume_data_dict[display_name] = {'target': iqn, 'ocid': ocid}
                    break
                else:
                    ind += 1
        if v.startswith('Volume '):
            display_name = v.split(' ')[1]
            ind += 1
            for y in volume_data[ind:]:
                if 'OCID' in y:
                    ocid = singlespace.sub(' ', y.split(': ', 1)[1]).strip()
                    volume_data_dict[display_name] = {'target': None, 'ocid': ocid}
                    break
                ind += 1
    return volume_data_dict


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
        self.iscsi_config_path = self.properties.get_property('oci-iscsi-config-path')
        if not os.path.exists(self.iscsi_config_path):
            raise unittest.SkipTest("%s not present" % self.iscsi_config_path)
        self.volume_name = uuid.uuid4().hex
        try:
            self.waittime = int(self.properties.get_property('waittime'))
        except Exception as e:
            self.waittime = 10
        try:
            self.volume_size = self.properties.get_property('volume-size')
        except Exception as e:
            self.volume_size = '60'
        try:
            self.compartment_name = self.properties.get_property('compartment-name')
        except Exception as e:
            self.compartment_name = 'ImageDev'

    @staticmethod
    def _get_ocid(create_data, display_name):
        """
        Find the ocid of a volume.

        Parameters
        ----------
        create_data: list
            Block volume data.
        display_name: str
            Display name of the volume.

        Returns
        -------
            str: the ocid
        """
        vol_dict = _get_volume_data(create_data)[display_name]
        return vol_dict['ocid']

    @staticmethod
    def _get_iqn(create_data, display_name):
        """
        Find the ocid of a volume.

        Parameters
        ----------
        create_data: list
            Block volume data.
        display_name: str
            Display name of the volume.

        Returns
        -------
            str: the ocid
        """
        vol_dict = _get_volume_data(create_data)[display_name]
        return vol_dict['target']

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.iscsi_config_path, '--help'])
            _ = subprocess.check_output([self.iscsi_config_path, 'sync', '--help'])
            _ = subprocess.check_output([self.iscsi_config_path, 'usage', '--help'])
            _ = subprocess.check_output([self.iscsi_config_path, 'show', '--help'])
            _ = subprocess.check_output([self.iscsi_config_path, 'create', '--help'])
            _ = subprocess.check_output([self.iscsi_config_path, 'attach', '--help'])
            _ = subprocess.check_output([self.iscsi_config_path, 'detach', '--help'])
            _ = subprocess.check_output([self.iscsi_config_path, 'destroy', '--help'])
        except Exception as e:
            self.fail('oci-iscsi-config --help has failed: %s' % str(e))

    def test_show_no_check(self):
        """
        Test basic run of --show command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.iscsi_config_path, '--show'])
            _ = subprocess.check_output([self.iscsi_config_path, 'show'])
        except Exception as e:
            self.fail('oci-iscsi-config show has failed: %s' % str(e))

    def test_show_all_no_check(self):
        """
        Test basic run of --show command. We do not check out.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.iscsi_config_path, '--show', '--all'])
            _ = subprocess.check_output([self.iscsi_config_path, 'show', '--all'])
        except Exception as e:
            self.fail('oci-iscsi-config show --all has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_create_destroy(self):
        """
        Test block volume creation and destruction

        Returns
        -------
            No return value.
        """
        try:
            create_volume_data = subprocess.check_output([self.iscsi_config_path,
                                                          'create',
                                                          '--size', self.volume_size,
                                                          '--volume-name', self.volume_name,
                                                          '--show']).decode('utf-8').splitlines()
            # print('\nvolume created: %s' % create_volume_data)
            time.sleep(self.waittime)
            new_ocid = self._get_ocid(create_volume_data, self.volume_name)
            destroy_volume_data = subprocess.check_output([self.iscsi_config_path,
                                                           'destroy',
                                                           '--ocids', new_ocid,
                                                           '--yes',
                                                           '--show']).decode('utf-8').splitlines()
            # print('\nvolume %s destroyed: %s' % (self.volume_name, destroy_volume_data))
        except Exception as e:
            self.fail('oci-iscsi-config create/destroy has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_attach_detach(self):
        """
        Test block device attach and detach.

        Returns
        -------
            No return value
        """
        try:
            create_volume_data = subprocess.check_output([self.iscsi_config_path,
                                                          'create',
                                                          '--size', self.volume_size,
                                                          '--volume-name', self.volume_name,
                                                          '--show']).decode('utf-8').splitlines()
            # print('\nvolume created: %s' % create_volume_data)
            time.sleep(self.waittime)
            new_ocid = self._get_ocid(create_volume_data, self.volume_name)
            attach_volume_data = subprocess.check_output([self.iscsi_config_path,
                                                          'attach',
                                                          '--iqns', new_ocid,
                                                          '--show']).decode('utf-8').splitlines()
            attach_volume_data_show = subprocess.check_output([self.iscsi_config_path,
                                                               'show']).decode('utf-8').splitlines()
            # print('\nvolume attached: %s' % attach_volume_data_show)
            time.sleep(self.waittime)
            new_iqn = self._get_iqn(attach_volume_data_show, self.volume_name)
            detach_volume_data = subprocess.check_output([self.iscsi_config_path,
                                                          'detach',
                                                          '--iqns', new_iqn]).decode('utf-8').splitlines()
            # print('\nvolume detached: %s' % detach_volume_data)
            time.sleep(self.waittime)
            destroy_volume_data = subprocess.check_output([self.iscsi_config_path,
                                                           'destroy',
                                                           '--ocids', new_ocid,
                                                           '--yes',
                                                           '--show']).decode('utf-8').splitlines()
            # print('\nvolume %s destroyed: %s' % (self.volume_name, destroy_volume_data))
        except Exception as e:
            self.fail('oci-iscsi-config attach/detach has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_sync(self):
        """
        Test volume attach.

        Returns
        -------
            No return value.
        """
        try:
            sync_data = subprocess.check_output([self.iscsi_config_path,
                                                 'sync',
                                                 '--apply',
                                                 '--yes']).decode('utf-8').splitlines()
            # print('\nvolumes synced.')
        except Exception as e:
            self.fail('oci-iscsi-config sync has failed: %s' % str(e))

