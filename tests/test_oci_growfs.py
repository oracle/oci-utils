# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at
# http://oss.oracle.com/licenses/upl.

import os
import subprocess
import unittest

from tools.decorators import (skipUnlessOCI, skipUnlessRoot, skipItAsUnresolved)
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

SMALL_CHUNK = 2048
LARGE_CHUNK = 65536


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


def create_small_file(fn):
    """
    Create a small file in /tmp

    Parameters
    ----------
    fn: str
        file path to create the file from.

    Returns
    -------
        No return value
    """
    f_size = os.stat(fn).st_size
    if f_size < SMALL_CHUNK:
        with open(fn, 'rb') as f:
            buffer = f.read();
    else:
        with open(fn, 'rb') as f:
            buffer = f.read(SMALL_CHUNK)
    with open('/tmp/small_file', 'wb') as g:
        g.write(buffer)


def create_large_file(fn):
    """
    Create a small file in /tmp

    Parameters
    ----------
    fn: str
        file path to create the file from.

    Returns
    -------
        No return value
    """
    f_size = os.stat(fn).st_size
    if f_size < LARGE_CHUNK:
        with open(fn, 'rb') as f:
            buffer = f.read()
            chunksize = f_size
    else:
        with open(fn, 'rb') as f:
            buffer = f.read(LARGE_CHUNK)
            chunksize = LARGE_CHUNK
    largefilesize = LARGE_CHUNK * 2 + SMALL_CHUNK
    nbbuf = divmod(largefilesize, chunksize)[0] + 1
    with open('/tmp/large_file', 'wb') as g:
        for _ in range(nbbuf):
            g.write(buffer)


class TestOciNotify(OciTestCase):
    """ Test oci-notify code.
    """

    def setUp(self):
        """
        Test initialisation.

        Returns
        -------
            No return value.
        """
        super(TestOciNotify, self).setUp()
        self.oci_notify = self.properties.get_property('oci-notify')
        self.valid_topic = self.properties.get_property('valid_topic')
        self.non_exist_topic = self.properties.get_property('non_exist_topic')
        self.invalid_topic = self.properties.get_property('invalid_topic')
        self.test_file = self.properties.get_property('test_file')

    def test_display_help(self):
        """
        Test displaying help. Dummy test to check that the oci-notify at least runs.

        Returns
        -------
            No return value.
        """
        try:
            _ = subprocess.check_output([self.oci_notify, '--help'])
        except Exception as e:
            self.fail('Execution has failed: %s' % str(e))


    @skipUnlessRoot()
    def test_aaa_config_valid(self):
        """
        Tests oci notify configuration with a valid notification topic.

        Returns
        -------
            No return value.
        """
        cmd = [self.oci_notify, 'config', self.valid_topic]
        try:
            valid_config_output = _run_step('Config with valid topic', cmd)
            self.assertIn('Configured OCI notification service', str(valid_config_output), 'Failed to configure OCI notification service.')
        except Exception as e:
            self.fail('oci notification configuration failed.')

    def test_config_invalid(self):
        """
        Tests oci notify configuration with an invalid notification topic.

        Returns
        -------
            No return value.
        """
        cmd = [self.oci_notify, 'config', self.invalid_topic]
        try:
            invalid_config_output = _run_step('Config with invalid topic', cmd)
            self.assertIn('is a not valid notification topic id', str(invalid_config_output), 'oci-notify configure with invalid topic failed.')
        except Exception as e:
            self.fail('oci notification with invalid topic failed.')

    def test_config_non_existent(self):
        """
        Tests oci notify configuration with a non-existent notification topic.

        Returns
        -------
            No return value.
        """
        cmd = [self.oci_notify, 'config', self.non_exist_topic]
        try:
            invalid_config_output = _run_step('Config with non existent topic', cmd)
            self.assertIn('notification topic does not exist', str(invalid_config_output), 'oci-notify configure with non existent topic failed.')
        except Exception as e:
            self.fail('oci notification with non existent topic failed.')

    def test_file_message_small(self):
        """
        Test oci notify message with a small file

        Returns
        -------
            No return value
        """
        create_small_file(self.test_file)
        cmd = [self.oci_notify, 'message', '--title', 'small_file_notification', '--file', '/tmp/small_file']
        try:
            small_notification_output = _run_step('Send small file notification', cmd)
            self.assertIn('Published message', str(small_notification_output), 'Sending small file message failed.')
        except Exception as e:
            self.fail('Sending small file message failed.')


    def test_file_message_large(self):
        """
        Test oci notify message with a large file

        Returns
        -------
            No return value
        """
        create_large_file(self.test_file)
        cmd = [self.oci_notify, 'message', '--title', 'large_file_notification', '--file', '/tmp/large_file']
        try:
            large_notification_output = _run_step('Send large file notification', cmd)
            self.assertIn('Published message', str(large_notification_output), 'Sending large file message failed.')
        except Exception as e:
            self.fail('Sending large file message failed.')

    def test_text_message_small(self):
        """
        Test oci notify message with a large file

        Returns
        -------
            No return value
        """
        small_text = self.valid_topic
        cmd = [self.oci_notify, 'message', '--title', 'small_text_notification', '--file', small_text]
        try:
            small_text_output = _run_step('Send small text notification', cmd)
            self.assertIn('Published message', str(small_text_output), 'Sending small text message failed.')
        except Exception as e:
            self.fail('Sending small text message failed.')

    def test_text_message_large(self):
        """
        Test oci notify message with a large file

        Returns
        -------
            No return value
        """
        text = '1234567890'
        large_text = ''
        for _ in range(15):
            large_text += text
        cmd = [self.oci_notify, 'message', '--title', 'large_text_notification', '--file', large_text]
        try:
            large_text_output = _run_step('Send large text notification', cmd)
            self.assertIn('Published message', str(large_text_output), 'Sending large text message failed.')
        except Exception as e:
            self.fail('Sending large text message failed.')

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOciNotify)
    unittest.TextTestRunner().run(suite)
