# Visualization Engine V2 — User Holdout Report

- Frozen pre-holdout candidate: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd` at `2026-08-27T12:07:54+01:00`
- Final revision: `9a11a8b5682167441ff5e051aafb4e8eff7d8931`
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
| user-holdout-001 | Linear function | mathematics | interactive visualization | explicit_curve | svg | none | 6.067 | 39.1 | pass | pass | pass |
| user-holdout-002 | Parabola | mathematics | interactive visualization | explicit_curve | svg | none | 1.860 | 73.8 | pass | pass | pass |
| user-holdout-003 | Sine wave | mathematics | interactive visualization | explicit_curve | svg | none | 1.729 | 104.3 | pass | pass | pass |
| user-holdout-004 | Circle | mathematics | interactive visualization | implicit_curve | svg | none | 5.556 | 49.0 | pass | pass | pass |
| user-holdout-005 | 3D sphere | mathematics | interactive visualization | implicit_surface | three | orbit, reset_view | 95.257 | 357.3 | pass | pass | pass |
| user-holdout-006 | Vector addition | mathematics | interactive visualization | vector_addition | svg | none | 0.197 | 24.4 | pass | pass | pass |
| user-holdout-007 | Basic atom | chemistry | interactive visualization | atom | svg | atomic_number | 1.488 | 92.9 | pass | pass | pass |
| user-holdout-008 | Animal cell | biology | interactive visualization | animal_cell | svg | organelle | 0.304 | 82.0 | pass | pass | pass |
| user-holdout-009 | Simple electric circuit | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.255 | 85.0 | pass | pass | pass |
| user-holdout-010 | Binary representation | computer science | interactive visualization | binary_representation | svg | none | 0.187 | 24.5 | pass | pass | pass |
| user-holdout-011 | Interactive parabola | mathematics | interactive visualization | quadratic | svg | a, b, c | 0.519 | 84.8 | pass | pass | pass |
| user-holdout-012 | Interactive unit circle | mathematics | interactive visualization | unit_circle | svg | angle | 0.469 | 43.3 | pass | pass | pass |
| user-holdout-013 | 3D Gaussian surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.495 | 255.0 | pass | pass | pass |
| user-holdout-014 | Damped wave surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.820 | 272.6 | pass | pass | pass |
| user-holdout-015 | Projectile motion | physics | interactive visualization | projectile | svg | angle, speed | 0.482 | 68.6 | pass | pass | pass |
| user-holdout-016 | Inclined plane | physics | interactive visualization | inclined_plane | svg | incline | 0.250 | 43.6 | pass | pass | pass |
| user-holdout-017 | Hooke's law | physics | interactive visualization | spring_mass | svg | spring_constant, displacement | 0.292 | 64.6 | pass | pass | pass |
| user-holdout-018 | Ohm's law | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.276 | 86.6 | pass | pass | pass |
| user-holdout-019 | Refraction | physics | interactive visualization | refraction | svg | incident_angle, medium | 0.217 | 62.3 | pass | pass | pass |
| user-holdout-020 | Molecular geometry | chemistry | interactive visualization | molecular_geometry | three | molecule | 0.286 | 142.6 | pass | pass | pass |
| user-holdout-021 | Derivative visualizer | mathematics | interactive visualization | derivative_tangent | svg | x | 0.561 | 41.5 | pass | pass | pass |
| user-holdout-022 | Riemann sum | mathematics | interactive visualization | riemann_sum | svg | rectangles | 0.446 | 40.1 | pass | pass | pass |
| user-holdout-023 | Gradient field | mathematics | interactive visualization | gradient_linked | svg | point_x, point_y | 1.903 | 132.3 | pass | pass | pass |
| user-holdout-024 | Matrix transformation | mathematics | interactive visualization | linear_transform | svg | matrix | 0.368 | 72.9 | pass | pass | pass |
| user-holdout-025 | Eigenvector visualization | mathematics | interactive visualization | linear_transform | svg | matrix | 0.279 | 42.8 | pass | pass | pass |
| user-holdout-026 | Travelling wave | physics | interactive animation | travelling_wave | canvas | amplitude, wavelength, frequency, play, pause, restart | 0.438 | 283.6 | pass | pass | pass |
| user-holdout-027 | Simple harmonic oscillator | physics | interactive animation | harmonic_motion | canvas | spring_constant, mass, play, pause, restart | 0.651 | 294.5 | pass | pass | pass |
| user-holdout-028 | Elastic collision | physics | interactive visualization | elastic_collision | svg | mass_1, velocity_1, mass_2, velocity_2 | 0.243 | 119.9 | pass | pass | pass |
| user-holdout-029 | Electric field | physics | interactive visualization | electric_field_vectors | canvas | positive_charge_x, negative_charge_x, test_x, test_y | 1.293 | 138.4 | pass | pass | pass |
| user-holdout-030 | RC circuit | physics | interactive animation | rc_circuit | svg | mode, resistance, capacitance, play, pause, restart | 0.857 | 364.4 | pass | pass | pass |
| user-holdout-031 | Binary search | computer science | interactive animation | binary_search | svg | target, step, play, pause, restart | 0.421 | 260.1 | pass | pass | pass |
| user-holdout-032 | Sorting algorithm | computer science | interactive visualization | merge_sort | svg | step | 0.656 | 101.8 | pass | pass | pass |
| user-holdout-033 | Binary search tree | computer science | interactive animation | binary_search_tree | svg | insert, step, play, pause, restart | 0.256 | 251.2 | pass | pass | pass |
| user-holdout-034 | Dijkstra's algorithm | computer science | interactive animation | dijkstra | svg | source, destination, step, play, pause, restart | 0.291 | 281.8 | pass | pass | pass |
| user-holdout-035 | Neural network | computer science | interactive visualization | neural_network | svg | weight, step | 0.335 | 67.8 | pass | pass | pass |
| user-holdout-036 | Gradient descent | mathematics | interactive visualization | gradient_descent | svg | learning_rate, step | 2.097 | 88.9 | pass | pass | pass |
| user-holdout-037 | Differential-drive robot | robotics | interactive visualization | differential_drive | canvas | left_velocity, right_velocity | 0.530 | 67.2 | pass | pass | pass |
| user-holdout-038 | Robot arm forward kinematics | robotics | interactive visualization | robot_forward_kinematics | svg | joint_1, joint_2, joint_3 | 0.176 | 86.7 | pass | pass | pass |
| user-holdout-039 | Sampling and aliasing | signals | interactive visualization | sampling_aliasing | canvas | signal_frequency, sample_frequency | 1.411 | 89.5 | pass | pass | pass |
| user-holdout-040 | Fourier decomposition | signals | interactive visualization | fourier_series | svg | terms | 1.407 | 71.9 | pass | pass | pass |
| user-holdout-041 | 3D vector field | mathematics | interactive visualization | vector_field_3d | three | point_x, point_y, point_z | 0.419 | 333.8 | pass | pass | pass |
| user-holdout-042 | Double pendulum | physics | interactive animation | double_pendulum | canvas | angle_1, angle_2, play, pause, restart | 2.027 | 304.8 | pass | pass | pass |
| user-holdout-043 | Lorenz attractor | dynamical systems | interactive animation | lorenz_attractor | three | sigma, rho, beta, play, pause, restart | 2.566 | 642.4 | pass | pass | pass |
| user-holdout-044 | Gyroid | mathematics | interactive visualization | implicit_surface | three | clip_z, orbit, reset_view | 0.721 | 581.1 | pass | pass | pass |
| user-holdout-045 | Electromagnetic wave | physics | interactive animation | electromagnetic_wave | three | amplitude, wavelength, play, pause, restart | 1.201 | 523.8 | pass | pass | pass |
| user-holdout-046 | Action potential | biology | interactive visualization | action_potential | svg | time | 0.679 | 132.3 | pass | pass | pass |
| user-holdout-047 | Chemical titration | chemistry | interactive animation | titration | svg | titrant_volume, play, pause, restart | 0.729 | 260.5 | pass | pass | pass |
| user-holdout-048 | CPU memory hierarchy | computer science | interactive animation | virtual_memory | svg | address, step, play, pause, restart | 0.256 | 258.6 | pass | pass | pass |
| user-holdout-049 | Robot localization | robotics | interactive visualization | robot_localization | canvas | odometry_noise, sensor_noise, step | 1.242 | 148.9 | pass | pass | pass |
| user-holdout-050 | Full Kalman filter visualization | controls | interactive animation | kalman_filter | svg | noise, process_noise, step, play, pause, restart | 1.276 | 372.9 | pass | pass | pass |
