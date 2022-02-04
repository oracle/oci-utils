#!/bin/python3
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Upload an (image) file to object storage.
"""
import argparse
import logging
import os
import sys
import termios
import threading
import time
import tty
from datetime import datetime

import oci

# logging.basicConfig(level=logging.DEBUG, filename='/tmp/upload_image.log', filemode='w', format='%(asctime)s - %(name)s - %(level)s : %(message)s', datefmt='%d-%b-%y %H:%M:%S')
_logger = logging.getLogger(__name__)

def parse_args():
    """
    Parse the command line arguments and return an object representing the
    command line as returned by the argparse's parse-args().
    arguments:
    -i|--image-name <image name>; mandatory.
    -b|--bucket-name <bucket name>; mandatory.
    -o|--output-name <output image name>; optional
    -y|--yes suppose the answer YES to all Y/N questions

    Returns
    -------
        The command line namespace.
    """
    parser = argparse.ArgumentParser(description='Utility to upload a file to object storage of '
                                                 'the Oracle Cloud Infrastructure.')
    #
    parser.add_argument('-p', '--profile',
                        action='store',
                        dest='profile',
                        type=str,
                        default='DEFAULT',
                        help='The profile from the config file, the default is DEFAULT.')
    parser.add_argument('-c', '--config-file',
                        action='store',
                        dest='config_file',
                        type=argparse.FileType('r'),
                        default='~/.oci/config',
                        help='The oci config file, the default = ~/.oci/config.')
    parser.add_argument('-f', '--file-name',
                        action='store',
                        dest='file_name',
                        type=argparse.FileType('r'),
                        required=True,
                        help='The file name to be uploaded.')
    parser.add_argument('-b', '--bucket-name',
                        action='store',
                        dest='bucket_name',
                        required=True,
                        help='The name of the object storage.')
    parser.add_argument('-o', '--output-name',
                        action='store',
                        dest='output_name',
                        help='The name the image will be stored in the object storage.')
    parser.add_argument('--yes', '-y',
                        action='store_true',
                        dest='yes_flag',
                        default=False,
                        help='Answer YES to all y/n questions.')
    parser._optionals.title = 'Arguments'
    args = parser.parse_args()
    if args.output_name is None:
        args.output_name = args.image_name
    return args


def terminal_dimension():
    """
    Collect the dimension of the terminal window.

    Returns
    -------
        tuple: (nb rows, nb colums)
    """
    try:
        terminal_size = os.get_terminal_size()
        return terminal_size.lines, terminal_size.columns
    except Exception as e:
        #
        # fail to get terminal dimension, because not connected to terminal?
        # returning dummy
        print('  Failed to determine terminal dimensions: %s; falling back to 80x80'% str(e))
        return 80, 80


class ProgressBar(threading.Thread):
    """
    Class to generate an indication of progress, does not actually
    measure real progress, just shows the process is not hanging.
    """
    _default_progress_chars = ['#']

    def __init__(self, bar_length, progress_interval, progress_chars=None):
        """
        Progressbar initialisation.

        Parameters:
        ----------
        bar_length: int
            Length of the progress bar.
        progress_interval: float
            Interval in sec of change.
        progress_chars: list
            List of char or str to use; the list is mirrored before use.
        """
        self._stopthread = threading.Event()
        threading.Thread.__init__(self)
        #
        # length of variable progress bar
        self._bar_len = bar_length - 14
        #
        # progress interval in sec
        self._prog_int = progress_interval
        if progress_chars is None:
            self._prog_chars = self._default_progress_chars
        else:
            self._prog_chars = progress_chars
        #
        # nb progress symbols
        self._nb_prog_chars = len(self._prog_chars)
        #
        # the max len of the progress symbols, should be all equal
        self._prog_len = 0
        for s in self._prog_chars:
            ls = len(s)
            if ls > self._prog_len:
                self._prog_len = ls
        #
        # nb iterations per bar
        self._cntr = self._bar_len - self._prog_len + 1
        self.stop_the_progress_bar = False

    def run(self):
        """
        Execute the progress bar.

        Returns
        -------
            No return value.
        """
        #
        # counter in progress bar symbols
        i = 0
        j = i % self._nb_prog_chars
        #
        # counter in bar
        k = 0
        sys.stdout.write('\n')
        sys.stdout.flush()
        start_time = datetime.now()
        while True:
            now_time = datetime.now()
            delta_time = now_time - start_time
            hrs, rest = divmod(delta_time.seconds, 3600)
            mins, secs = divmod(rest, 60)
            pbar = '  ' \
                   + '%02d:%02d:%02d' % (hrs, mins, secs) \
                   + ' [' \
                   + ' '*k \
                   + self._prog_chars[j] \
                   + ' ' * (self._bar_len - k - self._prog_len) \
                   + ']'
            sys.stdout.write('\r%s' % pbar)
            sys.stdout.flush()
            k += 1
            if k == self._cntr:
                k = 0
                i += 1
                j = i % self._nb_prog_chars
            time.sleep(self._prog_int)
            if self.stop_the_progress_bar:
                now_time = datetime.now()
                delta_time = now_time - start_time
                hrs, rest = divmod(delta_time.seconds, 3600)
                mins, secs = divmod(rest, 60)
                pbar = '  ' \
                    + '%02d:%02d:%02d' % (hrs, mins, secs) \
                    + ' [ ' \
                    + ' %s' % self._prog_chars[j] \
                    + ' done ]' \
                    + (self._bar_len - self._prog_len - 5)*' '
                sys.stdout.write('\r%s\n' % pbar)
                sys.stdout.flush()
                break

    def stop(self):
        """
        Notify thread to stop the progress bar.

        Returns
        -------
            No return value.
        """
        self.stop_the_progress_bar = True
        self.join()
        sys.stdout.write('\n')
        sys.stdout.flush()

    def join(self, timeout=None):
        """
        Terminate the thread.

        Parameters
        ----------
        timeout: float
            Time to wait if set.

        Returns
        -------
            No return value.
        """
        self._stopthread.set()
        threading.Thread.join(self, timeout)


def _getch():
    """
    Read a single keypress from stdin.

    Returns
    -------
        The resulting character.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def read_yn(prompt, yn=True, waitenter=False, suppose_yes=False):
    """
    Read yes or no form stdin, No being the default.

    Parameters
    ----------
        prompt: str
            The message.
        yn: bool
            Add (y/N) to the prompt if True.
        waitenter: bool
            Wait for the enter key pressed if True, proceed immediately
            otherwise.
        suppose_yes: bool
            if True, consider the answer is yes.
    Returns
    -------
        bool: True on yes, False otherwise.
    """
    yn_prompt = prompt + ' '
    #
    # if yes is supposed, write prompt and return True.
    if suppose_yes:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        return True
    #
    # add y/N to prompt if necessary.
    if yn:
        yn_prompt += ' (y/N) '
    #
    # if wait is set, wait for return key.
    if waitenter:
        resp_len = 0
        while resp_len == 0:
            resp = input(yn_prompt).lstrip()
            resp_len = len(resp)
        yn = list(resp)[0]
    #
    # if wait is not set, proceed on any key pressed.
    else:
        _ = sys.stdout.write(yn_prompt)
        sys.stdout.flush()
        yn = _getch()

    sys.stdout.write('\n')
    return bool(yn.upper() == 'Y')


def get_oci_config(configfile, profile):
    """
    Read the oci-sdk configuration data from file.

    configfile: str
        The oci config file.
    profile: str
        The oci profile.

    Returns
    -------
        dict: The configuration on success, None otherwise.
    """
    try:
        config = oci.config.from_file(file_location=configfile, profile_name=profile)
        return config
    except oci.exceptions.ProfileNotFound as notfound:
        print('  OCI configuration file %s not found.', configfile)
    except oci.exceptions.ConfigFileNotFound as notfound:
        print('  OCI profile %s not found.', profile)
    except Exception as e:
        print('  Failed to load oci configuration data: %s' % str(e))
    return None


def bucket_exists(bucket_name, config):
    """
    Verify if the object storage exists.

    Parameters
    ----------
    bucket_name: str
        The object storage name.
    config: dict
        The oci-sdk configuration.

    Returns
    -------
        bool: True on success, False on failure.
    """
    try:
        object_storage_client = oci.object_storage.ObjectStorageClient(config)
        namespace = object_storage_client.get_namespace().data
        bucket_data = object_storage_client.get_bucket(namespace_name=namespace, bucket_name=bucket_name)
        print('  Bucket %s exists in namespace %s.' % (bucket_data.data.name, bucket_data.data.namespace))
        return True
    except Exception as e:
        if hasattr(e, 'message'):
            print('  Failed to locate bucket %s: %s' % (bucket_name, e.message))
        else:
            print('  Failed to locate bucket %s' % bucket_name)
        return False


def object_exists(object_name, bucket_name, config):
    """
    Verify if object is present in the object storage.

    Parameters
    ----------
    object_name: str
        The object name.
    bucket_name: str
        The bucket name.
    config: dict
        The oci-sdk configuration.

    Returns
    -------
        bool: True on success, False on failure.
    """
    try:
        object_storage_client = oci.object_storage.ObjectStorageClient(config)
        namespace = object_storage_client.get_namespace().data
        object_list_data = object_storage_client.list_objects(namespace_name=namespace, bucket_name=bucket_name)
    except Exception as e:
        print('  Failed to get contents of %s: %s' % (bucket_name, str(e)))
        return False
    for obj in object_list_data.data.objects:
        if obj.name == object_name:
            print('  %s is already present in %s.' % (object_name, bucket_name))
            return False
    print('  %s is not yet present in %s.' % (object_name, bucket_name))
    return True


def upload_object(object_name, output_name, bucket_name, config):
    """
    Upload object to bucket as output.

    Parameters
    ----------
    object_name: str
        The path of the object to upload.
    output_name: str
        The name the object is stored in the object storage.
    bucket_name: str
        The name of the object storage.
    config: dict
        The oci-sdk configuration.

    Returns
    -------
        bool: True on success, False on failure.
    """
    try:
        object_storage_client = oci.object_storage.ObjectStorageClient(config)
        namespace_name = object_storage_client.get_namespace().data
        upload_manager = oci.object_storage.UploadManager(object_storage_client=object_storage_client, allow_parallel_uploads=True, parallel_process_count=10)
        response = upload_manager.upload_file(namespace_name=namespace_name, bucket_name=bucket_name, file_path=object_name, object_name=output_name)
        print('  Successfully uploaded %s to %s: %s' % (object_name, bucket_name, response.data))
        return True
    except Exception as e:
        print('  Failed to upload %s to %s: %s' % (object_name, bucket_name, str(e)))
        _logger.error('%s' % str(e), stack_info=True, exc_info=True)
        return False


def main():
    """
    Main

    Returns
    -------
    int: 0 on success, 1 on failure.
    """
    os.environ['LC_ALL'] = 'en_US.UTF8'
    args = parse_args()
    #
    sdk_config = get_oci_config(args.config_file, args.profile)
    if sdk_config is None:
        sys.exit(1)
    #
    file_path = args.file_name.name
    if not (os.path.isfile(file_path) and os.access(file_path, os.R_OK)):
        print('  %s does not exists or os not readable.' % file_path)
        sys.exit(1)
    #
    bucket_name = args.bucket_name
    if not bucket_exists(bucket_name, sdk_config):
        sys.exit(1)
    #
    if args.output_name:
        output_name = args.output_name
    else:
        output_name = os.path.splitext(os.path.basename(file_path))[0]
    #
    yes_flag = args.yes_flag
    #
    if not object_exists(output_name, bucket_name, sdk_config):
        sys.exit(1)
    #
    if not read_yn('\n  Agree to proceed uploading %s to %s as %s?' % (file_path, bucket_name, output_name),
                   waitenter=True,
                   suppose_yes=yes_flag):
        sys.exit('\n  Exiting.')
    #
    try:
        _, nb_columns = terminal_dimension()
        upload_progress = ProgressBar(nb_columns, 0.2, progress_chars=['uploading %s' % output_name])
        upload_progress.start()
        if upload_object(file_path, output_name, bucket_name, sdk_config):
            pass
        upload_progress.stop()
    except Exception as e:
        print('  Upload failed: %s' % str(e))


if __name__ == "__main__":
    sys.exit(main())
