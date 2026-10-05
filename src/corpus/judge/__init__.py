"""Judge (docs/CORPUS.md §6): a strong model decides what a person used to, so nothing waits in a review queue.

audit   labels the Extractor's claims (corpus.review judge labels): wrong ones leave the evidence
status  places reviewers reported closed or changed -> decisions kind place_status
dedup   two Maps entries of one real place -> decisions kind place_merge (aggregate folds them into one)
"""

from .audit import run as audit
from .dedup import merges, run as dedup
from .status import run as status, verdicts as place_verdicts

PHASES = {"audit": audit, "status": status, "dedup": dedup}

__all__ = ["PHASES", "audit", "dedup", "merges", "place_verdicts", "status"]
