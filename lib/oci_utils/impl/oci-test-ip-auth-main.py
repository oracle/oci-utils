#
# Copyright (c) 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.
#

import sys
import urllib
try:
    import oci as oci_sdk
except ImportError as e:
    print('OCI SDK is not installed: %s.' % str(e))
    sys.exit(1)


def main():
    """
    Test if Instance Principal Authentication is configured correctly.

    Returns
    -------
        int
            0 on success, 1 otherwise.
    """
    url = 'http://169.254.169.254/opc/v2/instance/id'
    try:
        req = urllib.request.Request(url=url)
        req.add_header('Authorization', 'Bearer Oracle')
        response = urllib.request.urlopen(req)
        instance_id = response.readline().decode('utf-8')
        print('\n--- This instance instance_id: %s ---'% instance_id)
    except Exception as e:
        print('Failed to collect instance_id: %s' % str(e))
        sys.exit(1)

    try:
        signer = oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
        identity_client = oci_sdk.identity.IdentityClient(config={}, signer=signer)
        compute_client = oci_sdk.core.compute_client.ComputeClient(config={}, signer=signer)
        instance_data = compute_client.get_instance(instance_id=instance_id).data
        print('--- Successfully verified Instance Principal Authentication on %s. ---' % instance_data.display_name)
        sys.exit(0)
    except Exception as e:
        print('\n--- ERROR --- Unable to authenticate correctly using Instance Principal Authentication '
              'using OCI SDK only. Verify the configuration or switch to Direct Authentication.\n')
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())


