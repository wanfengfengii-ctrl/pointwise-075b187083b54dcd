import json

from ledger.catalog import ReportCatalog
from ledger.history import read_overlap_review
from review.assemble import issue_overlap_review
from sheet.overlap import decode_overlap_packet
from sheet.publish import publish_overlap_sheet
from sheet.store import SheetStore, read_sheet
from survey.register import open_survey
from tests.fixtures import (
    CommitInterrupted, ProjectTestCase, interrupt_commit,
)

SQUARE = ((1, -1), (-1, 1))
SQUARE_ALT = ((2, -3), (-3, 2))
EMPTY = ((1, 2), (3, 4))
WIDE = ((1, -1, 1), (-1, 1, -1))
WIDE_ONE = {'whole': (0, 0, 1, 2)}
WIDE_SPLIT = {'west': (0, 0, 1, 1), 'east': (0, 1, 1, 2)}
ONE = {'whole': (0, 0, 1, 1)}


class OverlapReviewTests(ProjectTestCase):
    def bundle(self, order, names=None):
        names = tuple(names or order.layout.sheet_ids())
        adopted = []
        packets = []
        for name in names:
            issued = publish_overlap_sheet(self.source, self.surveys, self.sheets, order.survey_id, name)
            self.assertEqual(self.sheets.read_receipt(issued.packet_id), issued.receipt)
            adopted.append((name, issued.packet_id))
            packets.append(read_sheet(self.sheets, issued.packet_id))
        return order.survey_id, names, tuple(packets)

    def issue(self, old, new, **kwargs):
        return issue_overlap_review(self.surveys, self.reports, old, new, **kwargs)

    def offline(self):
        self.take_source_offline()
        self.sheets.path.rename(self.root / 'sheets.offline')

    def test_packet_identity_and_evidence(self):
        order = self.order(SQUARE, ONE)
        side = self.bundle(order)
        packet = decode_overlap_packet(side[2][0])
        self.assertEqual(packet.revision_id, order.revision_id)
        self.assertEqual(packet.survey_id, order.survey_id)
        self.assertEqual(packet.coverage.coordinates, (0, 0, 1, 1))
        self.assertEqual([record.cell for record in packet.evidence.cells], [(0, 0)])
        self.assertTrue(packet.evidence.cells[0].parts)
        for record in packet.evidence.cells:
            for part in record.parts:
                for contact in part:
                    self.assertTrue(0 <= contact.start[0] <= 1)

    def test_empty_cell_and_empty_correspondence(self):
        old = self.bundle(self.order(SQUARE, ONE))
        new = self.bundle(self.order(EMPTY, ONE))
        self.offline()
        record = read_overlap_review(self.reports, self.issue(old, new).report_id)
        self.assertEqual(record.report.pairs, ())
        self.assertEqual(len(record.report.old.groups), 1)
        self.assertEqual(record.report.new.groups, ())

    def test_recut_across_layouts(self):
        old = self.bundle(self.order(WIDE, WIDE_SPLIT))
        new = self.bundle(self.order(WIDE, WIDE_ONE))
        self.offline()
        record = read_overlap_review(self.reports, self.issue(old, new).report_id)
        self.assertEqual(record.report.pairs, ((0, 0),))
        self.assertEqual(len(record.report.old.groups), 1)
        self.assertEqual(len(record.report.new.groups), 1)
        self.assertEqual(tuple(name for name, _ in record.report.new.adopted), ('whole',))

    def test_many_to_one_correspondence(self):
        old = self.bundle(self.order(((1, -2), (-2, 1)), ONE))
        new = self.bundle(self.order(((0, 0), (0, 0)), ONE))
        self.offline()
        record = read_overlap_review(self.reports, self.issue(old, new).report_id)
        self.assertEqual(record.report.pairs, ((0, 0), (1, 0)))
        self.assertEqual(len(record.report.old.groups), 2)
        self.assertEqual(len(record.report.new.groups), 1)

    def test_rejections_leave_no_report(self):
        base_order = self.order(SQUARE, ONE)
        base = self.bundle(base_order)
        wide_order = self.order(WIDE, WIDE_SPLIT)
        split = self.bundle(wide_order)
        after = self.bundle(self.order(SQUARE_ALT, ONE))
        other_revision = self.register(((9, 9), (9, 9)))
        rebound = open_survey(self.source, self.surveys, other_revision, 0, ONE)
        rebound_packets = tuple(
            self.publish(rebound, 'whole')[1],
        )
        rebound_side = (rebound.survey_id, ('whole',), rebound_packets)
        v1_packet = self.publish(base_order, 'whole')[1]
        self.offline()

        def drop_evidence(raw):
            data = json.loads(raw)
            del data['evidence']
            return json.dumps(data)

        def bad_evidence(raw):
            data = json.loads(raw)
            data['evidence'][0]['parts'] = [[{'start': [[0, 1], [0, 1]], 'end': [[0, 1], [0, 1]]}]]
            return json.dumps(data)

        def change_corners(raw):
            data = json.loads(raw)
            data['evidence'][0]['corners'] = [[1, 1], [1, 1], [1, 1], [1, 1]]
            return json.dumps(data)

        def change_revision(raw):
            data = json.loads(raw)
            data['revision_id'] = 'not-the-pinned-revision'
            return json.dumps(data)

        def drop_cell(raw):
            data = json.loads(raw)
            data['evidence'] = []
            return json.dumps(data)

        cases = (
            ('missing', (base[0], base[1], ())),
            ('duplicate', (base[0], base[1], base[2] + base[2])),
            ('many', (base[0], ('whole',), base[2] + split[2])),
            ('v1', (base[0], base[1], (v1_packet,))),
            ('rebound', rebound_side),
            ('drop', (base[0], base[1], (drop_evidence(base[2][0]),))),
            ('bad', (base[0], base[1], (bad_evidence(base[2][0]),))),
            ('corners', (base[0], base[1], (change_corners(base[2][0]),))),
            ('revision', (base[0], base[1], (change_revision(base[2][0]),))),
            ('empty', (base[0], base[1], (drop_cell(base[2][0]),))),
            ('unknown_survey', ('missing-survey', base[1], base[2])),
        )
        for label, side in cases:
            with self.subTest(case=label):
                expected = LookupError if label == 'unknown_survey' else ValueError
                with self.assertRaises(expected):
                    self.issue(side, after)
            self.assertEqual(self.report_counts(), (0, 0))

    def test_mismatched_geometry_and_cells(self):
        base = self.bundle(self.order(SQUARE, ONE))
        shifted = self.bundle(self.order(SQUARE, ONE, origin=('1/9', 0)))
        split = self.bundle(self.order(WIDE, WIDE_SPLIT))
        self.offline()
        for other in (shifted, split):
            with self.subTest(other=other[0]), self.assertRaises(ValueError):
                self.issue(base, other)
        self.assertEqual(self.report_counts(), (0, 0))

    def test_transaction_rollback_and_reopen(self):
        base = self.bundle(self.order(SQUARE, ONE))
        after = self.bundle(self.order(SQUARE_ALT, ONE))
        self.offline()
        first = self.issue(base, after)
        record = read_overlap_review(self.reports, first.report_id)
        counts = self.report_counts()
        with self.assertRaises(CommitInterrupted):
            self.issue(base, after, before_commit=interrupt_commit)
        self.assertEqual(self.report_counts(), counts)
        reopened = ReportCatalog(self.reports.path)
        reopened.initialize()
        self.assertEqual(read_overlap_review(reopened, first.report_id), record)
        with self.assertRaises(LookupError):
            read_overlap_review(reopened, 'unknown-overlap-report')
        self.assertFalse(self.sheets.path.exists())

    def test_sheet_signature_rollback(self):
        order = self.order(SQUARE, ONE)
        before = self.sheet_counts()
        with self.assertRaises(CommitInterrupted):
            publish_overlap_sheet(self.source, self.surveys, self.sheets, order.survey_id, 'whole',
                                  before_commit=interrupt_commit)
        self.assertEqual(self.sheet_counts(), before)
        reopened = SheetStore(self.sheets.path)
        reopened.initialize()
        self.assertEqual(self.sheet_counts(), before)
