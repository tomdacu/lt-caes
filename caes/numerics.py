"""Bracketed one-dimensional search, shared by the solver's searches.

The plant runs six searches over one scalar - the cold-loop closure, its
feasibility boundary, the charge blend, the interheater target, the extraction
margin and the interheater inverse. Each narrows a bracket whose ends it can
evaluate, and each has its own POLICY: how many refinements, what counts as
converged, what a refused trial means, and which end of the final bracket is
the answer. Those policies are tuned and documented where they live.

What lives here is only the ARITHMETIC they have to agree on: the trial point,
the two update rules, and the plain bracketing step. Keeping one copy is what
makes the six loops comparable - a reader who has checked these three
functions has checked every search.

The recovery helpers additionally provide a contracting signed bracket,
finite-resolution isolation on partially defined domains, and constrained
simplex feasibility restoration. Their finite budgets never certify absence.

The heat-user search adds two textbook pieces: a geometric scan grid and
Brent's bounded maximization, which also drives the charge-split shares.
"""

from __future__ import annotations

from math import isfinite, log
from typing import Callable


class SearchUnresolved(ValueError):
    """A finite search budget is exhausted; this is NOT an infeasibility proof."""


def affine_fixed_point(intercept: float, slope: float, low: float, high: float) -> float:
    """Solve x = intercept + slope*x on a declared interval.

    Useful for a linearized/ideal-model predictor, not a certificate about a
    nonlinear model. A singular or out-of-domain predictor is unresolved.
    """
    if not (isfinite(intercept) and isfinite(slope)) or abs(1.0-slope) <= 1e-12:
        raise SearchUnresolved("singular affine closure predictor")
    root = intercept / (1.0-slope)
    if not isfinite(root) or not low <= root <= high:
        raise SearchUnresolved("affine closure predictor is outside the search domain")
    return root


def bracketed_root(
    function: Callable[[float], float],
    low: float,
    high: float,
    *,
    residual_tolerance: float,
    x_tolerance: float = 1e-10,
    max_iterations: int = 128,
) -> float:
    """Safeguarded secant/bisection on a continuous, finite, signed bracket.

    Interpolation is accepted only in the central half of the bracket. Thus
    its width contracts by at least 3/4 on every iteration (unlike an
    unrestricted false position). IVT guarantees existence ONLY if the caller
    has established continuity on this interval. Neither an invalid interior
    nor a small bracket with a large residual constitutes a root.
    """
    a, b = low, high
    fa, fb = function(a), function(b)
    if not (isfinite(fa) and isfinite(fb)) or fa * fb > 0:
        raise SearchUnresolved("root requires finite opposite-sign endpoints")
    for _ in range(max_iterations):
        if abs(fa) <= residual_tolerance:
            return a
        if abs(fb) <= residual_tolerance:
            return b
        if b - a <= x_tolerance:
            break
        x = trial_point(a, fa, b, fb)
        if not a + .25 * (b - a) <= x <= b - .25 * (b - a):
            x = .5 * (a + b)
        fx = function(x)
        if not isfinite(fx):
            raise SearchUnresolved("non-finite interior: bracket continuity unverified")
        if abs(fx) <= residual_tolerance:
            return x
        if fa * fx <= 0:
            b, fb = x, fx
        else:
            a, fa = x, fx
    raise SearchUnresolved("bracket retained but residual tolerance not achieved")


def sampled_roots(
    function: Callable[[float], float | None],
    low: float,
    high: float,
    *,
    subdivisions: int,
    residual_tolerance: float,
) -> list[float]:
    """Isolate sampled sign changes without assigning a sign to undefined points.

    Both edges of each observed valid component are approached by bisection.
    This is finite-resolution isolation, NOT interval arithmetic: an empty
    result does not exclude an unsampled island or a tangential root. The
    caller must report unresolved search, never certified nonexistence.
    """
    if high <= low:
        return []
    cache: dict[float, float | None] = {}
    def evaluate(x: float) -> float | None:
        if x not in cache:
            value = function(x)
            cache[x] = value if value is not None and isfinite(value) else None
        return cache[x]
    points = [low + (high - low) * i / subdivisions for i in range(subdivisions + 1)]
    for x in points:
        evaluate(x)
    for a, b in zip(points, points[1:]):
        va, vb = evaluate(a), evaluate(b)
        if (va is None) == (vb is None):
            continue
        bad, good = (a, b) if va is None else (b, a)
        for _ in range(24):
            mid = .5 * (bad + good)
            if evaluate(mid) is None:
                bad = mid
            else:
                good = mid
    roots: list[float] = []
    ordered = sorted(cache)
    for a in ordered:
        value = cache[a]
        if value is not None and abs(value) <= residual_tolerance:
            roots.append(a)
    for a, b in zip(ordered, ordered[1:]):
        va, vb = cache[a], cache[b]
        if va is None or vb is None or va * vb >= 0:
            continue
        def finite(x: float) -> float:
            value = evaluate(x)
            if value is None:
                raise SearchUnresolved("undefined interior splits the physical domain")
            return value
        try:
            roots.append(bracketed_root(finite, a, b, residual_tolerance=residual_tolerance))
        except SearchUnresolved:
            # Do not return a best-but-unconverged point as an accepted root.
            continue
    return sorted(set(roots))


def simplex_feasible(
    violation: Callable[[list[float]], float],
    total: float,
    count: int,
    *,
    max_evaluations: int = 800,
) -> list[float] | None:
    """Deterministic pair-transfer pattern search on the nonnegative simplex.

    Transfers preserve total mass exactly and explore intermediate allocations,
    not only the N+1 original candidates. This derivative-free feasibility
    restoration is local and budgeted; failure is not a global certificate.
    The caller rechecks all original constraints before accepting a design.
    """
    point = [total / count] * count
    best = violation(point)
    evaluations = 1
    step = total / 4
    while evaluations < max_evaluations and step > total * 1e-7:
        if best == 0:
            return point
        improved = False
        for donor in range(count):
            for recipient in range(count):
                if donor == recipient or point[donor] < step:
                    continue
                trial = list(point)
                trial[donor] -= step
                trial[recipient] += step
                score = violation(trial)
                evaluations += 1
                if score < best:
                    point, best, improved = trial, score, True
                    if best == 0:
                        return point
                if evaluations >= max_evaluations:
                    break
            if evaluations >= max_evaluations:
                break
        if not improved:
            step *= .5
    return None


def bisect(
    fits: Callable[[float], bool],
    low: float,
    high: float,
    *,
    iterations: int,
    tolerance: float = 0.0,
    geometric: bool = False,
) -> tuple[float, float]:
    """Narrow ``[low, high]`` with a yes/no test, ``iterations`` times.

    ``fits(x)`` is True for trials on the HIGH side of the boundary - the end
    the search keeps. The midpoint is arithmetic, or geometric when the bracket
    spans orders of magnitude (a pressure). Stops early once the bracket is
    tighter than ``tolerance``: absolute, or a RATIO when geometric. Returns the
    final bracket; the caller picks the end it wants.
    """
    for _ in range(iterations):
        middle = (low * high) ** 0.5 if geometric else 0.5 * (low + high)
        if fits(middle):
            high = middle
        else:
            low = middle
        if (high / low - 1.0 if geometric else high - low) < tolerance:
            break
    return low, high


def trial_point(low: float, f_low: float, high: float, f_high: float) -> float:
    """One safeguarded regula-falsi step toward the root in the bracket.

    The false position is exact for a linear residual, which is what makes
    these searches take a handful of iterations instead of thirty. It can leave
    the bracket on badly scaled problems, so the midpoint is the fallback - for
    a degenerate denominator and for a trial outside the bracket alike.
    """
    denominator = f_high - f_low
    if abs(denominator) < 1e-30:
        return 0.5 * (low + high)
    trial = (low * f_high - high * f_low) / denominator
    return trial if low < trial < high else 0.5 * (low + high)


def geometric_grid(low: float, high: float, ratio: float) -> list[float]:
    """Points from ``low`` to ``high`` whose neighbours differ by at most ``ratio``.

    Both ends are included. Used for positive scale-like coordinates (the
    coolant inventory), where a relative step is the meaningful resolution.
    """
    if not 0.0 < low < high or ratio <= 1.0:
        raise ValueError("a geometric grid needs 0 < low < high and ratio > 1")
    count = max(1, int(-(-log(high / low) // log(ratio))))
    return [low * (high / low) ** (i / count) for i in range(count + 1)]


def brent_maximize(
    function: Callable[[float], float | None],
    low: float,
    high: float,
    *,
    x_tolerance: float,
    max_iterations: int = 60,
) -> tuple[float, float | None]:
    """Brent's golden-section/parabolic search for a maximum on ``[low, high]``.

    Brent (1973), *Algorithms for Minimization without Derivatives*, ch. 5.
    ``None`` means the trial is infeasible; it is ranked below every feasible
    value, and parabolic steps are only taken through three finite points, so
    an infeasible pocket degrades the search to golden section instead of
    breaking it. The interval ends are never evaluated: a caller whose
    maximum may sit on a constraint boundary compares its own endpoints.
    Converges to a LOCAL maximum; unimodality is the caller's claim.
    """
    golden = 0.3819660112501051
    infinite = float("inf")

    def cost(x: float) -> float:
        value = function(x)
        return infinite if value is None or not isfinite(value) else -value

    a, b = low, high
    x = w = v = a + golden * (b - a)
    fx = fw = fv = cost(x)
    d = e = 0.0
    for _ in range(max_iterations):
        middle = 0.5 * (a + b)
        tol1 = x_tolerance
        tol2 = 2.0 * tol1
        if abs(x - middle) <= tol2 - 0.5 * (b - a):
            break
        parabolic = False
        if abs(e) > tol1 and isfinite(fx) and isfinite(fw) and isfinite(fv):
            r = (x - w) * (fx - fv)
            q = (x - v) * (fx - fw)
            p = (x - v) * q - (x - w) * r
            q = 2.0 * (q - r)
            if q > 0.0:
                p = -p
            q = abs(q)
            if abs(p) < abs(0.5 * q * e) and q * (a - x) < p < q * (b - x):
                e, d = d, p / q
                u = x + d
                if u - a < tol2 or b - u < tol2:
                    d = tol1 if x < middle else -tol1
                parabolic = True
        if not parabolic:
            e = (a - x) if x >= middle else (b - x)
            d = golden * e
        u = x + (d if abs(d) >= tol1 else (tol1 if d > 0.0 else -tol1))
        fu = cost(u)
        # Two infeasible trials are not a tie to move toward: without this a
        # search that starts inside an infeasible region walks deeper into it.
        if fu < fx or (fu == fx and isfinite(fu)):
            if u >= x:
                a = x
            else:
                b = x
            v, fv, w, fw, x, fx = w, fw, x, fx, u, fu
        else:
            if u < x:
                a = u
            else:
                b = u
            if fu <= fw or w == x:
                v, fv, w, fw = w, fw, u, fu
            elif fu <= fv or v == x or v == w:
                v, fv = u, fu
    return x, (None if fx == infinite else -fx)


def illinois_residuals(
    f_low: float, f_high: float, *, moved_high: bool
) -> tuple[float, float]:
    """The Illinois update: halve the residual of the end that did NOT move.

    Without it the retained end keeps its value and the false position sticks to
    one side of the bracket - the classic regula-falsi stall. Returns the two
    residuals, still in bracket order.
    """
    if moved_high:
        return f_low * 0.5, f_high
    return f_low, f_high * 0.5
