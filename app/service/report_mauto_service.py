from datetime import date, datetime, timedelta
from logging import getLogger
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.report_mauto_schema import ReportMautoCdsboRequest
from app.schemas.response import ResponseCode, error_response, success_response

logger = getLogger(__name__)

# Nilai yang dianggap "tidak diisi" (termasuk placeholder bawaan Swagger)
_EMPTY_VALUES = {"", "null", "none", "string"}

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

QUERY = text("""
    SELECT *
    FROM public.report_mauto_cdsbo
    WHERE nik = :nik
      AND apply_date >= :date_start
      AND apply_date <  :date_end
      AND (CAST(:cc_reff AS text)        IS NULL OR cc_reff        = :cc_reff)
      AND (CAST(:branch_code AS text)    IS NULL OR branch_code    = :branch_code)
      AND (CAST(:account_number AS text) IS NULL OR account_number = :account_number)
    -- ctid sebagai tiebreaker: apply_date tidak unik dan tabel tidak punya
    -- primary key, tanpa ini urutan antar halaman LIMIT/OFFSET tidak stabil
    -- (baris bisa muncul ganda / hilang).
    ORDER BY apply_date, ctid
    LIMIT :limit OFFSET :offset
""")


def _clean(value: Optional[str]) -> Optional[str]:
    """Strip whitespace; kembalikan None untuk nilai kosong/placeholder."""
    if value is None:
        return None
    value = str(value).strip()
    return None if value.lower() in _EMPTY_VALUES else value


def _parse_apply_date(value: Optional[str]) -> Optional[date]:
    """Parse format ddmmyyyy, None jika tidak valid."""
    value = _clean(value)
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%d%m%Y").date()
    except ValueError:
        return None


def _resolve_paging(
    request: ReportMautoCdsboRequest, limit: Optional[int], offset: Optional[int]
) -> tuple[int, int]:
    """Ambil limit/offset dari argumen, fallback ke request, lalu batasi."""
    lim = limit if limit is not None else getattr(request, "limit", None)
    off = offset if offset is not None else getattr(request, "offset", None)

    lim = DEFAULT_LIMIT if not lim or lim < 1 else min(int(lim), MAX_LIMIT)
    off = 0 if not off or off < 0 else int(off)
    return lim, off


class ReportMautoService:
    @staticmethod
    def get_report_mauto(
        db: Session,
        request: ReportMautoCdsboRequest,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ):
        # --- Validasi field mandatory ---
        parsed_date = _parse_apply_date(request.apply_date)
        if parsed_date is None:
            return error_response(
                ResponseCode.BAD_REQUEST,
                "apply_date is required with format ddmmyyyy.",
            )

        nik = _clean(request.nik)
        if nik is None:
            return error_response(ResponseCode.BAD_REQUEST, "nik is required.")

        # --- Parameter query ---
        page_limit, page_offset = _resolve_paging(request, limit, offset)

        params = {
            "nik": nik,
            "date_start": parsed_date,
            "date_end": parsed_date + timedelta(days=1),
            "cc_reff": _clean(getattr(request, "cc_reff", None)),
            "branch_code": _clean(getattr(request, "branch_code", None)),
            "account_number": _clean(getattr(request, "account_number", None)),
            "limit": page_limit,
            "offset": page_offset,
        }

        # --- Eksekusi ---
        try:
            rows = db.execute(QUERY, params).mappings().all()
            data = [dict(row) for row in rows]
            logger.info(
                "report_mauto nik=%s apply_date=%s rows=%d",
                nik, parsed_date, len(data),
            )
            return success_response(data)
        except Exception:
            logger.exception("get_report_mauto failed, params=%s", params)
            return error_response(
                ResponseCode.INTERNAL_ERROR, "Internal Server Error"
            )