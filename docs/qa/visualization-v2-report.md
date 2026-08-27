# Visualization V2 — 200-case acceptance report

Generated from production compiler code at `6bce30843781052a63f28d5e116442f84a9e9dfe`.

Result: **200/200 passed**; 0 failed; zero cases waived.

## Frozen pre-holdout candidate

- SHA: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd`
- Frozen at: `2026-08-27T12:07:54+01:00`
- The separate post-implementation holdout was not opened before this candidate was frozen.

| ID | Domain | Intent / family | Renderer / spec | Controls | Invariants | Browser evidence | Compile | Result |
|---|---|---|---|---|---|---|---:|---|
| stem-001 | mathematics | interactive_visual / pythagoras | svg / scene2d | a, b | a2_plus_b2_equals_c2, square_areas | svg: 31 primitives; 63.3 ms | 1.652 ms | PASS |
| stem-002 | mathematics | interactive_visual / unit_circle | svg / scene2d | angle | point_on_unit_circle, sin_cos_projection | svg: 29 primitives; 41 ms | 0.717 ms | PASS |
| stem-003 | mathematics | interactive_visual / quadratic | svg / scene2d | a, b, c | semantic_relationship, labels_and_units, control_consistency | svg: 28 primitives; 85.5 ms | 3.497 ms | PASS |
| stem-004 | mathematics | interactive_visual / line_intersection | svg / scene2d | m1, c1, m2, c2 | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 105.3 ms | 1.555 ms | PASS |
| stem-005 | mathematics | interactive_visual / triangle_angles | svg / scene2d | vertex_a, vertex_b, vertex_c | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 85.5 ms | 0.906 ms | PASS |
| stem-006 | mathematics | interactive_visual / derivative_tangent | svg / scene2d | x | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 46.1 ms | 1.259 ms | PASS |
| stem-007 | mathematics | interactive_visual / riemann_sum | svg / scene2d | rectangles | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 42.1 ms | 1.190 ms | PASS |
| stem-008 | mathematics | interactive_visual / gradient_field | svg / scene2d | point_x, point_y | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 77.2 ms | 3.142 ms | PASS |
| stem-009 | mathematics | interactive_visual / plane_intersection | three / scene3d | orbit | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 144.8 ms | 1.328 ms | PASS |
| stem-010 | mathematics | interactive_visual / linear_transform | svg / scene2d | matrix | semantic_relationship, labels_and_units, control_consistency | svg: 59 primitives; 45.6 ms | 0.702 ms | PASS |
| stem-011 | physics | interactive_visual / projectile | svg / scene2d | angle, speed | trajectory_endpoints, range_height_units | svg: 29 primitives; 65.8 ms | 0.704 ms | PASS |
| stem-012 | physics | interactive_visual / inclined_plane | svg / scene2d | incline | semantic_relationship, labels_and_units, control_consistency | svg: 12 primitives; 46.3 ms | 0.376 ms | PASS |
| stem-013 | physics | interactive_visual / spring_mass | svg / scene2d | spring_constant, mass | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 64.3 ms | 0.366 ms | PASS |
| stem-014 | physics | interactive_visual / elastic_collision | svg / scene2d | mass_1, velocity_1, mass_2, velocity_2 | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 106.9 ms | 0.368 ms | PASS |
| stem-015 | physics | interactive_visual / pendulum | svg / scene2d | length, angle, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 249.8 ms | 0.530 ms | PASS |
| stem-016 | physics | interactive_visual / travelling_wave | canvas / simulation2d | amplitude, wavelength, frequency | semantic_relationship, labels_and_units, control_consistency | canvas: 820 primitives; 98.2 ms | 1.018 ms | PASS |
| stem-017 | physics | interactive_visual / wave_interference | canvas / simulation2d | phase | semantic_relationship, labels_and_units, control_consistency | canvas: 648 primitives; 89.9 ms | 1.261 ms | PASS |
| stem-018 | physics | interactive_visual / circular_motion | svg / scene2d | angular_velocity | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 40 ms | 0.815 ms | PASS |
| stem-019 | physics | interactive_visual / harmonic_motion | canvas / simulation2d | spring_constant, mass, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | canvas: 876 primitives; 270.4 ms | 1.077 ms | PASS |
| stem-020 | physics | interactive_visual / double_pendulum | canvas / simulation2d | angle_1, angle_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 1606 primitives; 117.6 ms | 4.298 ms | PASS |
| stem-021 | electromagnetism | interactive_visual / ohms_law_circuit | svg / scene2d | voltage, resistance, switch | current_v_over_r, current_direction | svg: 14 primitives; 87.2 ms | 0.421 ms | PASS |
| stem-022 | electromagnetism | interactive_visual / series_parallel_circuit | svg / scene2d | r1, r2, mode | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 86.8 ms | 0.310 ms | PASS |
| stem-023 | electromagnetism | interactive_visual / electric_field_lines | canvas / simulation2d | charge_1, charge_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 898 primitives; 85 ms | 3.875 ms | PASS |
| stem-024 | electromagnetism | interactive_visual / electric_field_vectors | canvas / simulation2d | test_x, test_y | semantic_relationship, labels_and_units, control_consistency | canvas: 461 primitives; 142.3 ms | 1.437 ms | PASS |
| stem-025 | electromagnetism | interactive_visual / magnetic_field_wire | canvas / simulation2d | current_direction | semantic_relationship, labels_and_units, control_consistency | canvas: 1190 primitives; 74.8 ms | 1.402 ms | PASS |
| stem-026 | electromagnetism | interactive_visual / rc_circuit | svg / scene2d | mode, resistance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 39 primitives; 137.9 ms | 0.945 ms | PASS |
| stem-027 | electromagnetism | interactive_visual / rlc_circuit | svg / scene2d | resistance, inductance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 41 primitives; 101.9 ms | 0.598 ms | PASS |
| stem-028 | electromagnetism | interactive_visual / ac_phase | svg / scene2d | load | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 52.4 ms | 1.267 ms | PASS |
| stem-029 | optics_thermodynamics | interactive_visual / converging_lens | svg / scene2d | object_distance | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 101.3 ms | 0.364 ms | PASS |
| stem-030 | optics_thermodynamics | interactive_visual / refraction | svg / scene2d | incident_angle, medium | snell_law, normal_and_ray_direction | svg: 15 primitives; 65.5 ms | 0.311 ms | PASS |
| stem-031 | optics_thermodynamics | interactive_visual / ideal_gas | svg / scene2d | pressure, volume, temperature | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 86.6 ms | 0.973 ms | PASS |
| stem-032 | optics_thermodynamics | interactive_visual / carnot_cycle | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 229.8 ms | 0.467 ms | PASS |
| stem-033 | chemistry | interactive_visual / atom | svg / scene2d | atomic_number | semantic_relationship, labels_and_units, control_consistency | svg: 46 primitives; 126 ms | 1.903 ms | PASS |
| stem-034 | chemistry | interactive_visual / ionic_bond | svg / scene2d | playback | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 44.5 ms | 0.347 ms | PASS |
| stem-035 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 138.4 ms | 0.385 ms | PASS |
| stem-036 | chemistry | interactive_visual / reaction_profile | svg / scene2d | catalyst | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 81.5 ms | 1.041 ms | PASS |
| stem-037 | chemistry | interactive_visual / titration | svg / scene2d | titrant_volume | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 126.2 ms | 1.017 ms | PASS |
| stem-038 | chemistry | interactive_visual / molecular_orbitals | svg / scene2d | orbital | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 98.7 ms | 0.496 ms | PASS |
| stem-039 | biology | interactive_visual / animal_cell | svg / scene2d | organelle | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 46.7 ms | 0.326 ms | PASS |
| stem-040 | biology | interactive_visual / mitosis | svg / scene2d | step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 41.6 ms | 0.335 ms | PASS |
| stem-041 | biology | interactive_visual / circulation | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 19 primitives; 232.6 ms | 0.365 ms | PASS |
| stem-042 | biology | interactive_visual / action_potential | svg / scene2d | time | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 78.2 ms | 1.303 ms | PASS |
| stem-043 | computer_science | interactive_visual / binary_search | svg / scene2d | target, step, play, pause, restart | interval_shrinks, target_found | svg: 15 primitives; 253.4 ms | 0.536 ms | PASS |
| stem-044 | computer_science | interactive_visual / binary_search_tree | svg / scene2d | insert, step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 260.3 ms | 0.371 ms | PASS |
| stem-045 | computer_science | interactive_visual / dijkstra | svg / scene2d | source, destination, step, play, pause, restart | nondecreasing_settled_distance, shortest_path | svg: 31 primitives; 274.1 ms | 0.432 ms | PASS |
| stem-046 | computer_science | interactive_visual / stack_queue | svg / scene2d | operation, step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 67.6 ms | 0.412 ms | PASS |
| stem-047 | computer_science | interactive_visual / cpu_memory | svg / scene2d | step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 228.8 ms | 0.888 ms | PASS |
| stem-048 | engineering_signals_robotics_ai | interactive_visual / sampling_aliasing | canvas / simulation2d | signal_frequency, sample_frequency | nyquist_condition, sample_locations | canvas: 1097 primitives; 153.7 ms | 1.982 ms | PASS |
| stem-049 | engineering_signals_robotics_ai | interactive_visual / differential_drive | canvas / simulation2d | left_velocity, right_velocity | curvature_from_wheel_speeds | canvas: 910 primitives; 71.2 ms | 0.806 ms | PASS |
| stem-050 | engineering_signals_robotics_ai | interactive_visual / neural_network | svg / scene2d | weight, step | weighted_activation_flow | svg: 23 primitives; 65.3 ms | 0.601 ms | PASS |
| math-001 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 268.5 ms | 1.488 ms | PASS |
| math-002 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 266.9 ms | 1.268 ms | PASS |
| math-003 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 265.6 ms | 1.238 ms | PASS |
| math-004 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 260 ms | 1.522 ms | PASS |
| math-005 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.4 ms | 1.913 ms | PASS |
| math-006 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.6 ms | 1.219 ms | PASS |
| math-007 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.3 ms | 1.472 ms | PASS |
| math-008 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276.9 ms | 1.249 ms | PASS |
| math-009 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.1 ms | 1.782 ms | PASS |
| math-010 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.9 ms | 1.970 ms | PASS |
| math-011 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.3 ms | 3.742 ms | PASS |
| math-012 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 1216 primitives; 265.9 ms | 2.017 ms | PASS |
| math-013 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 264.7 ms | 1.572 ms | PASS |
| math-014 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.7 ms | 1.551 ms | PASS |
| math-015 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 271.1 ms | 1.845 ms | PASS |
| math-016 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.8 ms | 0.887 ms | PASS |
| math-017 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.6 ms | 1.039 ms | PASS |
| math-018 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.4 ms | 0.937 ms | PASS |
| math-019 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.6 ms | 1.795 ms | PASS |
| math-020 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275.8 ms | 1.564 ms | PASS |
| math-021 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 269 ms | 0.672 ms | PASS |
| math-022 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 264.4 ms | 1.198 ms | PASS |
| math-023 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276.7 ms | 1.183 ms | PASS |
| math-024 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 268.5 ms | 1.092 ms | PASS |
| math-025 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.1 ms | 1.030 ms | PASS |
| math-026 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.2 ms | 1.599 ms | PASS |
| math-027 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.8 ms | 1.489 ms | PASS |
| math-028 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.7 ms | 1.782 ms | PASS |
| math-029 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 292.4 ms | 3.184 ms | PASS |
| math-030 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.4 ms | 1.856 ms | PASS |
| math-031 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 271.7 ms | 1.231 ms | PASS |
| math-032 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277 ms | 1.260 ms | PASS |
| math-033 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.6 ms | 1.177 ms | PASS |
| math-034 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 271.8 ms | 1.246 ms | PASS |
| math-035 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 266 ms | 0.938 ms | PASS |
| math-036 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.8 ms | 1.511 ms | PASS |
| math-037 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.1 ms | 2.399 ms | PASS |
| math-038 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.6 ms | 1.946 ms | PASS |
| math-039 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 268.2 ms | 2.353 ms | PASS |
| math-040 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 269.3 ms | 4.303 ms | PASS |
| math-041 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 266.7 ms | 1.712 ms | PASS |
| math-042 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.6 ms | 2.206 ms | PASS |
| math-043 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 268.8 ms | 2.098 ms | PASS |
| math-044 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.4 ms | 2.878 ms | PASS |
| math-045 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 269.3 ms | 4.525 ms | PASS |
| math-046 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.5 ms | 6.717 ms | PASS |
| math-047 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.8 ms | 2.068 ms | PASS |
| math-048 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.1 ms | 2.041 ms | PASS |
| math-049 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.9 ms | 2.472 ms | PASS |
| math-050 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.9 ms | 2.946 ms | PASS |
| math-051 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.6 ms | 2.067 ms | PASS |
| math-052 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 279.5 ms | 2.575 ms | PASS |
| math-053 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4584 primitives; 278.4 ms | 2.582 ms | PASS |
| math-054 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 279 ms | 3.947 ms | PASS |
| math-055 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.3 ms | 1.759 ms | PASS |
| math-056 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 271.3 ms | 1.819 ms | PASS |
| math-057 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 274.3 ms | 1.580 ms | PASS |
| math-058 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 276.6 ms | 1.579 ms | PASS |
| math-059 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 277.4 ms | 1.552 ms | PASS |
| math-060 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275.5 ms | 2.227 ms | PASS |
| math-061 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 282.8 ms | 2.417 ms | PASS |
| math-062 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4140 primitives; 270.4 ms | 1.014 ms | PASS |
| math-063 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4120 primitives; 274.3 ms | 1.551 ms | PASS |
| math-064 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 279.9 ms | 2.727 ms | PASS |
| math-065 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4232 primitives; 279.5 ms | 1.939 ms | PASS |
| math-066 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 12024 primitives; 378 ms | 100.808 ms | PASS |
| math-067 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9296 primitives; 382.1 ms | 135.186 ms | PASS |
| math-068 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18440 primitives; 386.8 ms | 93.485 ms | PASS |
| math-069 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19928 primitives; 404.9 ms | 125.913 ms | PASS |
| math-070 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15624 primitives; 385.9 ms | 76.192 ms | PASS |
| math-071 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 14632 primitives; 384.8 ms | 99.744 ms | PASS |
| math-072 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 21576 primitives; 411.5 ms | 78.955 ms | PASS |
| math-073 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15004 primitives; 387.6 ms | 57.144 ms | PASS |
| math-074 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19560 primitives; 401.4 ms | 104.101 ms | PASS |
| math-075 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18104 primitives; 401.7 ms | 105.277 ms | PASS |
| math-076 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9588 primitives; 363.2 ms | 79.416 ms | PASS |
| math-077 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.4 ms | 1.411 ms | PASS |
| math-078 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 11864 primitives; 379.4 ms | 208.690 ms | PASS |
| math-079 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9288 primitives; 364.3 ms | 101.130 ms | PASS |
| math-080 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 5616 primitives; 391.8 ms | 94.748 ms | PASS |
| math-081 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 388.1 ms | 136.610 ms | PASS |
| math-082 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 379 ms | 175.856 ms | PASS |
| math-083 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7408 primitives; 362.7 ms | 132.305 ms | PASS |
| math-084 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9024 primitives; 370.8 ms | 145.009 ms | PASS |
| math-085 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276 ms | 4.668 ms | PASS |
| math-086 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276.6 ms | 1.850 ms | PASS |
| math-087 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7880 primitives; 361.2 ms | 149.564 ms | PASS |
| math-088 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 13680 primitives; 379.8 ms | 79.080 ms | PASS |
| math-089 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 96 primitives; 345.9 ms | 195.978 ms | PASS |
| math-090 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 3000 primitives; 349.2 ms | 265.329 ms | PASS |
| math-091 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 26594 primitives; 459.8 ms | 6.004 ms | PASS |
| math-092 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20252 primitives; 417.6 ms | 3.382 ms | PASS |
| math-093 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20196 primitives; 420.9 ms | 3.380 ms | PASS |
| math-094 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20624 primitives; 455.1 ms | 6.189 ms | PASS |
| math-095 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.5 ms | 1.402 ms | PASS |
| math-096 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 269.8 ms | 3.747 ms | PASS |
| math-097 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4600 primitives; 280.7 ms | 3.638 ms | PASS |
| math-098 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 268.6 ms | 1.630 ms | PASS |
| math-099 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275.1 ms | 1.801 ms | PASS |
| math-100 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.7 ms | 5.643 ms | PASS |
| heldout-001 | mathematics | interactive_visual / complex_mapping | svg / scene2d | point_angle, point_radius | complex_square_mapping, angle_doubles | svg: 71 primitives; 140.9 ms | 2.970 ms | PASS |
| heldout-002 | mathematics | interactive_visual / polar_plot | svg / scene2d | theta, playback, play, pause, restart | polar_radius, four_petals | svg: 35 primitives; 272.3 ms | 1.509 ms | PASS |
| heldout-003 | mathematics | interactive_visual / fourier_series | svg / scene2d | terms | odd_harmonics, gibbs_overshoot | svg: 36 primitives; 101 ms | 1.832 ms | PASS |
| heldout-004 | mathematics | interactive_visual / logistic_map | canvas / simulation2d | growth_rate, initial_value | iterate_logistic, bounded_unit_interval | canvas: 943 primitives; 127.1 ms | 4.244 ms | PASS |
| heldout-005 | mathematics | interactive_visual / lagrange_multiplier | svg / scene2d | constraint_offset | tangent_contours, parallel_gradients | svg: 37 primitives; 66 ms | 1.499 ms | PASS |
| heldout-006 | mathematics | interactive_visual / parametric_surface | three / scene3d | path_position, playback | mobius_single_boundary, parametric_samples | three: 1890 primitives; 307.9 ms | 0.551 ms | PASS |
| heldout-007 | mathematics | interactive_visual / vector_field | svg / scene2d | probe_x, probe_y | field_components, divergence_zero | svg: 49 primitives; 69.4 ms | 0.574 ms | PASS |
| heldout-008 | mathematics | interactive_visual / convolution | svg / scene2d | shift | overlap_equals_convolution, triangular_result | svg: 33 primitives; 44.1 ms | 0.550 ms | PASS |
| heldout-009 | physics | interactive_visual / kepler_orbit | canvas / simulation2d | eccentricity, true_anomaly, playback, play, pause, restart | acceleration_inward, equal_area | canvas: 1019 primitives; 280.3 ms | 0.730 ms | PASS |
| heldout-010 | physics | interactive_visual / coupled_oscillators | canvas / simulation2d | mode, playback, play, pause, restart | normal_mode_phase, energy_bounded | canvas: 1065 primitives; 315.8 ms | 1.087 ms | PASS |
| heldout-011 | physics | interactive_visual / standing_wave | svg / scene2d | harmonic | node_count, fixed_endpoints | svg: 41 primitives; 49.6 ms | 0.621 ms | PASS |
| heldout-012 | physics | interactive_visual / doppler | canvas / simulation2d | source_speed, playback | front_wavelength_shorter, wavefront_spacing | canvas: 632 primitives; 164.3 ms | 1.242 ms | PASS |
| heldout-013 | physics | interactive_visual / double_slit | svg / scene2d | slit_separation, wavelength | fringe_spacing, central_maximum | svg: 39 primitives; 64.7 ms | 0.741 ms | PASS |
| heldout-014 | physics | interactive_visual / lorentz_force | three / scene3d | charge, field, speed, playback, play, pause, restart | force_perpendicular_velocity, helix_radius | three: ? primitives; 697.7 ms | 0.563 ms | PASS |
| heldout-015 | physics | interactive_visual / blackbody | svg / scene2d | temperature | peak_shifts_shorter, radiance_positive | svg: 32 primitives; 104.8 ms | 1.314 ms | PASS |
| heldout-016 | physics | interactive_visual / entropy_cycle | canvas / simulation2d | step | closed_cycle, process_direction | canvas: 1169 primitives; 101.6 ms | 0.453 ms | PASS |
| heldout-017 | chemistry | interactive_visual / benzene | svg / scene2d | bond_model | six_carbon_ring, alternating_or_delocalized | svg: 20 primitives; 45.2 ms | 0.364 ms | PASS |
| heldout-018 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | coordination_geometry, bond_angles | three: ? primitives; 138.8 ms | 0.309 ms | PASS |
| heldout-019 | chemistry | interactive_visual / electrochemical_cell | svg / scene2d | zinc_concentration, copper_concentration | electron_anode_to_cathode, ion_migration | svg: 17 primitives; 64.9 ms | 0.324 ms | PASS |
| heldout-020 | chemistry | interactive_visual / kinetics | svg / scene2d | order, rate_constant | integrated_rate_law, half_life_behavior | svg: 37 primitives; 95.3 ms | 2.505 ms | PASS |
| heldout-021 | chemistry | interactive_visual / phase_diagram | svg / scene2d | temperature, pressure | phase_region, triple_point | svg: 31 primitives; 65.4 ms | 0.371 ms | PASS |
| heldout-022 | chemistry | interactive_visual / equilibrium_shift | svg / scene2d | pressure, temperature | stoichiometric_ratio, le_chatelier_direction | svg: 37 primitives; 66.2 ms | 0.399 ms | PASS |
| heldout-023 | biology | interactive_visual / enzyme_kinetics | svg / scene2d | substrate, inhibitor | vmax_limit, competitive_km_shift | svg: 29 primitives; 131.1 ms | 1.129 ms | PASS |
| heldout-024 | biology | interactive_visual / dna_replication | svg / scene2d | step, play, pause, restart | five_to_three_synthesis, strand_roles | svg: 23 primitives; 227.7 ms | 0.432 ms | PASS |
| heldout-025 | biology | interactive_visual / nephron | svg / scene2d | segment | flow_order, reabsorption_location | svg: 43 primitives; 53.5 ms | 0.477 ms | PASS |
| heldout-026 | biology | interactive_visual / predator_prey | canvas / simulation2d | prey_growth, predation, playback, play, pause, restart | population_nonnegative, phase_cycle | canvas: 824 primitives; 342.9 ms | 2.321 ms | PASS |
| heldout-027 | biology | interactive_visual / membrane_transport | svg / scene2d | transport_mode | gradient_direction, atp_only_active | svg: 23 primitives; 48.2 ms | 0.262 ms | PASS |
| heldout-028 | computer_science | interactive_visual / merge_sort | svg / scene2d | step, play, pause, restart | sorted_output, stable_merge | svg: 81 primitives; 232.9 ms | 0.719 ms | PASS |
| heldout-029 | computer_science | interactive_visual / hash_table | svg / scene2d | key, operation, step | bucket_hash, collision_chain | svg: 35 primitives; 90.6 ms | 0.400 ms | PASS |
| heldout-030 | computer_science | interactive_visual / graph_traversal | svg / scene2d | algorithm, step | frontier_policy, visits_once | svg: 23 primitives; 64.5 ms | 0.325 ms | PASS |
| heldout-031 | computer_science | interactive_visual / heap | svg / scene2d | operation, value, step, play, pause, restart | parent_not_greater_child, extracts_minimum | svg: 27 primitives; 272.1 ms | 0.407 ms | PASS |
| heldout-032 | computer_science | interactive_visual / recursion_stack | svg / scene2d | step | stack_lifo, factorial_result | svg: 39 primitives; 47.2 ms | 0.451 ms | PASS |
| heldout-033 | computer_science | interactive_visual / virtual_memory | svg / scene2d | address, step, play, pause, restart | page_offset_preserved, fault_path | svg: 25 primitives; 249.7 ms | 0.273 ms | PASS |
| heldout-034 | signals | interactive_visual / impulse_response | svg / scene2d | shift, step | discrete_convolution_sum, output_length | svg: 29 primitives; 68.7 ms | 0.310 ms | PASS |
| heldout-035 | controls | interactive_visual / bode_plot | svg / scene2d | cutoff | minus3db_at_cutoff, phase_transition | svg: 27 primitives; 75.3 ms | 0.906 ms | PASS |
| heldout-036 | controls | interactive_visual / nyquist | svg / scene2d | gain | encirclement_count, closed_loop_stability | svg: 27 primitives; 64.8 ms | 0.629 ms | PASS |
| heldout-037 | controls | interactive_visual / pid_response | svg / scene2d | kp, ki, kd | response_metrics, final_value | svg: 35 primitives; 183.2 ms | 1.385 ms | PASS |
| heldout-038 | signals | interactive_visual / pwm | svg / scene2d | duty_cycle | pulse_width_ratio, average_voltage | svg: 27 primitives; 53.1 ms | 0.427 ms | PASS |
| heldout-039 | signals | interactive_visual / spectrogram | canvas / simulation2d | sweep_rate, playback | frequency_rises_with_time, time_frequency_alignment | canvas: 4379 primitives; 127.9 ms | 2.626 ms | PASS |
| heldout-040 | robotics | interactive_visual / robot_arm | svg / scene2d | target_x, target_y, elbow_mode | link_lengths_constant, end_effector_target | svg: 13 primitives; 136.3 ms | 0.443 ms | PASS |
| heldout-041 | robotics | interactive_visual / kalman_filter | svg / scene2d | noise, step, play, pause, restart | covariance_contracts_on_update, estimate_between_prior_measurement | svg: 39 primitives; 345.5 ms | 1.480 ms | PASS |
| heldout-042 | engineering | interactive_visual / truss | svg / scene2d | load | joint_force_balance, member_sign | svg: 19 primitives; 48.1 ms | 0.409 ms | PASS |
| heldout-043 | engineering | interactive_visual / beam_bending | canvas / simulation2d | load_position, play, pause, restart | support_reactions, moment_zero_at_supports | canvas: 1682 primitives; 339 ms | 1.493 ms | PASS |
| heldout-044 | engineering | interactive_visual / fluid_flow | canvas / simulation2d | speed | streamline_symmetry, no_penetration | canvas: 1231 primitives; 95.4 ms | 12.331 ms | PASS |
| heldout-045 | engineering | interactive_visual / heat_diffusion | canvas / simulation2d | time, playback, play, pause, restart | temperature_smooths, energy_bounded | canvas: 4315 primitives; 323.7 ms | 1.765 ms | PASS |
| heldout-046 | computer_science | interactive_visual / state_machine | svg / scene2d | pedestrian_request, step | legal_transition, mutually_exclusive_lights | svg: 17 primitives; 69 ms | 0.342 ms | PASS |
| heldout-047 | ai | interactive_visual / decision_boundary | canvas / simulation2d | epoch, learning_rate | class_regions, loss_nonincreasing | canvas: 4355 primitives; 171.7 ms | 13.487 ms | PASS |
| heldout-048 | ai | interactive_visual / backprop_graph | svg / scene2d | w, x, b, step | chain_rule_gradients, forward_value | svg: 27 primitives; 108.7 ms | 0.652 ms | PASS |
| heldout-049 | mixed | interactive_visual / energy_sankey | svg / scene2d | efficiency | energy_conservation, units_joules | svg: 15 primitives; 45.1 ms | 0.366 ms | PASS |
| heldout-050 | mixed | interactive_visual / uncertainty_propagation | canvas / simulation2d | mass_sigma, volume_sigma, samples | positive_volume, density_distribution | canvas: 959 primitives; 139.2 ms | 1.616 ms | PASS |

## Reproduce

```bash
.venv/bin/python scripts/visualization_v2_gate.py --write
.venv/bin/python scripts/visualization_v2_browser_server.py --port 18084 \
  --output /tmp/muta-v2-browser-results.json \
  --matrix-output /tmp/muta-v2-browser-matrix.json \
  --lru-output /tmp/muta-v2-lru.json --directory .
# Open http://127.0.0.1:18084/ui/tests/visualization-v2-browser-gate.html?report=1
.venv/bin/python scripts/visualization_v2_gate.py --write \
  --browser-results /tmp/muta-v2-browser-results.json \
  --revision 6bce30843781052a63f28d5e116442f84a9e9dfe --pre-holdout-candidate-sha ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd --pre-holdout-frozen-at 2026-08-27T12:07:54+01:00
```

A pass requires intent, family, renderer, spec kind, exact named controls, accessible fallback, semantic oracles, and a real non-empty browser render. Presence of a canvas or WebGL context alone is never counted.
