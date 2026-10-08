"""Parse monetary amounts without currency conversion or rounding."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .common import InputError


CURRENCY_SYMBOLS = {
    "$": frozenset({"USD", "SGD", "AUD", "CAD", "NZD", "HKD"}),
    "£": frozenset({"GBP"}),
    "€": frozenset({"EUR"}),
    "S$": frozenset({"SGD"}),
}
UNLIMITED = re.compile(r"\b(?:no (?:spending |budget )?limit|unlimited|any budget)\b", re.I)
AMOUNT = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
AMOUNT_RE = re.compile(r"(?P<amount>" + AMOUNT + r")\s*(?:(?P<multiplier>k)(?![A-Za-z]))?(?:\s*(?P<unit>[A-Za-z][A-Za-z_ ]*))?", re.I)
MONEY_MENTION = re.compile(r"(?<!\w)(?:[A-Za-z]{3}\s*|S\$\s*|[$£€]\s*)" + AMOUNT + r"(?:\s*k\b)?(?![\w,]|\.\d)", re.I)


def decimal_string(value: object, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InputError("INVALID_VALUE", path, "Expected a finite decimal amount")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise InputError("INVALID_VALUE", path, "Expected a finite decimal amount") from exc
    if not number.is_finite():
        raise InputError("INVALID_VALUE", path, "Expected a finite decimal amount")
    return format(number, "f")


def _shift(number: Decimal, places: int) -> Decimal:
    sign, digits, exponent = number.as_tuple()
    return Decimal((sign, digits, exponent + places))


def parse_amount(value: object, unit: str | None, path: str) -> str:
    if not isinstance(value, str):
        return decimal_string(value, path)
    text = value.strip()
    for symbol in sorted(CURRENCY_SYMBOLS, key=len, reverse=True):
        if text.casefold().startswith(symbol.casefold()):
            if unit not in CURRENCY_SYMBOLS[symbol]:
                raise InputError("UNIT_MISMATCH", path, "Currency symbol and declared unit differ")
            text = text[len(symbol):].strip()
            break
    prefix = re.match(r"([A-Za-z]{3})\s*(?=[+-]?\d)", text)
    if prefix:
        if prefix.group(1).casefold() != (unit or "").casefold():
            raise InputError("UNIT_MISMATCH", path, "Currency code and declared unit differ")
        text = text[prefix.end():]
    match = AMOUNT_RE.fullmatch(text)
    if not match:
        raise InputError("AMBIGUOUS_ANSWER", path, "Provide one amount with valid thousands separators")
    suffix = match.group("unit")
    if suffix and suffix.casefold() != (unit or "").casefold():
        raise InputError("UNIT_MISMATCH", path, "Amount unit differs from the declared unit")
    number = Decimal(match.group("amount").replace(",", ""))
    if match.group("multiplier"):
        number = _shift(number, 3)
    return format(number, "f")


def parse_budget(text: str, currency: str | None, path: str, *, open_text: bool = False) -> dict:
    unlimited = UNLIMITED.search(text) if open_text else UNLIMITED.fullmatch(text.strip())
    mentions = list(MONEY_MENTION.finditer(text))
    if unlimited:
        if re.search(r"\b(?:not|never|isn't|cannot|can't)\b", text[:unlimited.start()], re.I):
            raise InputError("AMBIGUOUS_ANSWER", path, "Clarify the negated spending limit")
        if mentions or re.search(r"\d", text):
            raise InputError("AMBIGUOUS_ANSWER", path, "Both a limit and unlimited spending were stated")
        return {"kind": "unlimited"}
    if open_text:
        if len(mentions) != 1:
            raise InputError("AMBIGUOUS_ANSWER", path, "State one amount with its currency, or unlimited")
        mention = mentions[0]
        suffix = re.match(r"\s+([A-Z]{3})\b", text[mention.end():])
        text = mention.group() + (" " + suffix.group(1) if suffix else "")
    amount = parse_amount(text, currency, path)
    if Decimal(amount) < 0:
        raise InputError("AMBIGUOUS_BUDGET", path, "Budget limits must be nonnegative")
    return {"kind": "limited", "amount": amount, "currency": currency}


def minor_amount(amount: str, digits: int, path: str) -> int:
    validate_minor_digits(digits, path)
    scaled = _shift(Decimal(decimal_string(amount, path)), digits)
    if scaled != scaled.to_integral_value():
        raise InputError("AMBIGUOUS_ANSWER", path, "Amount has more precision than the declared minor unit")
    return int(scaled)


def validate_minor_digits(digits: object, path: str) -> int:
    if type(digits) is not int or not 0 <= digits <= 9:
        raise InputError("INVALID_VALUE", path, "Minor-unit digits must be an integer from 0 to 9")
    return digits
