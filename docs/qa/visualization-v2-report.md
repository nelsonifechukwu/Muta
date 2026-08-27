# Visualization V2 — 200-case acceptance report

Generated from production compiler code at `e71e294299311d092fb450c989eec9a9c8ef0f0f`.

Result: **200/200 passed**; 0 failed; zero cases waived.

## Frozen pre-holdout candidate

- SHA: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd`
- Frozen at: `2026-08-27T12:07:54+01:00`
- The separate post-implementation holdout was not opened before this candidate was frozen.

| ID | Domain | Intent / family | Renderer / spec | Controls | Invariants | Browser evidence | Compile | Result |
|---|---|---|---|---|---|---|---:|---|
| stem-001 | mathematics | interactive_visual / pythagoras | svg / scene2d | a, b | a2_plus_b2_equals_c2, square_areas | svg: 31 primitives; 81.4 ms | 2.082 ms | PASS |
| stem-002 | mathematics | interactive_visual / unit_circle | svg / scene2d | angle | point_on_unit_circle, sin_cos_projection | svg: 29 primitives; 48.2 ms | 0.941 ms | PASS |
| stem-003 | mathematics | interactive_visual / quadratic | svg / scene2d | a, b, c | semantic_relationship, labels_and_units, control_consistency | svg: 28 primitives; 91.2 ms | 3.094 ms | PASS |
| stem-004 | mathematics | interactive_visual / line_intersection | svg / scene2d | m1, c1, m2, c2 | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 114.7 ms | 2.092 ms | PASS |
| stem-005 | mathematics | interactive_visual / triangle_angles | svg / scene2d | vertex_a, vertex_b, vertex_c | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 91.2 ms | 0.415 ms | PASS |
| stem-006 | mathematics | interactive_visual / derivative_tangent | svg / scene2d | x | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 47.6 ms | 1.675 ms | PASS |
| stem-007 | mathematics | interactive_visual / riemann_sum | svg / scene2d | rectangles | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 46.1 ms | 1.184 ms | PASS |
| stem-008 | mathematics | interactive_visual / gradient_field | svg / scene2d | point_x, point_y | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 69.8 ms | 2.908 ms | PASS |
| stem-009 | mathematics | interactive_visual / plane_intersection | three / scene3d | orbit | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 158.1 ms | 1.561 ms | PASS |
| stem-010 | mathematics | interactive_visual / linear_transform | svg / scene2d | matrix | semantic_relationship, labels_and_units, control_consistency | svg: 59 primitives; 50.5 ms | 0.864 ms | PASS |
| stem-011 | physics | interactive_visual / projectile | svg / scene2d | angle, speed | trajectory_endpoints, range_height_units | svg: 29 primitives; 69.9 ms | 0.883 ms | PASS |
| stem-012 | physics | interactive_visual / inclined_plane | svg / scene2d | incline | semantic_relationship, labels_and_units, control_consistency | svg: 12 primitives; 52.9 ms | 0.459 ms | PASS |
| stem-013 | physics | interactive_visual / spring_mass | svg / scene2d | spring_constant, mass | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 70.2 ms | 0.453 ms | PASS |
| stem-014 | physics | interactive_visual / elastic_collision | svg / scene2d | mass_1, velocity_1, mass_2, velocity_2 | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 114.8 ms | 0.483 ms | PASS |
| stem-015 | physics | interactive_visual / pendulum | svg / scene2d | length, angle, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 256.1 ms | 0.706 ms | PASS |
| stem-016 | physics | interactive_visual / travelling_wave | canvas / simulation2d | amplitude, wavelength, frequency | semantic_relationship, labels_and_units, control_consistency | canvas: 776 primitives; 100.3 ms | 1.351 ms | PASS |
| stem-017 | physics | interactive_visual / wave_interference | canvas / simulation2d | phase | semantic_relationship, labels_and_units, control_consistency | canvas: 820 primitives; 72.8 ms | 1.582 ms | PASS |
| stem-018 | physics | interactive_visual / circular_motion | svg / scene2d | angular_velocity | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 46.4 ms | 0.869 ms | PASS |
| stem-019 | physics | interactive_visual / harmonic_motion | canvas / simulation2d | spring_constant, mass, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | canvas: 876 primitives; 262.5 ms | 1.367 ms | PASS |
| stem-020 | physics | interactive_visual / double_pendulum | canvas / simulation2d | angle_1, angle_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 1134 primitives; 124.8 ms | 5.887 ms | PASS |
| stem-021 | electromagnetism | interactive_visual / ohms_law_circuit | svg / scene2d | voltage, resistance, switch | current_v_over_r, current_direction | svg: 14 primitives; 103.9 ms | 0.650 ms | PASS |
| stem-022 | electromagnetism | interactive_visual / series_parallel_circuit | svg / scene2d | r1, r2, mode | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 89.5 ms | 0.448 ms | PASS |
| stem-023 | electromagnetism | interactive_visual / electric_field_lines | canvas / simulation2d | charge_1, charge_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 893 primitives; 102.5 ms | 5.287 ms | PASS |
| stem-024 | electromagnetism | interactive_visual / electric_field_vectors | canvas / simulation2d | test_x, test_y | semantic_relationship, labels_and_units, control_consistency | canvas: 461 primitives; 74.8 ms | 1.988 ms | PASS |
| stem-025 | electromagnetism | interactive_visual / magnetic_field_wire | canvas / simulation2d | current_direction | semantic_relationship, labels_and_units, control_consistency | canvas: 1182 primitives; 54.7 ms | 1.967 ms | PASS |
| stem-026 | electromagnetism | interactive_visual / rc_circuit | svg / scene2d | mode, resistance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 39 primitives; 179.9 ms | 1.330 ms | PASS |
| stem-027 | electromagnetism | interactive_visual / rlc_circuit | svg / scene2d | resistance, inductance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 41 primitives; 92.5 ms | 0.856 ms | PASS |
| stem-028 | electromagnetism | interactive_visual / ac_phase | svg / scene2d | load | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 61.4 ms | 1.766 ms | PASS |
| stem-029 | optics_thermodynamics | interactive_visual / converging_lens | svg / scene2d | object_distance | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 101.4 ms | 0.506 ms | PASS |
| stem-030 | optics_thermodynamics | interactive_visual / refraction | svg / scene2d | incident_angle, medium | snell_law, normal_and_ray_direction | svg: 15 primitives; 68.5 ms | 0.435 ms | PASS |
| stem-031 | optics_thermodynamics | interactive_visual / ideal_gas | svg / scene2d | pressure, volume, temperature | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 89.7 ms | 1.389 ms | PASS |
| stem-032 | optics_thermodynamics | interactive_visual / carnot_cycle | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 232.6 ms | 0.643 ms | PASS |
| stem-033 | chemistry | interactive_visual / atom | svg / scene2d | atomic_number | semantic_relationship, labels_and_units, control_consistency | svg: 46 primitives; 117 ms | 2.371 ms | PASS |
| stem-034 | chemistry | interactive_visual / ionic_bond | svg / scene2d | playback | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 47.1 ms | 0.418 ms | PASS |
| stem-035 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 151 ms | 0.483 ms | PASS |
| stem-036 | chemistry | interactive_visual / reaction_profile | svg / scene2d | catalyst | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 52.6 ms | 1.275 ms | PASS |
| stem-037 | chemistry | interactive_visual / titration | svg / scene2d | titrant_volume | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 141.4 ms | 1.464 ms | PASS |
| stem-038 | chemistry | interactive_visual / molecular_orbitals | svg / scene2d | orbital | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 98.2 ms | 0.693 ms | PASS |
| stem-039 | biology | interactive_visual / animal_cell | svg / scene2d | organelle | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 46 ms | 0.459 ms | PASS |
| stem-040 | biology | interactive_visual / mitosis | svg / scene2d | step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 46 ms | 0.459 ms | PASS |
| stem-041 | biology | interactive_visual / circulation | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 19 primitives; 232.5 ms | 0.509 ms | PASS |
| stem-042 | biology | interactive_visual / action_potential | svg / scene2d | time | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 78.6 ms | 1.836 ms | PASS |
| stem-043 | computer_science | interactive_visual / binary_search | svg / scene2d | target, step, play, pause, restart | interval_shrinks, target_found | svg: 15 primitives; 253.3 ms | 0.730 ms | PASS |
| stem-044 | computer_science | interactive_visual / binary_search_tree | svg / scene2d | insert, step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 265.6 ms | 0.530 ms | PASS |
| stem-045 | computer_science | interactive_visual / dijkstra | svg / scene2d | source, destination, step, play, pause, restart | nondecreasing_settled_distance, shortest_path | svg: 31 primitives; 284 ms | 0.628 ms | PASS |
| stem-046 | computer_science | interactive_visual / stack_queue | svg / scene2d | operation, step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 78.9 ms | 0.604 ms | PASS |
| stem-047 | computer_science | interactive_visual / cpu_memory | svg / scene2d | step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 230.4 ms | 1.000 ms | PASS |
| stem-048 | engineering_signals_robotics_ai | interactive_visual / sampling_aliasing | canvas / simulation2d | signal_frequency, sample_frequency | nyquist_condition, sample_locations | canvas: 1094 primitives; 114 ms | 2.592 ms | PASS |
| stem-049 | engineering_signals_robotics_ai | interactive_visual / differential_drive | canvas / simulation2d | left_velocity, right_velocity | curvature_from_wheel_speeds | canvas: 790 primitives; 96.4 ms | 1.064 ms | PASS |
| stem-050 | engineering_signals_robotics_ai | interactive_visual / neural_network | svg / scene2d | weight, step | weighted_activation_flow | svg: 23 primitives; 69 ms | 0.631 ms | PASS |
| math-001 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.9 ms | 2.173 ms | PASS |
| math-002 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.5 ms | 1.795 ms | PASS |
| math-003 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.4 ms | 1.777 ms | PASS |
| math-004 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284.6 ms | 2.126 ms | PASS |
| math-005 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.7 ms | 2.272 ms | PASS |
| math-006 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.7 ms | 1.666 ms | PASS |
| math-007 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.5 ms | 2.094 ms | PASS |
| math-008 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.7 ms | 1.754 ms | PASS |
| math-009 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.8 ms | 2.561 ms | PASS |
| math-010 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 294.2 ms | 2.804 ms | PASS |
| math-011 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.3 ms | 4.784 ms | PASS |
| math-012 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 1216 primitives; 284.6 ms | 2.506 ms | PASS |
| math-013 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286 ms | 2.142 ms | PASS |
| math-014 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284.5 ms | 2.190 ms | PASS |
| math-015 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.3 ms | 2.535 ms | PASS |
| math-016 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 285.2 ms | 0.964 ms | PASS |
| math-017 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.8 ms | 1.348 ms | PASS |
| math-018 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.5 ms | 1.350 ms | PASS |
| math-019 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 298.1 ms | 2.549 ms | PASS |
| math-020 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.8 ms | 2.195 ms | PASS |
| math-021 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 282.6 ms | 0.937 ms | PASS |
| math-022 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287 ms | 1.677 ms | PASS |
| math-023 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.7 ms | 1.684 ms | PASS |
| math-024 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.2 ms | 1.334 ms | PASS |
| math-025 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284.7 ms | 1.324 ms | PASS |
| math-026 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 285.1 ms | 2.108 ms | PASS |
| math-027 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.4 ms | 2.109 ms | PASS |
| math-028 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 289.9 ms | 2.493 ms | PASS |
| math-029 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 320.9 ms | 4.560 ms | PASS |
| math-030 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.3 ms | 2.414 ms | PASS |
| math-031 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.4 ms | 1.659 ms | PASS |
| math-032 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.4 ms | 1.667 ms | PASS |
| math-033 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.4 ms | 1.675 ms | PASS |
| math-034 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.9 ms | 1.344 ms | PASS |
| math-035 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.9 ms | 1.313 ms | PASS |
| math-036 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.1 ms | 2.122 ms | PASS |
| math-037 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 305.5 ms | 3.135 ms | PASS |
| math-038 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.5 ms | 2.435 ms | PASS |
| math-039 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.9 ms | 3.073 ms | PASS |
| math-040 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 296.4 ms | 5.767 ms | PASS |
| math-041 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 282.7 ms | 2.384 ms | PASS |
| math-042 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.1 ms | 3.144 ms | PASS |
| math-043 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284.7 ms | 2.929 ms | PASS |
| math-044 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.2 ms | 3.174 ms | PASS |
| math-045 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 296.5 ms | 6.040 ms | PASS |
| math-046 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 294.8 ms | 9.140 ms | PASS |
| math-047 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284.3 ms | 2.757 ms | PASS |
| math-048 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 282.9 ms | 2.730 ms | PASS |
| math-049 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 285.3 ms | 3.121 ms | PASS |
| math-050 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.2 ms | 4.377 ms | PASS |
| math-051 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 289.2 ms | 2.723 ms | PASS |
| math-052 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.5 ms | 3.463 ms | PASS |
| math-053 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4584 primitives; 292.1 ms | 3.460 ms | PASS |
| math-054 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 295.3 ms | 4.972 ms | PASS |
| math-055 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.2 ms | 2.227 ms | PASS |
| math-056 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 297.2 ms | 2.551 ms | PASS |
| math-057 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 300.7 ms | 2.194 ms | PASS |
| math-058 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 296.2 ms | 2.184 ms | PASS |
| math-059 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 295.4 ms | 2.184 ms | PASS |
| math-060 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 298.6 ms | 2.946 ms | PASS |
| math-061 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 298.2 ms | 3.404 ms | PASS |
| math-062 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4140 primitives; 289 ms | 1.415 ms | PASS |
| math-063 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4120 primitives; 296.7 ms | 2.175 ms | PASS |
| math-064 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 298.9 ms | 3.733 ms | PASS |
| math-065 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4232 primitives; 294.2 ms | 2.453 ms | PASS |
| math-066 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 12024 primitives; 432.9 ms | 141.390 ms | PASS |
| math-067 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9296 primitives; 422.1 ms | 190.804 ms | PASS |
| math-068 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18440 primitives; 456.4 ms | 128.036 ms | PASS |
| math-069 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19928 primitives; 468.3 ms | 160.932 ms | PASS |
| math-070 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15624 primitives; 442.2 ms | 107.562 ms | PASS |
| math-071 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 14632 primitives; 449.9 ms | 139.436 ms | PASS |
| math-072 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 21576 primitives; 466.7 ms | 109.963 ms | PASS |
| math-073 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15004 primitives; 472.3 ms | 79.684 ms | PASS |
| math-074 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19560 primitives; 468.2 ms | 143.278 ms | PASS |
| math-075 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18104 primitives; 470.8 ms | 143.678 ms | PASS |
| math-076 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9588 primitives; 413.4 ms | 108.142 ms | PASS |
| math-077 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 285.1 ms | 1.926 ms | PASS |
| math-078 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 11864 primitives; 439.3 ms | 292.775 ms | PASS |
| math-079 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9288 primitives; 423.7 ms | 149.379 ms | PASS |
| math-080 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 5616 primitives; 424.1 ms | 139.412 ms | PASS |
| math-081 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 434.3 ms | 199.689 ms | PASS |
| math-082 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 428.1 ms | 240.112 ms | PASS |
| math-083 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7408 primitives; 425.2 ms | 185.478 ms | PASS |
| math-084 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9024 primitives; 420.3 ms | 202.897 ms | PASS |
| math-085 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 294.6 ms | 6.336 ms | PASS |
| math-086 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.2 ms | 2.610 ms | PASS |
| math-087 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7880 primitives; 430.8 ms | 206.646 ms | PASS |
| math-088 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 13680 primitives; 437.7 ms | 110.272 ms | PASS |
| math-089 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 96 primitives; 389.9 ms | 269.454 ms | PASS |
| math-090 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 3000 primitives; 413.4 ms | 364.879 ms | PASS |
| math-091 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 26594 primitives; 537.5 ms | 8.381 ms | PASS |
| math-092 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20252 primitives; 483.9 ms | 4.498 ms | PASS |
| math-093 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20196 primitives; 481 ms | 4.495 ms | PASS |
| math-094 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20624 primitives; 512.8 ms | 8.535 ms | PASS |
| math-095 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 289.7 ms | 1.810 ms | PASS |
| math-096 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 292.2 ms | 4.782 ms | PASS |
| math-097 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4600 primitives; 301.3 ms | 4.607 ms | PASS |
| math-098 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 285.3 ms | 2.189 ms | PASS |
| math-099 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293 ms | 2.507 ms | PASS |
| math-100 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 313.1 ms | 7.135 ms | PASS |
| heldout-001 | mathematics | interactive_visual / complex_mapping | svg / scene2d | point_angle, point_radius | complex_square_mapping, angle_doubles | svg: 71 primitives; 154.1 ms | 3.908 ms | PASS |
| heldout-002 | mathematics | interactive_visual / polar_plot | svg / scene2d | theta, playback, play, pause, restart | polar_radius, four_petals | svg: 35 primitives; 281.1 ms | 1.827 ms | PASS |
| heldout-003 | mathematics | interactive_visual / fourier_series | svg / scene2d | terms | odd_harmonics, gibbs_overshoot | svg: 36 primitives; 97.9 ms | 2.541 ms | PASS |
| heldout-004 | mathematics | interactive_visual / logistic_map | canvas / simulation2d | growth_rate, initial_value | iterate_logistic, bounded_unit_interval | canvas: 1085 primitives; 122 ms | 5.568 ms | PASS |
| heldout-005 | mathematics | interactive_visual / lagrange_multiplier | svg / scene2d | constraint_offset | tangent_contours, parallel_gradients | svg: 37 primitives; 67.4 ms | 2.194 ms | PASS |
| heldout-006 | mathematics | interactive_visual / parametric_surface | three / scene3d | path_position, playback | mobius_single_boundary, parametric_samples | three: 1890 primitives; 266.7 ms | 0.753 ms | PASS |
| heldout-007 | mathematics | interactive_visual / vector_field | svg / scene2d | probe_x, probe_y | field_components, divergence_zero | svg: 49 primitives; 74.9 ms | 0.833 ms | PASS |
| heldout-008 | mathematics | interactive_visual / convolution | svg / scene2d | shift | overlap_equals_convolution, triangular_result | svg: 33 primitives; 46 ms | 0.791 ms | PASS |
| heldout-009 | physics | interactive_visual / kepler_orbit | canvas / simulation2d | eccentricity, true_anomaly, playback, play, pause, restart | acceleration_inward, equal_area | canvas: 968 primitives; 285 ms | 1.032 ms | PASS |
| heldout-010 | physics | interactive_visual / coupled_oscillators | canvas / simulation2d | mode, playback, play, pause, restart | normal_mode_phase, energy_bounded | canvas: 1064 primitives; 348.9 ms | 1.361 ms | PASS |
| heldout-011 | physics | interactive_visual / standing_wave | svg / scene2d | harmonic | node_count, fixed_endpoints | svg: 41 primitives; 52.7 ms | 0.732 ms | PASS |
| heldout-012 | physics | interactive_visual / doppler | canvas / simulation2d | source_speed, playback | front_wavelength_shorter, wavefront_spacing | canvas: 620 primitives; 145.1 ms | 1.806 ms | PASS |
| heldout-013 | physics | interactive_visual / double_slit | svg / scene2d | slit_separation, wavelength | fringe_spacing, central_maximum | svg: 39 primitives; 92.4 ms | 1.070 ms | PASS |
| heldout-014 | physics | interactive_visual / lorentz_force | three / scene3d | charge, field, speed, playback, play, pause, restart | force_perpendicular_velocity, helix_radius | three: ? primitives; 721 ms | 0.847 ms | PASS |
| heldout-015 | physics | interactive_visual / blackbody | svg / scene2d | temperature | peak_shifts_shorter, radiance_positive | svg: 32 primitives; 54.5 ms | 1.888 ms | PASS |
| heldout-016 | physics | interactive_visual / entropy_cycle | canvas / simulation2d | step | closed_cycle, process_direction | canvas: 1169 primitives; 48.4 ms | 0.651 ms | PASS |
| heldout-017 | chemistry | interactive_visual / benzene | svg / scene2d | bond_model | six_carbon_ring, alternating_or_delocalized | svg: 20 primitives; 45.9 ms | 0.514 ms | PASS |
| heldout-018 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | coordination_geometry, bond_angles | three: ? primitives; 154.2 ms | 0.440 ms | PASS |
| heldout-019 | chemistry | interactive_visual / electrochemical_cell | svg / scene2d | zinc_concentration, copper_concentration | electron_anode_to_cathode, ion_migration | svg: 17 primitives; 71.2 ms | 0.462 ms | PASS |
| heldout-020 | chemistry | interactive_visual / kinetics | svg / scene2d | order, rate_constant | integrated_rate_law, half_life_behavior | svg: 37 primitives; 98.8 ms | 3.556 ms | PASS |
| heldout-021 | chemistry | interactive_visual / phase_diagram | svg / scene2d | temperature, pressure | phase_region, triple_point | svg: 31 primitives; 97.4 ms | 0.428 ms | PASS |
| heldout-022 | chemistry | interactive_visual / equilibrium_shift | svg / scene2d | pressure, temperature | stoichiometric_ratio, le_chatelier_direction | svg: 37 primitives; 67.7 ms | 0.542 ms | PASS |
| heldout-023 | biology | interactive_visual / enzyme_kinetics | svg / scene2d | substrate, inhibitor | vmax_limit, competitive_km_shift | svg: 29 primitives; 133.2 ms | 1.364 ms | PASS |
| heldout-024 | biology | interactive_visual / dna_replication | svg / scene2d | step, play, pause, restart | five_to_three_synthesis, strand_roles | svg: 23 primitives; 265 ms | 0.498 ms | PASS |
| heldout-025 | biology | interactive_visual / nephron | svg / scene2d | segment | flow_order, reabsorption_location | svg: 43 primitives; 55.3 ms | 0.613 ms | PASS |
| heldout-026 | biology | interactive_visual / predator_prey | canvas / simulation2d | prey_growth, predation, playback, play, pause, restart | population_nonnegative, phase_cycle | canvas: 821 primitives; 296.1 ms | 3.172 ms | PASS |
| heldout-027 | biology | interactive_visual / membrane_transport | svg / scene2d | transport_mode | gradient_direction, atp_only_active | svg: 23 primitives; 51.6 ms | 0.337 ms | PASS |
| heldout-028 | computer_science | interactive_visual / merge_sort | svg / scene2d | step, play, pause, restart | sorted_output, stable_merge | svg: 81 primitives; 235.4 ms | 0.948 ms | PASS |
| heldout-029 | computer_science | interactive_visual / hash_table | svg / scene2d | key, operation, step | bucket_hash, collision_chain | svg: 35 primitives; 95.9 ms | 0.551 ms | PASS |
| heldout-030 | computer_science | interactive_visual / graph_traversal | svg / scene2d | algorithm, step | frontier_policy, visits_once | svg: 23 primitives; 71.2 ms | 0.441 ms | PASS |
| heldout-031 | computer_science | interactive_visual / heap | svg / scene2d | operation, value, step, play, pause, restart | parent_not_greater_child, extracts_minimum | svg: 27 primitives; 278.6 ms | 0.551 ms | PASS |
| heldout-032 | computer_science | interactive_visual / recursion_stack | svg / scene2d | step | stack_lifo, factorial_result | svg: 39 primitives; 50.2 ms | 0.629 ms | PASS |
| heldout-033 | computer_science | interactive_visual / virtual_memory | svg / scene2d | address, step, play, pause, restart | page_offset_preserved, fault_path | svg: 25 primitives; 260.5 ms | 0.374 ms | PASS |
| heldout-034 | signals | interactive_visual / impulse_response | svg / scene2d | shift, step | discrete_convolution_sum, output_length | svg: 29 primitives; 80.7 ms | 0.448 ms | PASS |
| heldout-035 | controls | interactive_visual / bode_plot | svg / scene2d | cutoff | minus3db_at_cutoff, phase_transition | svg: 27 primitives; 129.5 ms | 1.238 ms | PASS |
| heldout-036 | controls | interactive_visual / nyquist | svg / scene2d | gain | encirclement_count, closed_loop_stability | svg: 27 primitives; 97.7 ms | 0.809 ms | PASS |
| heldout-037 | controls | interactive_visual / pid_response | svg / scene2d | kp, ki, kd | response_metrics, final_value | svg: 35 primitives; 146.9 ms | 2.022 ms | PASS |
| heldout-038 | signals | interactive_visual / pwm | svg / scene2d | duty_cycle | pulse_width_ratio, average_voltage | svg: 27 primitives; 52.4 ms | 0.564 ms | PASS |
| heldout-039 | signals | interactive_visual / spectrogram | canvas / simulation2d | sweep_rate, playback | frequency_rises_with_time, time_frequency_alignment | canvas: 4379 primitives; 132.3 ms | 3.637 ms | PASS |
| heldout-040 | robotics | interactive_visual / robot_arm | svg / scene2d | target_x, target_y, elbow_mode | link_lengths_constant, end_effector_target | svg: 13 primitives; 136.4 ms | 0.478 ms | PASS |
| heldout-041 | robotics | interactive_visual / kalman_filter | svg / scene2d | noise, step, play, pause, restart | covariance_contracts_on_update, estimate_between_prior_measurement | svg: 39 primitives; 347.8 ms | 1.965 ms | PASS |
| heldout-042 | engineering | interactive_visual / truss | svg / scene2d | load | joint_force_balance, member_sign | svg: 19 primitives; 57 ms | 0.465 ms | PASS |
| heldout-043 | engineering | interactive_visual / beam_bending | canvas / simulation2d | load_position, play, pause, restart | support_reactions, moment_zero_at_supports | canvas: 1682 primitives; 325.8 ms | 1.904 ms | PASS |
| heldout-044 | engineering | interactive_visual / fluid_flow | canvas / simulation2d | speed | streamline_symmetry, no_penetration | canvas: 1231 primitives; 67 ms | 16.963 ms | PASS |
| heldout-045 | engineering | interactive_visual / heat_diffusion | canvas / simulation2d | time, playback, play, pause, restart | temperature_smooths, energy_bounded | canvas: 4315 primitives; 353.7 ms | 2.631 ms | PASS |
| heldout-046 | computer_science | interactive_visual / state_machine | svg / scene2d | pedestrian_request, step | legal_transition, mutually_exclusive_lights | svg: 17 primitives; 76.3 ms | 0.522 ms | PASS |
| heldout-047 | ai | interactive_visual / decision_boundary | canvas / simulation2d | epoch, learning_rate | class_regions, loss_nonincreasing | canvas: 4355 primitives; 139.8 ms | 19.522 ms | PASS |
| heldout-048 | ai | interactive_visual / backprop_graph | svg / scene2d | w, x, b, step | chain_rule_gradients, forward_value | svg: 27 primitives; 121.4 ms | 0.845 ms | PASS |
| heldout-049 | mixed | interactive_visual / energy_sankey | svg / scene2d | efficiency | energy_conservation, units_joules | svg: 15 primitives; 46.2 ms | 0.508 ms | PASS |
| heldout-050 | mixed | interactive_visual / uncertainty_propagation | canvas / simulation2d | mass_sigma, volume_sigma, samples | positive_volume, density_distribution | canvas: 957 primitives; 139.2 ms | 2.246 ms | PASS |

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
  --revision e71e294299311d092fb450c989eec9a9c8ef0f0f --pre-holdout-candidate-sha ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd --pre-holdout-frozen-at 2026-08-27T12:07:54+01:00
```

A pass requires intent, family, renderer, spec kind, exact named controls, accessible fallback, semantic oracles, and a real non-empty browser render. Presence of a canvas or WebGL context alone is never counted.
