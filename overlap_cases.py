import json
import sys
import unittest
from fractions import Fraction

from grid.geometry import build_geometry
from grid.samples import validate_samples
from ledger.catalog import ReportCatalog
from ledger.history import read_review
from review.assemble import issue_review
from review.contacts import iter_contact_links
from review.groups import build_groups
from review.selection import validate_review_selection
from sheet.evidence import build_sheet_evidence
from sheet.packet import SheetPacket, encode_packet
from sheet.store import read_sheet
from survey.catalog import SurveyOrder
from survey.layout import validate_layout
from tests.fixtures import CommitInterrupted, ProjectTestCase, interrupt_commit


LINE = ((-1, 1), (1, 3))
SCALED_LINE = ((-2, 2), (2, 6))
ENDPOINTS_ONLY = ((-1, 1), (1, 5))
TWO_BRANCHES = ((1, -2), (-2, 1))
ZERO = ((0, 0), (0, 0))
POINTS = ((0, 1), (1, 0))
ONE = {"whole": (0, 0, 1, 1)}
WHOLE = {"whole": (0, 0, 1, 2)}
SPLIT = {"west": (0, 0, 1, 1), "east": (0, 1, 1, 2)}
CASES = (
    ("kept", LINE, SCALED_LINE, ((0, 0),)),
    ("endpoints", LINE, ENDPOINTS_ONLY, ()),
    ("split", ZERO, TWO_BRANCHES, ((0, 0), (0, 1))),
    ("merge", TWO_BRANCHES, ZERO, ((0, 0), (1, 0))),
    ("same_branches", TWO_BRANCHES, ((-1, 2), (2, -1)), ((0, 0), (1, 1))),
    ("points", POINTS, POINTS, ()),
    ("point_and_arc", ZERO, ((0, -1), (-1, 1)), ((0, 1),)),
    ("bottom_edge", ((0, 0), (-1, 1)), ((0, 0), (-1, 2)), ((0, 0),)),
    ("outside_factor", ((2, 1), (-4, -2)), ((4, 2), (-2, -1)), ()),
    ("recut_seam", ((1, 0, -1), (-1, 0, 3)), ((3, 0, -2), (-1, 0, 2)), ((0, 0),)),
)


def v1_projection(rows, ranges):
    samples = validate_samples(rows)
    geometry = build_geometry((0, 0), (1, 1))
    layout = validate_layout(ranges, samples.cell_shape)
    order = SurveyOrder("same-survey", "same-revision", Fraction(0), geometry, samples.cell_shape, layout)
    packets = tuple(
        encode_packet(SheetPacket(
            order.survey_id, name, name, coverage,
            build_sheet_evidence(samples, geometry, order.level, coverage),
        ))
        for name, coverage in layout.items()
    )
    selection = validate_review_selection(order, reversed(tuple(ranges)), reversed(packets))
    groups = build_groups(selection.components, iter_contact_links(selection.components))
    return packets, groups


def check_v1():
    packets, groups = v1_projection(LINE, ONE)
    for rows in (SCALED_LINE, ENDPOINTS_ONLY):
        if v1_projection(rows, ONE) != (packets, groups):
            raise AssertionError("expected identical V1 projections after normalizing IDs")
    for rows in CASES[-1][1:3]:
        split = v1_projection(rows, SPLIT)[1]
        if split != v1_projection(rows, WHOLE)[1] or tuple(map(len, split)) != (2,):
            raise AssertionError("expected one two-cell group under either layout")
    print("V1 normalized packet and groups:", packets[0])
    print("V1 seam fixture: one group with two cell parts under either layout")


class OverlapExamples(ProjectTestCase):
    def bundles(self, order):
        from sheet.publish import publish_overlap_sheet

        names = order.layout.sheet_ids()
        legacy = []
        current = []
        adopted = []
        for name in names:
            issued = publish_overlap_sheet(self.source, self.surveys, self.sheets, order.survey_id, name)
            self.assertEqual(self.sheets.read_receipt(issued.packet_id), issued.receipt)
            current.append(read_sheet(self.sheets, issued.packet_id))
            adopted.append((name, issued.packet_id))
            legacy.append(self.publish(order, name)[1])
        return (order.survey_id, names[::-1], tuple(current)), tuple(legacy), tuple(adopted)

    def offline(self):
        self.take_source_offline()
        self.sheets.path.rename(self.root / "sheets.offline")
        self.assertFalse(self.sheets.path.exists())

    def issue(self, old, new, **kwargs):
        from review.assemble import issue_overlap_review

        return issue_overlap_review(self.surveys, self.reports, old, new, **kwargs)

    def read(self, issued):
        from ledger.history import read_overlap_review

        record = read_overlap_review(ReportCatalog(self.reports.path), issued.report_id)
        self.assertEqual((record.report_id, record.receipt), (issued.report_id, issued.receipt))
        return record

    def test_cases(self):
        for name, old_rows, new_rows, pairs in CASES:
            with self.subTest(case=name):
                self.run_case(name, old_rows, new_rows, pairs)

    def run_case(self, name, old_rows, new_rows, pairs):
        old_ranges, new_ranges = (WHOLE, SPLIT) if name == "recut_seam" else (ONE, ONE)
        old, old_v1, old_adopted = self.bundles(self.order(old_rows, old_ranges))
        new, new_v1, new_adopted = self.bundles(self.order(new_rows, new_ranges))
        self.offline()
        try:
            issued = self.issue(old, new)
            report = self.read(issued).report
            for side, v1, frozen, adopted in (
                (old, old_v1, report.old, old_adopted),
                (new, new_v1, report.new, new_adopted),
            ):
                legacy = issue_review(self.surveys, self.reports, side[0], side[1], v1)
                expected = read_review(self.reports, legacy.report_id).report
                self.assertEqual(frozen.survey_id, side[0])
                self.assertEqual(frozen.adopted, adopted)
                self.assertEqual(frozen.groups, expected.groups)
            self.assertEqual(report.pairs, pairs)
            if name == "recut_seam":
                east_packet = next(raw for raw in new[2] if json.loads(raw)["sheet_id"] == "east")
                with self.assertRaises(ValueError):
                    self.issue(old, (new[0], ("east",), (east_packet,)))
            print(json.dumps({"case": name, "report_id": issued.report_id, "pairs": report.pairs,
                              "group_counts": [len(report.old.groups), len(report.new.groups)]}))
        finally:
            (self.root / "source.offline").rename(self.source.path)
            (self.root / "sheets.offline").rename(self.sheets.path)

    def test_rejection_and_rollback(self):
        from sheet.publish import publish_overlap_sheet

        order = self.order(LINE, ONE)
        old, legacy, _ = self.bundles(order)
        new, _, _ = self.bundles(self.order(SCALED_LINE, ONE))
        old_counts = self.sheet_counts()
        with self.assertRaises(CommitInterrupted):
            publish_overlap_sheet(self.source, self.surveys, self.sheets, order.survey_id, "whole",
                                  before_commit=interrupt_commit)
        self.assertEqual(self.sheet_counts(), old_counts)
        self.offline()
        issued = self.issue(old, new)
        frozen = self.read(issued)
        counts = self.report_counts()
        broken = json.loads(old[2][0])
        del broken["evidence"]
        for packets in ((), legacy, new[2], (json.dumps(broken),)):
            with self.subTest(packets=packets), self.assertRaises(ValueError):
                self.issue((old[0], old[1], packets), new)
        with self.assertRaises(CommitInterrupted):
            self.issue(old, new, before_commit=interrupt_commit)
        self.assertEqual(self.report_counts(), counts)
        self.assertEqual(self.read(issued), frozen)


if __name__ == "__main__":
    if not sys.argv[1:]:
        check_v1()
    elif sys.argv[1:] == ["--v2"]:
        unittest.main(argv=sys.argv[:1], verbosity=2)
    else:
        raise SystemExit("usage: python3.11 -B overlap_cases.py [--v2]")
