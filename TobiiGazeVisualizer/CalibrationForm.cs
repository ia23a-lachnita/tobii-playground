using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Windows.Forms;

namespace TobiiGazeVisualizer;

/// <summary>
/// 9-point per-eye calibration with smooth minimum-jerk dot transitions,
/// blink-aware sample collection, velocity-gated fixation sampling,
/// and retry-worst-point.
/// </summary>
public class CalibrationForm : Form
{
    readonly TobiiUsb _tracker;
    readonly CalibrationEngine _engine;
    List<(double x, double y, long timestampMs, bool isLeft)>[] _allSamples;
    CalibrationResult? _result;

    int _currentPoint;
    DateTime _phaseStart; // start of current phase

    // Phase states
    enum Phase { Transit, Settle, Collect, Done, Results }
    Phase _phase = Phase.Transit;

    // Timing (ms)
    const int TRANSIT_MS = 600;      // smooth dot movement
    const int SETTLE_MS = 350;       // eye settle after dot arrives (saccade latency
                                     // alone is 180-250 ms + flight + PSO; 200 ms
                                     // sampled mid-saccade)
    const int COLLECT_MIN_MS = 800;  // minimum collection after settle
    const int COLLECT_MAX_MS = 2000; // maximum collection window
    const int SAMPLE_QUOTA = 40;     // target valid eye-samples

    // Fixation gate (normalized units/sec ≈ 35 deg/s at 60 cm on 27"): samples
    // faster than this are saccades/glissades/PSOs, not fixations.
    const double VELOCITY_GATE = 0.7;

    // Blink masking (ms)
    const int BLINK_PRE_MASK_MS = 40;   // discard before blink
    const int BLINK_POST_MASK_MS = 60;  // discard after blink

    // Animation
    float _targetSize = 40f;
    float _targetSizeTarget = 12f;
    readonly System.Windows.Forms.Timer _animTimer;

    // Dot positions (current animated position)
    double _dotX, _dotY;
    // Dot start/end for transit
    double _dotFromX, _dotFromY, _dotToX, _dotToY;

    // Gaze
    double _gazeX, _gazeY;
    bool _gazeValid;
    int _validSampleCount;
    DateTime _lastGazeEvent = DateTime.UtcNow;

    // Velocity gate timing (Stopwatch: DateTime quantizes ~15 ms, useless at 90 Hz)
    readonly Stopwatch _clock = Stopwatch.StartNew();
    long _prevTicks;
    double _prevX, _prevY;
    bool _hasPrev;

    // Retry-worst-point state
    bool _retrySingle;
    int _worstIdx = -1;

    // Blink tracking
    bool _lastValid;
    DateTime _lastBlinkEnd;
    bool _inBlinkMask;

    public CalibrationResult Result => _result ?? new CalibrationResult();
    public bool WasCancelled { get; private set; } = true;

    public CalibrationForm(TobiiUsb tracker)
    {
        _tracker = tracker;
        _engine = new CalibrationEngine();
        _allSamples = new List<(double x, double y, long timestampMs, bool isLeft)>[9];
        for (int i = 0; i < 9; i++)
            _allSamples[i] = new List<(double, double, long, bool)>();
        _prevTicks = _clock.ElapsedTicks;

        Text = "Eye Tracker Calibration";
        Size = new Size(1920, 1080);
        StartPosition = FormStartPosition.Manual;
        FormBorderStyle = FormBorderStyle.None;
        BackColor = Color.FromArgb(20, 20, 30);
        TopMost = true;
        DoubleBuffered = true;
        Cursor.Hide();

        var screen = Screen.PrimaryScreen?.Bounds ?? new Rectangle(0, 0, 1920, 1080);
        Bounds = screen;

        _tracker.OnGazeStereo += OnGazeStereo;

        _animTimer = new System.Windows.Forms.Timer { Interval = 16 };
        _animTimer.Tick += AnimTick;
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        _animTimer.Start();
        StartPoint(0);
    }

    void StartPoint(int index)
    {
        _currentPoint = index;
        _validSampleCount = 0;
        _inBlinkMask = false;
        _lastValid = false;
        _lastBlinkEnd = DateTime.MinValue;
        _allSamples[index].Clear();

        var target = CalibrationEngine.GridTargets[index];

        if (index == 0)
        {
            // First dot: start from center
            _dotFromX = 0.5; _dotFromY = 0.5;
            _dotToX = target.x; _dotToY = target.y;
            _dotX = _dotFromX; _dotY = _dotFromY;
        }
        else
        {
            // Start from previous dot position
            var prev = CalibrationEngine.GridTargets[index - 1];
            _dotFromX = prev.x; _dotFromY = prev.y;
            _dotToX = target.x; _dotToY = target.y;
            _dotX = _dotFromX; _dotY = _dotFromY;
        }

        _phase = Phase.Transit;
        _phaseStart = DateTime.UtcNow;
        _targetSize = 40f;
        _targetSizeTarget = 12f;
    }

    void AnimTick(object? sender, EventArgs e)
    {
        var now = DateTime.UtcNow;
        var elapsed = (now - _phaseStart).TotalMilliseconds;

        switch (_phase)
        {
            case Phase.Transit:
            {
                // Minimum-jerk: 10t^3 - 15t^4 + 6t^5
                double t = Math.Clamp(elapsed / TRANSIT_MS, 0, 1);
                double mj = 10 * t * t * t - 15 * t * t * t * t + 6 * t * t * t * t * t;
                _dotX = _dotFromX + (_dotToX - _dotFromX) * mj;
                _dotY = _dotFromY + (_dotToY - _dotFromY) * mj;

                if (elapsed >= TRANSIT_MS)
                {
                    _phase = Phase.Settle;
                    _phaseStart = now;
                    _targetSize = 12f;
                }
                break;
            }
            case Phase.Settle:
            {
                if (elapsed >= SETTLE_MS)
                {
                    _phase = Phase.Collect;
                    _phaseStart = now;
                    _targetSizeTarget = 10f;
                }
                break;
            }
            case Phase.Collect:
            {
                // End when: enough valid samples AND min time passed, OR max time reached
                bool enoughSamples = _validSampleCount >= SAMPLE_QUOTA;
                bool minTimePassed = elapsed >= COLLECT_MIN_MS;
                bool maxTimeReached = elapsed >= COLLECT_MAX_MS;

                if ((enoughSamples && minTimePassed) || maxTimeReached)
                {
                    _phase = Phase.Done;
                    _targetSizeTarget = 40f;

                    System.Threading.Timer? delayTimer = null;
                    delayTimer = new System.Threading.Timer(_ =>
                    {
                        delayTimer?.Dispose();
                        if (IsDisposed) return;
                        BeginInvoke(() =>
                        {
                            if (_retrySingle)
                            {
                                _retrySingle = false;
                                ComputeAndShow();
                            }
                            else if (_currentPoint < CalibrationEngine.GridTargets.Length - 1)
                                StartPoint(_currentPoint + 1);
                            else
                                ComputeAndShow();
                        });
                    }, null, 200, Timeout.Infinite);
                }
                break;
            }
        }

        _targetSize += (_targetSizeTarget - _targetSize) * 0.15f;
        Invalidate();
    }

    void OnGazeStereo(double lx, double ly, bool lok, double rx, double ry, bool rok)
    {
        _lastGazeEvent = DateTime.UtcNow;

        // Representative position for display + velocity gate (prefer left).
        double px = lok ? lx : rx;
        double py = lok ? ly : ry;
        bool anyValid = lok || rok;
        px = Math.Clamp(px, -0.5, 1.5);
        py = Math.Clamp(py, -0.5, 1.5);

        _gazeX = px;
        _gazeY = py;
        _gazeValid = anyValid;

        // Velocity gate: update reference every sample, decide in Collect.
        long nowTicks = _clock.ElapsedTicks;
        double dt = _hasPrev
            ? Math.Max((nowTicks - _prevTicks) / (double)Stopwatch.Frequency, 0.001)
            : 1.0;
        double speed = _hasPrev
            ? Math.Sqrt((px - _prevX) * (px - _prevX) + (py - _prevY) * (py - _prevY)) / dt
            : 0;
        _prevTicks = nowTicks;
        _prevX = px; _prevY = py;
        _hasPrev = true;

        if (_phase != Phase.Collect) return;

        long tsMs = (long)(DateTime.UtcNow - _phaseStart).TotalMilliseconds;

        // Blink detection and masking (either-eye validity)
        bool currentlyValid = anyValid;

        if (_lastValid && !currentlyValid)
        {
            // Blink onset: start mask, retroactively discard recent samples
            _inBlinkMask = true;
            long maskStart = tsMs - BLINK_PRE_MASK_MS;
            _allSamples[_currentPoint] = _allSamples[_currentPoint]
                .Where(s => s.timestampMs < maskStart)
                .ToList();
        }
        else if (!_lastValid && currentlyValid)
        {
            // Blink offset: start post-mask period
            _lastBlinkEnd = DateTime.UtcNow;
            _inBlinkMask = true;
        }

        // Post-blink mask
        if (_inBlinkMask && currentlyValid)
        {
            var postMaskElapsed = (DateTime.UtcNow - _lastBlinkEnd).TotalMilliseconds;
            if (postMaskElapsed < BLINK_POST_MASK_MS)
            {
                _lastValid = currentlyValid;
                return; // skip this sample
            }
            _inBlinkMask = false;
        }

        _lastValid = currentlyValid;

        if (!currentlyValid) return;

        // Fixation-only data: drop saccades, glissades, post-saccadic wobble.
        if (speed > VELOCITY_GATE) return;

        if (lok)
        {
            _allSamples[_currentPoint].Add((Math.Clamp(lx, 0, 1), Math.Clamp(ly, 0, 1), tsMs, true));
            _validSampleCount++;
        }
        if (rok)
        {
            _allSamples[_currentPoint].Add((Math.Clamp(rx, 0, 1), Math.Clamp(ry, 0, 1), tsMs, false));
            _validSampleCount++;
        }
    }

    void ComputeAndShow()
    {
        var pointSamples = new CalibrationEngine.PointSamples[9];
        for (int i = 0; i < 9; i++)
        {
            pointSamples[i] = new CalibrationEngine.PointSamples();
            pointSamples[i].LeftSamples.AddRange(
                _allSamples[i].Where(s => s.isLeft).Select(s => (s.x, s.y)));
            pointSamples[i].RightSamples.AddRange(
                _allSamples[i].Where(s => !s.isLeft).Select(s => (s.x, s.y)));
        }

        _result = _engine.ComputeCalibration(pointSamples);

        // Worst usable point drives the retry hint (NaN = unusable, skipped).
        _worstIdx = -1;
        double worstErr = double.NaN;
        for (int i = 0; i < _result.PointErrors.Length; i++)
        {
            double e = _result.PointErrors[i];
            if (!double.IsNaN(e) && (double.IsNaN(worstErr) || e > worstErr))
            {
                worstErr = e;
                _worstIdx = i;
            }
        }

        // Stay open: Enter accepts, R retries the worst point, ESC cancels.
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;

        // Progress dots at top
        int pointCount = CalibrationEngine.GridTargets.Length;
        for (int i = 0; i < pointCount; i++)
        {
            float px = Width / 2f + (i - (pointCount - 1) / 2f) * 30;
            using var dotBrush = new SolidBrush(i < _currentPoint ? Color.LimeGreen :
                i == _currentPoint ? Color.White : Color.Gray);
            g.FillEllipse(dotBrush, px - 6, 30, 12, 12);
        }

        if (_result != null)
        {
            DrawResults(g);
            return;
        }

        // Draw target at animated position
        float tx = (float)(_dotX * Width);
        float ty = (float)(_dotY * Height);

        // Outer ring
        using (var pen = new Pen(Color.FromArgb(120, 255, 255, 255), 2.5f))
            g.DrawEllipse(pen, tx - _targetSize, ty - _targetSize, _targetSize * 2, _targetSize * 2);

        // Progress arc during collection
        if (_phase == Phase.Collect)
        {
            float progress = Math.Clamp((float)_validSampleCount / SAMPLE_QUOTA, 0, 1);
            using var progressPen = new Pen(Color.LimeGreen, 3);
            g.DrawArc(progressPen, tx - _targetSize, ty - _targetSize, _targetSize * 2, _targetSize * 2,
                -90, progress * 360);
        }

        // Inner dot
        float innerSize = _phase == Phase.Collect ? 6f : 10f;
        Color dotColor = _phase switch
        {
            Phase.Collect => Color.LimeGreen,
            Phase.Settle => Color.Yellow,
            Phase.Transit => Color.White,
            _ => Color.White
        };
        using var innerBrush = new SolidBrush(dotColor);
        g.FillEllipse(innerBrush, tx - innerSize / 2, ty - innerSize / 2, innerSize, innerSize);

        // No gaze pointer during calibration (prevent gaze chasing)

        // Instructions
        using var font = new Font("Segoe UI", 16);
        using var brush = new SolidBrush(Color.FromArgb(200, 220, 220, 220));
        string msg = _phase switch
        {
            Phase.Transit => $"Moving to dot {_currentPoint + 1}/{CalibrationEngine.GridTargets.Length}...",
            Phase.Settle => $"Hold steady on dot {_currentPoint + 1}/{CalibrationEngine.GridTargets.Length}...",
            Phase.Collect => $"Look at the dot ({_validSampleCount}/{SAMPLE_QUOTA} samples)",
            _ => "Processing..."
        };
        var size = g.MeasureString(msg, font);
        g.DrawString(msg, font, brush, (Width - size.Width) / 2, Height - 80);

        using var smallFont = new Font("Segoe UI", 11);
        g.DrawString("Press ESC to cancel", smallFont, Brushes.Gray, 10, 10);

        // Stream watchdog: the progress ring fills from live gaze samples, so a
        // stalled stream looks like "dots never complete". Say so explicitly.
        if ((DateTime.UtcNow - _lastGazeEvent).TotalMilliseconds > 1500 && _result == null)
        {
            using var warnFont = new Font("Segoe UI", 14, FontStyle.Bold);
            string warn = "NO GAZE DATA — stream stalled, check tracker connection";
            var wsize = g.MeasureString(warn, warnFont);
            g.DrawString(warn, warnFont, Brushes.Red, (Width - wsize.Width) / 2, 60);
        }
    }

    void DrawResults(Graphics g)
    {
        var r = _result!;
        string quality = r.Quality switch
        {
            CalibrationQuality.Excellent => "EXCELLENT",
            CalibrationQuality.Good => "GOOD",
            CalibrationQuality.Poor => "POOR - Consider recalibrating",
            CalibrationQuality.Failed => "FAILED - Please recalibrate",
            _ => "UNKNOWN"
        };

        Color qualityColor = r.Quality switch
        {
            CalibrationQuality.Excellent => Color.LimeGreen,
            CalibrationQuality.Good => Color.SpringGreen,
            CalibrationQuality.Poor => Color.Gold,
            CalibrationQuality.Failed => Color.Red,
            _ => Color.Gray
        };

        using var titleFont = new Font("Segoe UI", 28, FontStyle.Bold);
        using var font = new Font("Segoe UI", 16);
        using var smallFont = new Font("Segoe UI", 13);
        using var qualityBrush = new SolidBrush(qualityColor);

        float cx = Width / 2f;
        float cy = Height / 2f;

        g.DrawString("Calibration Complete", titleFont, Brushes.White, cx - 180, cy - 120);
        g.DrawString(quality, titleFont, qualityBrush, cx - 100, cy - 70);

        string stats = $"Mean Error: {r.MeanErrorDegrees:F2}°  |  Max Error: {r.MaxErrorDegrees:F2}°  |  RMS: {r.RmsNoiseDegrees:F2}°";
        g.DrawString(stats, font, Brushes.LightGray, cx - 250, cy - 10);

        string loocv = $"LOOCV accuracy: {r.LoocvMeanErrorDegrees:F2}° (leave-one-out, affine)";
        g.DrawString(loocv, font, Brushes.LightGray, cx - 250, cy + 22);

        string points = $"Points: {r.PointsCollected}/{CalibrationEngine.GridTargets.Length} collected  |  " +
            $"L/R weight: {r.LeftWeight:F2}/{r.RightWeight:F2}";
        g.DrawString(points, font, Brushes.LightGray, cx - 250, cy + 54);

        if (_worstIdx >= 0 && !double.IsNaN(r.PointErrors[_worstIdx]))
        {
            string worst = $"Worst point #{_worstIdx + 1}: {r.PointErrors[_worstIdx]:F2}° — press R to retry it";
            g.DrawString(worst, smallFont, Brushes.Gold, cx - 250, cy + 92);
        }

        g.DrawString("ENTER = accept   |   R = retry worst point   |   ESC = cancel",
            smallFont, Brushes.White, cx - 250, cy + 122);

        if (r.Quality == CalibrationQuality.Failed)
        {
            g.DrawString("Position yourself 60-70cm from the tracker and try again.",
                smallFont, Brushes.OrangeRed, cx - 220, cy + 152);
        }
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape)
        {
            WasCancelled = true;
            _tracker.OnGazeStereo -= OnGazeStereo;
            Close();
        }
        else if (e.KeyCode == Keys.Enter && _result != null)
        {
            WasCancelled = false;
            _tracker.OnGazeStereo -= OnGazeStereo;
            Close();
        }
        else if (e.KeyCode == Keys.R && _result != null && _worstIdx >= 0)
        {
            // Re-collect only the worst point, then recompute everything.
            _result = null;
            _retrySingle = true;
            StartPoint(_worstIdx);
        }
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _tracker.OnGazeStereo -= OnGazeStereo;
        _animTimer.Stop();
        base.OnFormClosed(e);
    }
}
