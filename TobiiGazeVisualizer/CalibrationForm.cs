using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Windows.Forms;

namespace TobiiGazeVisualizer;

/// <summary>
/// 9-point calibration with smooth minimum-jerk dot transitions,
/// blink-aware sample collection, and dynamic sample quota.
/// </summary>
public class CalibrationForm : Form
{
    readonly TobiiUsb _tracker;
    readonly CalibrationEngine _engine;
    List<(double x, double y, long timestampMs, bool valid)>[] _allSamples;
    CalibrationResult? _result;

    int _currentPoint;
    bool _collecting;
    DateTime _phaseStart; // start of current phase

    // Phase states
    enum Phase { Transit, Settle, Collect, Done, Results }
    Phase _phase = Phase.Transit;

    // Timing (ms)
    const int TRANSIT_MS = 600;      // smooth dot movement
    const int SETTLE_MS = 200;       // eye settle after dot arrives
    const int COLLECT_MIN_MS = 800;  // minimum collection after settle
    const int COLLECT_MAX_MS = 2000; // maximum collection window
    const int SAMPLE_QUOTA = 40;     // target valid samples

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
        _allSamples = new List<(double x, double y, long timestampMs, bool valid)>[9];
        for (int i = 0; i < 9; i++)
            _allSamples[i] = new List<(double, double, long, bool)>();

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

        _tracker.OnGaze += OnGaze;

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
                            if (_currentPoint < 8)
                                StartPoint(_currentPoint + 1);
                            else
                                FinishCalibration();
                        });
                    }, null, 200, Timeout.Infinite);
                }
                break;
            }
        }

        _targetSize += (_targetSizeTarget - _targetSize) * 0.15f;
        Invalidate();
    }

    void OnGaze(double rawX, double rawY, bool leftOk, bool rightOk)
    {
        rawX = Math.Clamp(rawX, 0, 1);
        rawY = Math.Clamp(rawY, 0, 1);

        _gazeX = rawX;
        _gazeY = rawY;
        _gazeValid = leftOk || rightOk;

        if (_phase != Phase.Collect) return;

        long tsMs = (long)(DateTime.UtcNow - _phaseStart).TotalMilliseconds;

        // Blink detection and masking
        bool currentlyValid = leftOk || rightOk;

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

        _allSamples[_currentPoint].Add((rawX, rawY, tsMs, true));
        _validSampleCount++;
    }

    void FinishCalibration()
    {
        _tracker.OnGaze -= OnGaze;

        var pointSamples = new CalibrationEngine.PointSamples[9];
        for (int i = 0; i < 9; i++)
        {
            pointSamples[i] = new CalibrationEngine.PointSamples();
            // Only use valid samples
            var validSamples = _allSamples[i]
                .Where(s => s.valid)
                .Select(s => (s.x, s.y))
                .ToList();
            pointSamples[i].AllSamples.AddRange(validSamples);
        }

        _result = _engine.ComputeCalibration(pointSamples);
        WasCancelled = false;

        Invalidate();
        System.Threading.Timer? closeTimer = null;
        closeTimer = new System.Threading.Timer(_ =>
        {
            closeTimer?.Dispose();
            if (!IsDisposed) BeginInvoke(() => Close());
        }, null, 3000, Timeout.Infinite);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;

        // Progress dots at top
        for (int i = 0; i < 9; i++)
        {
            float px = Width / 2f + (i - 4) * 30;
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
            float progress = Math.Clamp(
                (float)(DateTime.UtcNow - _phaseStart).TotalMilliseconds / COLLECT_MAX_MS, 0, 1);
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
            Phase.Transit => $"Moving to dot {_currentPoint + 1}/9...",
            Phase.Settle => $"Hold steady on dot {_currentPoint + 1}/9...",
            Phase.Collect => $"Look at the dot ({_validSampleCount}/{SAMPLE_QUOTA} samples)",
            _ => "Processing..."
        };
        var size = g.MeasureString(msg, font);
        g.DrawString(msg, font, brush, (Width - size.Width) / 2, Height - 80);

        using var smallFont = new Font("Segoe UI", 11);
        g.DrawString("Press ESC to cancel", smallFont, Brushes.Gray, 10, 10);
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

        string points = $"Points: {r.PointsCollected}/9 collected";
        g.DrawString(points, font, Brushes.LightGray, cx - 250, cy + 30);

        if (r.Quality == CalibrationQuality.Failed)
        {
            g.DrawString("Position yourself 60-70cm from the tracker and try again.",
                smallFont, Brushes.OrangeRed, cx - 220, cy + 80);
        }
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape)
        {
            WasCancelled = true;
            _tracker.OnGaze -= OnGaze;
            Close();
        }
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _tracker.OnGaze -= OnGaze;
        _animTimer.Stop();
        base.OnFormClosed(e);
    }
}
