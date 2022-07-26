#!/bin/python3
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
"""
Installs the latest version of the Packer software, download it from the Hashicorp website.
"""
import os
from zipfile import ZipFile
import sys
from urllib.request import urlopen
import urllib.request
import subprocess
from html.parser import HTMLParser

url_base = 'https://releases.hashicorp.com/packer'
packer_exec = '/usr/local/bin/packer'
os.environ['http_proxy'] = 'http://www-proxy.us.oracle.com:80'
os.environ['https_proxy'] = 'http://www-proxy.us.oracle.com:80'

version = '0.9.0'

class MyHTMLParser(HTMLParser):
    """
    Parse webpage.
    """
    lsVersions = list()

    def handle_starttag(self, startTag, attrs):
        if startTag == 'a':
            for name, value in attrs:
                if name == 'href':
                    if 'packer' in value:
                        self.lsVersions.append(value)


def get_most_recent_packer_version(url):
    """
    Find the latest Packer version.

    Parameters
    ----------
    url: str
        The Hashicorp website.

    Returns
    -------
        str: the most recent packer version.
    """
    parser = MyHTMLParser()
    packer_base = urlopen(url_base)
    parser.feed(str(packer_base.read()))
    packer_version_list = parser.lsVersions
    pure_version_list = list()
    for ver in packer_version_list:
        pure_version_list.append(ver.split('/')[2])
    version_dict = dict()
    for ver in pure_version_list:
        ver_nb = 0
        for ver_x in ver.split('.'):
            ver_nb = ver_nb*100 + int(ver_x)
        version_dict[ver_nb] = ver
    return '%s' % sorted(version_dict.items(), reverse=True)[0][1]


def download_file(url, destination):
    """
    Download a file using an url.

    Parameters
    ----------
    url: str
        The file locator.
    destination: str
        Full path of destination.

    Returns
    -------
        bool: True on success, False on failure.
    """
    try:
        with urllib.request.urlopen(url) as response, open(destination, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
            return True
    except Exception as e:
        print('Failed to download %s: %s' % (url, str(e)))
        return False


def unzip_file(zipped_file):
    """
    Unzip a zipfile in /tmp.

    Parameters
    ----------
    zipped_file: str
        Zipped file name.

    Returns
    -------
        bool: True on success, False on failure.
    """
    try:
        zipfile = ZipFile(zipped_file, 'r')
        zipfile.extractall('/tmp')
        zipfile.close()
        return True
    except Exception as e:
        print('Failed to unzip %s; %s' % (zipped_file, str(e)))
        return False


def remove_file(somepath):
    """
    Delete the packer executable from /usr/local/bin.

    Parameters
    ----------
    somepepath: str
        File path to be removed.

    Returns
    -------
        bool: True on success, False on failure.
    """
    remove_cmd = ['sudo', 'rm', '-rf', somepath]
    try:
        if os.path.exists(packer_exec):
            proc = subprocess.Popen(remove_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            print('%s does not exists.' % packer_exec)
        return  True
    except Exception as e:
        print('Failed to remove %s; %s' % (packer_exec, str(e)))
        return False


def install_usrlocalbin(from_path, exec_file):
    """
    Install a file in /usr/local/bin.

    Parameters
    ----------
    from_path: str
        Source directory.
    exec_file: str
        File name.

    Returns
    -------
        bool: True on succes, False on failure.
    """
    install_cmd = ['sudo', '-S', 'install', '-m', '755', '%s/%s' % (from_path, exec_file), '/usr/local/bin']
    try:
        proc = subprocess.Popen(install_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception as e:
        print('Failed to install %s: %s' % (exec_file, str(e)))
        return False


def main():
    """
    Install most recent version of Packer software.

    Returns
    -------
        int: 0 on success, 1 on failure.
    """
    print('Running %s version %s' % (sys.argv[0], version))
    packer_version = get_most_recent_packer_version(url_base)
    print('Most recent version of Packer: %s' % packer_version)
    packer_zip = 'packer_%s_linux_amd64.zip' % packer_version
    packer_url = url_base + '/%s/%s' %  (packer_version,packer_zip)
    print('URL for Packer distro:         %s' % packer_url)
    if download_file(packer_url, packer_zip):
        print('Successfully downloaded:       %s' % packer_url)
    else:
        print('Failed to download             %s' % packer_url)
        sys.exit(1)
    if unzip_file(packer_zip):
        print('Sucessfully unzipped           %s' % packer_zip)
    else:
        print('Failed to unzip                %s' % packer_zip)
        sys.exit(1)
    if remove_file(packer_exec):
        print('Successfully removed           %s' % packer_exec)
    else:
        print('Failed to remove               %s' % packer_exec)
        sys.exit(1)
    if install_usrlocalbin('/tmp', 'packer'):
        print('Successfully installed         %s' % packer_exec)
    else:
        print('Failed to install              %s' % packer_exec)
        sys.exit(1)
    if remove_file(packer_zip):
        print('Successfully removed           %s' % packer_zip)
    else:
        print('Failed to remove               %s' % packer_zip)
    sys.exit(0)


if __name__ == "__main__":
    sys.exit(main())
