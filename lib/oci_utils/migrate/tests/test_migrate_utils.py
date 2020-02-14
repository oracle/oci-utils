import shutil
import os
import tempfile
import unittest
try:
    import unittest.mock as mock
    from unittest.mock import Mock
except ImportError:
    import mock
    from mock import Mock

from oci_utils.migrate import migrate_tools as migrate_tools
from oci_utils.migrate import migrate_utils as migrate_utils
from oci_utils.migrate.exception import OciMigrateException

def my_fake_open(path, mode):
    print ('fake open')
    return open('fake_file_path', mode)

def my_fake_call(somecall):
    print ('fake call')
    return False

class TestMigrateUtils(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_bucket_exists(self, patched_popen):
        #
        # oci cli exists, buckect exists
        patched_popen.side_effect = ['oci_cli_path', 'bucket_result']
        self.assertTrue(migrate_utils.bucket_exists('fake_bucket'))
        patched_popen.assert_called_with(['oci', 'os', 'object', 'list', '--bucket-name', 'fake_bucket'])
        #
        # oci cli exists, bucket does not exists
        patched_popen.side_effect = ['oci_cli_path' ]
        self.assertRaises(OciMigrateException, migrate_utils.bucket_exists, 'fake_bucket')
        patched_popen.assert_called_with(['oci', 'os', 'object', 'list', '--bucket-name', 'fake_bucket'])
        #
        # oci cli does not exist (not redefining the popen side effect causes popen excepts out)
        self.assertRaises(OciMigrateException, migrate_utils.bucket_exists, 'fake_bucket')
        patched_popen.assert_called_with(['oci', 'os', 'object', 'list', '--bucket-name', 'fake_bucket'])

    @mock.patch('oci_utils.migrate.migrate_utils.run_call_cmd')
    def test_create_nbd(self, patched_call):
        patched_call.side_effect = [0, 1]
        self.assertTrue(migrate_utils.create_nbd())
        patched_call.assert_called_with(['modprobe', 'nbd', 'max_part=63'])
        self.assertFalse(migrate_utils.create_nbd())
        patched_call.assert_called_with(['modprobe', 'nbd', 'max_part=63'])

    @mock.patch.dict('oci_utils.migrate.migrate_utils.os.environ', {'PATH': '/usr/local/bin:/usr/bin:/bin'}, clear=True)
    @mock.patch('oci_utils.migrate.migrate_utils.os')
    def test_enter_chroot(self, patched_os):
        patched_os.open.return_value = '/someroot'
        oldroot, oldpath = migrate_utils.enter_chroot('self.tempdir')
        # ignore oldpath, not used
        self.assertEqual(oldroot,  '/someroot')
        #
        # os.open throws an exception
        with mock.patch('oci_utils.migrate.migrate_utils.os.open') as mock_oserror:
            mock_oserror.side_effect = OSError
            self.assertRaises(OciMigrateException, migrate_utils.enter_chroot, 'self.tempdir')
        #
        # 
        # with mock.patch('oci_utils.migrate.migrate_utils.os.environ') as mock_keyerror:
        #    mock_keyerror.side_effect = KeyError
        #    self.assertRaises(OciMigrateException, migrate_utils.enter_chroot, 'self.tempdir')

    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_exec_blkid(self, patched_popen):
        blkidres = ['ID_FS_USAGE=raid', 'ID_PART_ENTRY_SCHEME=dos', 'ID_MORE=xyz']
        patched_popen.return_value = blkidres
        self.assertEqual(migrate_utils.exec_blkid(['some', 'blkid', 'cmd']), blkidres)
        #
        # run_popen_cmd raises an exception
        with mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd') as mock_popenerror:
            mock_popenerror.side_effect = OSError
            self.assertIsNone(migrate_utils.exec_blkid(['some', 'blkid', 'cmd']))
    
    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_exec_lsblk(self, patched_popen):
        patched_popen.return_value = 0
        self.assertEqual(migrate_utils.exec_lsblk(['some', 'lsblk', 'cmd']), 0)
        #
        # run_popen_cmd raises an exception
        with mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd') as mock_popenerror:
            mock_popenerror.side_effect = OSError
            self.assertRaises(OciMigrateException, migrate_utils.exec_lsblk, ['some', 'blkid', 'cmd'])
    
    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_exec_lvscan(self, patched_popen):
        patched_popen.return_value = "  inactive            '/dev/ol_tstoci-001/swap' [2.00 GiB] inherit\n  inactive            '/dev/ol_tstoci-001/root' [20.99 GiB] inherit\n"
        self.assertEqual(migrate_utils.exec_lvscan(),{'ol_tstoci-001': [('swap', 'ol_tstoci--001-swap'), ('root', 'ol_tstoci--001-root')]})
        #
        # run_popen_cmd raises an exception
        with mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd') as mock_popenerror:
            mock_popenerror.side_effect = OSError
            self.assertRaises(OciMigrateException, migrate_utils.exec_lvscan)
    
    @mock.patch('oci_utils.migrate.migrate_tools.os.path.exists')
    @mock.patch('oci_utils.migrate.migrate_tools.os.makedirs')  
    def test_exec_mkdir(self, patched_os_makedirs, patched_os_exists):
        dirname = mock.Mock()
        patched_os_exists.side_effect = [False, True]
        #
        # does not exist
        migrate_utils.exec_mkdir(dirname)
        patched_os_exists.assert_called_with(dirname)
        patched_os_makedirs.assert_called_with(dirname)
        #
        # already exists
        migrate_utils.exec_mkdir(dirname)
        patched_os_exists.assert_called_with(dirname)
        #
        # os.makedirs raises an exception
        with mock.patch('oci_utils.migrate.migrate_tools.os.makedirs') as mock_mkdirerror:
            mock_mkdirerror.side_effect = OSError
            self.assertRaises(OciMigrateException, migrate_utils.exec_mkdir, dirname)
    
    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_exec_parted(self, patched_popen):
        patched_popen.return_value = '^[[?1034hModel: Unknown (unknown)\n' \
            'Disk /dev/nbd3: 25.8GB\n' \
            'Sector size (logical/physical): 512B/512B\n' \
            'Partition Table: msdos\n' \
            'Disk Flags:\n' \
            'Number  Start   End     Size    Type     File system  Flags\n' \
            ' 1      1049kB  1075MB  1074MB  primary  xfs          boot\n' \
            ' 2      1075MB  25.8GB  24.7GB  primary               lvm'
        parted_return_value = {'Model': ' Unknown (unknown)', 'Disk': '', 'Partition Table': ' msdos'}
        self.assertEqual(migrate_utils.exec_parted('xyz'), parted_return_value)
        #
        # run_popen_cmd raises an exception
        with mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd') as mock_popenerror:
            mock_popenerror.side_effect = OSError
            self.assertIsNone(migrate_utils.exec_parted('xyz'))

    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_exec_pvscan(self, patched_popen):
        patched_popen.return_value = 'the physical volumes'
        self.assertTrue('oci_utils.exec_pvscan()')
        devname = '/device/name'
        self.assertTrue('oci_utils.exec_pvscan(devname)')
        #
        # run_popen_cmd raises an exception
        with mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd') as mock_popenerror:
            mock_popenerror.side_effect = OSError
            self.assertRaises(OciMigrateException, migrate_utils.exec_pvscan, 'xyz')
    
    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_exec_qemunbd(self, patched_popen):
        patched_popen.return_value = 0
        self.assertEqual(migrate_utils.exec_qemunbd([ '-c','/dev/nbd_x','/image/path']), 0)
        #
        # run_popen_cmd raises an exception
        with mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd') as mock_popenerror:
            mock_popenerror.side_effect = OSError
            self.assertRaises(OciMigrateException, migrate_utils.exec_qemunbd, ['xyz'])
    
    @mock.patch('oci_utils.migrate.migrate_utils.shutil')
    def test_exec_rmdir(self, patched_shutil):
        dirname = mock.Mock()
        migrate_utils.exec_rmdir(dirname)
        patched_shutil.rmtree.assert_called_with(dirname)
        #
        # rmtree raises an exception
        with mock.patch('oci_utils.migrate.migrate_utils.shutil.rmtree') as mock_rmtreeerror:
            mock_rmtreeerror.side_effect = OSError
            self.assertRaises(OciMigrateException, migrate_utils.exec_rmdir, dirname)

    @mock.patch('oci_utils.migrate.migrate_utils.subprocess')
    def test_exec_rmmod(self, patched_subprocess):
        patched_subprocess.side_effect = [0, 1]
        self.assertTrue(migrate_utils.exec_rmmod('module'))
        self.assertTrue(migrate_utils.exec_rmmod('module'))
        #
        # check_call raises an exception
        with mock.patch('oci_utils.migrate.migrate_utils.subprocess.check_call') as mock_checkcallerror:
            mock_checkcallerror.side_effect = OSError
            self.assertTrue(migrate_utils.exec_rmmod('module'))

    @mock.patch('oci_utils.migrate.migrate_utils.os')
    def test_exec_search(self, patched_os):
        patched_os.walk.return_value = [('/a',('b',), ('1',)),
                                        ('/a/1',(),('c','2','3'))]
        self.assertEqual(str(migrate_utils.exec_search('c')), 'a/b/c')
       
    
    def exec_sfdisk(self):
        pass
    
    def exec_vgchange(self):
        pass
    
    def exec_vgscan(self):
        pass
    
    def find_os_specific(self):
        pass
    
    def get_free_nbd(self):
        pass
    
    def get_nameserver(self):
        pass
    
    def get_oci_config(self):
        pass
    
    def leave_chroot(self):
        pass
    
    def mount_fs(self):
        pass
    
    def mount_imgfn(self):
        pass
    
    def mount_lvm2(self):
        pass
    
    def mount_partition(self):
        pass
    
    def mount_pseudo(self):
        pass
    
    def object_exists(self):
        pass
    
    def print_header(self):
        pass
    
    def rm_nbd(self):
        pass
    
    def set_default_user(self):
        pass
    
    def show_fstab(self):
        pass
    
    def show_grub_data(self):
        pass
    
    def show_hex_dump(self):
        pass
    
    def show_image_data(self):
        pass
    
    def show_img_header(self):
        pass
    
    def show_lvm2_data(self):
        pass
    
    def show_network_data(self):
        pass
    
    def show_parted_data(self):
        pass
    
    def show_partition_data(self):
        pass
    
    def show_partition_table(self):
        pass
    
    def state_loop(self):
        pass
    
    def unmount_imgfn(self):
        pass
    
    def unmount_lvm2(self):
        pass
    
    def unmount_part(self):
        pass
    
    def unmount_pseudo(self):
        pass
    
    def unmount_something(self):
        pass
    
    def upload_image(self):
        pass
    
    
if __name__ == '__main__':
    unittest.main()
