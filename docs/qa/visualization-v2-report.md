# Visualization V2 — 200-case acceptance report

Generated from production compiler code at `6f33d3f`.

Result: **200/200 passed**; 0 failed; zero cases waived.

## Frozen pre-holdout candidate

- SHA: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd`
- Frozen at: `2026-08-27T12:07:54+01:00`
- The separate post-implementation holdout was not opened before this candidate was frozen.

## Structural renderer boundary

- Real-browser inert-string sink-flow preflight: **PASS**
- Literal source-shaped text fields preserved: 6
- Proposal-controlled event/resource/style attributes: 0
- Descriptive-label behavior attributes: 0
- Child markup sink created: False
- Frame/parent global mutated: False

| ID | Domain | Intent / family | Renderer / spec | Controls | Invariants | Browser evidence | Compile | Result |
|---|---|---|---|---|---|---|---:|---|
| stem-001 | mathematics | interactive_visual / pythagoras | svg / scene2d | a, b | a2_plus_b2_equals_c2, square_areas | svg: 31 primitives; 69.3 ms | 1.519 ms | PASS |
| stem-002 | mathematics | interactive_visual / unit_circle | svg / scene2d | angle | point_on_unit_circle, sin_cos_projection | svg: 29 primitives; 44.9 ms | 0.743 ms | PASS |
| stem-003 | mathematics | interactive_visual / quadratic | svg / scene2d | a, b, c | semantic_relationship, labels_and_units, control_consistency | svg: 28 primitives; 88.3 ms | 2.946 ms | PASS |
| stem-004 | mathematics | interactive_visual / line_intersection | svg / scene2d | m1, c1, m2, c2 | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 109.8 ms | 1.634 ms | PASS |
| stem-005 | mathematics | interactive_visual / triangle_angles | svg / scene2d | vertex_a, vertex_b, vertex_c | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 90.7 ms | 0.356 ms | PASS |
| stem-006 | mathematics | interactive_visual / derivative_tangent | svg / scene2d | x | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 45.5 ms | 1.232 ms | PASS |
| stem-007 | mathematics | interactive_visual / riemann_sum | svg / scene2d | rectangles | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 46.4 ms | 0.834 ms | PASS |
| stem-008 | mathematics | interactive_visual / gradient_field | svg / scene2d | point_x, point_y | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 274.8 ms | 1.943 ms | PASS |
| stem-009 | mathematics | interactive_visual / plane_intersection | three / scene3d | orbit | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 181 ms | 1.047 ms | PASS |
| stem-010 | mathematics | interactive_visual / linear_transform | svg / scene2d | matrix | semantic_relationship, labels_and_units, control_consistency | svg: 59 primitives; 45.5 ms | 0.638 ms | PASS |
| stem-011 | physics | interactive_visual / projectile | svg / scene2d | angle, speed | trajectory_endpoints, range_height_units | svg: 29 primitives; 64.1 ms | 0.618 ms | PASS |
| stem-012 | physics | interactive_visual / inclined_plane | svg / scene2d | incline | semantic_relationship, labels_and_units, control_consistency | svg: 12 primitives; 43.8 ms | 0.329 ms | PASS |
| stem-013 | physics | interactive_visual / spring_mass | svg / scene2d | spring_constant, mass | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 63 ms | 0.308 ms | PASS |
| stem-014 | physics | interactive_visual / elastic_collision | svg / scene2d | mass_1, velocity_1, mass_2, velocity_2 | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 106.7 ms | 0.346 ms | PASS |
| stem-015 | physics | interactive_visual / pendulum | svg / scene2d | length, angle, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 257.7 ms | 0.505 ms | PASS |
| stem-016 | physics | interactive_visual / travelling_wave | canvas / simulation2d | amplitude, wavelength, frequency | semantic_relationship, labels_and_units, control_consistency | canvas: 820 primitives; 101.6 ms | 0.676 ms | PASS |
| stem-017 | physics | interactive_visual / wave_interference | canvas / simulation2d | phase | semantic_relationship, labels_and_units, control_consistency | canvas: 648 primitives; 115 ms | 1.389 ms | PASS |
| stem-018 | physics | interactive_visual / circular_motion | svg / scene2d | angular_velocity | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 89.1 ms | 0.876 ms | PASS |
| stem-019 | physics | interactive_visual / harmonic_motion | canvas / simulation2d | spring_constant, mass, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | canvas: 876 primitives; 323.2 ms | 1.307 ms | PASS |
| stem-020 | physics | interactive_visual / double_pendulum | canvas / simulation2d | angle_1, angle_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 1606 primitives; 126 ms | 5.021 ms | PASS |
| stem-021 | electromagnetism | interactive_visual / ohms_law_circuit | svg / scene2d | voltage, resistance, switch | current_v_over_r, current_direction | svg: 14 primitives; 85.8 ms | 0.565 ms | PASS |
| stem-022 | electromagnetism | interactive_visual / series_parallel_circuit | svg / scene2d | r1, r2, mode | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 87.9 ms | 0.417 ms | PASS |
| stem-023 | electromagnetism | interactive_visual / electric_field_lines | canvas / simulation2d | charge_1, charge_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 898 primitives; 108.4 ms | 5.028 ms | PASS |
| stem-024 | electromagnetism | interactive_visual / electric_field_vectors | canvas / simulation2d | test_x, test_y | semantic_relationship, labels_and_units, control_consistency | canvas: 461 primitives; 99 ms | 1.845 ms | PASS |
| stem-025 | electromagnetism | interactive_visual / magnetic_field_wire | svg / scene2d | current_direction | semantic_relationship, labels_and_units, control_consistency | svg: 35 primitives; 72.7 ms | 1.802 ms | PASS |
| stem-026 | electromagnetism | interactive_visual / rc_circuit | svg / scene2d | mode, resistance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 39 primitives; 141.9 ms | 1.251 ms | PASS |
| stem-027 | electromagnetism | interactive_visual / rlc_circuit | svg / scene2d | resistance, inductance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 41 primitives; 98 ms | 0.827 ms | PASS |
| stem-028 | electromagnetism | interactive_visual / ac_phase | svg / scene2d | load | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 58.8 ms | 1.755 ms | PASS |
| stem-029 | optics_thermodynamics | interactive_visual / converging_lens | svg / scene2d | object_distance | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 100.6 ms | 0.423 ms | PASS |
| stem-030 | optics_thermodynamics | interactive_visual / refraction | svg / scene2d | incident_angle, medium | snell_law, normal_and_ray_direction | svg: 15 primitives; 65.1 ms | 0.324 ms | PASS |
| stem-031 | optics_thermodynamics | interactive_visual / ideal_gas | svg / scene2d | pressure, volume, temperature | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 85.3 ms | 0.978 ms | PASS |
| stem-032 | optics_thermodynamics | interactive_visual / carnot_cycle | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 226.4 ms | 0.473 ms | PASS |
| stem-033 | chemistry | interactive_visual / atom | svg / scene2d | atomic_number | semantic_relationship, labels_and_units, control_consistency | svg: 46 primitives; 130.7 ms | 1.669 ms | PASS |
| stem-034 | chemistry | interactive_visual / ionic_bond | svg / scene2d | playback | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 42.8 ms | 0.314 ms | PASS |
| stem-035 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 146.2 ms | 0.333 ms | PASS |
| stem-036 | chemistry | interactive_visual / reaction_profile | svg / scene2d | catalyst | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 55.4 ms | 0.887 ms | PASS |
| stem-037 | chemistry | interactive_visual / titration | svg / scene2d | titrant_volume | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 146.4 ms | 1.034 ms | PASS |
| stem-038 | chemistry | interactive_visual / molecular_orbitals | svg / scene2d | orbital | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 100.9 ms | 0.477 ms | PASS |
| stem-039 | biology | interactive_visual / animal_cell | svg / scene2d | organelle | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 43.3 ms | 0.343 ms | PASS |
| stem-040 | biology | interactive_visual / mitosis | svg / scene2d | step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 42 ms | 0.336 ms | PASS |
| stem-041 | biology | interactive_visual / circulation | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 19 primitives; 225.9 ms | 0.347 ms | PASS |
| stem-042 | biology | interactive_visual / action_potential | svg / scene2d | time | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 83.1 ms | 1.491 ms | PASS |
| stem-043 | computer_science | interactive_visual / binary_search | svg / scene2d | target, step, play, pause, restart | interval_shrinks, target_found | svg: 15 primitives; 250.8 ms | 0.741 ms | PASS |
| stem-044 | computer_science | interactive_visual / binary_search_tree | svg / scene2d | insert, step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 257.3 ms | 0.501 ms | PASS |
| stem-045 | computer_science | interactive_visual / dijkstra | svg / scene2d | source, destination, step, play, pause, restart | nondecreasing_settled_distance, shortest_path | svg: 31 primitives; 273.8 ms | 0.563 ms | PASS |
| stem-046 | computer_science | interactive_visual / stack_queue | svg / scene2d | operation, step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 156.2 ms | 0.557 ms | PASS |
| stem-047 | computer_science | interactive_visual / cpu_memory | svg / scene2d | step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 229.8 ms | 0.902 ms | PASS |
| stem-048 | engineering_signals_robotics_ai | interactive_visual / sampling_aliasing | canvas / simulation2d | signal_frequency, sample_frequency | nyquist_condition, sample_locations | canvas: 1097 primitives; 181.6 ms | 2.577 ms | PASS |
| stem-049 | engineering_signals_robotics_ai | interactive_visual / differential_drive | canvas / simulation2d | left_velocity, right_velocity | curvature_from_wheel_speeds | canvas: 910 primitives; 94.1 ms | 0.989 ms | PASS |
| stem-050 | engineering_signals_robotics_ai | interactive_visual / neural_network | svg / scene2d | weight, step | weighted_activation_flow | svg: 23 primitives; 65.5 ms | 0.585 ms | PASS |
| math-001 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 264 ms | 1.976 ms | PASS |
| math-002 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275.7 ms | 1.603 ms | PASS |
| math-003 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.9 ms | 1.615 ms | PASS |
| math-004 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.9 ms | 1.931 ms | PASS |
| math-005 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 261.6 ms | 1.714 ms | PASS |
| math-006 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.9 ms | 1.413 ms | PASS |
| math-007 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 267 ms | 1.866 ms | PASS |
| math-008 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.2 ms | 1.575 ms | PASS |
| math-009 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.2 ms | 1.673 ms | PASS |
| math-010 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 282.9 ms | 1.839 ms | PASS |
| math-011 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 269.7 ms | 3.236 ms | PASS |
| math-012 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 1216 primitives; 262.8 ms | 1.696 ms | PASS |
| math-013 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 279.9 ms | 1.543 ms | PASS |
| math-014 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 281.4 ms | 1.625 ms | PASS |
| math-015 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 262.7 ms | 1.688 ms | PASS |
| math-016 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 258.8 ms | 0.669 ms | PASS |
| math-017 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 263.9 ms | 0.965 ms | PASS |
| math-018 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.6 ms | 0.959 ms | PASS |
| math-019 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.9 ms | 1.974 ms | PASS |
| math-020 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.7 ms | 1.518 ms | PASS |
| math-021 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 261.1 ms | 0.663 ms | PASS |
| math-022 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.5 ms | 1.160 ms | PASS |
| math-023 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.9 ms | 1.170 ms | PASS |
| math-024 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.8 ms | 0.933 ms | PASS |
| math-025 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.5 ms | 0.926 ms | PASS |
| math-026 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293 ms | 1.519 ms | PASS |
| math-027 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.7 ms | 1.492 ms | PASS |
| math-028 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.2 ms | 1.769 ms | PASS |
| math-029 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 298.1 ms | 3.199 ms | PASS |
| math-030 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.8 ms | 1.768 ms | PASS |
| math-031 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 266.3 ms | 1.154 ms | PASS |
| math-032 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.2 ms | 1.170 ms | PASS |
| math-033 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 267.8 ms | 1.137 ms | PASS |
| math-034 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 307.1 ms | 0.954 ms | PASS |
| math-035 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.5 ms | 0.918 ms | PASS |
| math-036 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.1 ms | 1.511 ms | PASS |
| math-037 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 297.1 ms | 2.210 ms | PASS |
| math-038 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.4 ms | 1.696 ms | PASS |
| math-039 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.9 ms | 2.166 ms | PASS |
| math-040 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 295.8 ms | 4.294 ms | PASS |
| math-041 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 268.6 ms | 1.684 ms | PASS |
| math-042 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 264.1 ms | 2.075 ms | PASS |
| math-043 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276.4 ms | 2.068 ms | PASS |
| math-044 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.2 ms | 2.194 ms | PASS |
| math-045 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 281 ms | 4.247 ms | PASS |
| math-046 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276.7 ms | 6.479 ms | PASS |
| math-047 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 281.4 ms | 2.163 ms | PASS |
| math-048 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.2 ms | 2.298 ms | PASS |
| math-049 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 266 ms | 2.565 ms | PASS |
| math-050 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.5 ms | 3.287 ms | PASS |
| math-051 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 267.9 ms | 2.228 ms | PASS |
| math-052 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.9 ms | 2.910 ms | PASS |
| math-053 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4584 primitives; 272.9 ms | 2.927 ms | PASS |
| math-054 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 281 ms | 3.853 ms | PASS |
| math-055 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.3 ms | 1.891 ms | PASS |
| math-056 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.9 ms | 1.684 ms | PASS |
| math-057 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 275.2 ms | 1.455 ms | PASS |
| math-058 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 287.9 ms | 1.501 ms | PASS |
| math-059 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 278.7 ms | 1.590 ms | PASS |
| math-060 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.1 ms | 2.138 ms | PASS |
| math-061 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 272.7 ms | 2.442 ms | PASS |
| math-062 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4140 primitives; 274.8 ms | 1.032 ms | PASS |
| math-063 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4120 primitives; 272.6 ms | 1.535 ms | PASS |
| math-064 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 290.4 ms | 2.693 ms | PASS |
| math-065 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4232 primitives; 277.4 ms | 1.764 ms | PASS |
| math-066 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 12024 primitives; 403.2 ms | 102.712 ms | PASS |
| math-067 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9296 primitives; 381.8 ms | 134.756 ms | PASS |
| math-068 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18440 primitives; 512.9 ms | 89.516 ms | PASS |
| math-069 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19928 primitives; 421.6 ms | 114.515 ms | PASS |
| math-070 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15624 primitives; 395.7 ms | 78.625 ms | PASS |
| math-071 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 14632 primitives; 387.8 ms | 99.709 ms | PASS |
| math-072 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 21576 primitives; 412.6 ms | 77.945 ms | PASS |
| math-073 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15004 primitives; 391.1 ms | 55.230 ms | PASS |
| math-074 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19560 primitives; 410.4 ms | 100.181 ms | PASS |
| math-075 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18104 primitives; 403.4 ms | 100.716 ms | PASS |
| math-076 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9588 primitives; 389 ms | 76.781 ms | PASS |
| math-077 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.1 ms | 1.256 ms | PASS |
| math-078 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 11864 primitives; 384.6 ms | 200.135 ms | PASS |
| math-079 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9288 primitives; 387.7 ms | 97.538 ms | PASS |
| math-080 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 5616 primitives; 378.3 ms | 89.282 ms | PASS |
| math-081 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 365.1 ms | 130.718 ms | PASS |
| math-082 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 386.3 ms | 167.439 ms | PASS |
| math-083 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7408 primitives; 359.8 ms | 130.410 ms | PASS |
| math-084 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9024 primitives; 372.8 ms | 142.155 ms | PASS |
| math-085 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.3 ms | 4.277 ms | PASS |
| math-086 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.6 ms | 1.822 ms | PASS |
| math-087 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7880 primitives; 372.5 ms | 144.730 ms | PASS |
| math-088 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 13680 primitives; 389.6 ms | 76.412 ms | PASS |
| math-089 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 96 primitives; 336.9 ms | 188.506 ms | PASS |
| math-090 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 3000 primitives; 367.8 ms | 258.617 ms | PASS |
| math-091 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 26594 primitives; 475.8 ms | 6.076 ms | PASS |
| math-092 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20252 primitives; 437.7 ms | 3.265 ms | PASS |
| math-093 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20196 primitives; 450.9 ms | 3.208 ms | PASS |
| math-094 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20624 primitives; 443.8 ms | 6.031 ms | PASS |
| math-095 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 285.1 ms | 1.288 ms | PASS |
| math-096 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275 ms | 3.378 ms | PASS |
| math-097 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4600 primitives; 293.1 ms | 3.319 ms | PASS |
| math-098 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 281.4 ms | 1.519 ms | PASS |
| math-099 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.4 ms | 1.709 ms | PASS |
| math-100 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 304.3 ms | 4.933 ms | PASS |
| heldout-001 | mathematics | interactive_visual / complex_mapping | svg / scene2d | point_angle, point_radius | complex_square_mapping, angle_doubles | svg: 71 primitives; 105.6 ms | 2.891 ms | PASS |
| heldout-002 | mathematics | interactive_visual / polar_plot | svg / scene2d | theta, playback, play, pause, restart | polar_radius, four_petals | svg: 35 primitives; 327.3 ms | 1.383 ms | PASS |
| heldout-003 | mathematics | interactive_visual / fourier_series | svg / scene2d | terms | odd_harmonics, gibbs_overshoot | svg: 36 primitives; 98.7 ms | 1.886 ms | PASS |
| heldout-004 | mathematics | interactive_visual / logistic_map | canvas / simulation2d | growth_rate, initial_value | iterate_logistic, bounded_unit_interval | canvas: 943 primitives; 125.9 ms | 4.205 ms | PASS |
| heldout-005 | mathematics | interactive_visual / lagrange_multiplier | svg / scene2d | constraint_offset | tangent_contours, parallel_gradients | svg: 37 primitives; 65.1 ms | 1.625 ms | PASS |
| heldout-006 | mathematics | interactive_visual / parametric_surface | three / scene3d | path_position, playback | mobius_single_boundary, parametric_samples | three: 1890 primitives; 306.6 ms | 0.564 ms | PASS |
| heldout-007 | mathematics | interactive_visual / vector_field | svg / scene2d | probe_x, probe_y | field_components, divergence_zero | svg: 49 primitives; 66.3 ms | 0.554 ms | PASS |
| heldout-008 | mathematics | interactive_visual / convolution | svg / scene2d | shift | overlap_equals_convolution, triangular_result | svg: 33 primitives; 45.7 ms | 0.584 ms | PASS |
| heldout-009 | physics | interactive_visual / kepler_orbit | canvas / simulation2d | eccentricity, true_anomaly, playback, play, pause, restart | acceleration_inward, equal_area | canvas: 1019 primitives; 288.7 ms | 0.754 ms | PASS |
| heldout-010 | physics | interactive_visual / coupled_oscillators | canvas / simulation2d | mode, playback, play, pause, restart | normal_mode_phase, energy_bounded | canvas: 1064 primitives; 302.4 ms | 0.984 ms | PASS |
| heldout-011 | physics | interactive_visual / standing_wave | svg / scene2d | harmonic | node_count, fixed_endpoints | svg: 41 primitives; 107.7 ms | 0.550 ms | PASS |
| heldout-012 | physics | interactive_visual / doppler | canvas / simulation2d | source_speed, playback | front_wavelength_shorter, wavefront_spacing | canvas: 632 primitives; 120.3 ms | 1.310 ms | PASS |
| heldout-013 | physics | interactive_visual / double_slit | svg / scene2d | slit_separation, wavelength | fringe_spacing, central_maximum | svg: 39 primitives; 63.2 ms | 0.808 ms | PASS |
| heldout-014 | physics | interactive_visual / lorentz_force | three / scene3d | charge, field, speed, playback, play, pause, restart | force_perpendicular_velocity, helix_radius | three: ? primitives; 698.2 ms | 0.599 ms | PASS |
| heldout-015 | physics | interactive_visual / blackbody | svg / scene2d | temperature | peak_shifts_shorter, radiance_positive | svg: 32 primitives; 116 ms | 1.431 ms | PASS |
| heldout-016 | physics | interactive_visual / entropy_cycle | canvas / simulation2d | step | closed_cycle, process_direction | canvas: 1169 primitives; 94.5 ms | 0.483 ms | PASS |
| heldout-017 | chemistry | interactive_visual / benzene | svg / scene2d | bond_model | six_carbon_ring, alternating_or_delocalized | svg: 20 primitives; 43.1 ms | 0.418 ms | PASS |
| heldout-018 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | coordination_geometry, bond_angles | three: ? primitives; 139.9 ms | 0.330 ms | PASS |
| heldout-019 | chemistry | interactive_visual / electrochemical_cell | svg / scene2d | zinc_concentration, copper_concentration | electron_anode_to_cathode, ion_migration | svg: 17 primitives; 69.2 ms | 0.341 ms | PASS |
| heldout-020 | chemistry | interactive_visual / kinetics | svg / scene2d | order, rate_constant | integrated_rate_law, half_life_behavior | svg: 37 primitives; 169.6 ms | 2.623 ms | PASS |
| heldout-021 | chemistry | interactive_visual / phase_diagram | svg / scene2d | temperature, pressure | phase_region, triple_point | svg: 31 primitives; 91.4 ms | 0.329 ms | PASS |
| heldout-022 | chemistry | interactive_visual / equilibrium_shift | svg / scene2d | pressure, temperature | stoichiometric_ratio, le_chatelier_direction | svg: 37 primitives; 67.4 ms | 0.419 ms | PASS |
| heldout-023 | biology | interactive_visual / enzyme_kinetics | svg / scene2d | substrate, inhibitor | vmax_limit, competitive_km_shift | svg: 29 primitives; 134.9 ms | 1.047 ms | PASS |
| heldout-024 | biology | interactive_visual / dna_replication | svg / scene2d | step, play, pause, restart | five_to_three_synthesis, strand_roles | svg: 23 primitives; 259.9 ms | 0.368 ms | PASS |
| heldout-025 | biology | interactive_visual / nephron | svg / scene2d | segment | flow_order, reabsorption_location | svg: 43 primitives; 51.6 ms | 0.461 ms | PASS |
| heldout-026 | biology | interactive_visual / predator_prey | canvas / simulation2d | prey_growth, predation, playback, play, pause, restart | population_nonnegative, phase_cycle | canvas: 824 primitives; 310.6 ms | 2.410 ms | PASS |
| heldout-027 | biology | interactive_visual / membrane_transport | svg / scene2d | transport_mode | gradient_direction, atp_only_active | svg: 23 primitives; 48.5 ms | 0.260 ms | PASS |
| heldout-028 | computer_science | interactive_visual / merge_sort | svg / scene2d | step, play, pause, restart | sorted_output, stable_merge | svg: 81 primitives; 233 ms | 0.703 ms | PASS |
| heldout-029 | computer_science | interactive_visual / hash_table | svg / scene2d | key, operation, step | bucket_hash, collision_chain | svg: 35 primitives; 90 ms | 0.418 ms | PASS |
| heldout-030 | computer_science | interactive_visual / graph_traversal | svg / scene2d | algorithm, step | frontier_policy, visits_once | svg: 23 primitives; 67 ms | 0.328 ms | PASS |
| heldout-031 | computer_science | interactive_visual / heap | svg / scene2d | operation, value, step, play, pause, restart | parent_not_greater_child, extracts_minimum | svg: 27 primitives; 270.7 ms | 0.415 ms | PASS |
| heldout-032 | computer_science | interactive_visual / recursion_stack | svg / scene2d | step | stack_lifo, factorial_result | svg: 39 primitives; 44.4 ms | 0.464 ms | PASS |
| heldout-033 | computer_science | interactive_visual / virtual_memory | svg / scene2d | address, step, play, pause, restart | page_offset_preserved, fault_path | svg: 25 primitives; 250.4 ms | 0.289 ms | PASS |
| heldout-034 | signals | interactive_visual / impulse_response | svg / scene2d | shift, step | discrete_convolution_sum, output_length | svg: 29 primitives; 64.4 ms | 0.329 ms | PASS |
| heldout-035 | controls | interactive_visual / bode_plot | svg / scene2d | cutoff | minus3db_at_cutoff, phase_transition | svg: 27 primitives; 75.7 ms | 0.911 ms | PASS |
| heldout-036 | controls | interactive_visual / nyquist | svg / scene2d | gain | encirclement_count, closed_loop_stability | svg: 27 primitives; 42.4 ms | 0.606 ms | PASS |
| heldout-037 | controls | interactive_visual / pid_response | svg / scene2d | kp, ki, kd | response_metrics, final_value | svg: 35 primitives; 97.2 ms | 1.509 ms | PASS |
| heldout-038 | signals | interactive_visual / pwm | svg / scene2d | duty_cycle | pulse_width_ratio, average_voltage | svg: 27 primitives; 42.3 ms | 0.438 ms | PASS |
| heldout-039 | signals | interactive_visual / spectrogram | canvas / simulation2d | sweep_rate, playback | frequency_rises_with_time, time_frequency_alignment | canvas: 4379 primitives; 147.5 ms | 2.751 ms | PASS |
| heldout-040 | robotics | interactive_visual / robot_arm | svg / scene2d | target_x, target_y, elbow_mode | link_lengths_constant, end_effector_target | svg: 13 primitives; 113.3 ms | 0.356 ms | PASS |
| heldout-041 | robotics | interactive_visual / kalman_filter | svg / scene2d | noise, step, play, pause, restart | covariance_contracts_on_update, estimate_between_prior_measurement | svg: 39 primitives; 265.8 ms | 1.644 ms | PASS |
| heldout-042 | engineering | interactive_visual / truss | svg / scene2d | load | joint_force_balance, member_sign | svg: 19 primitives; 49.5 ms | 0.327 ms | PASS |
| heldout-043 | engineering | interactive_visual / beam_bending | canvas / simulation2d | load_position, play, pause, restart | support_reactions, moment_zero_at_supports | canvas: 1682 primitives; 353.7 ms | 1.365 ms | PASS |
| heldout-044 | engineering | interactive_visual / fluid_flow | canvas / simulation2d | speed | streamline_symmetry, no_penetration | canvas: 1231 primitives; 105.4 ms | 12.291 ms | PASS |
| heldout-045 | engineering | interactive_visual / heat_diffusion | canvas / simulation2d | time, playback, play, pause, restart | temperature_smooths, energy_bounded | canvas: 4315 primitives; 284.9 ms | 1.770 ms | PASS |
| heldout-046 | computer_science | interactive_visual / state_machine | svg / scene2d | pedestrian_request, step | legal_transition, mutually_exclusive_lights | svg: 17 primitives; 64 ms | 0.349 ms | PASS |
| heldout-047 | ai | interactive_visual / decision_boundary | canvas / simulation2d | epoch, learning_rate | class_regions, loss_nonincreasing | canvas: 4355 primitives; 176.1 ms | 13.175 ms | PASS |
| heldout-048 | ai | interactive_visual / backprop_graph | svg / scene2d | w, x, b, step | chain_rule_gradients, forward_value | svg: 27 primitives; 106.5 ms | 0.586 ms | PASS |
| heldout-049 | mixed | interactive_visual / energy_sankey | svg / scene2d | efficiency | energy_conservation, units_joules | svg: 15 primitives; 41.2 ms | 0.349 ms | PASS |
| heldout-050 | mixed | interactive_visual / uncertainty_propagation | canvas / simulation2d | mass_sigma, volume_sigma, samples | positive_volume, density_distribution | canvas: 959 primitives; 102.2 ms | 1.645 ms | PASS |

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
  --revision 6f33d3f --pre-holdout-candidate-sha ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd --pre-holdout-frozen-at 2026-08-27T12:07:54+01:00
```

A pass requires intent, family, renderer, spec kind, exact named controls, accessible fallback, semantic oracles, and a real non-empty browser render. Presence of a canvas or WebGL context alone is never counted.
