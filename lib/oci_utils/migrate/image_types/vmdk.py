# oci-utils
#
# Copyright (c) 2019, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle VMDK formatted virtual disk images.
"""
import logging
import os
import re
import struct

from oci_utils.migrate import migrate_data
from oci_utils.migrate import read_yn
from oci_utils.migrate import result_msg
from oci_utils.migrate.exception import OciMigrateException
from oci_utils.migrate.imgdevice import DeviceData
from oci_utils.migrate.migrate_data import gigabyte

"""
typedef uint64 SectorType;
typedef uint8 Bool;
typedef struct SparseExtentHeader {
    uint32       magicNumber;
    uint32       version;
    uint32       flags;
    SectorType   capacity;
    SectorType   grainSize;
    SectorType   descriptorOffset;
    SectorType   descriptorSize;
    uint32       numGTEsPerGT;
    SectorType   rgdOffset;
    SectorType   gdOffset;
    SectorType   overHead;
    Bool         uncleanShutdown;
    char         singleEndLineChar;
    char         nonEndLineChar;
    char         doubleEndLineChar1;
    char         doubleEndLineChar2;
    uint16       compressAlgorithm;
    uint8        pad[433];
} SparseExtentHeader
"""

format_data = {'4b444d56': {'name': 'vmdk',
                            'module': 'vmdk',
                            'clazz': 'VmdkHead',
                            'prereq': {'MAX_IMG_SIZE_GB': 400.0,
                                       'vmdk_supported_types': ['monolithicSparse', 'streamOptimized']}}}

_logger = logging.getLogger('oci-utils.vmdk')


class VmdkHead(DeviceData):
    """
    Class to analyse header of vmdk image file.

    Attributes
    ----------
        filename: str
            The full path of the vmdk image file.
        stat: tuple
            The image file stat data.
        img_tag: str
            The bare file name.
        vmdkhead_dict: dict
            The VMDK file header as a dictionary.
        vmdkdesc_dict: dict
            The VMDK file description as a dictionary.
    """
    #
    Bool = '?'
    char = 'B'        # 1 byte char
    uint8 = 'B'       # 1 byte unsigned int
    uint16 = 'H'      # 16bit unsigned int
    uint32 = 'I'      # 32bit unsigned int
    uint64 = 'Q'      # 64bit unsigned long
    SectorType = 'Q'  # 64bit unsigned long
    string = 's'      # string
    #
    # vmdk header0 definition:
    header0_structure = [[uint32,     '%#x', 'magic'],
                         [uint32,     '%d',  'version'],
                         [uint32,     '%#x', 'flags'],
                         [SectorType, '%d',  'capacity'],
                         [SectorType, '%d',  'grainSize'],
                         [SectorType, '%d',  'descriptorOffset'],
                         [SectorType, '%d',  'descriptorSize'],
                         [uint32,     '%d',  'numGTEsPerGT'],
                         [SectorType, '%d',  'rgdOffset'],
                         [SectorType, '%d',  'gdOffset'],
                         [SectorType, '%d',  'overHead'],
                         [Bool,       '%#x', 'uncleanShutdown'],
                         [char,       '%#x', 'singleEndLineChar'],
                         [char,       '%#x', 'nonEndLineChar'],
                         [char,       '%#x', 'doubleEndLineChar1'],
                         [char,       '%#x', 'doubleEndLineChar2'],
                         [uint16,     '%s',  'compressAlgorithm'],
                         [uint8,      '%#x', 'pad'] * 433]
    #
    # struct format string
    vmdkhead_fmt = '<' + ''.join(f[0] for f in header0_structure)
    head_size = struct.calcsize(vmdkhead_fmt)
    _logger = logging.getLogger('oci-utils.vmdk')

    streamoptimized_msg = '\n  Although streamOptimized is a supported format, ' \
                          'issues might arise during or after mounting the ' \
                          'image file. It is advised\n  to convert the image ' \
                          'file to monolithicSparse by running ' \
                          '[qemu-img convert -O vmdk thisimage.vmdk newimage.vmdk]\n'

    def __init__(self, filename):
        """
        Initialisation of the vmdk header analysis.

        Parameters
        ----------
        filename: str
            Full path of the vmdk image file.
        """
        super().__init__(filename)
        _logger.debug('VMDK header size: %d bytes', self.head_size)

        try:
            with open(self._fn, 'rb') as f:
                head_bin = f.read(self.head_size)
                _logger.debug('%s header successfully read', self._fn)
        except Exception as e:
            _logger.critical('   Failed to read header of %s: %s', self._fn, str(e))
            raise OciMigrateException('Failed to read the header of %s: %s' % self._fn) from e

        vmdkheader = struct.unpack(VmdkHead.vmdkhead_fmt, head_bin)

        try:
            with open(self._fn, 'rb') as f:
                f.seek(512)
                head_descr = [it for
                              it in f.read(1024).decode('utf-8').splitlines()
                              if '=' in it]
        except Exception as e:
            _logger.critical('   Failed to read description of %s: %s', self._fn, str(e))
            raise OciMigrateException('Failed to read the description  of %s: %s' % self._fn) from e

        self.stat = os.stat(self._fn)
        self.img_tag = os.path.splitext(os.path.split(self._fn)[1])[0]
        self.vmdkhead_dict = dict((name[2], vmdkheader[i]) for i, name in
                                  enumerate(VmdkHead.header0_structure))
        self.vmdkdesc_dict = dict(
            [re.sub(r'"', '', kv).split('=') for kv in head_descr])
        self.img_header = dict()
        self.img_header['head'] = self.vmdkhead_dict
        self.img_header['desc'] = self.vmdkdesc_dict
        result_msg(msg='Got image %s header' % filename, result=False)

    def show_header(self):
        """
        Lists the header contents formatted.

        Returns
        -------
            No return value.
        """
        result_msg(msg='\n  %30s\n  %30s   %30s' % ('VMDK file header data', '-' * 30, '-' * 30), result=False)
        for f in VmdkHead.header0_structure:
            result_msg(msg=''.join(['  %30s : ' % f[2], f[1] % self.vmdkhead_dict[f[2]]]), result=False)
        result_msg(msg='\n  %30s\n  %30s   %30s' % ('VMDK file descriptor data', '-' * 30, '-' * 30), result=False)
        for k in sorted(self.vmdkdesc_dict):
            result_msg(msg='  %30s : %-30s' % (k, self.vmdkdesc_dict[k]), result=False)

    def image_size(self):
        """
        Get the size of the image file.

        Returns
        -------
            dict:
                physical file size, logical file size
        """
        img_sz = {'physical': float(self.stat.st_size)/gigabyte,
                  'logical': float(self.vmdkhead_dict['capacity']*512)/gigabyte}

        result_msg(
            msg='Image size: physical %10.2f GB, logical %10.2f GB'
                % (img_sz['physical'], img_sz['logical']),
            result=True)
        return img_sz

    def image_supported(self, image_defs):
        """
        Verifies if the image file is supported for migration to the Oracle
        cloud infrastructure.

        Parameters
        ----------
            image_defs: dict
                The predefined data and prerequisits for this type of image.
        Returns
        -------
            bool: True on success, False otherwise.
            str:  Eventual message on success or failure.
        """
        _logger.debug('__ Image support.')
        supp = True
        prerequisites = image_defs['prereq']
        msg = ''
        if self.vmdkdesc_dict['createType'] \
                in prerequisites['vmdk_supported_types']:
            msg += 'Type is %s, OK.\n' % self.vmdkdesc_dict['createType']
        else:
            msg += 'Type %s is not supported.\n' % \
                   self.vmdkdesc_dict['createType']
            supp = False
        sizes = self.image_size()
        if sizes['logical'] > prerequisites['MAX_IMG_SIZE_GB']:
            msg += 'Size of the image %.2f GB exceeds the maximum allowed ' \
                   'size of %.2f GB.\n' % \
                   (sizes['logical'], prerequisites['MAX_IMG_SIZE_GB'])
            supp = False
        else:
            msg += 'Image size of %.2f GB below maximum allowed size ' \
                   'of %.2f GB, OK.\n' % \
                   (sizes['logical'], prerequisites['MAX_IMG_SIZE_GB'])
        return supp, msg

    def image_data(self):
        """
        Collect data about contents of the image file.

        Returns
        -------
            bool: True on success, False otherwise;
            dict: The image data.
        """
        _logger.debug('Image data: %s', self._fn)
        #
        # initialise the dictionary for the image data
        self.image_info['img_name'] = self._fn
        self.image_info['img_type'] = 'VMDK'
        self.image_info['img_header'] = self.img_header
        self.image_info['img_size'] = self.image_size()

        #
        # mount the image using the nbd
        try:
            result = self.handle_image()
        except Exception as e:
            _logger.critical('   Error %s', str(e))
            raise OciMigrateException('Failed') from e
        return result, self.image_info

    def type_specific_prereq_test(self):
        """
        Verify the prerequisites specific for the image type from the header.

        Returns
        -------
            bool: True or False.
            str : Message
        """
        _logger.debug('__ Specific prerequisites.')
        prereqs = format_data['4b444d56']['prereq']
        failmsg = ''
        #
        # size
        passed_requirement = True
        if self.image_info['img_size']['logical'] > prereqs['MAX_IMG_SIZE_GB']:
            _logger.critical('   Image size %8.2f GB exceeds maximum allowed %8.2f GB',
                             prereqs['MAX_IMG_SIZE_GB'], self.image_info['img_size']['logical'])
            failmsg += '\n  Image size %8.2f GB exceeds maximum allowed ' \
                       '%8.2f GB' % (prereqs['MAX_IMG_SIZE_GB'],
                                     self.image_info['img_size']['logical'])
            passed_requirement = False
        else:
            failmsg += '\n  Image size %8.2f GB meets maximum allowed size ' \
                       'of %8.2f GB' % (self.image_info['img_size']['logical'],
                                        prereqs['MAX_IMG_SIZE_GB'])

        #
        # type
        if self.img_header['desc']['createType'] \
                not in prereqs['vmdk_supported_types']:
            _logger.critical('   Image type %s is not in the supported type list: %s',
                             self.img_header['desc']['createType'], prereqs['vmdk_supported_types'])
            failmsg += '\n  Image type %s is not in the supported type list: %s' \
                       % (self.img_header['desc']['createType'], prereqs['vmdk_supported_types'])
            passed_requirement = False
        else:
            failmsg += '\n  Image type %s is in the supported type list: %s' \
                       % (self.img_header['desc']['createType'], prereqs['vmdk_supported_types'])
            #
            # Warning, for now, streamOptimized format will probably cause problems.
            if self.img_header['desc']['createType'] == 'streamOptimized':
                _ = read_yn('  %s\n  Continue' % self.streamoptimized_msg, yn=False, suppose_yes=migrate_data.yes_flag)

        return passed_requirement, failmsg
