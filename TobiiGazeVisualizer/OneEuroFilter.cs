using System;
using System.Diagnostics;

namespace TobiiGazeVisualizer;

/// <summary>
/// One Euro Filter - industry standard for real-time gaze smoothing.
/// Adaptive low-pass filter: strong smoothing at low speeds, minimal lag at high speeds.
/// Reference: Casiez et al. (2012) CHI
///
/// Tuned for ~90 Hz gaze in NORMALIZED [0,1] coordinates (NOT pixels):
/// minCutoff 0.1 Hz locks fixations (kills 2-8 Hz ocular tremor + tracker noise),
/// beta 10 opens the cutoff to tens of Hz during saccades (velocities here are
/// a few units/sec, so beta must be ~100x larger than pixel-space values).
/// Pixel-space equivalents would be minCutoff 0.1, beta ~0.005-0.015.
/// </summary>
public class OneEuroFilter
{
    private bool _firstTime = true;
    private readonly double _minCutoff;
    private readonly double _beta;
    private readonly LowpassFilter _xFilt = new();
    private readonly LowpassFilter _dxFilt = new();
    private const double DCutoff = 1.0;

    /// <param name="minCutoff">Controls jitter at slow speeds (lower = more smoothing)</param>
    /// <param name="beta">Controls lag at high speeds (higher = less lag during fast movement)</param>
    public OneEuroFilter(double minCutoff = 0.1, double beta = 10.0)
    {
        _minCutoff = minCutoff;
        _beta = beta;
    }

    public double Filter(double x, double rate)
    {
        double dx = _firstTime ? 0 : (x - _xFilt.Last()) * rate;
        if (_firstTime) _firstTime = false;

        double edx = _dxFilt.Filter(dx, Alpha(rate, DCutoff));
        double cutoff = _minCutoff + _beta * Math.Abs(edx);
        return _xFilt.Filter(x, Alpha(rate, cutoff));
    }

    public void Reset()
    {
        _firstTime = true;
        _xFilt.Reset();
        _dxFilt.Reset();
    }

    private static double Alpha(double rate, double cutoff)
    {
        double tau = 1.0 / (2 * Math.PI * cutoff);
        double te = 1.0 / rate;
        return 1.0 / (1.0 + tau / te);
    }
}

public class LowpassFilter
{
    private bool _firstTime = true;
    private double _hatXPrev;

    public double Last() => _hatXPrev;

    public double Filter(double x, double alpha)
    {
        double hatX = _firstTime ? x : alpha * x + (1 - alpha) * _hatXPrev;
        _firstTime = false;
        _hatXPrev = hatX;
        return hatX;
    }

    public void Reset()
    {
        _firstTime = true;
        _hatXPrev = 0;
    }
}

/// <summary>
/// 2D gaze smoother: paired One Euro Filters plus an I-VT style saccade snap.
/// Fixations get heavy smoothing (bubble freezes on target like Tobii Ghost);
/// samples faster than <see cref="SnapVelocity"/> bypass the filter so saccade
/// landings have zero trailing lag instead of elastic dragging.
/// Snap threshold 2.0 norm/s ≈ 60-100 deg/s at 60cm viewing distance, cleanly
/// between smooth pursuit (&lt;0.6 norm/s) and real saccades (100-500 deg/s).
/// </summary>
public class GazeSmoother
{
    private readonly OneEuroFilter _filterX;
    private readonly OneEuroFilter _filterY;
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private long _lastTicks;
    private double _lastX, _lastY;
    private bool _hasLast;

    /// <summary>Normalized units/sec above which the filter snaps to raw.</summary>
    public double SnapVelocity { get; set; } = 2.0;

    public GazeSmoother(double minCutoff = 0.1, double beta = 10.0)
    {
        _filterX = new OneEuroFilter(minCutoff, beta);
        _filterY = new OneEuroFilter(minCutoff, beta);
        _lastTicks = _clock.ElapsedTicks;
    }

    public (double x, double y) Filter(double rawX, double rawY)
    {
        long now = _clock.ElapsedTicks;
        // Stopwatch resolution (not DateTime.Now ~15ms wall clock) so the rate
        // estimate is stable at 90 Hz.
        double dt = Math.Max((now - _lastTicks) / (double)Stopwatch.Frequency, 0.001);
        _lastTicks = now;
        double rate = 1.0 / dt;

        if (_hasLast)
        {
            double dist = Math.Sqrt((rawX - _lastX) * (rawX - _lastX) + (rawY - _lastY) * (rawY - _lastY));
            if (dist / dt > SnapVelocity)
            {
                // Saccade: drop filter history and snap to the landing point.
                _filterX.Reset();
                _filterY.Reset();
            }
        }

        var result = (
            _filterX.Filter(rawX, rate),
            _filterY.Filter(rawY, rate)
        );
        _lastX = rawX;
        _lastY = rawY;
        _hasLast = true;
        return result;
    }

    public void Reset()
    {
        _filterX.Reset();
        _filterY.Reset();
        _hasLast = false;
        _lastTicks = _clock.ElapsedTicks;
    }
}
