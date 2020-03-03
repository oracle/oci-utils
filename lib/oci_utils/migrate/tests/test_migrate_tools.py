import shutil
import os
import tempfile
import unittest
import unittest.mock as mock 
from unittest.mock import Mock
from unittest.mock import mock_open

from oci_utils.migrate import migrate_tools as migrate_tools
from oci_utils.migrate.exception import OciMigrateException

def my_fake_open(path, mode):
    fake_file = tempfile.NamedTemporaryFile()
    fake_file_name = fake_file.name
    return open(fake_file_name, mode)


class TestMigrateTools(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_is_root(self):
        os.getuid = Mock()
        os.getuid.side_effect = [0, 100]
        self.assertTrue(migrate_tools.is_root())
        self.assertFalse(migrate_tools.is_root())

    def test_get_magic_data(self):
        fakeimage = tempfile.NamedTemporaryFile()
        fakeimage_name = fakeimage.name
        fakeimagemagic = b'\x4b\x44\x4d\x56 ... more ... data ...'
        with open(fakeimage_name, 'wb') as f:
            f.write(fakeimagemagic)
        self.assertEqual(migrate_tools.get_magic_data(fakeimage_name), '4b444d56')

    def test_get_magic_data_fail(self):
        self.assertIsNone(migrate_tools.get_magic_data('notexistingimage'))

    def test_exec_exists(self):
        self.assertTrue(migrate_tools.exec_exists('uname'))
        self.assertFalse(migrate_tools.exec_exists('some_very_weird_exec_name'))

    @mock.patch('oci_utils.migrate.migrate_tools.os.path')
    @mock.patch('oci_utils.migrate.migrate_tools.os')
    def test_exec_rename(self, patched_os, patched_os_path):
        fromname = mock.Mock()
        toname = mock.Mock()
        # to does not exist, from does not exist,
        # to is not a link, from is not a link
        # error message, return False
        print('exec_rename test 01')
        patched_os_path.exists.return_value = False
        patched_os_path.islink.return_value = False
        self.assertFalse(migrate_tools.exec_rename(fromname, toname))
        # to does not exists, from does exist
        # to is not a link, from is not a link
        # return True
        print('exec_rename test 02')
        patched_os_path.exists.side_effect = [False, True]
        patched_os_path.islink.side_effect = [False, False]
        tstrename = migrate_tools.exec_rename(fromname, toname)
        self.assertTrue(tstrename)
        patched_os.rename.assert_called_with(fromname, toname)
        # to does exists and is a file, from does not exist
        # to is not a link, from is not a link
        # return False
        print('exec_rename test 03')
        patched_os_path.isfile.return_value = True
        patched_os_path.exists.side_effect = [True, False]
        patched_os_path.islink.side_effect = [False, False]
        tstrename = migrate_tools.exec_rename(fromname, toname)
        self.assertFalse(tstrename)
        patched_os.remove.assert_called_with(toname)
        # to does exists and is a file, from does exist and is a file
        # to is not a link, from is not a link
        # return True
        print('exec_rename test 04')
        patched_os_path.isfile.return_value = True
        patched_os_path.exists.side_effect = [True, True]
        patched_os_path.islink.side_effect = [False, False]
        tstrename = migrate_tools.exec_rename(fromname, toname)
        self.assertTrue(tstrename)
        patched_os.remove.assert_called_with(toname)
        # to does exists and is a dir, from does not exist
        # to is not a link, from is not a link
        # return True
        print('exec_rename test 05')
        patched_os_path.isfile.return_value = False
        patched_os_path.isdir.return_value = True
        patched_os_path.exists.side_effect = [True, True]
        patched_os_path.islink.side_effect = [False, False]
        tstrename = migrate_tools.exec_rename(fromname, toname)
        self.assertTrue(tstrename)
        patched_os.rmdir.assert_called_with(toname)
        # to does exists and is a symbolic link, from does not exist
        # to is not a link, from is not a link
        # return True
        print('exec_rename test 06')
        patched_os_path.isfile.return_value = False
        patched_os_path.isdir.return_value = False
        patched_os_path.unlink.return_value = True
        patched_os_path.exists.side_effect = [True, True]
        patched_os_path.islink.side_effect = [True, False]
        tstrename = migrate_tools.exec_rename(fromname, toname)
        self.assertTrue(tstrename)
        patched_os.unlink.assert_called_with(toname)
        #
        # not all combinations are tested here, but except the exception raise,
        # all individual lines of code are used.

    @mock.patch('oci_utils.migrate.migrate_tools')
    def test_run_popen_cmd(self, patched_migrate_tools):
        #
        # existing
        somecommand = ['echo', 'test']
        patched_migrate_tools.exec_exists.return_value = True
        popenreturnval = migrate_tools.run_popen_cmd(somecommand)
        self.assertEqual(popenreturnval, b'test\n')
        #
        # not existing
        somecommand = ['noecho', 'test']
        self.assertRaises(OciMigrateException, migrate_tools.run_popen_cmd, somecommand)

    @mock.patch('oci_utils.migrate.migrate_tools.run_popen_cmd')
    def test_get_nameserver(self, patched_popen):
        patched_popen.return_value = 'no name server in here'
        self.assertFalse(migrate_tools.get_nameserver())
        patched_popen.return_value = \
b'IP4.ROUTE[2]:                           dst = 169.254.0.0/16, nh = 0.0.0.0, mt = 1000\n' \
b'IP4.ROUTE[3]:                           dst = 0.0.0.0/0, nh = 10.172.216.1, mt = 100\n' \
b'IP4.DNS[1]:                             10.254.231.168\n' \
b'IP6.ADDRESS[1]:                         2606:b400:808:44:5b20:2dcd:b2f0:298f/64\n' \
b'IP6.ADDRESS[2]:                         fe80::b8e4:4f25:6de5:3f0c/64'
        self.assertTrue(migrate_tools.get_nameserver())

    @mock.patch('os.path')
    @mock.patch('__main__.open', new_callable=mock_open)
    def test_set_nameserver(self, mock_file, patched_os_path):
        #
        # rename tested elsewhere, skip
        patched_os_path.isfile.return_value = False
        patched_os_path.isdir.return_value = False
        patched_os_path.islink.return_value = False
        #
        # destination exists
        patched_os_path.exists = True
        #with open('/tmp/testfile', 'w') as f:
        #    f.write('test data 001\n')
        nssetreturn = migrate_tools.set_nameserver()
        self.assertTrue(nssetreturn)

    def test_restore_nameserver(self):
        #
        #  rename files tested elsewhere
        pass

if __name__ == '__main__':
    unittest.main()
