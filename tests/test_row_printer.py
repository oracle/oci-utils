# Copyright (c) 2020, 2021 Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown
# at http://oss.oracle.com/licenses/upl.

import os
import unittest
from  oci_utils.impl.row_printer import (TablePrinter, ParsableTextPrinter,CSVPrinter , HtmlPrinter,TextPrinter, JSONPrinter)
from tools.oci_test_case import OciTestCase

os.environ['LC_ALL'] = 'en_US.UTF8'
os.environ['_OCI_UTILS_DEBUG'] = '1'

class foo():
        def attr1(self): return 'john'
        def attr2(self): return 'chris'
        def attr3(self): return 'joe'


_mylist=["john","chris","joe","paul"]
_mylist2=[1,2,3,4,5,6,7]
_mydict={'attr3':"john",'attr2':"chris","attr1":"paul"}
_myfoo=foo()


def _mycallback(cname, instance):
    if cname == 'COL4-1':
        return "CB1@ obj id =%d"%id(instance)
    if cname == 'COL4-2':
        return "CB2@ obj id =%d"%id(instance)


class TestRowPrinter(OciTestCase):
    """ Test around lib/oci_utils/impl/row_printer.py
    """

    def test_text_printer(self):
        tp=TextPrinter(title="mytitle",columns=(['COL1',25,'attr1'],['COL2',10,'attr2'],['COL3',12,'attr3'],['COL4-1',10,_mycallback]))
        tp.printHeader()
        tp.printRow(_mylist)
        tp.printRow(_mylist2)
        tp.printRow(_mydict)
        tp.printRow(_myfoo)
        tp.printKeyValue("myattr","myValue")
        tp.printFooter()
        tp.finish()

    def test_parsable_printer(self):
        tp=ParsableTextPrinter(title="mytitle",columns=(['COL1',25,'attr1'],['COL2',10,'attr2'],['COL3',12,'attr3'],['COL4-1',10,_mycallback]))
        tp.printHeader()
        tp.printRow(_mylist)
        tp.printRow(_mylist2)
        tp.printRow(_mydict)
        tp.printRow(_myfoo)
        tp.printKeyValue("myattr","myValue")
        tp.printFooter()
        tp.finish()

    def test_csv_printer(self):
        tp=CSVPrinter(title="mytitle",columns=(['COL1',25,'attr1'],['COL2',10,'attr2'],['COL3',12,'attr3'],['COL4-1',10,_mycallback]))
        tp.printHeader()
        tp.printRow(_mylist)
        tp.printRow(_mylist2)
        tp.printRow(_mydict)
        tp.printRow(_myfoo)
        tp.printKeyValue("myattr","myValue")
        tp.printFooter()
        tp.finish()

    def test_html_printer(self):
        tp=HtmlPrinter(title="mytitle",columns=(['COL1',25,'attr1'],['COL2',10,'attr2'],['COL3',12,'attr3'],['COL4-1',10,_mycallback]))
        tp.printHeader()
        tp.printRow(_mylist)
        tp.printRow(_mylist2)
        tp.printRow(_mydict)
        tp.printRow(_myfoo)
        tp.printKeyValue("myattr","myValue")
        tp.printFooter()
        tp.finish()

    def test_json_printer(self):
        tp=JSONPrinter(title="mytitle",columns=(['COL1',25,'attr1'],['COL2',10,'attr2'],['COL3',12,'attr3'],['COL4-1',10,_mycallback]))
        tp.printHeader()
        tp.printRow(_mylist)
        tp.printRow(_mylist2)
        tp.printRow(_mydict)
        tp.printRow(_myfoo)
        tp.printKeyValue("myattr","myValue")
        tp.printFooter()
        tp.finish()


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRowPrinter)
    unittest.TextTestRunner().run(suite)