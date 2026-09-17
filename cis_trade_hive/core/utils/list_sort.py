"""
Generic, deterministic list-page sorting.

Every list view (mascode, calendar, currency, party, ...) re-fetches its
data on each request and sorts it in Python via a sort_key_map + sorted().
When two rows tie on the chosen sort column (e.g. two mascodes with the
same industry_group), sorted()'s stability only guarantees their relative
order *within one call* — it does not guarantee the same two rows land on
the same side of a pagination boundary across separate requests, since the
underlying query result order isn't itself guaranteed stable call-to-call.

sort_list() fixes this generically: it always appends a tiebreaker key
(typically the table's natural/primary key) after the user's chosen sort
key, so ties are broken the same way on every request regardless of
fetch order. Any list view can opt in with a one-line change — no new
sort key map needed.
"""

from typing import Any, Callable, Dict, List, Optional


def sort_list(
    items: List[Dict[str, Any]],
    sort_key_map: Dict[str, Callable[[Dict[str, Any]], Any]],
    sort_by: str,
    sort_order: str,
    default_key: str,
    tiebreaker: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Sort a list of dicts using a view's existing sort_key_map, with a
    deterministic tiebreaker appended so pagination boundaries never
    shift between requests when rows tie on the primary sort key.

    Args:
        items: rows to sort (each a dict)
        sort_key_map: {sort_by value: key function}, same shape every
            reference_data view already builds
        sort_by: requested sort column (request.GET['sort'])
        sort_order: 'asc' or 'desc' (request.GET['order'])
        default_key: fallback key into sort_key_map when sort_by is
            unrecognized (mirrors the `sort_key_map.get(sort_by, ...)`
            pattern already used in every view)
        tiebreaker: optional key function for the secondary sort key
            (e.g. lambda x: (x.get('mas_code') or '').lower()). If the
            requested sort_by already equals default_key, no tiebreaker
            is needed since the primary key IS the natural key. If not
            given, no tiebreaker is applied (behaves exactly like a
            plain sorted() call, same as before).

    Returns:
        Sorted list. Reverse order only applies to the primary key —
        the tiebreaker always breaks ties in ascending order, so equal
        groups render in a stable, predictable sequence regardless of
        which direction the user sorted the primary column.

    Usage (replaces `sorted(items, key=sort_func, reverse=reverse_order)`):

        mascodes = sort_list(
            mascodes, sort_key_map, sort_by, sort_order,
            default_key='mas_code',
            tiebreaker=lambda x: (x.get('mas_code') or '').lower(),
        )
    """
    reverse_order = sort_order == 'desc'
    primary_func = sort_key_map.get(sort_by, sort_key_map[default_key])

    if tiebreaker is None or sort_by == default_key:
        return sorted(items, key=primary_func, reverse=reverse_order)

    # Break ties deterministically: sort by tiebreaker first (stable sort),
    # then by the primary key. Equal-primary-key groups keep a fixed
    # internal order regardless of source fetch order or sort direction.
    items = sorted(items, key=tiebreaker)
    return sorted(items, key=primary_func, reverse=reverse_order)
