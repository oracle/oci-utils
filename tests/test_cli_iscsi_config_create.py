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
    iqn = '-'
    for y in volume_data:
        if y.startswith('Currently attached iSCSI') or y.startswith('No iSCSI devices attached'):
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
                elif 'iqn' in y:
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

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_create_destroy(self):
        """
        Test block volume creation and destruction.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create
            volume_name_a = self.vol_name_prefix + uuid.uuid4().hex
            create_volume_data = subprocess.check_output([self.iscsi_config_path, 'create',
                                                          '--size', self.volume_size,
                                                          '--volume-name', volume_name_a]).decode('utf-8').splitlines()
            _show_res('Create Volume', create_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volume data', volume_data)
            new_ocid = self._get_ocid(volume_data, volume_name_a)
            self._volumes_created.append({'display_name': volume_name_a, 'ocid': new_ocid})
            #
            # destroy
            # _show_res('Volume data', volume_data)
            _show_res('Volume ocid', [new_ocid])
            destroy_volume_data = subprocess.check_output([self.iscsi_config_path, 'destroy',
                                                           '--ocids', new_ocid,
                                                           '--yes']).decode('utf-8').splitlines()
            _show_res('Destroy volume', destroy_volume_data)
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('oci-iscsi-config create/destroy has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_destroy_non_existent(self):
        """
        Test destruction of non existent volume.

        Returns
        -------
            No return value.
        """
        try:
            #
            # destroy
            this_ocid = uuid.uuid4().hex
            _show_res('Volume ocid', [this_ocid])
            with self.assertRaises(Exception) as e:
                destroy_volume_data = subprocess.check_output([self.iscsi_config_path, 'destroy', '--ocids', this_ocid, '--yes']).decode('utf-8').splitlines()
            err = e.exception
            print('Exception %s' % str(err))
        except Exception as e:
            self.fail('oci-iscsi-config destroy non existent volume failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_attach_non_existent(self):
        """
        Test attach of non existent volume.

        Returns
        -------
            No return value.
        """
        try:
            #
            # destroy
            this_ocid = uuid.uuid4().hex
            _show_res('Volume ocid', [this_ocid])
            with self.assertRaises(Exception) as e:
                attach_volume_data = subprocess.check_output([self.iscsi_config_path, 'attach', '--iqns', this_ocid]).decode('utf-8').splitlines()
            err = e.exception
            print('Exception %s' % str(err))
        except Exception as e:
            self.fail('oci-iscsi-config destroy non existent volume failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_detach_non_existent(self):
        """
        Test detach of non existent volume.

        Returns
        -------
            No return value.
        """
        try:
            #
            # destroy
            this_iqn = 'iqn.2015-12.com.oracleiaas:' + uuid.uuid4().hex
            _show_res('Volume ocid', [this_iqn])
            with self.assertRaises(Exception) as e:
                detach_volume_data = subprocess.check_output([self.iscsi_config_path, 'detach', '--iqns', this_iqn]).decode('utf-8').splitlines()
            err = e.exception
            print('Exception %s' % str(err))
        except Exception as e:
            self.fail('oci-iscsi-config destroy non existent volume failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_create_destroy_attach(self):
        """
        Test block volume creation, attachment, detachment and destruction.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create
            volume_name_a = self.vol_name_prefix + uuid.uuid4().hex
            create_volume_data = subprocess.check_output([self.iscsi_config_path, 'create',
                                                          '--size', self.volume_size,
                                                          '--volume-name', volume_name_a,
                                                          '--attach-volume']).decode('utf-8').splitlines()
            _show_res('Create Volume', create_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            new_ocid = self._get_ocid(volume_data, volume_name_a)
            self._volumes_created.append({'display_name': volume_name_a, 'ocid': new_ocid})
            #
            # destroy
            _show_res('Volume ocid', [new_ocid])
            with self.assertRaises(Exception) as e:
                destroy_volume_data = subprocess.check_output([self.iscsi_config_path, 'destroy', '--ocids', new_ocid, '--yes']).decode('utf-8').splitlines()
            err = e.exception
            print('Exception %s' % str(err))
            #
            # detach
            volume_data_show = self._get_iscsi_show(all_vol=False)
            new_iqn = self._get_iqn(volume_data_show, volume_name_a)
            detach_volume_data = subprocess.check_output([self.iscsi_config_path, 'detach', '--iqns', new_iqn]).decode('utf-8').splitlines()
            _show_res('Detach volume', detach_volume_data)
            self.assertTrue('is detached' in detach_volume_data[1], 'Detaching volume failed')
            #
            # destroy
            _show_res('Volume ocid', [new_ocid])
            destroy_volume_data = subprocess.check_output([self.iscsi_config_path, 'destroy',
                                                           '--ocids', new_ocid,
                                                           '--yes']).decode('utf-8').splitlines()
            _show_res('Destroy volume', destroy_volume_data)
            self.assertTrue('is destroyed' in destroy_volume_data[0], 'Destroying volume failed')
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('oci-iscsi-config create/destroy has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_multiple_create_destroy(self):
        """
        Test multiple block device detach, attache, destroy

        Returns
        -------
            No return value
        """
        try:
            vol_list = [self.vol_name_prefix + uuid.uuid4().hex,
                        self.vol_name_prefix + uuid.uuid4().hex,
                        self.vol_name_prefix + uuid.uuid4().hex]
            #
            # create
            for vol in vol_list:
                create_volume_data = subprocess.check_output([self.iscsi_config_path, 'create',
                                                              '--size', self.volume_size,
                                                              '--volume-name', vol,
                                                              '--attach-volume']).decode('utf-8').splitlines()
                _show_res('Volume created', create_volume_data)
                time.sleep(self.waittime)
            #
            # detach
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show()
            _show_res('Volumes', volume_data)
            detach_volume_data = ''
            for vol in vol_list:
                detach_volume_data += self._get_iqn(volume_data, vol) + ','
            _show_res('IQN list', [detach_volume_data])
            detach_volume_data = subprocess.check_output([self.iscsi_config_path, 'detach',
                                                          '--iqns', detach_volume_data[:-1]]).decode('utf-8').splitlines()
            _show_res('Volumes detached', detach_volume_data)
            time.sleep(self.waittime)
            #
            # destroy
            detach_volume_data = ''
            for vol in vol_list:
                detach_volume_data += self._get_ocid(volume_data, vol) + ','
            _show_res('OCID list', [detach_volume_data])
            destroy_volume_data = subprocess.check_output([self.iscsi_config_path, 'destroy',
                                                           '--ocids', detach_volume_data[:-1],
                                                           '--yes']).decode('utf-8').splitlines()
            _show_res('Volumes destroyed', destroy_volume_data)
        except Exception as e:
            self.fail('oci-iscsi-config multiple create/attach/detach/destroy has failed: %s' % str(e))

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
            #
            # create
            volume_name = self.vol_name_prefix + uuid.uuid4().hex
            create_volume_data = subprocess.check_output([self.iscsi_config_path, 'create',
                                                          '--size', self.volume_size,
                                                          '--volume-name', volume_name]).decode('utf-8').splitlines()
            _show_res('Volume created', create_volume_data)
            time.sleep(self.waittime)
            #
            # attach
            volume_data = self._get_iscsi_show(all_vol=True)
            new_ocid = self._get_ocid(volume_data, volume_name)
            attach_volume_data = subprocess.check_output([self.iscsi_config_path, 'attach',
                                                          '--iqns', new_ocid]).decode('utf-8').splitlines()
            _show_res('Volume attached', attach_volume_data)
            time.sleep(self.waittime)
            #
            # collect the info of the attached volume
            attach_volume_data_show = subprocess.check_output([self.iscsi_config_path, 'show',
                                                               '--detail']).decode('utf-8').splitlines()
            _show_res('Volumes attached', attach_volume_data_show)
            time.sleep(self.waittime)
            #
            # detach
            volume_data_show = self._get_iscsi_show(all_vol=False)
            new_iqn = self._get_iqn(volume_data_show, volume_name)
            detach_volume_data = subprocess.check_output([self.iscsi_config_path, 'detach',
                                                          '--iqns', new_iqn]).decode('utf-8').splitlines()
            _show_res('Volume detached', detach_volume_data)
            time.sleep(self.waittime)
            #
            # destroy
            destroy_volume_data = subprocess.check_output([self.iscsi_config_path, 'destroy',
                                                           '--ocids', new_ocid,
                                                           '--yes']).decode('utf-8').splitlines()
            _show_res('Volume destroyed', destroy_volume_data)
            time.sleep(self.waittime)
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

    def test_comp_create_destroy(self):
        """
        Test block volume creation and destruction in compatibility mode.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create
            volume_name = self.vol_name_prefix + uuid.uuid4().hex
            create_volume_data = subprocess.check_output([self.iscsi_config_path, '--create-volume', self.volume_size,
                                                          '--volume-name', volume_name]).decode('utf-8').splitlines()
            _show_res('Volume created', create_volume_data)
            time.sleep(self.waittime)
            #
            # detach
            volume_data = self._get_iscsi_show()
            new_iqn = self._get_iqn(volume_data, volume_name)
            detach_volume_data = subprocess.check_output([self.iscsi_config_path, '--detach', new_iqn]).decode('utf-8').splitlines()
            _show_res('Volume detached', detach_volume_data)
            time.sleep(self.waittime)
            #
            # reattach
            volume_data = self._get_iscsi_show()
            new_ocid = self._get_ocid(volume_data, volume_name)
            attach_volume_data = subprocess.check_output([self.iscsi_config_path, '--attach', new_ocid]).decode('utf-8').splitlines()
            _show_res('Volume re-attached', attach_volume_data)
            time.sleep(self.waittime)
            #
            # detach
            volume_data = self._get_iscsi_show()
            new_iqn = self._get_iqn(volume_data, volume_name)
            detach_volume_data = subprocess.check_output([self.iscsi_config_path, '--detach', new_iqn]).decode('utf-8').splitlines()
            _show_res('Volume detached again', detach_volume_data)
            time.sleep(self.waittime)
            #
            # destroy
            volume_data = self._get_iscsi_show()
            new_ocid = self._get_ocid(volume_data, volume_name)
            destroy_volume_data = subprocess.check_output([self.iscsi_config_path, '--destroy-volume', new_ocid,
                                                           '--yes']).decode('utf-8').splitlines()
            _show_res('Volume destroyed', destroy_volume_data)
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('oci-iscsi-config create/destroy has failed: %s' % str(e))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliOciIscsiConfig)
    unittest.TextTestRunner().run(suite)
