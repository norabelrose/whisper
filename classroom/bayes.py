from .pref_graph import PrefGraph
from scipy.optimize import Bounds, minimize
# from scipy.sparse.linalg import eigsh, inv
from scipy.special import log1p
from scipy.stats import logistic, norm, rv_continuous
from typing import Literal
import networkx as nx
import numpy as np
import warnings


def update_rewards(
        G: PrefGraph,
        family: Literal['bradley-terry', 'thurstone'] = 'bradley-terry',
        *,
        eps: float = 0.125,
        prior: rv_continuous | None = None,
        tol: float = 1e-5
    ):
    """
    Compute maximum a posteriori (MAP) estimates of the latent rewards associated with the
    non-isolated nodes of a preference graph, writing the results to the nodes' attribute
    dictionaries under the 'reward' key. If there are already reward estimates in the graph,
    they will be used to initialize the solver and then overwritten. Isolated nodes can be
    implicitly assumed to have zero reward.

    Parameters
    ----------
    graph: PrefGraph
        The preference graph whose reward estimates should be updated.
    family: Literal['bradley-terry', 'thurstone']
        The type of paired compairson model to use for estimation. Bradley-Terry
        models assume differences in rewards have a logistic distribution, whereas
        Thurstone models assume a Gaussian distribution.
    eps: float
        Laplace smoothing parameter to ensure that each node has a nonzero probability
        of being preferred to every other node.
    prior: rv_continuous | None
        A SciPy continuous probability distribution representing the prior over
        latent rewards. If None, an improper uniform prior is used.
    
    Raises
    -------
    RuntimeError
        If the inner L-BFGS-B solver fails to converge.
    """
    assert eps > 0, "Laplace smoothing parameter must be positive"

    # Only explicitly compute rewards for non-isolated nodes. Isolated nodes will always
    # be assigned a reward of 0, and in the common case where most nodes are isolated,
    # this will save us a lot of time.
    nonisolated = [n for n in G if G.degree(n) > 0]
    if not nonisolated:
        return

    # The estimates for the latent rewards are coefficients of a generalized linear
    # model whose design matrix is the negative transpose of the graph incidence matrix.
    # The matrix is constructed so that multiplying it by the vector of latent
    # rewards yields a vector of length k where each entry is the difference
    # in rewards f(i) - f(j) for the corresponding edge.
    X = -nx.incidence_matrix(G, nodelist=nonisolated, oriented=True).T
    y = np.array([G.pref_prob(a, b, eps=eps) for a, b in G.edges])

    # Start from previously computed estimates of the latent rewards if available.
    b0 = np.zeros(len(nonisolated))
    for i, node in enumerate(nonisolated):
        reward = G.nodes[node].get('reward')
        if reward is not None:
            b0[i] = reward
        else:
            break

    match family:
        case 'bradley-terry':   link = logistic     # Logistic regression
        case 'thurstone':       link = norm         # Probit model
        case other:
            raise ValueError(f"Unknown family: {other}")
    
    def loss_and_grad(b: np.ndarray):
        z = X @ b       # f(i) - f(j)
        p = link.cdf(z)

        loss = -y @ link.logcdf(z) - (1 - y) @ log1p(-p)
        grad = X.T @ (p - y)    # Reduced form of the gradient

        if prior:
            # Use a finite difference approximation to the gradient of the log
            # prior for simplicity and generality
            log_density = prior.logpdf(b)
            loss -= log_density.sum()
            grad -= (prior.logpdf(b + 1.5e-8) - log_density) / 1.5e-8
        
        return loss, grad

    result = minimize(
        loss_and_grad,
        b0,
        bounds=Bounds(*prior.support()) if prior else None,
        jac=True,
        method='L-BFGS-B',
        tol=tol
    )
    if not result.success:
        raise RuntimeError(f"Reward estimation failed to converge: {result.message}")
    
    # Write the results back to the graph
    for node, reward in zip(nonisolated, result.x):
        G.nodes[node]['reward'] = reward

warnings.filterwarnings('ignore', category=FutureWarning, message='incidence_matrix')