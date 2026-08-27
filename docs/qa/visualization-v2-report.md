# Visualization V2 — 200-case acceptance report

Generated from production compiler code at `working-tree`.

Result: **200/200 passed**; 0 failed; zero cases waived.

## Structural renderer boundary

- Real-browser inert-string sink-flow preflight: **PASS**
- Literal source-shaped text fields preserved: 6
- Proposal-controlled event/resource/style attributes: 0
- Descriptive-label behavior attributes: 0
- Child markup sink created: False
- Frame/parent global mutated: False

| ID | Domain | Intent / family | Renderer / spec | Controls | Invariants | Browser evidence | Compile | Result |
|---|---|---|---|---|---|---|---:|---|
| stem-001 | mathematics | interactive_visual / pythagoras | svg / scene2d | a, b | a2_plus_b2_equals_c2, square_areas | svg: 31 primitives; 65.6 ms | 2.724 ms | PASS |
| stem-002 | mathematics | interactive_visual / unit_circle | svg / scene2d | angle | point_on_unit_circle, sin_cos_projection | svg: 29 primitives; 42 ms | 1.042 ms | PASS |
| stem-003 | mathematics | interactive_visual / quadratic | svg / scene2d | a, b, c | semantic_relationship, labels_and_units, control_consistency | svg: 28 primitives; 84.8 ms | 3.180 ms | PASS |
| stem-004 | mathematics | interactive_visual / line_intersection | svg / scene2d | m1, c1, m2, c2 | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 108.1 ms | 2.875 ms | PASS |
| stem-005 | mathematics | interactive_visual / triangle_angles | svg / scene2d | vertex_a, vertex_b, vertex_c | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 88.7 ms | 0.468 ms | PASS |
| stem-006 | mathematics | interactive_visual / derivative_tangent | svg / scene2d | x | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 46.5 ms | 1.849 ms | PASS |
| stem-007 | mathematics | interactive_visual / riemann_sum | svg / scene2d | rectangles | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 43.1 ms | 1.309 ms | PASS |
| stem-008 | mathematics | interactive_visual / gradient_field | svg / scene2d | point_x, point_y | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 137.2 ms | 3.043 ms | PASS |
| stem-009 | mathematics | interactive_visual / plane_intersection | three / scene3d | orbit | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 204.9 ms | 1.576 ms | PASS |
| stem-010 | mathematics | interactive_visual / linear_transform | svg / scene2d | matrix | semantic_relationship, labels_and_units, control_consistency | svg: 59 primitives; 48.2 ms | 1.001 ms | PASS |
| stem-011 | physics | interactive_visual / projectile | svg / scene2d | angle, speed | trajectory_endpoints, range_height_units | svg: 29 primitives; 64.4 ms | 0.956 ms | PASS |
| stem-012 | physics | interactive_visual / inclined_plane | svg / scene2d | incline | semantic_relationship, labels_and_units, control_consistency | svg: 12 primitives; 44.4 ms | 0.517 ms | PASS |
| stem-013 | physics | interactive_visual / spring_mass | svg / scene2d | spring_constant, mass | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 64.3 ms | 0.499 ms | PASS |
| stem-014 | physics | interactive_visual / elastic_collision | svg / scene2d | mass_1, velocity_1, mass_2, velocity_2 | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 107 ms | 0.556 ms | PASS |
| stem-015 | physics | interactive_visual / pendulum | svg / scene2d | length, angle, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 13 primitives; 262.7 ms | 0.796 ms | PASS |
| stem-016 | physics | interactive_visual / travelling_wave | canvas / simulation2d | amplitude, wavelength, frequency | semantic_relationship, labels_and_units, control_consistency | canvas: 1035 primitives; 120.7 ms | 1.020 ms | PASS |
| stem-017 | physics | interactive_visual / wave_interference | canvas / simulation2d | phase | semantic_relationship, labels_and_units, control_consistency | canvas: 916 primitives; 60.1 ms | 1.713 ms | PASS |
| stem-018 | physics | interactive_visual / circular_motion | svg / scene2d | angular_velocity | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 44.1 ms | 0.918 ms | PASS |
| stem-019 | physics | interactive_visual / harmonic_motion | canvas / simulation2d | spring_constant, mass, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | canvas: 1027 primitives; 277.2 ms | 1.466 ms | PASS |
| stem-020 | physics | interactive_visual / double_pendulum | canvas / simulation2d | angle_1, angle_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 1339 primitives; 105.9 ms | 5.900 ms | PASS |
| stem-021 | electromagnetism | interactive_visual / ohms_law_circuit | svg / scene2d | voltage, resistance, switch | current_v_over_r, current_direction | svg: 14 primitives; 89 ms | 0.609 ms | PASS |
| stem-022 | electromagnetism | interactive_visual / series_parallel_circuit | svg / scene2d | r1, r2, mode | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 92.2 ms | 0.493 ms | PASS |
| stem-023 | electromagnetism | interactive_visual / electric_field_lines | canvas / simulation2d | charge_1, charge_2 | semantic_relationship, labels_and_units, control_consistency | canvas: 981 primitives; 89.2 ms | 5.784 ms | PASS |
| stem-024 | electromagnetism | interactive_visual / electric_field_vectors | canvas / simulation2d | test_x, test_y | semantic_relationship, labels_and_units, control_consistency | canvas: 752 primitives; 123.4 ms | 2.061 ms | PASS |
| stem-025 | electromagnetism | interactive_visual / magnetic_field_wire | svg / scene2d | current_direction | semantic_relationship, labels_and_units, control_consistency | svg: 35 primitives; 72.4 ms | 2.078 ms | PASS |
| stem-026 | electromagnetism | interactive_visual / rc_circuit | svg / scene2d | mode, resistance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 39 primitives; 144 ms | 1.412 ms | PASS |
| stem-027 | electromagnetism | interactive_visual / rlc_circuit | svg / scene2d | resistance, inductance, capacitance | semantic_relationship, labels_and_units, control_consistency | svg: 41 primitives; 89.5 ms | 0.945 ms | PASS |
| stem-028 | electromagnetism | interactive_visual / ac_phase | svg / scene2d | load | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 65.1 ms | 1.927 ms | PASS |
| stem-029 | optics_thermodynamics | interactive_visual / converging_lens | svg / scene2d | object_distance | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 46.7 ms | 0.566 ms | PASS |
| stem-030 | optics_thermodynamics | interactive_visual / refraction | svg / scene2d | incident_angle, medium | snell_law, normal_and_ray_direction | svg: 15 primitives; 62.1 ms | 0.492 ms | PASS |
| stem-031 | optics_thermodynamics | interactive_visual / ideal_gas | svg / scene2d | pressure, volume, temperature | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 87.3 ms | 1.461 ms | PASS |
| stem-032 | optics_thermodynamics | interactive_visual / carnot_cycle | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 289.6 ms | 0.709 ms | PASS |
| stem-033 | chemistry | interactive_visual / atom | svg / scene2d | atomic_number | semantic_relationship, labels_and_units, control_consistency | svg: 46 primitives; 121.4 ms | 2.902 ms | PASS |
| stem-034 | chemistry | interactive_visual / ionic_bond | svg / scene2d | playback | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 72.4 ms | 0.531 ms | PASS |
| stem-035 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | semantic_relationship, labels_and_units, control_consistency | three: ? primitives; 146.7 ms | 0.554 ms | PASS |
| stem-036 | chemistry | interactive_visual / reaction_profile | svg / scene2d | catalyst | semantic_relationship, labels_and_units, control_consistency | svg: 27 primitives; 70.2 ms | 1.378 ms | PASS |
| stem-037 | chemistry | interactive_visual / titration | svg / scene2d | titrant_volume | semantic_relationship, labels_and_units, control_consistency | svg: 33 primitives; 100.7 ms | 1.598 ms | PASS |
| stem-038 | chemistry | interactive_visual / molecular_orbitals | svg / scene2d | orbital | semantic_relationship, labels_and_units, control_consistency | svg: 17 primitives; 98.8 ms | 0.785 ms | PASS |
| stem-039 | biology | interactive_visual / animal_cell | svg / scene2d | organelle | semantic_relationship, labels_and_units, control_consistency | svg: 15 primitives; 42.9 ms | 0.513 ms | PASS |
| stem-040 | biology | interactive_visual / mitosis | svg / scene2d | step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 41.2 ms | 0.510 ms | PASS |
| stem-041 | biology | interactive_visual / circulation | svg / scene2d | playback, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 19 primitives; 241 ms | 0.568 ms | PASS |
| stem-042 | biology | interactive_visual / action_potential | svg / scene2d | time | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 79.6 ms | 2.010 ms | PASS |
| stem-043 | computer_science | interactive_visual / binary_search | svg / scene2d | target, step, play, pause, restart | interval_shrinks, target_found | svg: 15 primitives; 253.2 ms | 0.793 ms | PASS |
| stem-044 | computer_science | interactive_visual / binary_search_tree | svg / scene2d | insert, step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 31 primitives; 261.5 ms | 0.578 ms | PASS |
| stem-045 | computer_science | interactive_visual / dijkstra | svg / scene2d | source, destination, step, play, pause, restart | nondecreasing_settled_distance, shortest_path | svg: 31 primitives; 284.7 ms | 0.658 ms | PASS |
| stem-046 | computer_science | interactive_visual / stack_queue | svg / scene2d | operation, step | semantic_relationship, labels_and_units, control_consistency | svg: 25 primitives; 69.3 ms | 0.646 ms | PASS |
| stem-047 | computer_science | interactive_visual / cpu_memory | svg / scene2d | step, play, pause, restart | semantic_relationship, labels_and_units, control_consistency | svg: 21 primitives; 237.4 ms | 1.106 ms | PASS |
| stem-048 | engineering_signals_robotics_ai | interactive_visual / sampling_aliasing | canvas / simulation2d | signal_frequency, sample_frequency | nyquist_condition, sample_locations | canvas: 1083 primitives; 130.8 ms | 3.125 ms | PASS |
| stem-049 | engineering_signals_robotics_ai | interactive_visual / differential_drive | canvas / simulation2d | left_velocity, right_velocity | curvature_from_wheel_speeds | canvas: 1066 primitives; 89.4 ms | 1.153 ms | PASS |
| stem-050 | engineering_signals_robotics_ai | interactive_visual / neural_network | svg / scene2d | weight, step | weighted_activation_flow | svg: 23 primitives; 67.3 ms | 0.704 ms | PASS |
| math-001 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.9 ms | 2.201 ms | PASS |
| math-002 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 281.7 ms | 1.809 ms | PASS |
| math-003 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275.6 ms | 1.785 ms | PASS |
| math-004 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.7 ms | 2.168 ms | PASS |
| math-005 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 271.2 ms | 2.290 ms | PASS |
| math-006 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 265.6 ms | 1.674 ms | PASS |
| math-007 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 268 ms | 2.135 ms | PASS |
| math-008 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 281.6 ms | 1.772 ms | PASS |
| math-009 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.3 ms | 2.568 ms | PASS |
| math-010 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 274.9 ms | 2.806 ms | PASS |
| math-011 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.7 ms | 4.813 ms | PASS |
| math-012 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 1216 primitives; 276.1 ms | 2.503 ms | PASS |
| math-013 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276 ms | 2.275 ms | PASS |
| math-014 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 282.1 ms | 2.218 ms | PASS |
| math-015 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275.8 ms | 2.565 ms | PASS |
| math-016 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.6 ms | 0.982 ms | PASS |
| math-017 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.3 ms | 1.388 ms | PASS |
| math-018 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.1 ms | 1.395 ms | PASS |
| math-019 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 282 ms | 2.565 ms | PASS |
| math-020 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 288.5 ms | 2.226 ms | PASS |
| math-021 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.4 ms | 0.966 ms | PASS |
| math-022 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 273.2 ms | 1.735 ms | PASS |
| math-023 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 272.5 ms | 1.727 ms | PASS |
| math-024 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.2 ms | 1.339 ms | PASS |
| math-025 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276.3 ms | 1.375 ms | PASS |
| math-026 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.2 ms | 2.148 ms | PASS |
| math-027 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.6 ms | 2.148 ms | PASS |
| math-028 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.5 ms | 2.523 ms | PASS |
| math-029 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 301.1 ms | 4.531 ms | PASS |
| math-030 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 290.8 ms | 2.466 ms | PASS |
| math-031 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.4 ms | 1.693 ms | PASS |
| math-032 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.9 ms | 1.692 ms | PASS |
| math-033 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.5 ms | 1.696 ms | PASS |
| math-034 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 277.3 ms | 1.378 ms | PASS |
| math-035 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 282.8 ms | 1.336 ms | PASS |
| math-036 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.4 ms | 2.133 ms | PASS |
| math-037 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 276.9 ms | 3.156 ms | PASS |
| math-038 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.8 ms | 2.468 ms | PASS |
| math-039 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 264.3 ms | 3.111 ms | PASS |
| math-040 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.8 ms | 5.832 ms | PASS |
| math-041 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.1 ms | 2.419 ms | PASS |
| math-042 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 262.1 ms | 3.125 ms | PASS |
| math-043 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.3 ms | 3.006 ms | PASS |
| math-044 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 275.2 ms | 3.225 ms | PASS |
| math-045 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284.4 ms | 6.082 ms | PASS |
| math-046 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 287.6 ms | 9.439 ms | PASS |
| math-047 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.1 ms | 2.852 ms | PASS |
| math-048 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284 ms | 2.817 ms | PASS |
| math-049 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 286.1 ms | 3.224 ms | PASS |
| math-050 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 279.3 ms | 4.127 ms | PASS |
| math-051 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 284.3 ms | 2.802 ms | PASS |
| math-052 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 293.7 ms | 3.512 ms | PASS |
| math-053 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4584 primitives; 269.6 ms | 3.532 ms | PASS |
| math-054 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.4 ms | 5.040 ms | PASS |
| math-055 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 270.3 ms | 2.463 ms | PASS |
| math-056 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 285.6 ms | 2.601 ms | PASS |
| math-057 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 276.5 ms | 2.228 ms | PASS |
| math-058 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 286.5 ms | 2.226 ms | PASS |
| math-059 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4594 primitives; 270.6 ms | 2.231 ms | PASS |
| math-060 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283 ms | 2.982 ms | PASS |
| math-061 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 287.6 ms | 3.434 ms | PASS |
| math-062 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4140 primitives; 278.4 ms | 1.425 ms | PASS |
| math-063 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4120 primitives; 289.4 ms | 2.176 ms | PASS |
| math-064 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4602 primitives; 287.1 ms | 3.870 ms | PASS |
| math-065 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4232 primitives; 275.5 ms | 2.546 ms | PASS |
| math-066 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 12024 primitives; 368.4 ms | 141.191 ms | PASS |
| math-067 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9296 primitives; 375.7 ms | 189.734 ms | PASS |
| math-068 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18440 primitives; 399.4 ms | 126.956 ms | PASS |
| math-069 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19928 primitives; 429.2 ms | 160.415 ms | PASS |
| math-070 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15624 primitives; 390.3 ms | 108.186 ms | PASS |
| math-071 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 14632 primitives; 382.2 ms | 140.137 ms | PASS |
| math-072 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 21576 primitives; 414.7 ms | 112.003 ms | PASS |
| math-073 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 15004 primitives; 386.1 ms | 78.706 ms | PASS |
| math-074 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 19560 primitives; 401.4 ms | 142.759 ms | PASS |
| math-075 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 18104 primitives; 419.2 ms | 144.486 ms | PASS |
| math-076 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9588 primitives; 374.6 ms | 107.915 ms | PASS |
| math-077 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.4 ms | 1.873 ms | PASS |
| math-078 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 11864 primitives; 395.2 ms | 288.230 ms | PASS |
| math-079 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9288 primitives; 387 ms | 140.223 ms | PASS |
| math-080 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 5616 primitives; 415.1 ms | 128.994 ms | PASS |
| math-081 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 379.7 ms | 199.002 ms | PASS |
| math-082 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 10704 primitives; 363.8 ms | 266.107 ms | PASS |
| math-083 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7408 primitives; 379.4 ms | 208.035 ms | PASS |
| math-084 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 9024 primitives; 390.4 ms | 226.773 ms | PASS |
| math-085 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 278.4 ms | 6.411 ms | PASS |
| math-086 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 283.5 ms | 2.651 ms | PASS |
| math-087 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 7880 primitives; 397.5 ms | 212.442 ms | PASS |
| math-088 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 13680 primitives; 378.2 ms | 110.332 ms | PASS |
| math-089 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 96 primitives; 337.6 ms | 270.982 ms | PASS |
| math-090 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 3000 primitives; 362.2 ms | 370.608 ms | PASS |
| math-091 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 26594 primitives; 467.7 ms | 8.605 ms | PASS |
| math-092 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20252 primitives; 491.7 ms | 4.590 ms | PASS |
| math-093 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20196 primitives; 440.1 ms | 4.566 ms | PASS |
| math-094 | mathematics | mathematical_visual / implicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 20624 primitives; 434.7 ms | 8.616 ms | PASS |
| math-095 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 281.5 ms | 1.841 ms | PASS |
| math-096 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.2 ms | 4.784 ms | PASS |
| math-097 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4600 primitives; 342.3 ms | 4.784 ms | PASS |
| math-098 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels, undefined_domain_split | three: 4578 primitives; 282.3 ms | 2.283 ms | PASS |
| math-099 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 280.7 ms | 2.593 ms | PASS |
| math-100 | mathematics | mathematical_visual / explicit_surface | three / scene3d | orbit, reset_view | expression_residual, finite_geometry, axis_labels | three: 4608 primitives; 291.5 ms | 7.272 ms | PASS |
| heldout-001 | mathematics | interactive_visual / complex_mapping | svg / scene2d | point_angle, point_radius | complex_square_mapping, angle_doubles | svg: 71 primitives; 158.3 ms | 4.299 ms | PASS |
| heldout-002 | mathematics | interactive_visual / polar_plot | svg / scene2d | theta, playback, play, pause, restart | polar_radius, four_petals | svg: 35 primitives; 272.9 ms | 2.012 ms | PASS |
| heldout-003 | mathematics | interactive_visual / fourier_series | svg / scene2d | terms | odd_harmonics, gibbs_overshoot | svg: 36 primitives; 96.5 ms | 2.717 ms | PASS |
| heldout-004 | mathematics | interactive_visual / logistic_map | canvas / simulation2d | growth_rate, initial_value | iterate_logistic, bounded_unit_interval | canvas: 1045 primitives; 133.6 ms | 6.071 ms | PASS |
| heldout-005 | mathematics | interactive_visual / lagrange_multiplier | svg / scene2d | constraint_offset | tangent_contours, parallel_gradients | svg: 37 primitives; 61.5 ms | 2.417 ms | PASS |
| heldout-006 | mathematics | interactive_visual / parametric_surface | three / scene3d | path_position, playback | mobius_single_boundary, parametric_samples | three: 1890 primitives; 309.7 ms | 0.814 ms | PASS |
| heldout-007 | mathematics | interactive_visual / vector_field | svg / scene2d | probe_x, probe_y | field_components, divergence_zero | svg: 49 primitives; 76.7 ms | 0.916 ms | PASS |
| heldout-008 | mathematics | interactive_visual / convolution | svg / scene2d | shift | overlap_equals_convolution, triangular_result | svg: 33 primitives; 44.9 ms | 0.867 ms | PASS |
| heldout-009 | physics | interactive_visual / kepler_orbit | canvas / simulation2d | eccentricity, true_anomaly, playback, play, pause, restart | acceleration_inward, equal_area | canvas: 885 primitives; 288.9 ms | 1.127 ms | PASS |
| heldout-010 | physics | interactive_visual / coupled_oscillators | canvas / simulation2d | mode, playback, play, pause, restart | normal_mode_phase, energy_bounded | canvas: 1090 primitives; 297.5 ms | 1.479 ms | PASS |
| heldout-011 | physics | interactive_visual / standing_wave | svg / scene2d | harmonic | node_count, fixed_endpoints | svg: 41 primitives; 54.8 ms | 0.831 ms | PASS |
| heldout-012 | physics | interactive_visual / doppler | canvas / simulation2d | source_speed, playback | front_wavelength_shorter, wavefront_spacing | canvas: 722 primitives; 74.2 ms | 1.908 ms | PASS |
| heldout-013 | physics | interactive_visual / double_slit | svg / scene2d | slit_separation, wavelength | fringe_spacing, central_maximum | svg: 39 primitives; 69.1 ms | 1.180 ms | PASS |
| heldout-014 | physics | interactive_visual / lorentz_force | three / scene3d | charge, field, speed, playback, play, pause, restart | force_perpendicular_velocity, helix_radius | three: ? primitives; 703.2 ms | 0.903 ms | PASS |
| heldout-015 | physics | interactive_visual / blackbody | svg / scene2d | temperature | peak_shifts_shorter, radiance_positive | svg: 32 primitives; 70.5 ms | 2.045 ms | PASS |
| heldout-016 | physics | interactive_visual / entropy_cycle | canvas / simulation2d | step | closed_cycle, process_direction | canvas: 985 primitives; 104.6 ms | 0.677 ms | PASS |
| heldout-017 | chemistry | interactive_visual / benzene | svg / scene2d | bond_model | six_carbon_ring, alternating_or_delocalized | svg: 20 primitives; 44.1 ms | 0.544 ms | PASS |
| heldout-018 | chemistry | interactive_visual / molecular_geometry | three / scene3d | molecule | coordination_geometry, bond_angles | three: ? primitives; 141.6 ms | 0.479 ms | PASS |
| heldout-019 | chemistry | interactive_visual / electrochemical_cell | svg / scene2d | zinc_concentration, copper_concentration | electron_anode_to_cathode, ion_migration | svg: 17 primitives; 66.4 ms | 0.513 ms | PASS |
| heldout-020 | chemistry | interactive_visual / kinetics | svg / scene2d | order, rate_constant | integrated_rate_law, half_life_behavior | svg: 37 primitives; 165.3 ms | 3.825 ms | PASS |
| heldout-021 | chemistry | interactive_visual / phase_diagram | svg / scene2d | temperature, pressure | phase_region, triple_point | svg: 31 primitives; 91.8 ms | 0.470 ms | PASS |
| heldout-022 | chemistry | interactive_visual / equilibrium_shift | svg / scene2d | pressure, temperature | stoichiometric_ratio, le_chatelier_direction | svg: 37 primitives; 95.7 ms | 0.605 ms | PASS |
| heldout-023 | biology | interactive_visual / enzyme_kinetics | svg / scene2d | substrate, inhibitor | vmax_limit, competitive_km_shift | svg: 29 primitives; 103.8 ms | 1.535 ms | PASS |
| heldout-024 | biology | interactive_visual / dna_replication | svg / scene2d | step, play, pause, restart | five_to_three_synthesis, strand_roles | svg: 23 primitives; 267.3 ms | 0.542 ms | PASS |
| heldout-025 | biology | interactive_visual / nephron | svg / scene2d | segment | flow_order, reabsorption_location | svg: 43 primitives; 46.6 ms | 0.678 ms | PASS |
| heldout-026 | biology | interactive_visual / predator_prey | canvas / simulation2d | prey_growth, predation, playback, play, pause, restart | population_nonnegative, phase_cycle | canvas: 1005 primitives; 313.5 ms | 3.500 ms | PASS |
| heldout-027 | biology | interactive_visual / membrane_transport | svg / scene2d | transport_mode | gradient_direction, atp_only_active | svg: 23 primitives; 48 ms | 0.379 ms | PASS |
| heldout-028 | computer_science | interactive_visual / merge_sort | svg / scene2d | step, play, pause, restart | sorted_output, stable_merge | svg: 81 primitives; 232.2 ms | 1.021 ms | PASS |
| heldout-029 | computer_science | interactive_visual / hash_table | svg / scene2d | key, operation, step | bucket_hash, collision_chain | svg: 35 primitives; 95.7 ms | 0.610 ms | PASS |
| heldout-030 | computer_science | interactive_visual / graph_traversal | svg / scene2d | algorithm, step | frontier_policy, visits_once | svg: 23 primitives; 69 ms | 0.484 ms | PASS |
| heldout-031 | computer_science | interactive_visual / heap | svg / scene2d | operation, value, step, play, pause, restart | parent_not_greater_child, extracts_minimum | svg: 27 primitives; 278.4 ms | 0.623 ms | PASS |
| heldout-032 | computer_science | interactive_visual / recursion_stack | svg / scene2d | step | stack_lifo, factorial_result | svg: 39 primitives; 53.5 ms | 0.683 ms | PASS |
| heldout-033 | computer_science | interactive_visual / virtual_memory | svg / scene2d | address, step, play, pause, restart | page_offset_preserved, fault_path | svg: 25 primitives; 252.4 ms | 0.452 ms | PASS |
| heldout-034 | signals | interactive_visual / impulse_response | svg / scene2d | shift, step | discrete_convolution_sum, output_length | svg: 29 primitives; 68.2 ms | 0.468 ms | PASS |
| heldout-035 | controls | interactive_visual / bode_plot | svg / scene2d | cutoff | minus3db_at_cutoff, phase_transition | svg: 27 primitives; 44.3 ms | 1.336 ms | PASS |
| heldout-036 | controls | interactive_visual / nyquist | svg / scene2d | gain | encirclement_count, closed_loop_stability | svg: 27 primitives; 102.4 ms | 0.900 ms | PASS |
| heldout-037 | controls | interactive_visual / pid_response | svg / scene2d | kp, ki, kd | response_metrics, final_value | svg: 35 primitives; 146.7 ms | 2.129 ms | PASS |
| heldout-038 | signals | interactive_visual / pwm | svg / scene2d | duty_cycle | pulse_width_ratio, average_voltage | svg: 27 primitives; 51.8 ms | 0.622 ms | PASS |
| heldout-039 | signals | interactive_visual / spectrogram | canvas / simulation2d | sweep_rate, playback | frequency_rises_with_time, time_frequency_alignment | canvas: 2056 primitives; 80.1 ms | 3.865 ms | PASS |
| heldout-040 | robotics | interactive_visual / robot_arm | svg / scene2d | target_x, target_y, elbow_mode | link_lengths_constant, end_effector_target | svg: 13 primitives; 114 ms | 0.595 ms | PASS |
| heldout-041 | robotics | interactive_visual / kalman_filter | svg / scene2d | noise, step, play, pause, restart | covariance_contracts_on_update, estimate_between_prior_measurement | svg: 39 primitives; 319.9 ms | 2.495 ms | PASS |
| heldout-042 | engineering | interactive_visual / truss | svg / scene2d | load | joint_force_balance, member_sign | svg: 19 primitives; 45.1 ms | 0.528 ms | PASS |
| heldout-043 | engineering | interactive_visual / beam_bending | canvas / simulation2d | load_position, play, pause, restart | support_reactions, moment_zero_at_supports | canvas: 1603 primitives; 358.9 ms | 2.218 ms | PASS |
| heldout-044 | engineering | interactive_visual / fluid_flow | canvas / simulation2d | speed | streamline_symmetry, no_penetration | canvas: 855 primitives; 96.7 ms | 17.612 ms | PASS |
| heldout-045 | engineering | interactive_visual / heat_diffusion | canvas / simulation2d | time, playback, play, pause, restart | temperature_smooths, energy_bounded | canvas: 2053 primitives; 299.2 ms | 2.639 ms | PASS |
| heldout-046 | computer_science | interactive_visual / state_machine | svg / scene2d | pedestrian_request, step | legal_transition, mutually_exclusive_lights | svg: 17 primitives; 65.1 ms | 0.543 ms | PASS |
| heldout-047 | ai | interactive_visual / decision_boundary | canvas / simulation2d | epoch, learning_rate | class_regions, loss_nonincreasing | canvas: 2069 primitives; 176.7 ms | 18.833 ms | PASS |
| heldout-048 | ai | interactive_visual / backprop_graph | svg / scene2d | w, x, b, step | chain_rule_gradients, forward_value | svg: 27 primitives; 109.2 ms | 0.901 ms | PASS |
| heldout-049 | mixed | interactive_visual / energy_sankey | svg / scene2d | efficiency | energy_conservation, units_joules | svg: 15 primitives; 43.1 ms | 0.533 ms | PASS |
| heldout-050 | mixed | interactive_visual / uncertainty_propagation | canvas / simulation2d | mass_sigma, volume_sigma, samples | positive_volume, density_distribution | canvas: 903 primitives; 139.6 ms | 2.388 ms | PASS |

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
  --revision working-tree
```

A pass requires intent, family, renderer, spec kind, exact named controls, accessible fallback, semantic oracles, and a real non-empty browser render. Presence of a canvas or WebGL context alone is never counted.
