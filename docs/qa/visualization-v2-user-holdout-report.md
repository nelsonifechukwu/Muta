# Visualization Engine V2 — User Holdout Report

- Frozen pre-holdout candidate: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd` at `2026-08-27T12:07:54+01:00`
- Final revision: `edb6c93ea0901146911a8c0762d8fc247f633158`
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
| user-holdout-001 | Linear function | mathematics | interactive visualization | explicit_curve | svg | none | 5.302 | 116.7 | pass | pass | pass |
| user-holdout-002 | Parabola | mathematics | interactive visualization | explicit_curve | svg | none | 1.873 | 100.1 | pass | pass | pass |
| user-holdout-003 | Sine wave | mathematics | interactive visualization | explicit_curve | svg | none | 1.942 | 81.3 | pass | pass | pass |
| user-holdout-004 | Circle | mathematics | interactive visualization | implicit_curve | svg | none | 5.535 | 22.1 | pass | pass | pass |
| user-holdout-005 | 3D sphere | mathematics | interactive visualization | implicit_surface | three | orbit, reset_view | 96.553 | 370.4 | pass | pass | pass |
| user-holdout-006 | Vector addition | mathematics | interactive visualization | vector_addition | svg | none | 0.250 | 29.8 | pass | pass | pass |
| user-holdout-007 | Basic atom | chemistry | interactive visualization | atom | svg | atomic_number | 1.586 | 121.0 | pass | pass | pass |
| user-holdout-008 | Animal cell | biology | interactive visualization | animal_cell | svg | organelle | 0.300 | 98.6 | pass | pass | pass |
| user-holdout-009 | Simple electric circuit | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.231 | 88.4 | pass | pass | pass |
| user-holdout-010 | Binary representation | computer science | interactive visualization | binary_representation | svg | none | 0.212 | 22.8 | pass | pass | pass |
| user-holdout-011 | Interactive parabola | mathematics | interactive visualization | quadratic | svg | a, b, c | 0.514 | 85.5 | pass | pass | pass |
| user-holdout-012 | Interactive unit circle | mathematics | interactive visualization | unit_circle | svg | angle | 0.546 | 45.4 | pass | pass | pass |
| user-holdout-013 | 3D Gaussian surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.459 | 270.7 | pass | pass | pass |
| user-holdout-014 | Damped wave surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.964 | 286.4 | pass | pass | pass |
| user-holdout-015 | Projectile motion | physics | interactive visualization | projectile | svg | angle, speed | 0.497 | 78.2 | pass | pass | pass |
| user-holdout-016 | Inclined plane | physics | interactive visualization | inclined_plane | svg | incline | 0.263 | 45.9 | pass | pass | pass |
| user-holdout-017 | Hooke's law | physics | interactive visualization | spring_mass | svg | spring_constant, displacement | 0.331 | 65.1 | pass | pass | pass |
| user-holdout-018 | Ohm's law | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.307 | 87.8 | pass | pass | pass |
| user-holdout-019 | Refraction | physics | interactive visualization | refraction | svg | incident_angle, medium | 0.251 | 68.1 | pass | pass | pass |
| user-holdout-020 | Molecular geometry | chemistry | interactive visualization | molecular_geometry | three | molecule | 0.326 | 145.7 | pass | pass | pass |
| user-holdout-021 | Derivative visualizer | mathematics | interactive visualization | derivative_tangent | svg | x | 0.623 | 49.0 | pass | pass | pass |
| user-holdout-022 | Riemann sum | mathematics | interactive visualization | riemann_sum | svg | rectangles | 0.501 | 43.2 | pass | pass | pass |
| user-holdout-023 | Gradient field | mathematics | interactive visualization | gradient_linked | svg | point_x, point_y | 2.140 | 137.4 | pass | pass | pass |
| user-holdout-024 | Matrix transformation | mathematics | interactive visualization | linear_transform | svg | matrix | 0.397 | 73.6 | pass | pass | pass |
| user-holdout-025 | Eigenvector visualization | mathematics | interactive visualization | linear_transform | svg | matrix | 0.296 | 43.3 | pass | pass | pass |
| user-holdout-026 | Travelling wave | physics | interactive animation | travelling_wave | canvas | amplitude, wavelength, frequency, play, pause, restart | 0.493 | 286.3 | pass | pass | pass |
| user-holdout-027 | Simple harmonic oscillator | physics | interactive animation | harmonic_motion | canvas | spring_constant, mass, play, pause, restart | 0.709 | 295.4 | pass | pass | pass |
| user-holdout-028 | Elastic collision | physics | interactive visualization | elastic_collision | svg | mass_1, velocity_1, mass_2, velocity_2 | 0.257 | 121.7 | pass | pass | pass |
| user-holdout-029 | Electric field | physics | interactive visualization | electric_field_vectors | canvas | positive_charge_x, negative_charge_x, test_x, test_y | 1.214 | 124.2 | pass | pass | pass |
| user-holdout-030 | RC circuit | physics | interactive animation | rc_circuit | svg | mode, resistance, capacitance, play, pause, restart | 0.816 | 378.6 | pass | pass | pass |
| user-holdout-031 | Binary search | computer science | interactive animation | binary_search | svg | target, step, play, pause, restart | 0.408 | 264.2 | pass | pass | pass |
| user-holdout-032 | Sorting algorithm | computer science | interactive visualization | merge_sort | svg | step | 0.698 | 97.2 | pass | pass | pass |
| user-holdout-033 | Binary search tree | computer science | interactive animation | binary_search_tree | svg | insert, step, play, pause, restart | 0.289 | 301.7 | pass | pass | pass |
| user-holdout-034 | Dijkstra's algorithm | computer science | interactive animation | dijkstra | svg | source, destination, step, play, pause, restart | 0.323 | 295.6 | pass | pass | pass |
| user-holdout-035 | Neural network | computer science | interactive visualization | neural_network | svg | weight, step | 0.378 | 73.7 | pass | pass | pass |
| user-holdout-036 | Gradient descent | mathematics | interactive visualization | gradient_descent | svg | learning_rate, step | 2.161 | 142.4 | pass | pass | pass |
| user-holdout-037 | Differential-drive robot | robotics | interactive visualization | differential_drive | canvas | left_velocity, right_velocity | 0.560 | 102.7 | pass | pass | pass |
| user-holdout-038 | Robot arm forward kinematics | robotics | interactive visualization | robot_forward_kinematics | svg | joint_1, joint_2, joint_3 | 0.170 | 89.8 | pass | pass | pass |
| user-holdout-039 | Sampling and aliasing | signals | interactive visualization | sampling_aliasing | canvas | signal_frequency, sample_frequency | 1.353 | 115.6 | pass | pass | pass |
| user-holdout-040 | Fourier decomposition | signals | interactive visualization | fourier_series | svg | terms | 1.482 | 68.7 | pass | pass | pass |
| user-holdout-041 | 3D vector field | mathematics | interactive visualization | vector_field_3d | three | point_x, point_y, point_z | 0.418 | 403.5 | pass | pass | pass |
| user-holdout-042 | Double pendulum | physics | interactive animation | double_pendulum | canvas | angle_1, angle_2, play, pause, restart | 2.065 | 386.0 | pass | pass | pass |
| user-holdout-043 | Lorenz attractor | dynamical systems | interactive animation | lorenz_attractor | three | sigma, rho, beta, play, pause, restart | 2.762 | 732.8 | pass | pass | pass |
| user-holdout-044 | Gyroid | mathematics | interactive visualization | implicit_surface | three | clip_z, orbit, reset_view | 0.626 | 567.5 | pass | pass | pass |
| user-holdout-045 | Electromagnetic wave | physics | interactive animation | electromagnetic_wave | three | amplitude, wavelength, play, pause, restart | 1.203 | 645.6 | pass | pass | pass |
| user-holdout-046 | Action potential | biology | interactive visualization | action_potential | svg | time | 0.676 | 116.1 | pass | pass | pass |
| user-holdout-047 | Chemical titration | chemistry | interactive animation | titration | svg | titrant_volume, play, pause, restart | 0.804 | 280.8 | pass | pass | pass |
| user-holdout-048 | CPU memory hierarchy | computer science | interactive animation | virtual_memory | svg | address, step, play, pause, restart | 0.279 | 259.8 | pass | pass | pass |
| user-holdout-049 | Robot localization | robotics | interactive visualization | robot_localization | canvas | odometry_noise, sensor_noise, step | 1.160 | 115.5 | pass | pass | pass |
| user-holdout-050 | Full Kalman filter visualization | controls | interactive animation | kalman_filter | svg | noise, process_noise, step, play, pause, restart | 1.396 | 389.1 | pass | pass | pass |
