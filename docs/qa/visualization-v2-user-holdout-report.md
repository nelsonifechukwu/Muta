# Visualization Engine V2 — User Holdout Report

- Frozen pre-holdout candidate: `ae3cc2e1572b042a0d53ab5af4fe1143e9cb71cd` at `2026-08-27T12:07:54+01:00`
- Final revision: `fba3c2aa42675965aada60917a041f772b5b47a6`
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
| user-holdout-001 | Linear function | mathematics | interactive visualization | explicit_curve | svg | none | 5.318 | 70.7 | pass | pass | pass |
| user-holdout-002 | Parabola | mathematics | interactive visualization | explicit_curve | svg | none | 1.829 | 97.5 | pass | pass | pass |
| user-holdout-003 | Sine wave | mathematics | interactive visualization | explicit_curve | svg | none | 2.045 | 102.8 | pass | pass | pass |
| user-holdout-004 | Circle | mathematics | interactive visualization | implicit_curve | svg | none | 5.196 | 98.9 | pass | pass | pass |
| user-holdout-005 | 3D sphere | mathematics | interactive visualization | implicit_surface | three | orbit, reset_view | 95.272 | 392.4 | pass | pass | pass |
| user-holdout-006 | Vector addition | mathematics | interactive visualization | vector_addition | svg | none | 0.207 | 24.3 | pass | pass | pass |
| user-holdout-007 | Basic atom | chemistry | interactive visualization | atom | svg | atomic_number | 1.536 | 108.2 | pass | pass | pass |
| user-holdout-008 | Animal cell | biology | interactive visualization | animal_cell | svg | organelle | 0.293 | 101.7 | pass | pass | pass |
| user-holdout-009 | Simple electric circuit | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.228 | 88.0 | pass | pass | pass |
| user-holdout-010 | Binary representation | computer science | interactive visualization | binary_representation | svg | none | 0.176 | 19.8 | pass | pass | pass |
| user-holdout-011 | Interactive parabola | mathematics | interactive visualization | quadratic | svg | a, b, c | 0.533 | 157.5 | pass | pass | pass |
| user-holdout-012 | Interactive unit circle | mathematics | interactive visualization | unit_circle | svg | angle | 0.540 | 42.1 | pass | pass | pass |
| user-holdout-013 | 3D Gaussian surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.455 | 266.7 | pass | pass | pass |
| user-holdout-014 | Damped wave surface | mathematics | interactive visualization | explicit_surface | three | orbit, reset_view | 1.943 | 286.0 | pass | pass | pass |
| user-holdout-015 | Projectile motion | physics | interactive visualization | projectile | svg | angle, speed | 0.493 | 76.2 | pass | pass | pass |
| user-holdout-016 | Inclined plane | physics | interactive visualization | inclined_plane | svg | incline | 0.257 | 46.2 | pass | pass | pass |
| user-holdout-017 | Hooke's law | physics | interactive visualization | spring_mass | svg | spring_constant, displacement | 0.324 | 67.1 | pass | pass | pass |
| user-holdout-018 | Ohm's law | physics | interactive visualization | ohms_law_circuit | svg | voltage, resistance, switch | 0.292 | 88.1 | pass | pass | pass |
| user-holdout-019 | Refraction | physics | interactive visualization | refraction | svg | incident_angle, medium | 0.252 | 65.7 | pass | pass | pass |
| user-holdout-020 | Molecular geometry | chemistry | interactive visualization | molecular_geometry | three | molecule | 0.320 | 146.2 | pass | pass | pass |
| user-holdout-021 | Derivative visualizer | mathematics | interactive visualization | derivative_tangent | svg | x | 0.622 | 47.2 | pass | pass | pass |
| user-holdout-022 | Riemann sum | mathematics | interactive visualization | riemann_sum | svg | rectangles | 0.499 | 44.5 | pass | pass | pass |
| user-holdout-023 | Gradient field | mathematics | interactive visualization | gradient_linked | svg | point_x, point_y | 2.045 | 100.1 | pass | pass | pass |
| user-holdout-024 | Matrix transformation | mathematics | interactive visualization | linear_transform | svg | matrix | 0.387 | 79.2 | pass | pass | pass |
| user-holdout-025 | Eigenvector visualization | mathematics | interactive visualization | linear_transform | svg | matrix | 0.296 | 43.5 | pass | pass | pass |
| user-holdout-026 | Travelling wave | physics | interactive animation | travelling_wave | canvas | amplitude, wavelength, frequency, play, pause, restart | 0.487 | 287.4 | pass | pass | pass |
| user-holdout-027 | Simple harmonic oscillator | physics | interactive animation | harmonic_motion | canvas | spring_constant, mass, play, pause, restart | 0.751 | 298.0 | pass | pass | pass |
| user-holdout-028 | Elastic collision | physics | interactive visualization | elastic_collision | svg | mass_1, velocity_1, mass_2, velocity_2 | 0.256 | 118.9 | pass | pass | pass |
| user-holdout-029 | Electric field | physics | interactive visualization | electric_field_vectors | canvas | positive_charge_x, negative_charge_x, test_x, test_y | 1.209 | 121.0 | pass | pass | pass |
| user-holdout-030 | RC circuit | physics | interactive animation | rc_circuit | svg | mode, resistance, capacitance, play, pause, restart | 0.822 | 368.7 | pass | pass | pass |
| user-holdout-031 | Binary search | computer science | interactive animation | binary_search | svg | target, step, play, pause, restart | 0.411 | 259.6 | pass | pass | pass |
| user-holdout-032 | Sorting algorithm | computer science | interactive visualization | merge_sort | svg | step | 0.696 | 113.3 | pass | pass | pass |
| user-holdout-033 | Binary search tree | computer science | interactive animation | binary_search_tree | svg | insert, step, play, pause, restart | 0.276 | 306.6 | pass | pass | pass |
| user-holdout-034 | Dijkstra's algorithm | computer science | interactive animation | dijkstra | svg | source, destination, step, play, pause, restart | 0.327 | 293.7 | pass | pass | pass |
| user-holdout-035 | Neural network | computer science | interactive visualization | neural_network | svg | weight, step | 0.369 | 74.8 | pass | pass | pass |
| user-holdout-036 | Gradient descent | mathematics | interactive visualization | gradient_descent | svg | learning_rate, step | 2.158 | 148.1 | pass | pass | pass |
| user-holdout-037 | Differential-drive robot | robotics | interactive visualization | differential_drive | canvas | left_velocity, right_velocity | 0.549 | 98.7 | pass | pass | pass |
| user-holdout-038 | Robot arm forward kinematics | robotics | interactive visualization | robot_forward_kinematics | svg | joint_1, joint_2, joint_3 | 0.155 | 87.8 | pass | pass | pass |
| user-holdout-039 | Sampling and aliasing | signals | interactive visualization | sampling_aliasing | canvas | signal_frequency, sample_frequency | 1.341 | 114.4 | pass | pass | pass |
| user-holdout-040 | Fourier decomposition | signals | interactive visualization | fourier_series | svg | terms | 1.456 | 63.2 | pass | pass | pass |
| user-holdout-041 | 3D vector field | mathematics | interactive visualization | vector_field_3d | three | point_x, point_y, point_z | 0.424 | 344.4 | pass | pass | pass |
| user-holdout-042 | Double pendulum | physics | interactive animation | double_pendulum | canvas | angle_1, angle_2, play, pause, restart | 2.060 | 314.2 | pass | pass | pass |
| user-holdout-043 | Lorenz attractor | dynamical systems | interactive animation | lorenz_attractor | three | sigma, rho, beta, play, pause, restart | 2.678 | 653.4 | pass | pass | pass |
| user-holdout-044 | Gyroid | mathematics | interactive visualization | implicit_surface | three | clip_z, orbit, reset_view | 0.604 | 620.6 | pass | pass | pass |
| user-holdout-045 | Electromagnetic wave | physics | interactive animation | electromagnetic_wave | three | amplitude, wavelength, play, pause, restart | 1.272 | 636.2 | pass | pass | pass |
| user-holdout-046 | Action potential | biology | interactive visualization | action_potential | svg | time | 0.700 | 106.6 | pass | pass | pass |
| user-holdout-047 | Chemical titration | chemistry | interactive animation | titration | svg | titrant_volume, play, pause, restart | 0.815 | 287.3 | pass | pass | pass |
| user-holdout-048 | CPU memory hierarchy | computer science | interactive animation | virtual_memory | svg | address, step, play, pause, restart | 0.276 | 269.9 | pass | pass | pass |
| user-holdout-049 | Robot localization | robotics | interactive visualization | robot_localization | canvas | odometry_noise, sensor_noise, step | 1.165 | 201.7 | pass | pass | pass |
| user-holdout-050 | Full Kalman filter visualization | controls | interactive animation | kalman_filter | svg | noise, process_noise, step, play, pause, restart | 1.399 | 374.6 | pass | pass | pass |
