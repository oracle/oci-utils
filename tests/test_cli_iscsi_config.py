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

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

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
        if v.startswith('Target: '):
            iqn = singlespace.sub(' ', v.split(' ')[1]).strip()
            cnt = 0
            ind += 1
            for y in volume_data[ind:]:
                if 'Volume Name' in y:
                    display_name = singlespace.sub(' ', y.split(': ', 1)[1]).strip()
                    cnt += 1
                elif 'Volume OCID' in y:
                    ocid = singlespace.sub(' ', y.split(': ', 1)[1]).strip()
                    cnt += 1
                if cnt == 2:
                    volume_data_dict[display_name] = {'target': iqn, 'ocid': ocid}
                    break
                ind += 1
        if v.startswith('Name: '):
            display_name = v.split(' ')[1]
            cnt = 0
            ind += 1
            for y in volume_data[ind:]:
                if 'OCID' in y:
                    ocid = singlespace.sub(' ', y.split(': ', 1)[1]).strip()
                    cnt += 1
                elif 'IQN' in y:
                    iqn = singlespace.sub(' ', y.split(': ', 1)[1]).strip()
                    cnt += 1
                if cnt == 2:
                    if iqn == '-':
                        volume_data_dict[display_name] = {'target': None, 'ocid': ocid}
                    else:
                        volume_data_dict[display_name] = {'target': iqn, 'ocid': ocid}
                    break
                ind += 1
    return volume_data_dict


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
            self.volume_size = '57'
        try:
            self.compartment_name = self.properties.get_property('compartment-name')
        except Exception as e:
            self.compartment_name = 'ImageDev'
        self._volumes_created = list()

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
            _ = subprocess.check_output([self.iscsi_config_path, 'show', '--all', '--output-mode', 'parsable'])
            _ = subprocess.check_output([self.iscsi_config_path, 'show', '--all', '--output-mode', 'table'])
            _ = subprocess.check_output([self.iscsi_config_path, 'show', '--all', '--output-mode', 'text'])
            _ = subprocess.check_output([self.iscsi_config_path, 'show', '--all', '--output-mode', 'json'])
        except Exception as e:
            self.fail('oci-iscsi-config show --all has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_show_compartment(self):
        """
        Test show block volumes in given compartment. The output is not checked.

        Returns
        -------
            No return value.
        """
        try:
            vol_data = subprocess.check_output([self.iscsi_config_path, 'show',
                                                '--compartment', self.compartment_name]).decode('utf-8').splitlines()
            vol_data = subprocess.check_output([self.iscsi_config_path, 'show',
                                                '--compartment', self.compartment_name,
                                                '--details']).decode('utf-8').splitlines()
            vol_data = subprocess.check_output([self.iscsi_config_path, 'show',
                                                '--compartment', self.compartment_name,
                                                '--details', '--no-truncate']).decode('utf-8').splitlines()
            vol_data = subprocess.check_output([self.iscsi_config_path, 'show',
                                                '--compartment', self.compartment_name,
                                                '--details', '--no-truncate',
                                                '--output-mode', 'parsable']).decode('utf-8').splitlines()
            vol_data = subprocess.check_output([self.iscsi_config_path, 'show',
                                                '--compartment', self.compartment_name,
                                                '--details', '--no-truncate',
                                                '--output-mode', 'json']).decode('utf-8').splitlines()
            vol_data = subprocess.check_output([self.iscsi_config_path, 'show',
                                                '--compartment', self.compartment_name,
                                                '--details', '--no-truncate',
                                                '--output-mode', 'text']).decode('utf-8').splitlines()
            vol_data = subprocess.check_output([self.iscsi_config_path, 'show',
                                                '--compartment', self.compartment_name,
                                                '--details', '--no-truncate',
                                                '--output-mode', 'table']).decode('utf-8').splitlines()
            _show_res('iscsi volumes in %s' % self.compartment_name, vol_data)
        except Exception as e:
            self.fail('oci-iscsi-config show --compartment <name> has failed: %s' % str(e))

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
            sync_data = subprocess.check_output([self.iscsi_config_path, 'sync',
                                                 '--apply',
                                                 '--yes']).decode('utf-8').splitlines()
            _show_res('Volume sync', sync_data)
        except Exception as e:
            self.fail('oci-iscsi-config sync has failed: %s' % str(e))

    #
    # compatibility tests
    def test_comp_show_compartment(self):
        """
        Test show compartment in compatibility mode.

        Returns
        -------
            No return value.
        """
        try:
            help_data = subprocess.check_output([self.iscsi_config_path, '--show']).decode('utf-8').splitlines()
            _show_res('Show compartment compatibility', help_data)
            help_data = subprocess.check_output([self.iscsi_config_path, '--show',
                                                 '--all']).decode('utf-8').splitlines()
            _show_res('Show compartment compatibility', help_data)
            help_data = subprocess.check_output([self.iscsi_config_path, '--show',
                                                 '--compartment', self.compartment_name]).decode('utf-8').splitlines()
            _show_res('Show compartment compatibility', help_data)
        except Exception as e:
            self.fail('oci-iscsi-config --show --compartment <name> has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciIscsiConfig)
    unittest.TextTestRunner().run(suite)
