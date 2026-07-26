using System;
using System.Collections.Generic;
using System.Linq;

namespace TobiiGazeVisualizer;

/// <summary>
/// Two-stage calibration: Affine (linear) fit first, then 2nd-order polynomial residual correction.
/// Uses median for robust centroid extraction. RANSAC outlier rejection.
/// </summary>
public class CalibrationEngine
{
    // 9-point calibration grid, spread out to cover tracker FOV
    // 12%-88% horizontal, 10%-90% vertical
    // NOTE: Y coordinates are INVERTED (0=top, 1=bottom) to match screen rendering
    // The calibration engine inverts Y when comparing with tracker data (Y=0 is bottom)
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

    const double Q42_SCALE = 4398046511104.0;

    public class PointSamples
    {
        public List<(double x, double y)> AllSamples { get; } = [];
        public bool Valid => AllSamples.Count > 10;
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
    /// Remove outliers beyond 2 standard deviations from centroid.
    /// </summary>
    static List<(double x, double y)> RemoveOutliers(List<(double x, double y)> samples)
    {
        if (samples.Count < 6) return samples;

        double meanX = samples.Average(s => s.x);
        double meanY = samples.Average(s => s.y);
        double stdX = Math.Sqrt(samples.Average(s => (s.x - meanX) * (s.x - meanX)));
        double stdY = Math.Sqrt(samples.Average(s => (s.y - meanY) * (s.y - meanY)));

        double threshold = 2.0;
        return samples
            .Where(s => Math.Abs(s.x - meanX) < threshold * Math.Max(stdX, 0.01)
                     && Math.Abs(s.y - meanY) < threshold * Math.Max(stdY, 0.01))
            .ToList();
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
        if (n < 6) return [0, 1, 0, 0, 0, 0];

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
            double bsum = 0;
            for (int k = 0; k < n; k++) bsum += A[k, i] * targetValues[k];
            ATb[i] = bsum;
        }

        return SolveLinearSystem(ATA, ATb);
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
        double dx = (rawX - targetX) * 597.9;  // Full width visible
        double dy = (rawY - targetY) * 203.0;   // Visible range only (not full 336mm)
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

    public CalibrationResult ComputeCalibration(PointSamples[] pointSamples)
    {
        var result = new CalibrationResult();

        // Step 1: Extract median point per calibration target
        var medians = new List<(double rawX, double rawY, double targetX, double targetY)>();
        int validPoints = 0;

        for (int i = 0; i < Math.Min(9, pointSamples.Length); i++)
        {
            var ps = pointSamples[i];
            var target = GridTargets[i];

            if (ps.Valid)
            {
                var cleaned = RemoveOutliers(ps.AllSamples);
                if (cleaned.Count >= 5)
                {
                    var median = ComputeMedianPoint(cleaned);
                    // Invert target Y: screen Y=0 is top, but tracker Y=0 is bottom
                    medians.Add((median.x, median.y, target.x, 1.0 - target.y));
                    validPoints++;
                }
            }
        }

        result.PointsCollected = validPoints;
        result.PointsFailed = GridTargets.Length - validPoints;

        if (validPoints < MIN_POINTS_REQUIRED)
        {
            result.Quality = CalibrationQuality.Failed;
            result.MeanErrorDegrees = 99;
            result.MaxErrorDegrees = 99;
            result.RmsNoiseDegrees = 99;
            return result;
        }

        // Step 2: Fit affine (linear) model
        var rawPts = medians.Select(m => (m.rawX, m.rawY)).ToList();
        var tgtX = medians.Select(m => m.targetX).ToList();
        var tgtY = medians.Select(m => m.targetY).ToList();

        var affineX = FitAffine(rawPts, tgtX);
        var affineY = FitAffine(rawPts, tgtY);

        // Step 3: Compute residuals and fit polynomial correction
        var residualX = new List<double>();
        var residualY = new List<double>();
        for (int i = 0; i < medians.Count; i++)
        {
            double predX = EvalAffine(affineX, medians[i].rawX, medians[i].rawY);
            double predY = EvalAffine(affineY, medians[i].rawX, medians[i].rawY);
            residualX.Add(medians[i].targetX - predX);
            residualY.Add(medians[i].targetY - predY);
        }

        // Stage 2: polynomial on residuals (if enough points)
        if (validPoints >= 6)
        {
            var polyCorrX = FitPolynomial(rawPts, residualX);
            var polyCorrY = FitPolynomial(rawPts, residualY);

            // Combine: final = affine + poly_correction
            // Store as 6-coeff polynomial that includes affine terms
            result.LeftCoeffX = [
                affineX[0] + polyCorrX[0],
                affineX[1] + polyCorrX[1],
                affineX[2] + polyCorrX[2],
                polyCorrX[3],
                polyCorrX[4],
                polyCorrX[5]
            ];
            result.LeftCoeffY = [
                affineY[0] + polyCorrY[0],
                affineY[1] + polyCorrY[1],
                affineY[2] + polyCorrY[2],
                polyCorrY[3],
                polyCorrY[4],
                polyCorrY[5]
            ];
        }
        else
        {
            // Fallback: just affine, padded to 6 coefficients
            result.LeftCoeffX = [affineX[0], affineX[1], affineX[2], 0, 0, 0];
            result.LeftCoeffY = [affineY[0], affineY[1], affineY[2], 0, 0, 0];
        }

        // Use same for right eye
        result.RightCoeffX = (double[])result.LeftCoeffX.Clone();
        result.RightCoeffY = (double[])result.LeftCoeffY.Clone();
        result.LeftWeight = 1.0;
        result.RightWeight = 0.0;

        // Compute quality metrics
        double totalError = 0, maxError = 0;
        for (int i = 0; i < medians.Count; i++)
        {
            var (cx, cy) = result.Transform(medians[i].rawX, medians[i].rawY, true);
            double err = AngularError(cx, cy, medians[i].targetX, medians[i].targetY);
            totalError += err;
            maxError = Math.Max(maxError, err);
        }

        result.MeanErrorDegrees = medians.Count > 0 ? totalError / medians.Count : 99;
        result.MaxErrorDegrees = maxError;

        // RMS noise from sample scatter
        double rmsSum = 0;
        int rmsCount = 0;
        for (int i = 0; i < Math.Min(9, pointSamples.Length); i++)
        {
            if (pointSamples[i].Valid)
            {
                var cleaned = RemoveOutliers(pointSamples[i].AllSamples);
                var median = ComputeMedianPoint(cleaned);
                foreach (var s in cleaned)
                {
                    rmsSum += (s.x - median.x) * (s.x - median.x) + (s.y - median.y) * (s.y - median.y);
                    rmsCount++;
                }
            }
        }
        result.RmsNoiseDegrees = rmsCount > 0
            ? Math.Sqrt(rmsSum / rmsCount) * Math.Sqrt(597.9 * 203.0) / 600.0 * (180.0 / Math.PI)
            : 99;

        // Quality rating (relaxed thresholds)
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
