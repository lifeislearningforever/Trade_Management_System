"""
FX Rates Parser for GMP Daily FX Rates Files

This module parses pipe-delimited FX rates files from the GMP system.
File format: H|GMP|...|... (Header) and D|1|USD-AED|AED|...|... (Detail)
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class FXRateHeader:
    """Represents a header record from FX rates file"""
    record_type: str  # 'H'
    source_system: str  # 'GMP'
    start_date: str  # '19800101'
    system_timestamp: str  # '20251224111237'

    def __str__(self):
        return f"Header: {self.source_system} | {self.system_timestamp}"

    @property
    def parsed_timestamp(self) -> Optional[datetime]:
        """Parse system timestamp to datetime"""
        try:
            return datetime.strptime(self.system_timestamp, '%Y%m%d%H%M%S')
        except ValueError:
            return None


@dataclass
class FXRateDetail:
    """Represents a detail record from FX rates file"""
    record_type: str  # 'D'
    ref_quot: str  # '1'
    spot_ff0: str  # 'USD-AED'
    base: str  # 'AED'
    trade_date: str  # '20251124'
    spot_rf_a: Decimal  # 3.6732
    underlng: str  # 'USD'
    spot_rf_b: Decimal  # 3.6725
    alias: str  # 'BOSET'

    def __str__(self):
        return f"{self.spot_ff0} | {self.trade_date} | {self.mid_rate}"

    @property
    def mid_rate(self) -> Decimal:
        """Calculate mid rate as (spot_rf_a + spot_rf_b) / 2"""
        return (self.spot_rf_a + self.spot_rf_b) / Decimal('2')

    @property
    def parsed_date(self) -> Optional[datetime]:
        """Parse trade date to datetime"""
        try:
            return datetime.strptime(self.trade_date, '%Y%m%d')
        except ValueError:
            return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion"""
        return {
            'record_type': self.record_type,
            'ref_quot': self.ref_quot,
            'spot_ff0': self.spot_ff0,
            'base': self.base,
            'trade_date': self.trade_date,
            'spot_rf_a': float(self.spot_rf_a),
            'underlng': self.underlng,
            'spot_rf_b': float(self.spot_rf_b),
            'alias': self.alias,
            'mid_rate': float(self.mid_rate)
        }


class FXRatesParser:
    """Parser for GMP daily FX rates files"""

    HEADER_RECORD_TYPE = 'H'
    DETAIL_RECORD_TYPE = 'D'
    DELIMITER = '|'

    def __init__(self):
        self.headers: List[FXRateHeader] = []
        self.details: List[FXRateDetail] = []
        self.errors: List[Dict[str, Any]] = []

    def parse_header(self, line: str) -> Optional[FXRateHeader]:
        """
        Parse a header record line
        Format: H|GMP|19800101|20251224111237
        """
        try:
            parts = line.strip().split(self.DELIMITER)
            if len(parts) < 4:
                raise ValueError(f"Invalid header format: expected 4 fields, got {len(parts)}")

            return FXRateHeader(
                record_type=parts[0],
                source_system=parts[1],
                start_date=parts[2],
                system_timestamp=parts[3]
            )
        except Exception as e:
            logger.error(f"Error parsing header line: {line} | Error: {e}")
            self.errors.append({'line': line, 'error': str(e), 'type': 'header'})
            return None

    def parse_detail(self, line: str) -> Optional[FXRateDetail]:
        """
        Parse a detail record line
        Format: D|1|USD-AED|AED|20251124|3.6732|USD|3.6725|BOSET
        """
        try:
            parts = line.strip().split(self.DELIMITER)
            if len(parts) < 9:
                raise ValueError(f"Invalid detail format: expected 9 fields, got {len(parts)}")

            return FXRateDetail(
                record_type=parts[0],
                ref_quot=parts[1],
                spot_ff0=parts[2],
                base=parts[3],
                trade_date=parts[4],
                spot_rf_a=Decimal(parts[5]),
                underlng=parts[6],
                spot_rf_b=Decimal(parts[7]),
                alias=parts[8]
            )
        except (InvalidOperation, ValueError) as e:
            logger.error(f"Error parsing detail line: {line} | Error: {e}")
            self.errors.append({'line': line, 'error': str(e), 'type': 'detail'})
            return None

    def parse_line(self, line: str) -> Optional[Any]:
        """Parse a single line based on record type"""
        line = line.strip()
        if not line:
            return None

        record_type = line.split(self.DELIMITER)[0]

        if record_type == self.HEADER_RECORD_TYPE:
            header = self.parse_header(line)
            if header:
                self.headers.append(header)
            return header
        elif record_type == self.DETAIL_RECORD_TYPE:
            detail = self.parse_detail(line)
            if detail:
                self.details.append(detail)
            return detail
        else:
            logger.warning(f"Unknown record type: {record_type} in line: {line}")
            self.errors.append({'line': line, 'error': f'Unknown record type: {record_type}', 'type': 'unknown'})
            return None

    def parse_file(self, file_path: str, skip_header: bool = False) -> Dict[str, Any]:
        """
        Parse an entire FX rates file

        Args:
            file_path: Path to the FX rates file
            skip_header: If True, skip header records (H type)

        Returns:
            Dictionary with parsing results
        """
        self.headers = []
        self.details = []
        self.errors = []

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        line_count = 0
        with open(path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line_count += 1

                # Skip empty lines
                if not line.strip():
                    continue

                # Parse the line
                record = self.parse_line(line)

                # Skip header records if requested
                if skip_header and isinstance(record, FXRateHeader):
                    continue

        return {
            'total_lines': line_count,
            'headers_count': len(self.headers),
            'details_count': len(self.details),
            'errors_count': len(self.errors),
            'headers': self.headers,
            'details': self.details,
            'errors': self.errors
        }

    def parse_text(self, text: str, skip_header: bool = False) -> Dict[str, Any]:
        """
        Parse FX rates data from text string

        Args:
            text: Text content with pipe-delimited FX rates
            skip_header: If True, skip header records (H type)

        Returns:
            Dictionary with parsing results
        """
        self.headers = []
        self.details = []
        self.errors = []

        lines = text.strip().split('\n')

        for line_num, line in enumerate(lines, 1):
            # Skip empty lines
            if not line.strip():
                continue

            # Parse the line
            record = self.parse_line(line)

            # Skip header records if requested
            if skip_header and isinstance(record, FXRateHeader):
                continue

        return {
            'total_lines': len(lines),
            'headers_count': len(self.headers),
            'details_count': len(self.details),
            'errors_count': len(self.errors),
            'headers': self.headers,
            'details': self.details,
            'errors': self.errors
        }

    def get_details_as_dicts(self) -> List[Dict[str, Any]]:
        """Get all detail records as dictionaries"""
        return [detail.to_dict() for detail in self.details]

    def filter_by_currency_pair(self, currency_pair: str) -> List[FXRateDetail]:
        """Filter detail records by currency pair"""
        return [d for d in self.details if d.spot_ff0 == currency_pair]

    def filter_by_date(self, trade_date: str) -> List[FXRateDetail]:
        """Filter detail records by trade date (YYYYMMDD format)"""
        return [d for d in self.details if d.trade_date == trade_date]

    def filter_by_base_currency(self, base_currency: str) -> List[FXRateDetail]:
        """Filter detail records by base currency"""
        return [d for d in self.details if d.base == base_currency]

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of parsed data"""
        unique_currencies = set(d.base for d in self.details)
        unique_pairs = set(d.spot_ff0 for d in self.details)
        unique_dates = set(d.trade_date for d in self.details)

        return {
            'total_records': len(self.details),
            'unique_currencies': len(unique_currencies),
            'unique_currency_pairs': len(unique_pairs),
            'unique_dates': len(unique_dates),
            'currencies': sorted(unique_currencies),
            'date_range': {
                'earliest': min(unique_dates) if unique_dates else None,
                'latest': max(unique_dates) if unique_dates else None
            }
        }


# Convenience function
def parse_fx_rates_file(file_path: str, skip_header: bool = False) -> Dict[str, Any]:
    """
    Convenience function to parse an FX rates file

    Args:
        file_path: Path to the FX rates file
        skip_header: If True, skip header records

    Returns:
        Dictionary with parsing results
    """
    parser = FXRatesParser()
    return parser.parse_file(file_path, skip_header=skip_header)
