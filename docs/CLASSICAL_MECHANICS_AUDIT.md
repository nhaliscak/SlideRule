# Classical mechanics: audit of the library

The question was whether the library holds the full list of equations of classical mechanics. It did not. This document is the outcome of checking the library, topic by topic, against the contents of
two standard textbooks (Taylor, *Classical Mechanics*, and Halliday, Resnick & Walker, *Fundamentals of Physics*, mechanics part) and the usual first-year topics of Kleppner & Kolenkow; the topic list is the author's reading of those
tables of contents, not a copy of them. "Covered" means a calculation whose equations contain the topic's standard results, with a worked example and an independent test.

Status: 76 calculations are tagged Classical or Analytical Mechanics and 9 more Nonlinear Dynamics and Chaos (counts of the catalogue now). Three passes added to the original list: `library/mechanics_gaps.py` (26), `library/hamiltonian_chaos.py` (11) and `library/mechanics_formalism.py` (9).

| Topic | Calculation(s) | Status |
|---|---|---|
| Constant-acceleration kinematics | `physics.mechanics.kinematics_constant_acceleration` | covered |
| Newton's second law with several forces, 2-D components | `physics.mechanics.newton_second_law_2d` | **added** |
| Projectiles, with and without drag; launch from a height | `projectile_from_height`, `projectile_range`, `projectile_with_drag_range` | covered |
| Projectile on a slope | `physics.mechanics.projectile_on_incline` | **added** |
| Friction on an incline, blocks and pulleys, Atwood | `incline_friction`, `block_pulley_table`, `atwood_machine` | covered |
| Equilibrium: ladder, cables | `ladder_equilibrium`; `static_equilibrium_two_cables` | covered; **added** |
| Simple machines (lever, pulley, inclined plane) | `physics.mechanics.simple_machines` | **added** |
| Belt and rope friction (capstan) | `physics.mechanics.capstan_belt_friction` | **added** |
| Circular motion, banked curve, vertical circle, conical pendulum | `uniform_circular_motion`, `vertical_circle_conical_pendulum` | covered |
| Rotor ride (friction on a rotating wall) | `physics.mechanics.rotating_drum_friction` | **added** |
| Work–energy theorem with friction; energy conservation | `energy_conservation`; `physics.mechanics.work_energy_friction` | covered; **added** |
| Spring energy: bungee jump | `physics.mechanics.bungee_energy` | **added** |
| Power, lifting | `lifting_power_efficiency` | covered |
| Potential energy: equilibrium, stability, escape | `physics.analytical.cubic_potential_escape`, `bead_on_rotating_hoop` | **added** (cubic well) |
| Momentum, impulse, 1-D collisions with restitution | `impulse_momentum`, `collisions_1d`, `ballistic_pendulum` | covered |
| Collisions in two dimensions (inelastic; elastic with a target at rest, lab and CM angles) | `collision_2d_inelastic`, `elastic_scattering_target_at_rest` | **added** |
| Centre of mass: two bodies; several bodies; reduced mass | `centre_of_mass_two_bodies`; `centre_of_mass_system` | covered; **added** |
| Variable mass: rocket | `aerospace.propulsion.rocket_equation`, `rocket_thrust` | covered |
| Variable mass: falling chain, conveyor belt | `physics.mechanics.variable_mass_chain_belt` | **added** |
| Angular momentum, torque, flywheel dynamics | `angular_momentum_conservation`; `physics.mechanics.rotational_dynamics_torque` | covered; **added** |
| Moment of inertia, parallel-axis theorem | `moments_of_inertia` | covered |
| Principal axes and moments from a product of inertia | `physics.analytical.inertia_tensor_principal_2d` | **added** |
| Rolling without slipping | `rolling_incline` | covered |
| Torque-free rigid body (axisymmetric), gyroscope | `torque_free_rigid_body`, `gyroscope_precession` | covered |
| Euler's equations: stability of rotation about each axis (tennis racket) | `physics.analytical.euler_rotation_stability` | **added** |
| Simple harmonic motion: spring, pendulums, torsion | `spring_mass_oscillator`, `small_angle_pendulums`, `torsion_pendulum`, `springs_series_parallel` | covered |
| Large-amplitude pendulum | `mechanical.dynamics.pendulum_large_amplitude_period` | covered |
| Damped and driven oscillators, resonance, Q | `driven_damped_oscillator`, `damped_oscillator_response` | covered |
| Free decay: logarithmic decrement from measured peaks | `physics.mechanics.damped_free_decay` | **added** |
| Coupled oscillators, normal modes | `coupled_oscillators`, `double_pendulum_modes` | covered |
| Nonlinear oscillator: amplitude-dependent frequency | `physics.analytical.duffing_backbone` | **added** |
| Pendulum phase space: separatrix, libration and rotation | `physics.analytical.pendulum_separatrix` | **added** |
| Adiabatic invariants | `adiabatic_invariant_oscillator` | covered |
| Calculus of variations: brachistochrone | `physics.analytical.brachistochrone` | **added** |
| Lagrangian mechanics: constrained systems | `bead_on_rotating_hoop`, `double_pendulum_modes`, `kepler_effective_potential` | covered |
| Parametric stabilisation: the Kapitza pendulum | `physics.analytical.kapitza_pendulum` | **added** |
| Central forces: effective potential, orbit shape, period | `kepler_effective_potential`, `elliptical_orbit_vis_viva`, `newton_gravity` | covered |
| Position on an orbit at a given time (Kepler's equation) | `physics.analytical.kepler_equation_position` | **added** |
| Scattering: Rutherford; hard sphere | `modern.rutherford_scattering`; `physics.analytical.hard_sphere_scattering` | covered; **added** |
| Non-inertial frames: Coriolis, Foucault, rotating Earth | `rotating_earth`, `coriolis_foucault` | covered |
| Accelerating frames: apparent gravity, plumb line, elevator | `physics.mechanics.accelerating_frame_apparent_gravity` | **added** |
| Rotating liquid (paraboloid surface) | `physics.mechanics.rotating_bucket_surface` | **added** |
| Motion through a uniform planet (gravity tunnel) | `physics.mechanics.gravity_tunnel_shm` | **added** |
| Fluids: hydrostatics, buoyancy, Bernoulli, drag | `fluids.*` (separate sub-discipline) | covered elsewhere |
| Hamilton's equations as a phase-space flow (numerical) | `physics.analytical.hamilton_pendulum_trajectory` | **added** |
| Canonical momentum, gauge and the Hamiltonian of a charged particle | `physics.analytical.charged_particle_canonical_momentum` | **added** |
| Action variables, phase-space area, Bohr–Sommerfeld quantisation | `physics.analytical.oscillator_action_bohr_sommerfeld`, `kepler_action_variables` | **added** |
| Hidden symmetry and conserved vectors: Laplace–Runge–Lenz | `physics.analytical.laplace_runge_lenz` | **added** |
| Chaos: Lorenz trajectory and Lyapunov exponent | `physics.nonlinear.lorenz_lyapunov` | **added** |
| Chaos: Lorenz fixed points, Hopf threshold, Kaplan–Yorke dimension | `physics.nonlinear.lorenz_fixed_points_hopf` | **added** |
| Discrete maps: logistic-map cycles, Lyapunov exponent, Feigenbaum scaling | `physics.nonlinear.logistic_map_period_doubling` | **added** |
| Route to chaos in a driven oscillator: Melnikov threshold | `physics.nonlinear.melnikov_duffing_threshold` | **added** |
| Predictability horizon from a Lyapunov exponent | `physics.nonlinear.predictability_horizon` | **added** |
| Bifurcations: saddle-node, transcritical, pitchfork, Hopf normal forms | `physics.nonlinear.bifurcation_normal_forms` | **added** |
| The full 3-D inertia tensor: principal moments, angular momentum, kinetic energy | `physics.analytical.inertia_tensor_3d`, `rigid_body_angular_momentum_3d` | **added** (third pass) |
| Canonical transformations: the symplectic test and the transformed Hamiltonian | `physics.analytical.linear_canonical_transformation` | **added** |
| Action–angle variables as a canonical change of variables | `physics.analytical.canonical_action_angle_oscillator` | **added** |
| Hamilton–Jacobi theory: characteristic function, p = ∂W/∂q, t = ∂W/∂E | `physics.analytical.hamilton_jacobi_oscillator` | **added** |
| Noether's theorem: symmetry and conservation (isotropic against anisotropic) | `physics.analytical.noether_anisotropic_oscillator` | **added** |
| Area-preserving maps: the standard map and the chaos threshold | `physics.nonlinear.standard_map_stability` | **added** |
| Dissipative maps: Hénon fixed points, contraction, dimension | `physics.nonlinear.henon_map_properties` | **added** |
| Fractal dimension: self-similarity and box counting | `physics.nonlinear.fractal_dimension` | **added** |
| Orbital manoeuvres | `space.astronautical.hohmann_transfer`, `aerospace.orbits.circular_orbit` | covered elsewhere |

## Still not covered

* **Poisson brackets and canonical transformations in general.** What is a calculation is a specific case: the bracket test of a linear transformation, the action–angle transformation of the oscillator, Hamilton–Jacobi for the oscillator. A general bracket of two arbitrary functions is symbolic algebra and belongs in a computer-algebra system (or LiveCalc's function definitions with `derivative`).
* **Noether's theorem in general** is represented by one worked case (rotation symmetry of a 2-D oscillator); other symmetries appear as the conserved quantities of the individual systems.
* **Iterated dynamics that need a long run:** Poincaré sections and return maps, the full Lyapunov spectrum of a given system, correlation dimension from data. The library has the maps' analytic properties (fixed points, stability, thresholds, contraction, dimension from given exponents) and the Lorenz integration; a long iteration of a map is better done in LiveCalc (`range`, a user function and `sumover`) than as a fixed calculation.
* **Continuous mass distributions and elasticity** are in the structural sub-disciplines, not here; **waves and acoustics** are separate.
* **The audit is by topic.** It does not check that every individual formula a textbook states for a topic appears in the calculation that covers it (the worked examples and tests check what each calculation computes, not what it omits).
