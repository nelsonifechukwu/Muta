# Visualization Engine V2 — User Holdout Report

- Frozen pre-holdout candidate: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd` at `2026-08-27T12:07:54+01:00`
- Final revision: `4bc418b8a86a7c9ded5e1333239bb5e31b72b2bb`
- Immutable first run: 31/50 Python compile; 31/31 compiled specs rendered
- Final Python gate: 50/50
- Final browser gate: 50/50
- Combined: 50/50; failures 0; waivers 0

Reproduce the deterministic compile/oracle pass and merge the separately captured real-browser evidence with:

```bash
python -m scripts.visualization_v2_user_holdout --write --browser-results /tmp/muta-v2-user-holdout-final-browser.json --revision <candidate-revision>
```

| ID | Title | Domain | Intent | Family | Renderer | Controls | Compile ms | Browser ms | Oracle | Browser | Pass |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|
| user-holdout-001 | Linear function | mathematics | interactive visualization | explicit_curve | svg | none | 5.276 | 24.6 | pass | pass | pass |
| user-holdout-002 | Parabola | mathematics | interactive visualization | explicit_curve | svg | none | 1.929 | 91.0 | pass | pass | pass |
| user-holdout-003 | Sine wave | mathematics | interactive visualization | explicit_curve | svg | none | 2.068 | 101.7 | pass | pass | pass |
| user-holdout-004 | Circle | mathematics | interactive visualization | implicit_curve | svg | none | 5.719 | 99.7 | pass | pass | pass |
| user-holdout-005 | 3D sphere | mathematics | interactive visualization | implicit_surface | three | orbit, reset_view | 98.786 | 407.9 | pass | pass | pass |
| user-holdout-006 | Vector addition | mathematics | interactive visualization | vector_addition | svg | none | 0.230 | 20.3 | pass | pass | pass |
| user-holdout-007 | Basic atom | chemistry | interactive visualization | atom | svg | atomic_number | 1.361 | 131.7 | pass | pass | pass |
| user-holdout-008 | Animal cell | biology | interactive visualization | animal_cell | svg | organelle | 0.529 | 101.1 | pass | pass | pass |
| user-holdout-009 | Simple electric circuit | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.336 | 85.6 | pass | pass | pass |
| user-holdout-010 | Binary representation | computer science | interactive visualization | binary_representation | svg | none | 0.227 | 22.0 | pass | pass | pass |
| user-holdout-011 | Interactive parabola | mathematics | interactive visualization | quadratic | svg | a, b, c | 0.595 | 86.7 | pass | pass | pass |
| user-holdout-012 | Interactive unit circle | mathematics | interactive visualization | unit_circle | svg | angle | 0.501 | 43.8 | pass | pass | pass |
| user-holdout-013 | 3D Gaussian surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.366 | 268.0 | pass | pass | pass |
| user-holdout-014 | Damped wave surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.839 | 287.9 | pass | pass | pass |
| user-holdout-015 | Projectile motion | physics | interactive visualization | projectile | svg | angle, speed | 0.502 | 77.0 | pass | pass | pass |
| user-holdout-016 | Inclined plane | physics | interactive visualization | inclined_plane | svg | incline | 0.348 | 46.2 | pass | pass | pass |
| user-holdout-017 | Hooke's law | physics | interactive visualization | spring_mass | svg | spring_constant, displacement | 0.452 | 64.8 | pass | pass | pass |
| user-holdout-018 | Ohm's law | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.352 | 85.1 | pass | pass | pass |
| user-holdout-019 | Refraction | physics | interactive visualization | refraction | svg | incident_angle, medium | 0.288 | 66.1 | pass | pass | pass |
| user-holdout-020 | Molecular geometry | chemistry | interactive visualization | molecular_geometry | three | molecule | 0.354 | 143.9 | pass | pass | pass |
| user-holdout-021 | Derivative visualizer | mathematics | interactive visualization | derivative_tangent | svg | x | 0.679 | 48.7 | pass | pass | pass |
| user-holdout-022 | Riemann sum | mathematics | interactive visualization | riemann_sum | svg | rectangles | 0.554 | 42.6 | pass | pass | pass |
| user-holdout-023 | Gradient field | mathematics | interactive visualization | gradient_linked | svg | point_x, point_y | 2.147 | 156.1 | pass | pass | pass |
| user-holdout-024 | Matrix transformation | mathematics | interactive visualization | linear_transform | svg | matrix | 0.422 | 73.7 | pass | pass | pass |
| user-holdout-025 | Eigenvector visualization | mathematics | interactive visualization | linear_transform | svg | matrix | 0.324 | 43.4 | pass | pass | pass |
| user-holdout-026 | Travelling wave | physics | interactive animation | travelling_wave | canvas | amplitude, wavelength, frequency, play, pause, restart | 0.532 | 287.9 | pass | pass | pass |
| user-holdout-027 | Simple harmonic oscillator | physics | interactive animation | harmonic_motion | canvas | spring_constant, mass, play, pause, restart | 0.751 | 294.1 | pass | pass | pass |
| user-holdout-028 | Elastic collision | physics | interactive visualization | elastic_collision | svg | mass_1, velocity_1, mass_2, velocity_2 | 0.287 | 119.6 | pass | pass | pass |
| user-holdout-029 | Electric field | physics | interactive visualization | electric_field_vectors | canvas | positive_charge_x, negative_charge_x, test_x, test_y | 1.304 | 130.9 | pass | pass | pass |
| user-holdout-030 | RC circuit | physics | interactive animation | rc_circuit | svg | mode, resistance, capacitance, play, pause, restart | 0.956 | 367.5 | pass | pass | pass |
| user-holdout-031 | Binary search | computer science | interactive animation | binary_search | svg | target, step, play, pause, restart | 0.487 | 254.3 | pass | pass | pass |
| user-holdout-032 | Sorting algorithm | computer science | interactive visualization | merge_sort | svg | step | 0.759 | 117.3 | pass | pass | pass |
| user-holdout-033 | Binary search tree | computer science | interactive animation | binary_search_tree | svg | insert, step, play, pause, restart | 0.314 | 302.5 | pass | pass | pass |
| user-holdout-034 | Dijkstra's algorithm | computer science | interactive animation | dijkstra | svg | source, destination, step, play, pause, restart | 0.355 | 282.5 | pass | pass | pass |
| user-holdout-035 | Neural network | computer science | interactive visualization | neural_network | svg | weight, step | 0.417 | 65.9 | pass | pass | pass |
| user-holdout-036 | Gradient descent | mathematics | interactive visualization | gradient_descent | svg | learning_rate, step | 2.414 | 166.2 | pass | pass | pass |
| user-holdout-037 | Differential-drive robot | robotics | interactive visualization | differential_drive | canvas | left_velocity, right_velocity | 0.637 | 82.4 | pass | pass | pass |
| user-holdout-038 | Robot arm forward kinematics | robotics | interactive visualization | robot_forward_kinematics | svg | joint_1, joint_2, joint_3 | 0.183 | 86.3 | pass | pass | pass |
| user-holdout-039 | Sampling and aliasing | signals | interactive visualization | sampling_aliasing | canvas | signal_frequency, sample_frequency | 1.417 | 135.2 | pass | pass | pass |
| user-holdout-040 | Fourier decomposition | signals | interactive visualization | fourier_series | svg | terms | 1.475 | 131.6 | pass | pass | pass |
| user-holdout-041 | 3D vector field | mathematics | interactive visualization | vector_field_3d | three | point_x, point_y, point_z | 0.465 | 338.4 | pass | pass | pass |
| user-holdout-042 | Double pendulum | physics | interactive animation | double_pendulum | canvas | angle_1, angle_2, play, pause, restart | 2.124 | 353.7 | pass | pass | pass |
| user-holdout-043 | Lorenz attractor | dynamical systems | interactive animation | lorenz_attractor | three | sigma, rho, beta, play, pause, restart | 2.811 | 645.7 | pass | pass | pass |
| user-holdout-044 | Gyroid | mathematics | interactive visualization | implicit_surface | three | clip_z, orbit, reset_view | 0.675 | 570.5 | pass | pass | pass |
| user-holdout-045 | Electromagnetic wave | physics | interactive animation | electromagnetic_wave | three | amplitude, wavelength, play, pause, restart | 1.258 | 642.8 | pass | pass | pass |
| user-holdout-046 | Action potential | biology | interactive visualization | action_potential | svg | time | 0.717 | 105.8 | pass | pass | pass |
| user-holdout-047 | Chemical titration | chemistry | interactive animation | titration | svg | titrant_volume, play, pause, restart | 0.959 | 282.1 | pass | pass | pass |
| user-holdout-048 | CPU memory hierarchy | computer science | interactive animation | virtual_memory | svg | address, step, play, pause, restart | 0.327 | 262.3 | pass | pass | pass |
| user-holdout-049 | Robot localization | robotics | interactive visualization | robot_localization | canvas | odometry_noise, sensor_noise, step | 1.431 | 111.6 | pass | pass | pass |
| user-holdout-050 | Full Kalman filter visualization | controls | interactive animation | kalman_filter | svg | noise, process_noise, step, play, pause, restart | 1.509 | 389.1 | pass | pass | pass |
