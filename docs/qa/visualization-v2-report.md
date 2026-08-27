# Visualization V2 — 200-case acceptance report

Generated from production compiler code at `49237eb7938e68a6940afd5abfb36d7fc82d9fd9`.

Result: **200/200 passed**; 0 failed; zero cases waived.

## Frozen pre-holdout candidate

- SHA: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd`
- Frozen at: `2026-08-27T12:07:54+01:00`
- The separate post-implementation holdout was not opened before this candidate was frozen.

| ID | Domain | Intent / family | Renderer / spec | Controls | Invariants | Browser evidence | Compile | Result |
|---|---|---|---|---|---|---|---:|---|
| stem-001 | mathematics | interactive_visual / pythagoras | svg / scene2d | a, b | a2_plus_b2_equals_c2, square_areas | svg: 31 primitives; 98.3 ms | 1.635 ms | PASS |
| stem-002 | mathematics | interactive_visual / unit_circle | svg / scene2d | angle | point_on_unit_circle, sin_cos_projection | svg: 29 primitives; 42.9 ms | 0.726 ms | PASS |
| stem-003 | mathematics | interactive_visual / quadratic | svg / scene2d | a, b, c | semantic_relationship, labels_and_units, control_consistency | svg: 28 primitives; 85.6 ms | 2.450 ms | PASS |
| stem-004 | mathematics | interactive_visual / line_intersection | svg / scene2d | m1, c1, m2, c2 | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 110.2 ms | 1.413 ms | PASS |
| stem-005 | mathematics | interactive_visual / triangle_angles | svg / scene2d | vertex_a, vertex_b, vertex_c | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 90 ms | 0.289 ms | PASS |
| stem-006 | mathematics | interactive_visual / derivative_tangent | svg / scene2d | x | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 45.9 ms | 1.604 ms | PASS |
| stem-007 | mathematics | interactive_visual / riemann_sum | svg / scene2d | rectangles | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 43.7 ms | 0.848 ms | PASS |
| stem-008 | mathematics | interactive_visual / gradient_field | svg / scene2d | point_x, point_y | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 134 ms | 2.167 ms | PASS |
| stem-009 | mathematics | interactive_visual / plane_intersection | three / scene3d | orbit | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 191.9 ms | 1.275 ms | PASS |
| stem-010 | mathematics | interactive_visual / linear_transform | svg / scene2d | matrix | semantic_relationship, labels_and_units, control_consistency | svg: 59 primitives; 47.9 ms | 0.632 ms | PASS |
| stem-011 | physics | interactive_visual / projectile | svg / scene2d | angle, speed | trajectory_endpoints, range_height_units | svg: 29 primitives; 63.5 ms | 0.623 ms | PASS |
| stem-012 | physics | interactive_visual / inclined_plane | svg / scene2d | incline | semantic_relationship, labels_and_units, control_consistency | svg: 12 primitives; 44.2 ms | 0.322 ms | PASS |
| stem-013 | physics | interactive_visual / spring_mass | svg / scene2d | spring_constant, mass | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 64.2 ms | 0.315 ms | PASS |
| stem-014 | physics | interactive_visual / elastic_collision | svg / scene2d | mass_1, velocity_1, mass_2, velocity_2 | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 109.6 ms | 0.338 ms | PASS |
| stem-015 | physics | interactive_visual / pendulum | svg / scene2d | length, angle, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 251.2 ms | 0.494 ms | PASS |
| stem-016 | physics | interactive_visual / travelling_wave | canvas / simulation2d | amplitude, wavelength, frequency | semantic_relationship, labels_and_units, control_consistency | canvas: 1035 primitives; 95.7 ms | 0.646 ms | PASS |
| stem-017 | physics | interactive_visual / wave_interference | canvas / simulation2d | phase | semantic_relationship, labels_and_units, control_consistency | canvas: 916 primitives; 52.7 ms | 1.135 ms | PASS |
| stem-018 | physics | interactive_visual / circular_motion | svg / scene2d | angular_velocity | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 61.1 ms | 0.587 ms | PASS |
| stem-019 | physics | interactive_visual / harmonic_motion | canvas / simulation2d | spring_constant, mass, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | canvas: 1027 primitives; 330.9 ms | 0.964 ms | PASS |
| stem-020 | physics | interactive_visual / double_pendulum | canvas / simulation2d | angle_1, angle_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 1339 primitives; 131.1 ms | 4.164 ms | PASS |
| stem-021 | electromagnetism | interactive_visual / ohms_law_circuit | svg / scene2d | voltage, resistance, switch | current_v_over_r, current_direction | svg: 14 primitives; 88.5 ms | 0.416 ms | PASS |
| stem-022 | electromagnetism | interactive_visual / series_parallel_circuit | svg / scene2d | r1, r2, mode | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 87.2 ms | 0.305 ms | PASS |
| stem-023 | electromagnetism | interactive_visual / electric_field_lines | canvas / simulation2d | charge_1, charge_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 981 primitives; 106.6 ms | 3.997 ms | PASS |
| stem-024 | electromagnetism | interactive_visual / electric_field_vectors | canvas / simulation2d | test_x, test_y | semantic_relationship, labels_and_units, control_consistency | canvas: 752 primitives; 96.5 ms | 1.437 ms | PASS |
| stem-025 | electromagnetism | interactive_visual / magnetic_field_wire | canvas / simulation2d | current_direction | semantic_relationship, labels_and_units, control_consistency | canvas: 1085 primitives; 78.9 ms | 1.409 ms | PASS |
| stem-026 | electromagnetism | interactive_visual / rc_circuit | svg / scene2d | mode, resistance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 39 primitives; 134.4 ms | 0.963 ms | PASS |
| stem-027 | electromagnetism | interactive_visual / rlc_circuit | svg / scene2d | resistance, inductance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 41 primitives; 99 ms | 0.647 ms | PASS |
| stem-028 | electromagnetism | interactive_visual / ac_phase | svg / scene2d | load | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 51.7 ms | 1.290 ms | PASS |
| stem-029 | optics_thermodynamics | interactive_visual / converging_lens | svg / scene2d | object_distance | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 102.7 ms | 0.374 ms | PASS |
| stem-030 | optics_thermodynamics | interactive_visual / refraction | svg / scene2d | incident_angle, medium | snell_law, normal_and_ray_direction | svg: 15 primitives; 64.2 ms | 0.331 ms | PASS |
| stem-031 | optics_thermodynamics | interactive_visual / ideal_gas | svg / scene2d | pressure, volume, temperature | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 89.2 ms | 0.997 ms | PASS |
| stem-032 | optics_thermodynamics | interactive_visual / carnot_cycle | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 234.4 ms | 0.494 ms | PASS |
| stem-033 | chemistry | interactive_visual / atom | svg / scene2d | atomic_number | semantic_relationship, labels_and_units, control_consistency | svg: 46 primitives; 113.9 ms | 1.893 ms | PASS |
| stem-034 | chemistry | interactive_visual / ionic_bond | svg / scene2d | playback | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 98.9 ms | 0.327 ms | PASS |
| stem-035 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 148.2 ms | 0.353 ms | PASS |
| stem-036 | chemistry | interactive_visual / reaction_profile | svg / scene2d | catalyst | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 51 ms | 0.993 ms | PASS |
| stem-037 | chemistry | interactive_visual / titration | svg / scene2d | titrant_volume | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 95.3 ms | 1.027 ms | PASS |
| stem-038 | chemistry | interactive_visual / molecular_orbitals | svg / scene2d | orbital | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 101.4 ms | 0.488 ms | PASS |
| stem-039 | biology | interactive_visual / animal_cell | svg / scene2d | organelle | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 43.3 ms | 0.338 ms | PASS |
| stem-040 | biology | interactive_visual / mitosis | svg / scene2d | step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 44.9 ms | 0.336 ms | PASS |
| stem-041 | biology | interactive_visual / circulation | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 19 primitives; 239.4 ms | 0.383 ms | PASS |
| stem-042 | biology | interactive_visual / action_potential | svg / scene2d | time | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 74.5 ms | 1.359 ms | PASS |
| stem-043 | computer_science | interactive_visual / binary_search | svg / scene2d | target, step, play, pause, restart | interval_shrinks, target_found | svg: 15 primitives; 249.9 ms | 0.559 ms | PASS |
| stem-044 | computer_science | interactive_visual / binary_search_tree | svg / scene2d | insert, step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 307.8 ms | 0.416 ms | PASS |
| stem-045 | computer_science | interactive_visual / dijkstra | svg / scene2d | source, destination, step, play, pause, restart | nondecreasing_settled_distance, shortest_path | svg: 31 primitives; 279.9 ms | 0.413 ms | PASS |
| stem-046 | computer_science | interactive_visual / stack_queue | svg / scene2d | operation, step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 69.3 ms | 0.430 ms | PASS |
| stem-047 | computer_science | interactive_visual / cpu_memory | svg / scene2d | step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 233.5 ms | 0.732 ms | PASS |
| stem-048 | engineering_signals_robotics_ai | interactive_visual / sampling_aliasing | canvas / simulation2d | signal_frequency, sample_frequency | nyquist_condition, sample_locations | canvas: 1083 primitives; 154.4 ms | 1.879 ms | PASS |
| stem-049 | engineering_signals_robotics_ai | interactive_visual / differential_drive | canvas / simulation2d | left_velocity, right_velocity | curvature_from_wheel_speeds | canvas: 1066 primitives; 81.7 ms | 0.769 ms | PASS |
| stem-050 | engineering_signals_robotics_ai | interactive_visual / neural_network | svg / scene2d | weight, step | weighted_activation_flow | svg: 23 primitives; 66.1 ms | 0.470 ms | PASS |
| math-001 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.5 ms | 1.533 ms | PASS |
| math-002 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.7 ms | 1.416 ms | PASS |
| math-003 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.9 ms | 1.191 ms | PASS |
| math-004 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.6 ms | 1.437 ms | PASS |
| math-005 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.6 ms | 1.554 ms | PASS |
| math-006 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 306.8 ms | 1.145 ms | PASS |
| math-007 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.6 ms | 1.502 ms | PASS |
| math-008 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.2 ms | 1.268 ms | PASS |
| math-009 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.3 ms | 1.699 ms | PASS |
| math-010 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.9 ms | 1.910 ms | PASS |
| math-011 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.1 ms | 3.349 ms | PASS |
| math-012 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 1216 primitives; 275.5 ms | 1.833 ms | PASS |
| math-013 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.5 ms | 1.530 ms | PASS |
| math-014 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277 ms | 1.747 ms | PASS |
| math-015 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.3 ms | 1.885 ms | PASS |
| math-016 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293 ms | 0.711 ms | PASS |
| math-017 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 294.1 ms | 1.000 ms | PASS |
| math-018 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292 ms | 1.062 ms | PASS |
| math-019 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.5 ms | 1.724 ms | PASS |
| math-020 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.9 ms | 1.474 ms | PASS |
| math-021 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.1 ms | 0.665 ms | PASS |
| math-022 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292 ms | 1.162 ms | PASS |
| math-023 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 306.2 ms | 1.164 ms | PASS |
| math-024 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.6 ms | 0.933 ms | PASS |
| math-025 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.8 ms | 1.029 ms | PASS |
| math-026 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.5 ms | 1.400 ms | PASS |
| math-027 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.6 ms | 1.393 ms | PASS |
| math-028 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.7 ms | 1.724 ms | PASS |
| math-029 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 310.3 ms | 3.134 ms | PASS |
| math-030 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 326.5 ms | 1.642 ms | PASS |
| math-031 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.8 ms | 1.119 ms | PASS |
| math-032 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.1 ms | 1.119 ms | PASS |
| math-033 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.8 ms | 1.151 ms | PASS |
| math-034 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.4 ms | 0.964 ms | PASS |
| math-035 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.9 ms | 0.907 ms | PASS |
| math-036 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 302.3 ms | 1.544 ms | PASS |
| math-037 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 309.4 ms | 2.224 ms | PASS |
| math-038 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.3 ms | 1.708 ms | PASS |
| math-039 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.3 ms | 2.185 ms | PASS |
| math-040 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.1 ms | 4.064 ms | PASS |
| math-041 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.7 ms | 1.610 ms | PASS |
| math-042 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 308.7 ms | 2.154 ms | PASS |
| math-043 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.8 ms | 2.093 ms | PASS |
| math-044 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 343.1 ms | 2.398 ms | PASS |
| math-045 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.4 ms | 4.240 ms | PASS |
| math-046 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 308.5 ms | 6.364 ms | PASS |
| math-047 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.2 ms | 1.934 ms | PASS |
| math-048 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.3 ms | 2.019 ms | PASS |
| math-049 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.6 ms | 2.204 ms | PASS |
| math-050 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.9 ms | 2.791 ms | PASS |
| math-051 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 294.2 ms | 1.935 ms | PASS |
| math-052 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.1 ms | 2.478 ms | PASS |
| math-053 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4584 primitives; 295.3 ms | 2.358 ms | PASS |
| math-054 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 294.1 ms | 3.476 ms | PASS |
| math-055 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.8 ms | 1.598 ms | PASS |
| math-056 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293 ms | 1.891 ms | PASS |
| math-057 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 293.2 ms | 1.482 ms | PASS |
| math-058 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 293.3 ms | 1.516 ms | PASS |
| math-059 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 292 ms | 1.568 ms | PASS |
| math-060 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 308.2 ms | 2.163 ms | PASS |
| math-061 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 309.2 ms | 2.305 ms | PASS |
| math-062 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4140 primitives; 291.2 ms | 0.986 ms | PASS |
| math-063 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4120 primitives; 291 ms | 1.508 ms | PASS |
| math-064 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 293.2 ms | 2.685 ms | PASS |
| math-065 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4232 primitives; 308.7 ms | 1.755 ms | PASS |
| math-066 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 12024 primitives; 408.3 ms | 98.674 ms | PASS |
| math-067 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9296 primitives; 392.4 ms | 132.457 ms | PASS |
| math-068 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18440 primitives; 424.6 ms | 88.855 ms | PASS |
| math-069 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19928 primitives; 426.5 ms | 111.973 ms | PASS |
| math-070 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15624 primitives; 408.7 ms | 76.016 ms | PASS |
| math-071 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 14632 primitives; 407.5 ms | 100.032 ms | PASS |
| math-072 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 21576 primitives; 443.5 ms | 77.652 ms | PASS |
| math-073 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15004 primitives; 443.3 ms | 56.393 ms | PASS |
| math-074 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19560 primitives; 413 ms | 100.632 ms | PASS |
| math-075 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18104 primitives; 427.1 ms | 103.276 ms | PASS |
| math-076 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9588 primitives; 392 ms | 77.105 ms | PASS |
| math-077 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293 ms | 1.355 ms | PASS |
| math-078 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 11864 primitives; 392.7 ms | 202.262 ms | PASS |
| math-079 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9288 primitives; 394.2 ms | 99.848 ms | PASS |
| math-080 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 5616 primitives; 392.5 ms | 94.753 ms | PASS |
| math-081 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 392.7 ms | 133.641 ms | PASS |
| math-082 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 392.9 ms | 169.576 ms | PASS |
| math-083 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7408 primitives; 373.4 ms | 133.458 ms | PASS |
| math-084 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9024 primitives; 392.1 ms | 145.655 ms | PASS |
| math-085 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 307.9 ms | 4.570 ms | PASS |
| math-086 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 310 ms | 1.855 ms | PASS |
| math-087 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7880 primitives; 376.1 ms | 161.991 ms | PASS |
| math-088 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 13680 primitives; 409.4 ms | 77.703 ms | PASS |
| math-089 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 96 primitives; 358.5 ms | 190.136 ms | PASS |
| math-090 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 3000 primitives; 375.3 ms | 261.955 ms | PASS |
| math-091 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 26594 primitives; 493.7 ms | 6.124 ms | PASS |
| math-092 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20252 primitives; 437.5 ms | 3.216 ms | PASS |
| math-093 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20196 primitives; 446.1 ms | 3.278 ms | PASS |
| math-094 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20624 primitives; 459.9 ms | 5.975 ms | PASS |
| math-095 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.9 ms | 1.314 ms | PASS |
| math-096 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.9 ms | 3.393 ms | PASS |
| math-097 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4600 primitives; 308.2 ms | 3.226 ms | PASS |
| math-098 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 293.6 ms | 1.560 ms | PASS |
| math-099 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.9 ms | 2.004 ms | PASS |
| math-100 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 310.4 ms | 5.148 ms | PASS |
| heldout-001 | mathematics | interactive_visual / complex_mapping | svg / scene2d | point_angle, point_radius | complex_square_mapping, angle_doubles | svg: 71 primitives; 167.2 ms | 3.162 ms | PASS |
| heldout-002 | mathematics | interactive_visual / polar_plot | svg / scene2d | theta, playback, play, pause, restart | polar_radius, four_petals | svg: 35 primitives; 287.3 ms | 1.363 ms | PASS |
| heldout-003 | mathematics | interactive_visual / fourier_series | svg / scene2d | terms | odd_harmonics, gibbs_overshoot | svg: 36 primitives; 86.1 ms | 1.843 ms | PASS |
| heldout-004 | mathematics | interactive_visual / logistic_map | canvas / simulation2d | growth_rate, initial_value | iterate_logistic, bounded_unit_interval | canvas: 1045 primitives; 135.2 ms | 4.322 ms | PASS |
| heldout-005 | mathematics | interactive_visual / lagrange_multiplier | svg / scene2d | constraint_offset | tangent_contours, parallel_gradients | svg: 37 primitives; 60.1 ms | 1.691 ms | PASS |
| heldout-006 | mathematics | interactive_visual / parametric_surface | three / scene3d | path_position, playback | mobius_single_boundary, parametric_samples | three: 1890 primitives; 325.7 ms | 0.574 ms | PASS |
| heldout-007 | mathematics | interactive_visual / vector_field | svg / scene2d | probe_x, probe_y | field_components, divergence_zero | svg: 49 primitives; 73.8 ms | 0.595 ms | PASS |
| heldout-008 | mathematics | interactive_visual / convolution | svg / scene2d | shift | overlap_equals_convolution, triangular_result | svg: 33 primitives; 46 ms | 0.593 ms | PASS |
| heldout-009 | physics | interactive_visual / kepler_orbit | canvas / simulation2d | eccentricity, true_anomaly, playback, play, pause, restart | acceleration_inward, equal_area | canvas: 885 primitives; 291 ms | 0.767 ms | PASS |
| heldout-010 | physics | interactive_visual / coupled_oscillators | canvas / simulation2d | mode, playback, play, pause, restart | normal_mode_phase, energy_bounded | canvas: 1090 primitives; 285.9 ms | 1.031 ms | PASS |
| heldout-011 | physics | interactive_visual / standing_wave | svg / scene2d | harmonic | node_count, fixed_endpoints | svg: 41 primitives; 48.9 ms | 0.570 ms | PASS |
| heldout-012 | physics | interactive_visual / doppler | canvas / simulation2d | source_speed, playback | front_wavelength_shorter, wavefront_spacing | canvas: 722 primitives; 146.4 ms | 1.429 ms | PASS |
| heldout-013 | physics | interactive_visual / double_slit | svg / scene2d | slit_separation, wavelength | fringe_spacing, central_maximum | svg: 39 primitives; 95.7 ms | 0.774 ms | PASS |
| heldout-014 | physics | interactive_visual / lorentz_force | three / scene3d | charge, field, speed, playback, play, pause, restart | force_perpendicular_velocity, helix_radius | three: ? primitives; 749.3 ms | 0.635 ms | PASS |
| heldout-015 | physics | interactive_visual / blackbody | svg / scene2d | temperature | peak_shifts_shorter, radiance_positive | svg: 32 primitives; 52.8 ms | 1.403 ms | PASS |
| heldout-016 | physics | interactive_visual / entropy_cycle | canvas / simulation2d | step | closed_cycle, process_direction | canvas: 985 primitives; 46.3 ms | 0.457 ms | PASS |
| heldout-017 | chemistry | interactive_visual / benzene | svg / scene2d | bond_model | six_carbon_ring, alternating_or_delocalized | svg: 20 primitives; 41.3 ms | 0.371 ms | PASS |
| heldout-018 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | coordination_geometry, bond_angles | three: ? primitives; 140.2 ms | 0.327 ms | PASS |
| heldout-019 | chemistry | interactive_visual / electrochemical_cell | svg / scene2d | zinc_concentration, copper_concentration | electron_anode_to_cathode, ion_migration | svg: 17 primitives; 68 ms | 0.346 ms | PASS |
| heldout-020 | chemistry | interactive_visual / kinetics | svg / scene2d | order, rate_constant | integrated_rate_law, half_life_behavior | svg: 37 primitives; 92.1 ms | 2.664 ms | PASS |
| heldout-021 | chemistry | interactive_visual / phase_diagram | svg / scene2d | temperature, pressure | phase_region, triple_point | svg: 31 primitives; 97.4 ms | 0.376 ms | PASS |
| heldout-022 | chemistry | interactive_visual / equilibrium_shift | svg / scene2d | pressure, temperature | stoichiometric_ratio, le_chatelier_direction | svg: 37 primitives; 65.6 ms | 0.455 ms | PASS |
| heldout-023 | biology | interactive_visual / enzyme_kinetics | svg / scene2d | substrate, inhibitor | vmax_limit, competitive_km_shift | svg: 29 primitives; 139.1 ms | 1.073 ms | PASS |
| heldout-024 | biology | interactive_visual / dna_replication | svg / scene2d | step, play, pause, restart | five_to_three_synthesis, strand_roles | svg: 23 primitives; 265.4 ms | 0.385 ms | PASS |
| heldout-025 | biology | interactive_visual / nephron | svg / scene2d | segment | flow_order, reabsorption_location | svg: 43 primitives; 48.5 ms | 0.466 ms | PASS |
| heldout-026 | biology | interactive_visual / predator_prey | canvas / simulation2d | prey_growth, predation, playback, play, pause, restart | population_nonnegative, phase_cycle | canvas: 1005 primitives; 311.5 ms | 2.466 ms | PASS |
| heldout-027 | biology | interactive_visual / membrane_transport | svg / scene2d | transport_mode | gradient_direction, atp_only_active | svg: 23 primitives; 43.3 ms | 0.261 ms | PASS |
| heldout-028 | computer_science | interactive_visual / merge_sort | svg / scene2d | step, play, pause, restart | sorted_output, stable_merge | svg: 81 primitives; 232.2 ms | 0.761 ms | PASS |
| heldout-029 | computer_science | interactive_visual / hash_table | svg / scene2d | key, operation, step | bucket_hash, collision_chain | svg: 35 primitives; 119.4 ms | 0.430 ms | PASS |
| heldout-030 | computer_science | interactive_visual / graph_traversal | svg / scene2d | algorithm, step | frontier_policy, visits_once | svg: 23 primitives; 64.5 ms | 0.334 ms | PASS |
| heldout-031 | computer_science | interactive_visual / heap | svg / scene2d | operation, value, step, play, pause, restart | parent_not_greater_child, extracts_minimum | svg: 27 primitives; 276.5 ms | 0.485 ms | PASS |
| heldout-032 | computer_science | interactive_visual / recursion_stack | svg / scene2d | step | stack_lifo, factorial_result | svg: 39 primitives; 44.9 ms | 0.541 ms | PASS |
| heldout-033 | computer_science | interactive_visual / virtual_memory | svg / scene2d | address, step, play, pause, restart | page_offset_preserved, fault_path | svg: 25 primitives; 252.2 ms | 0.316 ms | PASS |
| heldout-034 | signals | interactive_visual / impulse_response | svg / scene2d | shift, step | discrete_convolution_sum, output_length | svg: 29 primitives; 69.1 ms | 0.305 ms | PASS |
| heldout-035 | controls | interactive_visual / bode_plot | svg / scene2d | cutoff | minus3db_at_cutoff, phase_transition | svg: 27 primitives; 55.9 ms | 0.916 ms | PASS |
| heldout-036 | controls | interactive_visual / nyquist | svg / scene2d | gain | encirclement_count, closed_loop_stability | svg: 27 primitives; 103 ms | 0.552 ms | PASS |
| heldout-037 | controls | interactive_visual / pid_response | svg / scene2d | kp, ki, kd | response_metrics, final_value | svg: 35 primitives; 142.8 ms | 1.429 ms | PASS |
| heldout-038 | signals | interactive_visual / pwm | svg / scene2d | duty_cycle | pulse_width_ratio, average_voltage | svg: 27 primitives; 54.5 ms | 0.418 ms | PASS |
| heldout-039 | signals | interactive_visual / spectrogram | canvas / simulation2d | sweep_rate, playback | frequency_rises_with_time, time_frequency_alignment | canvas: 2056 primitives; 135.4 ms | 2.654 ms | PASS |
| heldout-040 | robotics | interactive_visual / robot_arm | svg / scene2d | target_x, target_y, elbow_mode | link_lengths_constant, end_effector_target | svg: 13 primitives; 133.8 ms | 0.363 ms | PASS |
| heldout-041 | robotics | interactive_visual / kalman_filter | svg / scene2d | noise, step, play, pause, restart | covariance_contracts_on_update, estimate_between_prior_measurement | svg: 39 primitives; 350.7 ms | 1.680 ms | PASS |
| heldout-042 | engineering | interactive_visual / truss | svg / scene2d | load | joint_force_balance, member_sign | svg: 19 primitives; 47.4 ms | 0.359 ms | PASS |
| heldout-043 | engineering | interactive_visual / beam_bending | canvas / simulation2d | load_position, play, pause, restart | support_reactions, moment_zero_at_supports | canvas: 1603 primitives; 351.2 ms | 1.565 ms | PASS |
| heldout-044 | engineering | interactive_visual / fluid_flow | canvas / simulation2d | speed | streamline_symmetry, no_penetration | canvas: 855 primitives; 118.4 ms | 12.094 ms | PASS |
| heldout-045 | engineering | interactive_visual / heat_diffusion | canvas / simulation2d | time, playback, play, pause, restart | temperature_smooths, energy_bounded | canvas: 2053 primitives; 296.7 ms | 1.887 ms | PASS |
| heldout-046 | computer_science | interactive_visual / state_machine | svg / scene2d | pedestrian_request, step | legal_transition, mutually_exclusive_lights | svg: 17 primitives; 104.4 ms | 0.377 ms | PASS |
| heldout-047 | ai | interactive_visual / decision_boundary | canvas / simulation2d | epoch, learning_rate | class_regions, loss_nonincreasing | canvas: 2069 primitives; 134.4 ms | 13.416 ms | PASS |
| heldout-048 | ai | interactive_visual / backprop_graph | svg / scene2d | w, x, b, step | chain_rule_gradients, forward_value | svg: 27 primitives; 108.3 ms | 0.611 ms | PASS |
| heldout-049 | mixed | interactive_visual / energy_sankey | svg / scene2d | efficiency | energy_conservation, units_joules | svg: 15 primitives; 44.4 ms | 0.366 ms | PASS |
| heldout-050 | mixed | interactive_visual / uncertainty_propagation | canvas / simulation2d | mass_sigma, volume_sigma, samples | positive_volume, density_distribution | canvas: 903 primitives; 147.5 ms | 1.850 ms | PASS |

## Reproduce

Capture real-browser evidence first, then merge that evidence into the checked-in report. The compiler-only command intentionally does not write a passing acceptance report without browser results.

```bash
.venv/bin/python scripts/visualization_v2_browser_server.py --port 18084 \
  --output /tmp/muta-v2-browser-results.json \
  --matrix-output /tmp/muta-v2-browser-matrix.json \
  --lru-output /tmp/muta-v2-lru.json --directory .
# Open http://127.0.0.1:18084/ui/tests/visualization-v2-browser-gate.html?report=1
.venv/bin/python scripts/visualization_v2_gate.py --write \
  --browser-results /tmp/muta-v2-browser-results.json \
  --revision 49237eb7938e68a6940afd5abfb36d7fc82d9fd9 --pre-holdout-candidate-sha ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd --pre-holdout-frozen-at 2026-08-27T12:07:54+01:00
```

A pass requires intent, family, renderer, spec kind, exact named controls, accessible fallback, semantic oracles, and a real non-empty browser render. Presence of a canvas or WebGL context alone is never counted.
