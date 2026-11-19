from dataclasses import dataclass

from ledger.catalog import ReportCatalog
from ledger.report import FrozenReport, decode_report


@dataclass(frozen=True)
class ReviewRecord:
    report_id: str
    receipt: str
    report: FrozenReport


def read_review(catalog: ReportCatalog, report_id: str) -> ReviewRecord:
    raw, receipt = catalog.fetch_report(report_id)
    return ReviewRecord(report_id, receipt, decode_report(raw))


@dataclass(frozen=True)
class OverlapRecord:
    report_id: str
    receipt: str
    report: object


def read_overlap_review(catalog: ReportCatalog, report_id: str) -> OverlapRecord:
    from ledger.overlap import decode_overlap_report

    raw, receipt = catalog.fetch_report(report_id)
    return OverlapRecord(report_id, receipt, decode_overlap_report(raw))
