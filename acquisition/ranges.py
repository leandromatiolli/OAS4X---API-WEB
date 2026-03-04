"""
Faixas de tensão dos ADCs (USB-1808X) – conforme manual.
Mapeamento id (API/JSON) para enum uldaq Range.
"""
from typing import List, Optional

# Lista de faixas suportadas pela 1808X: id (uldaq) + label para UI
ADC_RANGES: List[dict] = [
    {"id": "BIP10VOLTS", "label": "\u00b110 V"},
    {"id": "BIP5VOLTS", "label": "\u00b15 V"},
    {"id": "UNI10VOLTS", "label": "0 a 10 V"},
    {"id": "UNI5VOLTS", "label": "0 a 5 V"},
]

VALID_RANGE_IDS = {r["id"] for r in ADC_RANGES}
DEFAULT_RANGE_ID = "BIP5VOLTS"

# Para clipping/métricas: range_id -> valor em volts (amplitude do range)
RANGE_ID_TO_VOLTS = {
    "BIP5VOLTS": 5.0,
    "BIP10VOLTS": 10.0,
    "UNI5VOLTS": 5.0,
    "UNI10VOLTS": 10.0,
}


def range_id_to_volts(range_id: Optional[str]) -> float:
    """Converte range_id (ex. BIP5VOLTS) para volts (ex. 5.0) para clipping/métricas."""
    if not range_id or range_id not in RANGE_ID_TO_VOLTS:
        return 5.0
    return RANGE_ID_TO_VOLTS[range_id]


def get_range_enum(range_id: str):
    """
    Retorna o enum Range da uldaq para o range_id dado.
    Se range_id for inválido, retorna o enum do DEFAULT_RANGE_ID.
    """
    if range_id not in VALID_RANGE_IDS:
        range_id = DEFAULT_RANGE_ID
    from uldaq import Range
    return getattr(Range, range_id)
