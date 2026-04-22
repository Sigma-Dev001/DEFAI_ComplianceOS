import asyncio
import logging
import time
import xml.etree.ElementTree as ET

import httpx

SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
CACHE_TTL_SECONDS = 24 * 3600
REQUEST_TIMEOUT = 30.0

logger = logging.getLogger(__name__)

_cache: dict[str, str] = {}
_loaded_at: float = 0.0
_lock = asyncio.Lock()


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _parse_sdn_xml(xml_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("OFAC SDN XML parse failed")
        return result

    for entry in root.iter():
        if _local_name(entry.tag) != "sdnEntry":
            continue

        first = last = ""
        for child in entry:
            name = _local_name(child.tag)
            if name == "firstName" and child.text:
                first = child.text.strip()
            elif name == "lastName" and child.text:
                last = child.text.strip()
        full_name = " ".join(p for p in (first, last) if p) or "Unknown SDN Entry"

        for id_el in entry.iter():
            if _local_name(id_el.tag) != "id":
                continue
            id_type = id_number = ""
            for sub in id_el:
                n = _local_name(sub.tag)
                if n == "idType" and sub.text:
                    id_type = sub.text.strip()
                elif n == "idNumber" and sub.text:
                    id_number = sub.text.strip()
            if id_type.startswith("Digital Currency Address") and id_number:
                result[id_number.lower()] = full_name

    return result


async def _fetch_sdn_xml() -> str | None:
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(SDN_URL, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
    except Exception:
        logger.warning("Failed to download OFAC SDN list", exc_info=True)
        return None


async def load_sdn_addresses() -> set[str]:
    global _cache, _loaded_at
    async with _lock:
        now = time.monotonic()
        if _cache and (now - _loaded_at) < CACHE_TTL_SECONDS:
            return set(_cache.keys())

        xml_text = await _fetch_sdn_xml()
        if xml_text is None:
            return set(_cache.keys())

        parsed = _parse_sdn_xml(xml_text)
        if not parsed:
            return set(_cache.keys())

        _cache = parsed
        _loaded_at = now
        logger.info(
            "Loaded %d OFAC SDN digital currency addresses", len(parsed)
        )
        return set(parsed.keys())


async def screen_wallet(address: str) -> dict:
    if not address:
        return {"hit": False, "address": None, "match": None}

    await load_sdn_addresses()
    match = _cache.get(address.lower())
    return {
        "hit": match is not None,
        "address": address,
        "match": match,
    }
