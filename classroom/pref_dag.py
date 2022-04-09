from .pref_graph import CoherenceViolation, PrefGraph
from typing import Generator
import networkx as nx


class PrefDAG(PrefGraph):
    """
    `PrefDAG` enforces the invariant that strict preferences must be transitive, and therefore
    the subgraph representing them must be acyclic. Violating this property will result in a
    `TransitivityViolation` exception, which has a `cycle` attribute that can be used to display
    the offending cycle to the user. We do not assume indifferences are transitive due to the Sorites
    paradox. See <https://en.wikipedia.org/wiki/Sorites_paradox#Resolutions_in_utility_theory>.
    """
    def add_edge(self, a: str, b: str, weight: float = 1, **attr):
        super().add_edge(a, b, weight, **attr)

        if weight > 0:
            # This is a strict preference, so we should check for cycles
            try:
                cycle = nx.find_cycle(self.strict_prefs, source=a)
            except nx.NetworkXNoCycle:
                pass
            else:
                # Remove the edge we just added.
                self.remove_edge(a, b)

                ex = TransitivityViolation(f"Adding {a} > {b} would create a cycle: {cycle}")
                ex.cycle = cycle
                raise ex
    
    def add_edges_from(self, ebunch_to_add, **attr):
        # We have to override this method separately since the default implementation doesn't in turn
        # call `add_edge`. As an added bonus we can amortize the cost of checking for coherence violations.
        super().add_edges_from(ebunch_to_add, **attr)

        try:
            cycle = nx.find_cycle(self.strict_prefs)
        except nx.NetworkXNoCycle:
            pass
        else:
            self.remove_edges_from(ebunch_to_add)
            raise TransitivityViolation(f"Edges would create a cycle: {cycle}")
    
    def median(self) -> str:
        """Return the node at index n // 2 of a topological ordering of the strict preference relation."""
        middle_idx = len(self.strict_prefs) // 2

        for i, node in enumerate(nx.topological_sort(self.strict_prefs)):
            if i == middle_idx:
                return node
        
        raise RuntimeError("Could not find median")
    
    def searchsorted(self) -> Generator[str, bool, int]:
        """Coroutine for asynchronously performing a binary search on the strict preference relation."""
        ordering = list(nx.topological_sort(self.strict_prefs))
        lo, hi = 0, len(ordering)

        while lo < hi:
            pivot = (lo + hi) // 2
            greater = yield ordering[pivot]
            if greater:
                lo = pivot + 1
            else:
                hi = pivot
        
        return lo


class TransitivityViolation(CoherenceViolation):
    """Raised when a mutation of a `PrefDAG` would cause transitivity to be violated"""
    cycle: list[int]
