"""
Lifting Line Theory (LLT) Solver — Nonlinear, Full-Span Version
---------------------------------------------------------------

Author:
    Leonardo Avoni
    avonileonardo@gmail.com
    17/11/2025

Short Description:
    This code, inspired by the method by Nyaga, solves Prandtl's Lifting 
    Line Theory with *nonlinear* Cl(alpha) airfoil laws, arbitrary 
    chord/twist distributions, and *full-span* (asymmetric-capable) 
    lifting-line evaluation. The solver iteratively enforces 
    CL_Γ(θ) = CL_alpha_eff(θ) using a Fourier-series approach.
    
Original Nyaga's code
    The original Nyaga's code enabled the simulation of LLT for linearly tapered, 
    linearly twisted wings using a single airfoil section, with user-defined wing 
    setting angles and linear lift-curve slopes. The code only modeled half wing, 
    assuming left/right symmetric wing behavior.

Updated code 
    The updated procedure allows LLT computations with the assumptions of 
    Nyaga's code, but extended to any chord distribution, any twist distribution, 
    and allowing user-defined C_L(alpha_eff) airfoil laws. Moreover, the code was extended 
    for full wing lift distribution, as to model asymmetric behavior if needed.
    
Sanity check:
    For AR = 10, alpha_wing = 14°, 
    Rectangular, untwisted wing,
    Uncambered airfoil,
    CL=2pi*alpha_eff,
    the solver should yield approximately CL_wing = 1.2332.
    (converged in 10 iterations)

References:
    - Nyaga, G. (2020). Lifting Line Theory Implementation.
      https://github.com/geoffreynyaga/lifting-line-theory

    - Anderson, J. D. (2017). Fundamentals of Aerodynamics (6th Ed.).
      McGraw-Hill Education.

---------------------------------------------------------------------------
"""

import numpy as np
import math
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------
# USER INPUTS
# ----------------------------------------------------------------------

alpha_wing = math.radians(14)   # Geometric wing setting angle [rad]

MAC = 1.0       # Mean Aerodynamic Chord [m]
AR = 10.0       # Aspect ratio
b = MAC * AR    # Full wingspan [m]

twist_0 = 0.0               # Reference twist [rad]
alpha_0 = math.radians(0.0) # Airfoil zero-lift angle [rad]

N = 30   # Number of internal spanwise stations (for the full span)

# ----------------------------------------------------------------------
# DEFINE THE Cl(alpha) FUNCTION
# ----------------------------------------------------------------------
def Cl_of_alpha(alpha):
    """
    Airfoil lift curve function.
    Returns both Cl(alpha) and dCl/dalpha.
    Here: linear 2π per radian, but users can replace with nonlinear model.
    """
    Cl = 2*np.pi*(alpha - alpha_0)
    dClda = 2*np.pi
    return Cl, dClda


def chord(y):
    """
    Chord distribution function c(y).
    Currently constant = MAC, but can be replaced with any distribution.
    """
    c = np.ones_like(y) * MAC
    return c


def twist(y):
    """
    Twist distribution t(y).
    Currently constant twist_0, but can be replaced with arbitrary function.
    """
    t = np.ones_like(y) * twist_0
    return t


# ----------------------------------------------------------------------
# GEOMETRY DISCRETIZATION
# ----------------------------------------------------------------------
# Using standard lifting-line substitution:
#   y = -(b/2) * cos(theta)
# where theta spans (0, π) excluding endpoints → interior collocation points.
theta = np.linspace(0, math.pi, N+2)[1:-1]

y_s = -(b / 2) * np.cos(theta)      # Spanwise stations [m]
c = chord(y_s)                      # Local chord distribution
alpha_twist = twist(y_s)            # Local twist distribution

# Local geometric angle of attack
alpha_geo = alpha_wing + alpha_twist


# ----------------------------------------------------------------------
# NONLINEAR LIFTING LINE SOLVER
# ----------------------------------------------------------------------
def solve_nonlinear_LLT(theta, c, b, alpha_geo, Cl_of_alpha,
                        N, max_iter=50, tol=1e-6, damping=0.8):
    """
    Iteratively solves Prandtl’s nonlinear LLT using a Fourier-series expansion.

    Parameters:
        theta       Collocation points (0 < θ < π)
        c           Local chord distribution
        b           Wingspan
        alpha_geo   Local geometric AoA (twist included)
        Cl_of_alpha User-provided airfoil law → Cl(alpha), dCl/dalpha
        N           Number of Fourier harmonics
        max_iter    Maximum iterations
        tol         Convergence tolerance
        damping     Relaxation factor for stability

    Algorithm:
        1. Build system matrix X based on harmonics n = 1..N
        2. Solve X A = RHS for Fourier coefficients A_n
        3. Compute circulation Γ and sectional Cl_Γ
        4. Update alpha_eff via Newton iteration to enforce Cl_Γ = Cl_alpha_eff
        5. Repeat until A_n converges
    """

    harmonics = np.arange(1, N+1)

    # Initial guess for effective angle alpha_eff
    alpha_eff = np.copy(alpha_geo)
    Cl, dCldalpha = Cl_of_alpha(alpha_eff)

    # Local alpha_L=0 extracted from Cl(alpha)
    alpha_0estimated = alpha_eff - Cl / dCldalpha

    # Fourier coefficients A_n (initialized to zero)
    A = np.zeros(N)

    is_converged = False

    # ----------------------- MAIN ITERATION LOOP -----------------------
    for it in range(max_iter):

        # Local parameter μ(θ)
        mu = c * dCldalpha / (4 * b)

        # Build matrix X (each column corresponds to harmonic n)
        X = np.column_stack([
            np.sin(n * theta) * (1.0 + (mu * n) / np.sin(theta))
            for n in harmonics
        ])

        # Right-hand-side for Fourier system
        RHS = mu * (alpha_geo - alpha_0estimated)

        # Solve for new Fourier coefficients
        A_new = np.linalg.solve(X, RHS)

        # Relaxation/damping update
        A = damping * A_new + (1 - damping) * A

        # Compute sectional lift coefficient via Fourier expansion
        f1 = np.sum([A[i] * np.sin(harmonics[i] * theta) for i in range(N)], axis=0)
        CL_section = (4.0 * b / c) * f1

        # Newton iteration on alpha_eff to satisfy Cl_Γ = Cl(alpha_eff)
        alpha_eff_new = np.copy(alpha_eff)
        for j in range(len(theta)):
            Cl_val, dCl_val = Cl_of_alpha(alpha_eff_new[j])
            delta = (Cl_val - CL_section[j]) / (dCl_val + 1e-12)
            alpha_eff_new[j] -= delta
            if abs(delta) < 1e-8:
                break

        # Update aerodynamic properties from new alpha_eff
        Cl, dCldalpha = Cl_of_alpha(alpha_eff_new)
        a_loc_new = dCldalpha
        alpha0_loc_new = alpha_eff_new - Cl / a_loc_new

        # Convergence check
        err = np.linalg.norm(A_new - A) / (np.linalg.norm(A_new) + 1e-12)
        if err < tol:
            print(f"✅ Converged in {it+1} iterations")
            is_converged = True
            break

        # Prepare next loop
        alpha_eff = alpha_eff_new
        a_loc = a_loc_new
        alpha0_loc = alpha0_loc_new

    # Final sectional Cl
    f1 = np.sum([A[i] * np.sin(harmonics[i] * theta) for i in range(N)], axis=0)
    CL_section = (4.0 * b / c) * f1

    return A, CL_section, it + 1, is_converged


# ----------------------------------------------------------------------
# RUN SOLVER
# ----------------------------------------------------------------------
A, CL_section, iters, is_converged = solve_nonlinear_LLT(
    theta, c, b, alpha_geo, Cl_of_alpha, N
)

# Overall wing CL from A1 term (classical LLT formula)
CL_wing = math.pi * AR * A[0]

if is_converged:
    print(f"\nOverall CL_wing = {CL_wing:.4f} (converged in {iters} iterations)")
else:
    print(f"\nOverall CL_wing = {CL_wing:.4f} (NOT CONVERGED, performed {iters} iterations)")


# ----------------------------------------------------------------------
# PLOT RESULTS
# ----------------------------------------------------------------------
# Add tip nodes for plot aesthetics
CL_section = np.append(0, CL_section)
y_s = np.append(-b/2, y_s)
CL_section = np.append(CL_section, 0)
y_s = np.append(y_s, b/2)

plt.figure(figsize=(8, 5))
plt.plot(y_s, CL_section, marker="o", lw=1.5)
plt.title("Lifting Line Theory (Nonlinear Cl(alpha)) — radians version")
plt.xlabel("Spanwise location y [m]")
plt.ylabel("Sectional lift coefficient Cl")
plt.grid(True)
plt.show()
