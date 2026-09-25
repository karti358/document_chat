"""Utilities for identifying duplicate purchase orders in invoice records."""


def flag_duplicate_po_ids(rows):
    """Return rows whose po_id occurs more than once.

    Parameters
    ----------
    rows : iterable of dict
        Each dictionary should contain a ``po_id`` key.

    Returns
    -------
    list of dict
        The subset of rows belonging to purchase orders that occur multiple
        times.
    """
    counts = {}
    for row in rows:
        po_id = row.get("po_id")
        counts[po_id] = counts.get(po_id, 0) + 1

    return [row for row in rows if counts.get(row.get("po_id"), 0) > 1]


if __name__ == "__main__":
    sample = [
        {"po_id": "PO-1042", "invoice_id": "INV-240701"},
        {"po_id": "PO-1042", "invoice_id": "INV-240718"},
        {"po_id": "PO-1051", "invoice_id": "INV-240722"},
    ]
    print(flag_duplicate_po_ids(sample))
