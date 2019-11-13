# #!/usr/bin/env python

# oci-utils
#
# Copyright (c) 2019 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

"""
Module to handle VMDK formatted virtual disk images.
"""
import logging
import os
import re
import struct

from oci_migrate.migrate import gen_tools
from oci_migrate.migrate.imgdevice import DeviceData
from oci_migrate.migrate.migrate_utils import gigabyte as gigabyte
from oci_migrate.migrate.migrate_utils import OciMigrateException

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
                            'prereq': {'MAX_IMG_SIZE_GB': 300.0,
                                       'vmdk_supported_types':
                                           ['monolithicSparse',
                                            'streamOptimized']}}}


def test():
    """
    Placeholder

    Returns
    -------
        No return value
    """
    gen_tools.result_msg(msg=__name__)


class VmdkHead(DeviceData):
    """
    Class to analyse header of vmdk image file.

    Attributes
    ----------
        filename: str
            The full path of the vmdk image file.
        logger: logger
            The logger.
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
    _logger = logging.getLogger('oci-image-migrate.VmdkHead')

    def __init__(self, filename, logger=None):
        """
        Initialisation of the vmdk header analysis.

        Parameters
        ----------
        filename: str
            Full path of the qcow2 image file.
        logger: loggername
            The logging specification.
        """
        super(VmdkHead, self).__init__(filename, logger)
        head_size = struct.calcsize(VmdkHead.vmdkhead_fmt)

        self._logger.info('vmdk header size: %d bytes' % head_size)

        try:
            with open(self.fn, 'rb') as f:
                head_bin = f.read(head_size)
                self._logger.debug('%s header successfully read' % self.fn)
        except Exception as e:
            self._logger.critical(
                'Failed to read header of %s: %s' % (self.fn, str(e)))
            raise OciMigrateException(
                'Failed to read the header of %s: %s' % (self.fn, str(e)))

        vmdkheader = struct.unpack(VmdkHead.vmdkhead_fmt, head_bin)

        try:
            with open(self.fn, 'rb') as f:
                f.seek(512)
                head_descr = [it for it in f.read(1024).splitlines() if
                              '=' in it]
        except Exception as e:
            self._logger.critical(
                'Failed to read description of %s: %s' % (self.fn, str(e)))
            raise OciMigrateException(
                'Failed to read the description  of %s: %s' % (self.fn, str(e)))

        self.stat = os.stat(self.fn)
        self.img_tag = os.path.splitext(os.path.split(self.fn)[1])[0]
        self.vmdkhead_dict = dict((name[2], vmdkheader[i]) for i, name in
                                  enumerate(VmdkHead.header0_structure))
        self.vmdkdesc_dict = dict(
            [re.sub(r'"', '', kv).split('=') for kv in head_descr])
        self.img_header = dict()
        self.img_header['head'] = self.vmdkhead_dict
        self.img_header['desc'] = self.vmdkdesc_dict
        gen_tools.result_msg(msg='Got image %s header' % filename, result=True)

    def show_header(self):
        """
        Lists the header contents formatted.

        Returns
        -------
            No return value.
        """
        gen_tools.result_msg(msg='\n  %30s\n  %30s   %30s'
                                 % ('VMDK file header data', '-' * 30, '-' * 30),
                             result=False)
        for f in VmdkHead.header0_structure:
            gen_tools.result_msg(msg=''.join(['  %30s : ' % f[2], f[1]
                                              % self.vmdkhead_dict[f[2]]]),
                                 result=False)
        gen_tools.result_msg(msg='\n  %30s\n  %30s   %30s'
                                 % ('VMDK file descriptor data',
                                    '-' * 30, '-' * 30),
                             result=False)
        for k in sorted(self.vmdkdesc_dict):
            gen_tools.result_msg(msg='  %30s : %-30s'
                                     % (k, self.vmdkdesc_dict[k]), result=False)

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

        gen_tools.result_msg(msg='Image size: physical %10.2f GB, '
                                 'logical %10.2f GB'
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
        self._logger.debug('Image data: %s' % self.fn)
        #
        # initialise the dictionary for the image data
        self.img_info['img_name'] = self.fn
        self.img_info['img_type'] = 'VMDK'
        self.img_info['img_header'] = self.img_header
        self.img_info['img_size'] = self.image_size()

        #
        # mount the image using the nbd
        try:
            result = self.handle_image()
        except Exception as e:
            self._logger.critical('error %s' % str(e))
            raise OciMigrateException(str(e))
        return result, self.img_info

    def type_specific_prereq_test(self):
        """
        Verify the prerequisites specific for the image type from the header.

        Returns
        -------
            bool: True or False.
            str : Message
        """
        prereqs = format_data['4b444d56']['prereq']
        failmsg = ''
        #
        # size:
        thispass = True
        if self.img_info['img_size']['logical'] > prereqs['MAX_IMG_SIZE_GB']:
            self._logger.critical('Image size %8.2f GB exceeds maximum '
                                  'allowed %8.2f GB' %
                                  (prereqs['MAX_IMG_SIZE_GB'],
                                   self.img_info['img_size']['logical']))
            failmsg += '\n  Image size %8.2f GB exceeds maximum allowed ' \
                       '%8.2f GB' % (prereqs['MAX_IMG_SIZE_GB'],
                                     self.img_info['img_size']['logical'])
            thispass = False
        else:
            failmsg += '\n  Image size %8.2f GB meets maximum allowed size ' \
                       'of %8.2f GB' % (self.img_info['img_size']['logical'],
                                        prereqs['MAX_IMG_SIZE_GB'])

        #
        # type:
        if self.img_header['desc']['createType'] \
                not in prereqs['vmdk_supported_types']:
            self._logger.critical(
                'Image type %s is not in the supported type list: %s' %
                (self.img_header['desc']['createType'],
                 prereqs['vmdk_supported_types']))
            failmsg += 'Image type %s is not in the supported type list: %s' %\
                       (self.img_header['desc']['createType'],
                        prereqs['vmdk_supported_types'])
            thispass = False
        else:
            failmsg += '  Image type %s is in the supported type list: %s' \
                       % (self.img_header['desc']['createType'],
                          prereqs['vmdk_supported_types'])

        return thispass, failmsg
