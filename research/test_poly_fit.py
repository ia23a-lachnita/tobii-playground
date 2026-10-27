import numpy as np

# 9-point grid
grid = [(x, y) for y in [0.1, 0.5, 0.9] for x in [0.1, 0.5, 0.9]]
screen_w, screen_h = 1920, 1080
targets = np.array([[x * screen_w, y * screen_h] for x, y in grid])

# Simulated raw with realistic corneal/perspective non-linearities
raw = np.array([[x + 0.02 * (x - 0.5)**2, y + 0.03 * (y - 0.5)**2 + 0.01] for x, y in grid])

def poly_features(pts):
    x, y = pts[:, 0], pts[:, 1]
    return np.column_stack([np.ones_like(x), x, y, x**2, y**2, x * y])

Phi = poly_features(raw)
coeffs, residuals, rank, s = np.linalg.lstsq(Phi, targets, rcond=None)
pred = Phi @ coeffs
err = np.sqrt(np.sum((pred - targets)**2, axis=1))
print('Polynomial 9-Point Mean fit error (px):', np.mean(err))
