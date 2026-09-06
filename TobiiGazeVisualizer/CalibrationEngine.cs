using System;
using System.Collections.Generic;
using System.Linq;

namespace TobiiGazeVisualizer;

/// <summary>
/// Per-eye two-stage calibration: affine fit first, then ridge-regularized
/// 2nd-order polynomial residual correction. Late fusion with affine-MSE
/// weights. Median + two-pass MAD rejection, LOOCV affine validation.
/// </summary>
public class CalibrationEngine
{
    // 9-point calibration grid, spread out to cover tracker FOV
    // 12%-88% horizontal, 10%-90% vertical
    // Both tracker (ADCS) and screen use Y=0 at top — coordinates match directly
    public static readonly (double x, double y)[] GridTargets =
    [
        (0.12, 0.10), (0.50, 0.10), (0.88, 0.10),
        (0.12, 0.50), (0.50, 0.50), (0.88, 0.50),
        (0.12, 0.90), (0.50, 0.90), (0.88, 0.90)
    ];

    const double HARD_FAIL_MEAN_ERROR = 2.5;
    const double WARN_SINGLE_POINT = 3.0;
    const double HARD_FAIL_RMS = 0.5;
    const int MIN_POINTS_REQUIRED = 6;

    // Minimum valid points before the 2nd-order polynomial stage is enabled.
    // A 6-coefficient fit on 6-7 points has ~0 degrees of freedom and exactly
    // interpolates sensor noise (Runge-type edge blowup); with < 8 points the
    // affine-only model generalises better.
    const int MIN_POINTS_POLY = 8;

    // L2 (ridge) penalty added to the polynomial normal-equation diagonal.
    // 1e-2 keeps 2nd-order curvature tame at screen peripheries where the fit
    // extrapolates (2nd-opinion: affine-stage evaluation, stronger poly prior).
    const double RIDGE_LAMBDA = 1e-2;

    const double Q42_SCALE = 4398046511104.0;

    public class PointSamples
    {
        public List<(double x, double y)> LeftSamples { get; } = [];
        public List<(double x, double y)> RightSamples { get; } = [];
        // Legacy combined pool (kept for compat, unused by the per-eye fit).
        public List<(double x, double y)> AllSamples { get; } = [];
        public bool Valid => LeftSamples.Count + RightSamples.Count > 10;
    }

    static double Median(List<double> values)
    {
        if (values.Count == 0) return 0;
        var sorted = values.OrderBy(v => v).ToList();
        int mid = sorted.Count / 2;
        return sorted.Count % 2 == 0
            ? (sorted[mid - 1] + sorted[mid]) / 2.0
            : sorted[mid];
    }

    static (double x, double y) ComputeMedianPoint(List<(double x, double y)> samples)
    {
        var xs = samples.Select(s => s.x).ToList();
        var ys = samples.Select(s => s.y).ToList();
        return (Median(xs), Median(ys));
    }

    /// <summary>
    /// Two-pass MAD rejection. sigma_hat = 1.4826 * MAD has a 50% breakdown
    /// point (best possible) for centroid estimation; RANSAC buys nothing for
    /// fitting a 0-D point and adds nondeterminism (2nd-opinion review).
    /// </summary>
    static List<(double x, double y)> RemoveOutliers(List<(double x, double y)> samples)
    {
        var current = samples;
        for (int pass = 0; pass < 2; pass++)
        {
            if (current.Count < 6) return current;
            var median = ComputeMedianPoint(current);
            double madX = Median(current.Select(s => Math.Abs(s.x - median.x)).ToList());
            double madY = Median(current.Select(s => Math.Abs(s.y - median.y)).ToList());
            double sigX = Math.Max(1.4826 * madX, 1e-4);
            double sigY = Math.Max(1.4826 * madY, 1e-4);
            const double threshold = 2.5;
            var kept = current
                .Where(s => Math.Abs(s.x - median.x) < threshold * sigX
                         && Math.Abs(s.y - median.y) < threshold * sigY)
                .ToList();
            if (kept.Count < 5) return current; // never gut the pool
            current = kept;
        }
        return current;
    }

    static double[] FitAffine(List<(double rawX, double rawY)> rawPoints, List<double> targetValues)
    {
        int n = rawPoints.Count;
        if (n < 3) return [0, 0, 0]; // fallback: constant 0

        // X' = a0 + a1*x + a2*y
        double[,] A = new double[n, 3];
        for (int i = 0; i < n; i++)
        {
            A[i, 0] = 1;
            A[i, 1] = rawPoints[i].rawX;
            A[i, 2] = rawPoints[i].rawY;
        }

        double[,] ATA = new double[3, 3];
        double[] ATb = new double[3];
        for (int i = 0; i < 3; i++)
        {
            for (int j = 0; j < 3; j++)
            {
                double sum = 0;
                for (int k = 0; k < n; k++) sum += A[k, i] * A[k, j];
                ATA[i, j] = sum;
            }
            double bsum = 0;
            for (int k = 0; k < n; k++) bsum += A[k, i] * targetValues[k];
            ATb[i] = bsum;
        }

        return SolveLinearSystem(ATA, ATb);
    }

    static double[] FitPolynomial(List<(double rawX, double rawY)> rawPoints, List<double> targetValues)
    {
        int n = rawPoints.Count;
        // Underdetermined: return a ZERO residual correction (not identity —
        // identity here would add the raw coordinate a second time).
        if (n < 6) return [0, 0, 0, 0, 0, 0];

        double[,] A = new double[n, 6];
        for (int i = 0; i < n; i++)
        {
            double x = rawPoints[i].rawX, y = rawPoints[i].rawY;
            A[i, 0] = 1;
            A[i, 1] = x;
            A[i, 2] = y;
            A[i, 3] = x * y;
            A[i, 4] = x * x;
            A[i, 5] = y * y;
        }

        double[,] ATA = new double[6, 6];
        double[] ATb = new double[6];
        for (int i = 0; i < 6; i++)
        {
            for (int j = 0; j < 6; j++)
            {
                double sum = 0;
                for (int k = 0; k < n; k++) sum += A[k, i] * A[k, j];
                ATA[i, j] = sum;
            }
            // Ridge: penalise large coefficients, stabilises near-singular fits
            ATA[i, i] += RIDGE_LAMBDA;
            double bsum = 0;
            for (int k = 0; k < n; k++) bsum += A[k, i] * targetValues[k];
            ATb[i] = bsum;
        }

        var coeff = SolveLinearSystem(ATA, ATb);
        // Solver guard: a singular system yields NaN/Inf — fall back to no
        // correction rather than poisoning the calibration.
        if (coeff.Any(double.IsNaN) || coeff.Any(double.IsInfinity))
            return [0, 0, 0, 0, 0, 0];
        return coeff;
    }

    static double[] SolveLinearSystem(double[,] M, double[] b)
    {
        int n = b.Length;
        double[,] aug = new double[n, n + 1];
        for (int i = 0; i < n; i++)
        {
            for (int j = 0; j < n; j++) aug[i, j] = M[i, j];
            aug[i, n] = b[i];
        }

        for (int col = 0; col < n; col++)
        {
            int maxRow = col;
            for (int row = col + 1; row < n; row++)
                if (Math.Abs(aug[row, col]) > Math.Abs(aug[maxRow, col]))
                    maxRow = row;
            for (int j = 0; j <= n; j++)
            {
                double tmp = aug[col, j];
                aug[col, j] = aug[maxRow, j];
                aug[maxRow, j] = tmp;
            }

            if (Math.Abs(aug[col, col]) < 1e-12) continue;

            for (int row = col + 1; row < n; row++)
            {
                double factor = aug[row, col] / aug[col, col];
                for (int j = col; j <= n; j++)
                    aug[row, j] -= factor * aug[col, j];
            }
        }

        double[] x = new double[n];
        for (int i = n - 1; i >= 0; i--)
        {
            x[i] = aug[i, n];
            for (int j = i + 1; j < n; j++)
                x[i] -= aug[i, j] * x[j];
            x[i] /= aug[i, i];
        }
        return x;
    }

    static double AngularError(double rawX, double rawY, double targetX, double targetY)
    {
        double dx = (rawX - targetX) * 597.9;
        double dy = (rawY - targetY) * 336.2;
        double distMm = 600.0;
        double angleRad = Math.Atan2(Math.Sqrt(dx * dx + dy * dy), distMm);
        return angleRad * 180.0 / Math.PI;
    }

    static double EvalAffine(double[] coeff, double x, double y)
    {
        return coeff[0] + coeff[1] * x + coeff[2] * y;
    }

    static double EvalPoly(double[] coeff, double x, double y)
    {
        return coeff[0] + coeff[1] * x + coeff[2] * y
             + coeff[3] * x * y + coeff[4] * x * x + coeff[5] * y * y;
    }

    /// <summary>
    /// Fit one eye: affine stage, then ridge-regularized polynomial on the
    /// residuals (only with MIN_POINTS_POLY+ points). Returns 6-coeff mappings
    /// plus the AFFINE-stage MSE (normalized units^2) used for fusion weights —
    /// affine MSE, because poly-residual MSE would let an overfitted eye steal
    /// all the weight (2nd-opinion review).
    /// </summary>
    static (double[] coeffX, double[] coeffY, double affineMse) FitEye(
        List<(double rawX, double rawY)> rawPts, List<double> tgtX, List<double> tgtY)
    {
        double[] identX = [0, 1, 0, 0, 0, 0];
        double[] identY = [0, 0, 1, 0, 0, 0];
        if (rawPts.Count < 3) return (identX, identY, double.PositiveInfinity);

        var affineX = FitAffine(rawPts, tgtX);
        var affineY = FitAffine(rawPts, tgtY);
        if (affineX.Any(double.IsNaN) || affineX.Any(double.IsInfinity) ||
            affineY.Any(double.IsNaN) || affineY.Any(double.IsInfinity))
            return (identX, identY, double.PositiveInfinity);

        double mse = 0;
        for (int i = 0; i < rawPts.Count; i++)
        {
            double ex = EvalAffine(affineX, rawPts[i].rawX, rawPts[i].rawY) - tgtX[i];
            double ey = EvalAffine(affineY, rawPts[i].rawX, rawPts[i].rawY) - tgtY[i];
            mse += ex * ex + ey * ey;
        }
        mse /= rawPts.Count;

        if (rawPts.Count < MIN_POINTS_POLY)
            return ([affineX[0], affineX[1], affineX[2], 0, 0, 0],
                    [affineY[0], affineY[1], affineY[2], 0, 0, 0], mse);

        var residualX = new List<double>();
        var residualY = new List<double>();
        for (int i = 0; i < rawPts.Count; i++)
        {
            residualX.Add(tgtX[i] - EvalAffine(affineX, rawPts[i].rawX, rawPts[i].rawY));
            residualY.Add(tgtY[i] - EvalAffine(affineY, rawPts[i].rawX, rawPts[i].rawY));
        }
        var polyCorrX = FitPolynomial(rawPts, residualX);
        var polyCorrY = FitPolynomial(rawPts, residualY);

        return ([affineX[0] + polyCorrX[0], affineX[1] + polyCorrX[1], affineX[2] + polyCorrX[2],
                 polyCorrX[3], polyCorrX[4], polyCorrX[5]],
                [affineY[0] + polyCorrY[0], affineY[1] + polyCorrY[1], affineY[2] + polyCorrY[2],
                 polyCorrY[3], polyCorrY[4], polyCorrY[5]], mse);
    }

    public CalibrationResult ComputeCalibration(PointSamples[] pointSamples)
    {
        var result = new CalibrationResult();
        result.PointErrors = new double[GridTargets.Length];
        Array.Fill(result.PointErrors, double.NaN);

        // Step 1: per-eye median centroids per target
        var points = new List<(int idx, double lx, double ly, bool hasL,
                               double rx, double ry, bool hasR, double tx, double ty)>();
        for (int i = 0; i < Math.Min(GridTargets.Length, pointSamples.Length); i++)
        {
            var ps = pointSamples[i];
            var target = GridTargets[i];
            bool hasL = false, hasR = false;
            double lx = 0, ly = 0, rx = 0, ry = 0;
            if (ps.LeftSamples.Count >= 5)
            {
                var m = ComputeMedianPoint(RemoveOutliers(ps.LeftSamples));
                lx = m.x; ly = m.y; hasL = true;
            }
            if (ps.RightSamples.Count >= 5)
            {
                var m = ComputeMedianPoint(RemoveOutliers(ps.RightSamples));
                rx = m.x; ry = m.y; hasR = true;
            }
            if (hasL || hasR) points.Add((i, lx, ly, hasL, rx, ry, hasR, target.x, target.y));
        }

        result.PointsCollected = points.Count;
        result.PointsFailed = GridTargets.Length - points.Count;

        if (points.Count < MIN_POINTS_REQUIRED)
        {
            result.Quality = CalibrationQuality.Failed;
            result.MeanErrorDegrees = 99;
            result.MaxErrorDegrees = 99;
            result.RmsNoiseDegrees = 99;
            result.LoocvMeanErrorDegrees = 99;
            return result;
        }

        // Step 2: fit each eye independently (late fusion preserves per-eye optics)
        var rawL = points.Where(p => p.hasL).Select(p => (p.lx, p.ly)).ToList();
        var tgtLX = points.Where(p => p.hasL).Select(p => p.tx).ToList();
        var tgtLY = points.Where(p => p.hasL).Select(p => p.ty).ToList();
        var rawR = points.Where(p => p.hasR).Select(p => (p.rx, p.ry)).ToList();
        var tgtRX = points.Where(p => p.hasR).Select(p => p.tx).ToList();
        var tgtRY = points.Where(p => p.hasR).Select(p => p.ty).ToList();

        var (lcx, lcy, lMse) = FitEye(rawL, tgtLX, tgtLY);
        var (rcx, rcy, rMse) = FitEye(rawR, tgtRX, tgtRY);

        result.LeftCoeffX = lcx; result.LeftCoeffY = lcy;
        result.RightCoeffX = rcx; result.RightCoeffY = rcy;

        double lw = double.IsInfinity(lMse) ? 0 : 1.0 / (lMse + 1e-9);
        double rw = double.IsInfinity(rMse) ? 0 : 1.0 / (rMse + 1e-9);
        if (lw + rw <= 0) { lw = 1; rw = 0; }
        result.LeftWeight = lw / (lw + rw);
        result.RightWeight = rw / (lw + rw);

        // Step 3: in-sample per-point fused errors (drives retry-worst-point UI)
        double totalError = 0, maxError = 0;
        foreach (var p in points)
        {
            var (cx, cy) = result.TransformFused(p.lx, p.ly, p.rx, p.ry, p.hasL, p.hasR);
            double err = AngularError(cx, cy, p.tx, p.ty);
            result.PointErrors[p.idx] = err;
            totalError += err;
            maxError = Math.Max(maxError, err);
        }
        result.MeanErrorDegrees = totalError / points.Count;
        result.MaxErrorDegrees = maxError;

        // Step 4: LOOCV, affine stage only. Poly LOOCV on 8 points (df=2) flares
        // at held-out corners and would punish genuine foveal accuracy, so the
        // honest generalization metric is affine-only (2nd-opinion review).
        double loocvSum = 0;
        int loocvCount = 0;
        foreach (var held in points)
        {
            var trainL = points.Where(p => p.idx != held.idx && p.hasL).ToList();
            var trainR = points.Where(p => p.idx != held.idx && p.hasR).ToList();
            bool predL = false, predR = false;
            double pxL = 0, pyL = 0, pxR = 0, pyR = 0;
            if (held.hasL && trainL.Count >= 3)
            {
                var ax = FitAffine(trainL.Select(p => (p.lx, p.ly)).ToList(), trainL.Select(p => p.tx).ToList());
                var ay = FitAffine(trainL.Select(p => (p.lx, p.ly)).ToList(), trainL.Select(p => p.ty).ToList());
                if (!ax.Any(double.IsNaN) && !ay.Any(double.IsNaN))
                {
                    pxL = EvalAffine(ax, held.lx, held.ly);
                    pyL = EvalAffine(ay, held.lx, held.ly);
                    predL = true;
                }
            }
            if (held.hasR && trainR.Count >= 3)
            {
                var ax = FitAffine(trainR.Select(p => (p.rx, p.ry)).ToList(), trainR.Select(p => p.tx).ToList());
                var ay = FitAffine(trainR.Select(p => (p.rx, p.ry)).ToList(), trainR.Select(p => p.ty).ToList());
                if (!ax.Any(double.IsNaN) && !ay.Any(double.IsNaN))
                {
                    pxR = EvalAffine(ax, held.rx, held.ry);
                    pyR = EvalAffine(ay, held.rx, held.ry);
                    predR = true;
                }
            }
            if (!predL && !predR) continue;
            double wSum = (predL ? result.LeftWeight : 0) + (predR ? result.RightWeight : 0);
            double fx = ((predL ? pxL * result.LeftWeight : 0) + (predR ? pxR * result.RightWeight : 0)) / wSum;
            double fy = ((predL ? pyL * result.LeftWeight : 0) + (predR ? pyR * result.RightWeight : 0)) / wSum;
            loocvSum += AngularError(fx, fy, held.tx, held.ty);
            loocvCount++;
        }
        result.LoocvMeanErrorDegrees = loocvCount > 0 ? loocvSum / loocvCount : 99;

        // RMS precision from per-eye sample scatter around per-eye medians
        double rmsSum = 0;
        int rmsCount = 0;
        for (int i = 0; i < Math.Min(GridTargets.Length, pointSamples.Length); i++)
        {
            foreach (var pool in new[] { pointSamples[i].LeftSamples, pointSamples[i].RightSamples })
            {
                if (pool.Count == 0) continue;
                var cleaned = RemoveOutliers(pool);
                if (cleaned.Count == 0) continue;
                var median = ComputeMedianPoint(cleaned);
                foreach (var s in cleaned)
                {
                    rmsSum += (s.x - median.x) * (s.x - median.x) + (s.y - median.y) * (s.y - median.y);
                    rmsCount++;
                }
            }
        }
        result.RmsNoiseDegrees = rmsCount > 0
            ? Math.Sqrt(rmsSum / rmsCount) * 597.9 / 600.0 * (180.0 / Math.PI)
            : 99;

        // Quality rating (LOOCV shown but not rated: held-out corners inflate it)
        if (result.PointsCollected < MIN_POINTS_REQUIRED)
            result.Quality = CalibrationQuality.Failed;
        else if (result.MeanErrorDegrees > HARD_FAIL_MEAN_ERROR || result.RmsNoiseDegrees > HARD_FAIL_RMS)
            result.Quality = CalibrationQuality.Failed;
        else if (result.MeanErrorDegrees > WARN_SINGLE_POINT || result.MaxErrorDegrees > 4.0)
            result.Quality = CalibrationQuality.Poor;
        else if (result.MeanErrorDegrees > 1.2 || result.MaxErrorDegrees > 2.0)
            result.Quality = CalibrationQuality.Good;
        else
            result.Quality = CalibrationQuality.Excellent;

        return result;
    }
}
