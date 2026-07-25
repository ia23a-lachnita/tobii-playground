using System;

namespace TobiiGazeVisualizer;

/// <summary>
/// One Euro Filter - industry standard for real-time gaze smoothing.
/// Adaptive low-pass filter: strong smoothing at low speeds, minimal lag at high speeds.
/// Reference: Casiez et al. (2012) CHI
/// </summary>
public class OneEuroFilter
{
    private bool _firstTime = true;
    private readonly double _minCutoff;
    private readonly double _beta;
    private readonly LowpassFilter _xFilt = new();
    private readonly LowpassFilter _dxFilt = new();
    private const double DCutoff = 1.0;

    /// <param name="minCutoff">Controls jitter at slow speeds (default 1.0 Hz, lower = more smoothing)</param>
    /// <param name="beta">Controls lag at high speeds (default 0.5, higher = less lag during fast movement)</param>
    public OneEuroFilter(double minCutoff = 1.0, double beta = 0.5)
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
}

/// <summary>
/// 2D gaze smoother using paired One Euro Filters.
/// </summary>
public class GazeSmoother
{
    private readonly OneEuroFilter _filterX;
    private readonly OneEuroFilter _filterY;
    private DateTime _lastTime = DateTime.Now;

    public GazeSmoother(double minCutoff = 1.0, double beta = 0.5)
    {
        _filterX = new OneEuroFilter(minCutoff, beta);
        _filterY = new OneEuroFilter(minCutoff, beta);
    }

    public (double x, double y) Filter(double rawX, double rawY)
    {
        var now = DateTime.Now;
        double rate = 1.0 / Math.Max((now - _lastTime).TotalSeconds, 0.001);
        _lastTime = now;

        return (
            _filterX.Filter(rawX, rate),
            _filterY.Filter(rawY, rate)
        );
    }

    public void Reset()
    {
        _filterX.Filter(0, 1);
        _filterY.Filter(0, 1);
        _lastTime = DateTime.Now;
    }
}
