# Copyright (c) 2018, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import subprocess
import uuid
import unittest
import time
from tools.oci_test_case import OciTestCase
from tools.decorators import (skipUnlessOCI, skipUnlessRoot)

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

def _run_step(step_name, cmd):
    """
    Execute a step in the test.
    Parameters
    ----------
    step_name: str
        The name of the step.
    cmd: list
        The command to execute.

    Returns
    -------
        str: The command output.
    """
    print('%s' % cmd)
    try:
        command_return = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').splitlines()
    except subprocess.CalledProcessError as e:
        return '%d %s' % (e.returncode, e.output.decode('utf-8'))
    else:
        _show_res(step_name, command_return)
        return ''.join(command_return)


class TestCliKvm(OciTestCase):
    """ oci-kvm tests.
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
            If the KVM config file does not exists.
        """
        super(TestCliKvm, self).setUp()
        self.oci_kvm_path = self.properties.get_property('oci-kvm')
        if not os.path.exists(self.oci_kvm_path):
            raise unittest.SkipTest("%s not present" % self.oci_kvm_path)
        self.oci_iscsi_config = self.properties.get_property('oci-iscsi-config')
        if not os.path.exists(self.oci_iscsi_config):
            raise unittest.SkipTest("%s not present" % self.oci_iscs_path)
        self.oci_network_path = self.properties.get_property('oci-network-config')
        if not os.path.exists(self.oci_network_path):
            raise unittest.SkipTest("%s not present" % self.oci_network_path)
        try:
            self.pool_name_prefix = self.properties.get_property('pool-name-prefix')
        except Exception:
            self.pool_name_prefix = 'auto-'
        try:
            self.waittime = int(self.properties.get_property('waittime'))
        except Exception:
            self.waittime = 20
        self.volume_name_prefix = self.properties.get_property('volume-name-prefix')
        self.volume_size = self.properties.get_property('volume-size')
        self.ip_bridge = self.properties.get_property('ip-bridge')
        self.ip_start = self.properties.get_property('ip-start')
        self.ip_end = self.properties.get_property('ip-end')
        self.ip_prefix = self.properties.get_property('ip-prefix')
        self.vnic_name_prefix = self.properties.get_property('vnic-name-prefix')
        self.kvm_net_prefix = self.properties.get_property('kvm-net-prefix')
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
        get_volumes = [self.oci_iscsi_config, 'show', '--detail', '--no-truncate', '--output-mode', 'text']
        if all_vol:
            get_volumes.append('--all')
        return subprocess.check_output(get_volumes).decode('utf-8').splitlines()

    def _get_volume_data(self, index, val, field):
        """
        Return val for volume based on index.

        Parameters
        ----------
        index: str
            base field name.
        val: str
            base field value.
        field: str
            requested field value.

        Returns
        -------
            str: the requested value, None if absent.
        """
        attached = ['iqn', 'name', 'ocid', 'persistentportal', 'currentportal', 'state', 'device', 'size']
        all = ['name', 'size', 'attached', 'ocid', 'iqn', 'compartment', 'availabilitydomain']
        cmd = [self.oci_iscsi_config, 'show', '--detail', '--no-truncate', '--output-mode', 'parsable', '--all']
        all_volume_data = subprocess.check_output(cmd).decode('utf-8').splitlines()

        for vol in all_volume_data:
            vol_list = vol.split('#')
            if vol_list[2].startswith('ocid1.'):
                if index not in attached or field not in attached:
                    continue
                # is a volume in the attached list
                if vol_list[attached.index(index)] == val:
                    return vol_list[attached.index(field)]
            else:
                if index not in all or field not in all:
                    continue
                # is a volume in the 'all' list
                if vol_list[all.index(index)] == val:
                    return vol_list[all.index(field)]
        return None

    def _get_vnic_data(self, index, val, field):
            """
            Return val for vnic based on index.
            Parameters
            ----------
            index: str
                base field name.
            val: str
                base field value.
            field: str
                requested field value.

            Returns
            -------
                str: the requested value, None if absent.
            """
            vnic_fields = ['state', 'link', 'status', 'ipaddress', 'vnic', 'mac', 'hostname', 'subnet',
                           'routerip', 'namespace', 'index', 'vlantag', 'vlan']
            cmd = [self.oci_network_path, 'show', '--details', '--output-mode', 'parsable']
            all_vnic_data = subprocess.check_output(cmd).decode('utf-8').splitlines()

            for vnic in all_vnic_data:
                vnic_list = vnic.split('#')
                if index not in vnic_fields or field not in vnic_fields:
                    return None
                if vnic_list[vnic_fields.index(index)] == val:
                    return vnic_list[vnic_fields.index(field)]
            return None

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the CLI at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_kvm_path, '--help'])
            _ = subprocess.check_output([self.oci_kvm_path, 'create', '--help'])
            _ = subprocess.check_output([self.oci_kvm_path, 'destroy', '--help'])
            _ = subprocess.check_output([self.oci_kvm_path, 'create-pool', '--help'])
            _ = subprocess.check_output([self.oci_kvm_path, 'list-pool', '--help'])
            _ = subprocess.check_output([self.oci_kvm_path, 'create-network', '--help'])
            _ = subprocess.check_output([self.oci_kvm_path, 'delete-network', '--help'])
        except Exception as e:
            self.fail('Execution of display help has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_create_disk_pool(self):
        """
        Test the creation of a disk based storage pool.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create volume
            volume_name_a = self.volume_name_prefix + uuid.uuid4().hex
            cmd = [self.oci_iscsi_config, 'create',
                   '--size', self.volume_size,
                   '--volume-name', volume_name_a,
                   '--attach-volume']

            create_volume_data = _run_step('Create Volume', cmd)
            self.assertIn('created', str(create_volume_data), 'Failed to create volume.')

            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show(all_vol=False)
            _show_res('Volume data', volume_data)
            time.sleep(self.waittime)
            #
            # create pool
            pool_name_a = self.pool_name_prefix + uuid.uuid4().hex
            this_disk = '/dev/' + self._get_volume_data('name', volume_name_a, 'device')
            cmd = [self.oci_kvm_path, 'create-pool',
                   '--disk', this_disk,
                   '--name', pool_name_a]
            create_pool_data = _run_step('Create Pool', cmd)
            self.assertIn('successfully', create_pool_data, 'Failed to create pool.')
            time.sleep(self.waittime)
            #
            # list pool
            cmd = [self.oci_kvm_path, 'list-pool',
                   '--output-mode', 'table']
            list_pool_data = _run_step('List Pool', cmd)
            # delete pool
            # using virsh commands for now till delete-pool is implemented.
            virsh_path = '/bin/virsh'
            cmd = [virsh_path, 'pool-destroy', pool_name_a]
            destroy_output = _run_step('Destroy pool by virsh', cmd)
            self.asssertIn('destroyed', destroy_output, 'Failed to destroy pool.')
            #
            cmd = [virsh_path, 'pool-delete', pool_name_a]
            delete_output = _run_step('Delete pool by virsh', cmd)
            self.assertIn('deleted', delete_output, 'Failed to delete pool.')
            #
            cmd = [virsh_path, 'pool-undefine', pool_name_a]
            undefine_output = _run_step('Undefine pool by virsh', cmd)
            self.assertIn('undefined', undefine_output, 'Failed to undefine pool.')
            #
            # detach volume
            this_iqn = self._get_volume_data('name', volume_name_a, 'iqn')
            cmd = [self.oci_iscsi_config, 'detach', '--iqns', this_iqn]
            detach_volume_data = _run_step('Detach volume', cmd)
            self.assertIn('detached', detach_volume_data, 'Failed to detach volume.')
            #
            # destroy volume
            this_ocid = self._get_volume_data('name', volume_name_a, 'ocid')
            cmd = [self.oci_iscsi_config, 'destroy', '--ocids', this_ocid, '--yes']
            destroy_volume_data = _run_step('Destroy volume', cmd)
            self.assertIn('destroyed', destroy_volume_data, 'Failed to destroy volume.')
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('Execution of create disk pool has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_create_nfs_pool(self):
        """
        Test the creation of a nfs based storage pool.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create volume
            volume_name_b = self.volume_name_prefix + uuid.uuid4().hex
            cmd = [self.oci_iscsi_config, 'create',
                   '--size', self.volume_size,
                   '--volume-name', volume_name_b,
                   '--attach-volume']
            print(cmd)
            create_volume_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Create Volume', create_volume_data)
            time.sleep(self.waittime)
            volume_data = self._get_iscsi_show(all_vol=False)
            _show_res('Volume data', volume_data)
            time.sleep(self.waittime)
            #
            # systemctl start nfs
            cmd = ['systemctl', 'start', 'nfs']
            print(cmd)
            nfs_start_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('systemctl start nfs', nfs_start_data)
            time.sleep(self.waittime)
            # parted --script /dev/sdc mklabel gpt
            this_disk = '/dev/' \
                        + self._get_volume_data('name', volume_name_b, 'device')
            print(this_disk)
            cmd = ['parted', '--script', this_disk,
                   'mklabel', 'gpt']
            print(cmd)
            parted_mklabel_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('parted mklabel data', parted_mklabel_data)
            # parted --script -a optimal /dev/sdc mkpart primary ext4 0% 100%
            cmd = ['parted', '--script', this_disk,
                   'mkpart', 'primary', 'ext4', '0%', '100%']
            print(cmd)
            parted_mkpart_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('parted mkpart data', parted_mkpart_data)
            # mkfs.ext4 /dev/sdc1
            cmd = ['mkfs.ext4', this_disk + '1']
            print(cmd)
            mkfs_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('mkfs data', mkfs_data)
            # mkdir /nfs_pool
            cmd = ['mkdir', '-p', '/nfs_pool']
            print(cmd)
            mkdir_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('mkdir data', mkdir_data)
            # mount /dev/sdc1 /nfs_pool
            cmd = ['mount', this_disk + '1', '/nfs_pool']
            print(cmd)
            mount_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('mount data', mount_data)
            # mkdir /nfs_pool/nsf_pool_space
            cmd = ['mkdir', '-p', '/nfs_pool/nfs_pool_space']
            print(cmd)
            mkdir_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('mkdir data', mkdir_data)
            # echo "/nfs_pool *(rw,sync)" >> /etc/exports
            with open('/etc/exports', 'w') as expf:
                expf.write('/nfs_pool *(rw,sync)')
            # exportfs -a
            cmd = ['exportfs', '-a']
            print(cmd)
            exportfs_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('exportfs data', exportfs_data)
            #
            # create pool
            # oci-kvm create-pool --netfshost localhost --path /nfs_pool/nfs_pool_space --name nfs_pool
            pool_name_b = self.pool_name_prefix + uuid.uuid4().hex
            cmd = [self.oci_kvm_path, 'create-pool',
                   '--netfshost', 'localhost',
                   '--path', '/nfs_pool/nfs_pool_space',
                   '--name', pool_name_b]
            print(cmd)
            create_pool_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Create Pool', create_pool_data)
            time.sleep(self.waittime)
            #
            #
            # list pool
            cmd = [self.oci_kvm_path, 'list-pool', '--output-mode', 'table']
            print(cmd)
            list_pool_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('List Pool', list_pool_data)
            #
            # delete pool
            # using virsh commands for now till delete-pool is implemented.
            virsh_path = '/bin/virsh'
            cmd = [virsh_path, 'pool-destroy', pool_name_b]
            print(cmd)
            destroy_output = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Destroy Pool by virsh', destroy_output)
            cmd = [virsh_path, 'pool-delete', pool_name_b]
            print(cmd)
            delete_output = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Delete pool by virsh', delete_output)
            cmd = [virsh_path, 'pool-undefine', pool_name_b]
            print(cmd)
            undefine_output = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Undefine pool by virsh', undefine_output)
            time.sleep(self.waittime)
            #
            # umount /nfs_pool
            # unable to unmount the nfs_pool: busy....
        except Exception as e:
            self.fail('Execution of create nfs pool has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_create_network(self):
        """
        Test the creation of an oci-kvm network.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create vnic
            vnic_name_b = self.vnic_name_prefix + uuid.uuid4().hex[:6]
            cmd = [self.oci_network_path, 'attach-vnic',
                   '--name', vnic_name_b]
            print(cmd)
            create_vnic_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            self.assertIn('Creating', str(create_vnic_data), 'attach vnic failed')
            _show_res('Create VNIC', create_vnic_data)
            time.sleep(self.waittime)
            cmd = [self.oci_network_path, 'show',
                   '--details',
                   '--output-mode', 'table']
            print(cmd)
            vnic_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Vnic Data', vnic_data)
            #
            # create kvm bridge
            kvm_network_name = self.kvm_net_prefix + uuid.uuid4().hex[:6]
            kvm_net_ip = self._get_vnic_data('vnic', vnic_name_b, 'ipaddress')
            cmd = [self.oci_kvm_path, 'create-network',
                   '--network-name', kvm_network_name,
                   '--net', kvm_net_ip,
                   '--ip-bridge', self.ip_bridge,
                   '--ip-start', self.ip_start,
                   '--ip-end', self.ip_end,
                   '--ip-prefix', self.ip_prefix]
            print(cmd)
            create_kvm_bridge_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Create KVM network', create_kvm_bridge_data)
            time.sleep(self.waittime)
            #
            # show
            cmd = [self.oci_network_path, 'show',
                   '--details',
                   '--output-mode', 'text']
            print(cmd)
            show_vnic_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Show network data', show_vnic_data)
            #
            # delete kvm bridge
            cmd = [self.oci_kvm_path, 'delete-network',
                   '--network-name', kvm_network_name,
                   '--yes']
            print(cmd)
            delete_kvm_bridge_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Delete KVM network', delete_kvm_bridge_data)
            time.sleep(self.waittime)
            #
            # delete vnic
            cmd = [self.oci_network_path, 'detach-vnic',
                   '--ip-address', kvm_net_ip]
            print(cmd)
            delete_vnic_data = subprocess.check_output(cmd).decode('utf-8').splitlines()
            _show_res('Delete VNIC', delete_vnic_data)
        except Exception as e:
            self.fail('Execution of create kvm network has failed: %s' % str(e))

    @skipUnlessOCI()
    @skipUnlessRoot()
    def test_create_long_network_LINUX_11442(self):
        """
        Test the creation of an oci-kvm network, kvm network longer than 14 chars should fail.

        Returns
        -------
            No return value.
        """
        try:
            #
            # create vnic
            vnic_name_b = self.vnic_name_prefix + uuid.uuid4().hex
            cmd = [self.oci_network_path, 'attach-vnic',
                   '--name', vnic_name_b]
            create_vnic_data = _run_step('Create VNIC', cmd)
            self.assertIn('Creating', create_vnic_data, 'attach vnic failed')
            #
            # show
            time.sleep(self.waittime)
            cmd = [self.oci_network_path, 'show',
                   '--details',
                   '--output-mode', 'table']
            vnic_data = _run_step('VNIC data', cmd)
            #
            # create kvm bridge
            kvm_network_name = self.kvm_net_prefix + uuid.uuid4().hex
            kvm_net_ip = self._get_vnic_data('vnic', vnic_name_b, 'ipaddress')
            cmd = [self.oci_kvm_path, 'create-network',
                   '--network-name', kvm_network_name,
                   '--net', kvm_net_ip,
                   '--ip-bridge', self.ip_bridge,
                   '--ip-start', self.ip_start,
                   '--ip-end', self.ip_end,
                   '--ip-prefix', self.ip_prefix]
            create_kvm_bridge_data = _run_step('Create KVM network', cmd)
            self.assertIn('characters', create_kvm_bridge_data, '%s should have failed' % cmd)
            time.sleep(self.waittime)
        except Exception as e:
            self.fail('Execution of create kvm network has failed: %s' % str(e))
        finally:
            # clean up
            #
            # delete kvm bridge
            try:
                cmd = [self.oci_kvm_path, 'delete-network',
                       '--network-name', kvm_network_name,
                       '--yes']
                delete_kvm_bridge_data = _run_step('Delete KVM network', cmd)
                time.sleep(self.waittime)
            except Exception as e:
                pass
            #
            # delete vnic
            try:
                cmd = [self.oci_network_path, 'detach-vnic',
                       '--ip-address', kvm_net_ip]
                delete_vnic_data = _run_step('Delete VNIC', cmd)
            except Exception as e:
                pass


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCliKvm)
    unittest.TextTestRunner().run(suite)
