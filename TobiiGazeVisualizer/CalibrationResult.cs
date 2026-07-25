using System;
using System.Collections.Generic;
using System.Text.Json;

namespace TobiiGazeVisualizer;

/// <summary>
/// Stores calibration coefficients and quality metrics for gaze mapping.
/// Uses 2nd-order bivariate polynomial: 12 coefficients per eye.
/// </summary>
public class CalibrationResult
{
    // Polynomial coefficients: [1, x, y, x*y, x^2, y^2]
    public double[] LeftCoeffX { get; set; } = [0, 1, 0, 0, 0, 0];
    public double[] LeftCoeffY { get; set; } = [0, 0, 1, 0, 0, 0];
    public double[] RightCoeffX { get; set; } = [0, 1, 0, 0, 0, 0];
    public double[] RightCoeffY { get; set; } = [0, 0, 1, 0, 0, 0];

    // Weights for binocular fusion (inversely proportional to MSE)
    public double LeftWeight { get; set; } = 0.5;
    public double RightWeight { get; set; } = 0.5;

    // Quality metrics
    public double MeanErrorDegrees { get; set; }
    public double MaxErrorDegrees { get; set; }
    public double RmsNoiseDegrees { get; set; }
    public int PointsCollected { get; set; }
    public int PointsFailed { get; set; }
    public DateTime Timestamp { get; set; } = DateTime.Now;

    // Pass/Fail status
    public CalibrationQuality Quality { get; set; } = CalibrationQuality.Uncalibrated;

    /// <summary>
    /// Transform raw gaze coordinates through calibration polynomial.
    /// </summary>
    public (double x, double y) Transform(double rawX, double rawY, bool useLeftEye)
    {
        double[] cx = useLeftEye ? LeftCoeffX : RightCoeffX;
        double[] cy = useLeftEye ? LeftCoeffY : RightCoeffY;

        double corrX = cx[0] + cx[1] * rawX + cx[2] * rawY + cx[3] * rawX * rawY + cx[4] * rawX * rawX + cx[5] * rawY * rawY;
        double corrY = cy[0] + cy[1] * rawX + cy[2] * rawY + cy[3] * rawX * rawY + cy[4] * rawX * rawX + cy[5] * rawY * rawY;

        return (Math.Clamp(corrX, 0, 1), Math.Clamp(corrY, 0, 1));
    }

    /// <summary>
    /// Fused gaze using weighted binocular combination.
    /// </summary>
    public (double x, double y) TransformFused(double rawLX, double rawLY, double rawRX, double rawRY,
        bool leftValid, bool rightValid)
    {
        if (leftValid && rightValid)
        {
            var (lx, ly) = Transform(rawLX, rawLY, true);
            var (rx, ry) = Transform(rawRX, rawRY, false);
            double wSum = LeftWeight + RightWeight;
            return ((lx * LeftWeight + rx * RightWeight) / wSum,
                    (ly * LeftWeight + ry * RightWeight) / wSum);
        }
        else if (leftValid)
        {
            return Transform(rawLX, rawLY, true);
        }
        else if (rightValid)
        {
            return Transform(rawRX, rawRY, false);
        }
        return (0.5, 0.5);
    }

    public string ToJson() => JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true });

    public static CalibrationResult? FromJson(string json) =>
        JsonSerializer.Deserialize<CalibrationResult>(json);

    public static CalibrationResult LoadDefault()
    {
        string path = GetCalibrationPath();
        if (System.IO.File.Exists(path))
        {
            try
            {
                var json = System.IO.File.ReadAllText(path);
                return FromJson(json) ?? new CalibrationResult();
            }
            catch { }
        }
        return new CalibrationResult();
    }

    public void Save()
    {
        string path = GetCalibrationPath();
        System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!);
        System.IO.File.WriteAllText(path, ToJson());
    }

    static string GetCalibrationPath() =>
        System.IO.Path.Combine(AppContext.BaseDirectory, "calibration.json");
}

public enum CalibrationQuality
{
    Uncalibrated,
    Failed,       // Hard fail - unusable
    Poor,         // Usable but with significant warnings
    Good,         // Acceptable quality
    Excellent     // High precision
}
