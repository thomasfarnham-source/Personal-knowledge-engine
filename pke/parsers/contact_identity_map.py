"""
Contact Identity Map
======================
Maps known email address variations to canonical addresses.

MVP approach — hardcoded dict. Will be replaced by contacts +
contact_identifiers table lookup when the Entity Layer is built.

Usage:
    from pke.parsers.contact_identity_map import normalize_address
    canonical = normalize_address("wrenahan@lmus.leggmason.com")
    # Returns: "william.renahan"
"""

# Map of known email variations → canonical local part
# The canonical form is the local part only (no domain)
# so that participant hashes are stable across employer changes.
IDENTITY_MAP: dict[str, str] = {
    # William Renahan
    "william.renahan@blackstone.com": "william.renahan",
    "william.renahan@dpimc.com": "william.renahan",
    "william.renahan@virtus.com": "william.renahan",
    "william.renahan@gmail.com": "william.renahan",
    "william.j.renahan@ssmb.com": "william.renahan",
    "wrenahan@lmus.leggmason.com": "william.renahan",
    "wrenahan@leggmason.com": "william.renahan",
    "williamrenahan@gmail.com": "william.renahan",
    # Sarah Renahan (William's wife — separate person)
    "saraherenahan@gmail.com": "saraherenahan",
    "sarah.renahan@theworthycompany.com": "saraherenahan",
    # Patrick Mangan
    "pjmangan@gmail.com": "pjmangan",
    "pj.mangan@yahoo.com": "pjmangan",
    # Bryan Mangan (Pat's brother — separate person)
    "bryan.t.mangan@gmail.com": "bryan.t.mangan",
    "btmangan@hotmail.com": "bryan.t.mangan",
    # Christopher Mangan (Pat's relative — separate person)
    "christophermangan@earthlink.net": "christophermangan",
    "cwmangan@gmail.com": "cwmangan",
    # Thomas Farnham (owner — all known addresses)
    "thomas.farnham@yahoo.com": "thomas.farnham",
    "thomas.farnham@citi.com": "thomas.farnham",
    "thomas.farnham@ubs.com": "thomas.farnham",
    "tfarnham1.f6e3b75@m.evernote.com": "thomas.farnham",
    # Chris Zichello
    "czichello@gmail.com": "czichello",
    "christopher.zichello@verizon.net": "czichello",
    "chriszichello@gmail.com": "czichello",
    # James Root
    "jcroot@gmail.com": "jcroot",
    # Family
    "nfarnham@gmail.com": "nfarnham",
    "farnhambn@gmail.com": "farnhambn",
    "bnfarnham@yahoo.com": "farnhambn",
    "tfarnham@mtholyoke.edu": "tfarnham",
}

# Display names for canonical addresses
DISPLAY_NAMES: dict[str, str] = {
    "william.renahan": "William Renahan",
    "saraherenahan": "Sarah Renahan",
    "pjmangan": "Patrick Mangan",
    "thomas.farnham": "Thomas Farnham",
    "czichello": "Chris Zichello",
    "jcroot": "James Root",
    "nfarnham": "Nicholas Farnham",
    "farnhambn": "Brian Farnham",
    "tfarnham": "Timothy Farnham",
}


def normalize_address(email_addr: str) -> str:
    """
    Normalize an email address to its canonical form.
    Returns the canonical local part if known, otherwise
    returns the original address lowercased.
    """
    addr = email_addr.lower().strip()
    if addr in IDENTITY_MAP:
        return IDENTITY_MAP[addr]
    return addr


def normalize_participants(participants: list[str]) -> list[str]:
    """
    Normalize a list of participant email addresses.
    Returns sorted, deduplicated canonical forms.
    """
    normalized = set()
    for addr in participants:
        normalized.add(normalize_address(addr))
    return sorted(normalized)


def get_display_name(canonical: str) -> str:
    """Get display name for a canonical address."""
    return DISPLAY_NAMES.get(canonical, canonical)
