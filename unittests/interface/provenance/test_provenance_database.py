# Copyright (c) 2021 The University of Manchester
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from testfixtures.logcapture import LogCapture
import unittest
from spinn_utilities.config_holder import set_config
from spinn_front_end_common.interface.config_setup import unittest_setup
from spinn_front_end_common.interface.provenance import (
    ProvenanceWriter, ProvenanceReader)
from spinn_front_end_common.utilities.utility_objs import ProvenanceDataItem


class TestProvenanceDatabase(unittest.TestCase):

    def setUp(self):
        unittest_setup()

    def test_create(self):
        ProvenanceWriter()
        ProvenanceWriter()

    def as_set(self, items):
        results = set()
        for item in items:
            results.add(
                ("/".join(item.names[:-1]), item.names[-1], item.value))
        return results

    def test_insert_items1(self):
        a = ProvenanceDataItem(["foo", "bar for 1,2", "gamma"], 75)
        b = ProvenanceDataItem(["foo", "alpha for 1,2", "gamma"], 100)
        items = [a, b]
        with ProvenanceWriter() as db:
            db.insert_items(items)
        data = set(ProvenanceReader().get_provenace_items())
        items_set = self.as_set(items)
        self.assertSetEqual(data, items_set)

    def test_insert_items2(self):
        a = ProvenanceDataItem(["foo", "bar for 1,2", "gamma"], 75)
        b = ProvenanceDataItem(["foo", "alpha for 1,2", "gamma"], 100)
        items = [a, b]
        with ProvenanceWriter() as db:
            db.insert_item(["foo", "bar for 1,2", "gamma"], 75)
            db.insert_item(["foo", "alpha for 1,2", "gamma"], 100)
        data = set(ProvenanceReader().get_provenace_items())
        items_set = self.as_set(items)
        self.assertSetEqual(data, items_set)


    def test_version(self):
        with ProvenanceWriter() as db:
            db.insert_version("spinn_utilities_version", "1!6.0.1")
            db.insert_version("numpy_version", "1.17.4")
        data = ProvenanceReader().run_query("select * from version_provenance")
        versions = [
            (1, 'spinn_utilities_version', '1!6.0.1'),
            (2, 'numpy_version', '1.17.4')]
        self.assertListEqual(data, versions)

    def test_timings(self):
        with ProvenanceWriter() as db:
            db.insert_timing("mapping", "compressor", 12)
            db.insert_timing("mapping", "router", 123)
            db.insert_timing("execute", "run", 134, "A message")
            db.insert_timing("execute", "run", 344)
            db.insert_timing("execute", "clear", 4)
        reader = ProvenanceReader()
        data = reader.get_timer_sums_by_category("mapping")
        self.assertEqual(12 + 123, data)
        data = reader.get_timer_sums_by_category("execute")
        self.assertEqual(134 + 344 + 4, data)
        data = reader.get_timer_sums_by_category("bacon")
        self.assertIsNone(data)
        data = reader.get_timer_sum_by_algorithm("router")
        self.assertEqual(123, data)
        data = reader.get_timer_sum_by_algorithm("clear")
        self.assertEqual(4, data)
        data = reader.get_timer_sum_by_algorithm("junk")
        self.assertIsNone(data)

    def test_other(self):
        with ProvenanceWriter() as db:
            db.insert_other("foo", "bar", 12)

    def test_router(self):
        with ProvenanceWriter() as db:
            db.insert_router(1, 3, "des1", 34, True)
            db.insert_router(1, 2, "des1", 45, True, "What message")
            db.insert_router(1, 3, "des2", 67, True)
            db.insert_router(1, 3, "des1", 48, True)
            db.insert_router(5, 5, "des1", 48, False)
        reader = ProvenanceReader()
        data = set(reader.get_router_by_chip("des1"))
        chip_set = {(1, 3, 34), (1, 2, 45), (1, 3, 48), (5, 5, 48)}
        self.assertSetEqual(data, chip_set)
        data = reader.get_router_by_chip("junk")
        self.assertEqual(0, len(data))

    def test_monitor(self):
        with ProvenanceWriter() as db:
            db.insert_monitor(1, 3, "des1", 34)
            db.insert_monitor(1, 2, "des1", 45, "What message")
            db.insert_monitor(1, 3, "des2", 67)
            db.insert_monitor(1, 3, "des1", 48)
        reader = ProvenanceReader()
        data = set(reader.get_monitor_by_chip("des1"))
        chip_set = {(1, 3, 34), (1, 2, 45), (1, 3, 48)}
        self.assertSetEqual(data, chip_set)
        data = reader.get_monitor_by_chip("junk")
        self.assertEqual(0, len(data))

    def test_cores(self):
        with ProvenanceWriter() as db:
            db.insert_core(1, 3, 2, "des1", 34)
            db.insert_core(1, 2, 3, "des1", 45, "ignore me")
            db.insert_core(1, 3, 2, "des2", 67)
            db.insert_core(1, 3, 1, "des1", 48)

    def test_core_name(self):
        with ProvenanceWriter() as db:
            db.add_core_name(1, 3, 2, "first_core")
            db.add_core_name(1, 3, 3, "second_core")
            db.add_core_name(1, 3, 2, "first_core")
            db.add_core_name(1, 3, 2, "new_name is ignored")
        reader = ProvenanceReader()
        data = reader.run_query("Select * from core_mapping")
        self.assertEqual(2, len(data))

    def test_messages(self):
        set_config("Reports", "provenance_report_cutoff", 3)
        with LogCapture() as lc:
            with ProvenanceWriter() as db:
                db.insert_report("een")
                db.insert_report(None)
                db.insert_report("")
                db.insert_report("twee")
                db.insert_report("drie")
                db.insert_report("vier")
            self.assertEqual(3, len(lc.records))

        reader = ProvenanceReader()
        data = reader.messages()
        self.assertEqual(4, len(data))