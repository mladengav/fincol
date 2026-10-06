"""Tests for :class:`~application.aggregation_updater.AggregationUpdater`."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest.mock import ANY, call

import pandas as pd
import pytest
from pytest_mock import MockerFixture

from application.aggregation_updater import AggregationUpdater
from application.dividend_loader import DividendLoader
from constants import BCE_TO, BNS_TO
from csv_io_test import seed_bce
from dividend_loader_test import CsvBackedYahooFinance
from domain.fincol_io import IFincolIo
from domain.ticker_snapshot import TickerSnapshot
from infrastructure.csv import CsvFincolIo


class TestFincolIo:
    """In-memory :class:`IFincolIo` for :class:`AggregationUpdater`: holds snapshots, records the commit."""

    __test__ = False  # not a pytest test class despite the name

    def __init__(
        self, snapshots: list[TickerSnapshot], dividend_history: pd.DataFrame
    ) -> None:
        self._snapshots = snapshots
        self._dividend_history = dividend_history
        self.dividends_by_year: pd.DataFrame | None = None

    @property
    def snapshots(self) -> list[TickerSnapshot]:
        return self._snapshots

    def read_cached_tickers(self, ticker_symbols: list[str]) -> list[TickerSnapshot]:
        wanted = set(ticker_symbols)
        return [s for s in self._snapshots if s.Symbol in wanted]

    def read_dividend_history(self) -> pd.DataFrame:
        return self._dividend_history

    def begin_aggregation_updates(self) -> None:
        pass

    def commit_aggregation_updates(
        self, snapshots: list[TickerSnapshot], dividends_by_year: pd.DataFrame
    ) -> None:
        self._snapshots = snapshots
        self.dividends_by_year = dividends_by_year

    def finish_aggregation_updates(self) -> None:
        pass

    def read_ttm_income(self) -> dict[str, float]:
        return {s.Symbol: float(s.TtmDivs) for s in self._snapshots}

    # Not used by AggregationUpdater.update_aggregations.

    def write_tickers_to_cache(self, snapshots: list[TickerSnapshot]) -> None:
        raise NotImplementedError

    def read_last_dividend_decrease(self) -> dict[str, date]:
        raise NotImplementedError

    def read_years_since_dividend_decrease(self) -> dict[str, int]:
        raise NotImplementedError

    def read_dividends_by_year(self) -> pd.DataFrame:
        raise NotImplementedError

    def read_years_consecutive_dividend_increase(self) -> dict[str, int]:
        raise NotImplementedError

    def update_dividend_history(self, new_dividends: pd.DataFrame) -> int:
        raise NotImplementedError


# TODO Generalize for any ticker in TESTCACHE_DIR, use CsvFincolIo directly instead of DividendLoader to write
@pytest.fixture(scope="module")
def generated_bns_fincol_io(tmp_path_factory: pytest.TempPathFactory) -> CsvFincolIo:
    """Ephemeral CSV cache with the BNS.TO ticker snapshot and dividend history (no aggregations)."""
    tmp_folder = tmp_path_factory.mktemp("aggregation_updater_bns_cache")
    fincol_io = CsvFincolIo(tmp_folder)
    dividend_loader = DividendLoader(CsvBackedYahooFinance(), fincol_io)
    dividend_loader.update_dividend_history([BNS_TO])
    return fincol_io


@pytest.fixture(scope="module")
def generated_bce_fincol_io(tmp_path_factory: pytest.TempPathFactory) -> CsvFincolIo:
    """Ephemeral CSV cache with the BCE.TO ticker snapshot and dividend history (no aggregations)."""
    tmp_folder = tmp_path_factory.mktemp("aggregation_updater_bce_cache")
    fincol_io = CsvFincolIo(tmp_folder)
    seed_bce(fincol_io)
    # testcache tickers.csv has no aggregation columns, so they read back as defaults
    # (e.g. YearsConsecutiveDividendIncrease = 0, which is BCE's expected value).
    # Reset them to the sentinels CsvBackedYahooFinance uses so each test's
    # "not already equal" pre-check can't pass without update_aggregations running.
    fincol_io.write_tickers_to_cache(
        [
            replace(
                s,
                LastDividendDecrease=date.min,
                YearsSinceDividendDecrease=-1,
                YearsConsecutiveDividendIncrease=-1,
                TtmDivs=Decimal(0),
            )
            for s in fincol_io.read_cached_tickers([BCE_TO])
        ]
    )
    return fincol_io


def _test_io(fincol_io: CsvFincolIo, symbol: str) -> TestFincolIo:
    """Fresh in-memory copy of the cached ``symbol`` snapshot and dividend history."""
    return TestFincolIo(
        fincol_io.read_cached_tickers([symbol]), fincol_io.read_dividend_history()
    )


def _snapshot(test_io: TestFincolIo, symbol: str) -> TickerSnapshot:
    (snap,) = test_io.read_cached_tickers([symbol])
    return snap


def _bns_test_io(fincol_io: CsvFincolIo) -> TestFincolIo:
    return _test_io(fincol_io, BNS_TO)


def _bns_snapshot(test_io: TestFincolIo) -> TickerSnapshot:
    return _snapshot(test_io, BNS_TO)


def _bce_test_io(fincol_io: CsvFincolIo) -> TestFincolIo:
    return _test_io(fincol_io, BCE_TO)


def _bce_snapshot(test_io: TestFincolIo) -> TickerSnapshot:
    return _snapshot(test_io, BCE_TO)


def test_bns_ttm_dividend_matches_fixture(
    generated_bns_fincol_io: CsvFincolIo,
) -> None:
    """BNS.TO ``TtmDivs`` computed from testcache dividend history is 4.40."""
    test_io = _bns_test_io(generated_bns_fincol_io)
    expected_ttm = 4.4
    assert float(_bns_snapshot(test_io).TtmDivs) != pytest.approx(expected_ttm)

    AggregationUpdater(test_io).update_aggregations([BNS_TO])

    actual_ttm = float(_bns_snapshot(test_io).TtmDivs)
    assert actual_ttm == pytest.approx(
        expected_ttm
    ), f"{BNS_TO} TtmDivs: expected {expected_ttm}, got {actual_ttm}"


def test_bns_last_decrease_matches_first_payment_date(
    generated_bns_fincol_io: CsvFincolIo,
) -> None:
    """BNS.TO ``LastDividendDecrease`` is the first payment date, as BNS has had no decreases."""
    test_io = _bns_test_io(generated_bns_fincol_io)
    expected_date = date(1995, 3, 29)
    assert _bns_snapshot(test_io).LastDividendDecrease != expected_date

    AggregationUpdater(test_io).update_aggregations([BNS_TO])

    actual_date = _bns_snapshot(test_io).LastDividendDecrease
    assert (
        actual_date == expected_date
    ), f"{BNS_TO} LastDividendDecrease: expected {expected_date}, got {actual_date}"


def test_bns_years_since_decrease_matches_fixture(
    generated_bns_fincol_io: CsvFincolIo,
) -> None:
    """BNS.TO ``YearsSinceDividendDecrease`` computed from testcache dividend history."""
    test_io = _bns_test_io(generated_bns_fincol_io)
    expected_years = 31
    assert _bns_snapshot(test_io).YearsSinceDividendDecrease != expected_years

    AggregationUpdater(test_io).update_aggregations([BNS_TO])

    actual_years = _bns_snapshot(test_io).YearsSinceDividendDecrease
    assert (
        actual_years == expected_years
    ), f"{BNS_TO} YearsSinceDividendDecrease: expected {expected_years}, got {actual_years}"


def test_bce_last_dividend_decrease_uses_latest_cut_date(
    generated_bce_fincol_io: CsvFincolIo,
) -> None:
    """BCE.TO last cut date from testcache dividend history matches the aggregation fixture."""
    test_io = _bce_test_io(generated_bce_fincol_io)
    expected_date = date(2025, 6, 16)
    assert _bce_snapshot(test_io).LastDividendDecrease != expected_date

    AggregationUpdater(test_io).update_aggregations([BCE_TO])

    result = _bce_snapshot(test_io).LastDividendDecrease
    assert (
        result == expected_date
    ), f"{BCE_TO} LastDividendDecrease: expected {expected_date}, got {result}"


def test_bns_dividends_by_year_2025_matches_expected(
    generated_bns_fincol_io: CsvFincolIo,
) -> None:
    """BNS.TO 2025 annual dividend total from testcache history is 4.32."""
    test_io = _bns_test_io(generated_bns_fincol_io)
    assert test_io.dividends_by_year is None

    AggregationUpdater(test_io).update_aggregations([BNS_TO])

    actual_df = test_io.dividends_by_year
    assert actual_df is not None
    row = actual_df.loc[(actual_df["symbol"] == BNS_TO) & (actual_df["year"] == 2025)]
    assert not row.empty, f"No 2025 row for {BNS_TO} in committed dividends_by_year"

    calculated_dividend = float(row["dividend"].iloc[0])
    expected_dividend = 4.32

    assert calculated_dividend == pytest.approx(
        expected_dividend
    ), f"{BNS_TO} 2025 dividend: expected {expected_dividend}, got {calculated_dividend}"


def test_bce_years_since_dividend_decrease_matches_expected(
    generated_bce_fincol_io: CsvFincolIo,
) -> None:
    """BCE.TO years since last cut from testcache dividend history matches the fixture."""
    test_io = _bce_test_io(generated_bce_fincol_io)
    expected_years = 1
    assert _bce_snapshot(test_io).YearsSinceDividendDecrease != expected_years

    AggregationUpdater(test_io).update_aggregations([BCE_TO])

    result = _bce_snapshot(test_io).YearsSinceDividendDecrease
    assert (
        result == expected_years
    ), f"{BCE_TO} YearsSinceDividendDecrease: expected {expected_years}, got {result}"


def test_bns_years_consecutive_dividend_increase_matches_expected(
    generated_bns_fincol_io: CsvFincolIo,
) -> None:
    """BNS.TO years consecutive dividend increase from testcache dividend history matches the fixture."""
    test_io = _bns_test_io(generated_bns_fincol_io)
    expected_years = 15
    assert _bns_snapshot(test_io).YearsConsecutiveDividendIncrease != expected_years

    AggregationUpdater(test_io).update_aggregations([BNS_TO])

    actual_years = _bns_snapshot(test_io).YearsConsecutiveDividendIncrease
    assert (
        actual_years == expected_years
    ), f"{BNS_TO} YearsConsecutiveDividendIncrease: expected {expected_years}, got {actual_years}"


def test_bce_years_consecutive_dividend_increase_matches_expected(
    generated_bce_fincol_io: CsvFincolIo,
) -> None:
    """BCE.TO years consecutive dividend increase from testcache dividend history matches the fixture."""
    test_io = _bce_test_io(generated_bce_fincol_io)
    expected_years = 0
    assert _bce_snapshot(test_io).YearsConsecutiveDividendIncrease != expected_years

    AggregationUpdater(test_io).update_aggregations([BCE_TO])

    result = _bce_snapshot(test_io).YearsConsecutiveDividendIncrease
    assert (
        result == expected_years
    ), f"{BCE_TO} YearsConsecutiveDividendIncrease: expected {expected_years}, got {result}"


def test_update_aggregations_sequence(mocker: MockerFixture) -> None:
    """``update_aggregations`` calls begin → commit → finish on ``IFincolIo``, in order."""
    fincol_io = mocker.create_autospec(IFincolIo, instance=True)
    fincol_io.read_cached_tickers.return_value = []
    fincol_io.read_dividend_history.return_value = pd.DataFrame(
        columns=["ticker", "date", "amount"]
    )

    AggregationUpdater(fincol_io).update_aggregations([BCE_TO])

    lifecycle = {
        "begin_aggregation_updates",
        "commit_aggregation_updates",
        "finish_aggregation_updates",
    }
    assert [c for c in fincol_io.mock_calls if c[0] in lifecycle] == [
        call.begin_aggregation_updates(),
        call.commit_aggregation_updates(ANY, ANY),
        call.finish_aggregation_updates(),
    ]


def test_update_aggregations_skips_symbols_without_cached_ticker(
    generated_bce_fincol_io: CsvFincolIo,
) -> None:
    """Symbols with no cached snapshot get no aggregations; the others still do."""
    test_io = _bce_test_io(generated_bce_fincol_io)
    assert test_io.read_ttm_income() == {BCE_TO: 0.0}

    AggregationUpdater(test_io).update_aggregations([BCE_TO, "NOPE.TO"])

    ttm = test_io.read_ttm_income()
    assert set(ttm) == {BCE_TO}
    assert ttm[BCE_TO] > 0.0, f"{BCE_TO} TtmDivs not updated: {ttm[BCE_TO]}"
