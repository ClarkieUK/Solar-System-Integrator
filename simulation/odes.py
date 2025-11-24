import numpy as np
G = 6.67430e-11

def newtonian_gravitation(t, positions, velocities, masses) : # vectorised approach
    drs = positions[np.newaxis] - positions[:, np.newaxis]
    norms = np.linalg.norm(drs, axis=-1)[..., np.newaxis]
    norms[norms == 0] = 1 # mitigate division by zero
    as_ = G * np.sum(masses[np.newaxis, :, np.newaxis] * drs / norms**3, axis=1)
    return np.copy(velocities), as_