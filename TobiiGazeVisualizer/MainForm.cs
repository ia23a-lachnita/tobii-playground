using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace TobiiGazeVisualizer;

public class MainForm : Form
{
    readonly TobiiUsb _tracker;
    readonly GazeSmoother _smoother;
    readonly System.Windows.Forms.Timer _renderTimer;
    CalibrationResult _calibration;

    double _rawX, _rawY;
    double _calibX, _calibY;
    double _smoothX, _smoothY;
    bool _isValid;
    bool _leftDetected, _rightDetected;
    readonly PointF[] _trail = new PointF[150];
    int _trailIdx;

    // Gaze cursor appearance
    const int CURSOR_RADIUS = 12;
    const int RING_RADIUS = 24;

    public MainForm()
    {
        Text = "Tobii Gaze Visualizer";
        Size = new Size(1920, 1080);
        StartPosition = FormStartPosition.Manual;
        Location = new Point(0, 0);
        FormBorderStyle = FormBorderStyle.None;
        BackColor = Color.Black;
        Opacity = 0.85;
        TopMost = true;
        DoubleBuffered = true;
        ShowInTaskbar = false;
        KeyPreview = true;

        var screen = Screen.PrimaryScreen?.Bounds ?? new Rectangle(0, 0, 1920, 1080);
        Bounds = screen;

        _smoother = new GazeSmoother(minCutoff: 1.0, beta: 0.5);
        _tracker = new TobiiUsb();
        _calibration = CalibrationResult.LoadDefault();

        for (int i = 0; i < _trail.Length; i++)
            _trail[i] = new PointF(-100, -100);

        _tracker.OnGaze += OnGazeReceived;

        _renderTimer = new System.Windows.Forms.Timer { Interval = 16 };
        _renderTimer.Tick += (_, _) => Invalidate();
        _renderTimer.Start();
    }

    protected override void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        Cursor.Hide();

        if (!_tracker.Connect())
        {
            MessageBox.Show("Could not connect to Tobii Eye Tracker 5L.\nMake sure it's connected and the Platform Runtime service is stopped.",
                "Connection Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Application.Exit();
            return;
        }

        _tracker.StartTracking();
    }

    void OnGazeReceived(double rawX, double rawY, bool leftOk, bool rightOk)
    {
        _rawX = rawX;
        _rawY = rawY;
        _leftDetected = leftOk;
        _rightDetected = rightOk;
        _isValid = leftOk || rightOk;

        if (_isValid)
        {
            // Only apply calibration if it's good quality
            double cx, cy;
            if (_calibration.Quality == CalibrationQuality.Good || _calibration.Quality == CalibrationQuality.Excellent)
            {
                (cx, cy) = _calibration.Transform(rawX, rawY, true);
            }
            else
            {
                // No calibration or bad calibration - use raw coordinates
                cx = rawX;
                cy = rawY;
            }
            _calibX = cx;
            _calibY = cy;

            // Apply smoothing on calibrated coordinates
            var (sx, sy) = _smoother.Filter(cx, cy);
            _smoothX = sx;
            _smoothY = sy;

            // Update trail - invert Y because tracker Y=0 is bottom, screen Y=0 is top
            float screenX = (float)(_smoothX * Width);
            float screenY = (float)((1 - _smoothY) * Height);
            _trail[_trailIdx] = new PointF(screenX, screenY);
            _trailIdx = (_trailIdx + 1) % _trail.Length;
        }
    }

    void StartCalibration()
    {
        // Don't stop tracking - CalibrationForm needs gaze data
        using var calForm = new CalibrationForm(_tracker);
        calForm.ShowDialog(this);

        if (!calForm.WasCancelled)
        {
            _calibration = calForm.Result;
            _calibration.Save();
        }

        _smoother.Reset();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;

        if (!_isValid)
        {
            using var font = new Font("Segoe UI", 18);
            using var brush = new SolidBrush(Color.FromArgb(120, 255, 255, 255));
            string msg = _leftDetected || _rightDetected
                ? "Tracking..."
                : "Look at the tracker (40-80cm away)";
            var size = g.MeasureString(msg, font);
            g.DrawString(msg, font, brush, (Width - size.Width) / 2, (Height - size.Height) / 2);

            // Show calibration status
            using var smallFont = new Font("Segoe UI", 12);
            using var statusBrush = new SolidBrush(Color.FromArgb(150, 200, 200, 200));
            string calStatus = _calibration.Quality switch
            {
                CalibrationQuality.Excellent => "Calibration: Excellent",
                CalibrationQuality.Good => "Calibration: Good",
                CalibrationQuality.Poor => "Calibration: Poor (press C to recalibrate)",
                CalibrationQuality.Failed => "Calibration: Failed (press C to calibrate)",
                _ => "Not calibrated (press C to calibrate)"
            };
            g.DrawString(calStatus, smallFont, statusBrush, 10, 10);
            g.DrawString("ESC to quit", smallFont, statusBrush, 10, 30);
            return;
        }

        float cx = (float)(_smoothX * Width);
        float cy = (float)((1 - _smoothY) * Height);  // Invert Y

        // Draw trail (fading)
        for (int i = 0; i < _trail.Length; i++)
        {
            int idx = (_trailIdx - i - 1 + _trail.Length) % _trail.Length;
            float alpha = 1.0f - (float)i / _trail.Length;
            if (alpha <= 0) continue;
            using var pen = new Pen(Color.FromArgb((int)(alpha * 80), 0, 200, 255), 2);
            int next = (idx + 1) % _trail.Length;
            g.DrawLine(pen, _trail[idx], _trail[next]);
        }

        // Outer glow ring
        using (var path = new GraphicsPath())
        {
            path.AddEllipse(cx - RING_RADIUS, cy - RING_RADIUS, RING_RADIUS * 2, RING_RADIUS * 2);
            using var pathBrush = new PathGradientBrush(path)
            {
                CenterColor = Color.FromArgb(60, 0, 180, 255),
                SurroundColors = new[] { Color.Transparent }
            };
            g.FillEllipse(pathBrush, cx - RING_RADIUS, cy - RING_RADIUS, RING_RADIUS * 2, RING_RADIUS * 2);
        }

        // Main cursor dot
        using (var path = new GraphicsPath())
        {
            path.AddEllipse(cx - CURSOR_RADIUS, cy - CURSOR_RADIUS, CURSOR_RADIUS * 2, CURSOR_RADIUS * 2);
            using var pathBrush = new PathGradientBrush(path)
            {
                CenterColor = Color.FromArgb(220, 0, 220, 255),
                SurroundColors = new[] { Color.FromArgb(40, 0, 100, 200) }
            };
            g.FillEllipse(pathBrush, cx - CURSOR_RADIUS, cy - CURSOR_RADIUS, CURSOR_RADIUS * 2, CURSOR_RADIUS * 2);
        }

        // Center crosshair
        using var crossPen = new Pen(Color.White, 1.5f);
        g.DrawLine(crossPen, cx - 6, cy, cx + 6, cy);
        g.DrawLine(crossPen, cx, cy - 6, cx, cy + 6);

        // Debug info (top-left)
        using var debugFont = new Font("Consolas", 11);
        using var debugBrush = new SolidBrush(Color.FromArgb(180, 200, 200, 200));
        g.DrawString($"Raw: ({_rawX:F4}, {_rawY:F4})", debugFont, debugBrush, 10, 10);
        g.DrawString($"Calib: ({_calibX:F4}, {_calibY:F4})", debugFont, debugBrush, 10, 28);
        g.DrawString($"Smooth: ({_smoothX:F4}, {_smoothY:F4})", debugFont, debugBrush, 10, 46);
        g.DrawString($"Screen: ({cx:F0}, {cy:F0})", debugFont, debugBrush, 10, 64);

        string eyeStatus = $"L:{(_leftDetected ? "OK" : "--")} R:{(_rightDetected ? "OK" : "--")}";
        string calInfo = _calibration.Quality != CalibrationQuality.Uncalibrated
            ? $"  Cal:{_calibration.Quality} ({_calibration.MeanErrorDegrees:F1}°)"
            : "";
        g.DrawString(eyeStatus + calInfo, debugFont, debugBrush, 10, 82);

        g.DrawString("C = calibrate | ESC = quit", debugFont, debugBrush, 10, 100);
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape)
        {
            _tracker.Dispose();
            Application.Exit();
        }
        else if (e.KeyCode == Keys.C)
        {
            StartCalibration();
        }
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _tracker.Dispose();
        base.OnFormClosed(e);
    }

    protected override CreateParams CreateParams
    {
        get
        {
            var cp = base.CreateParams;
            cp.ExStyle |= 0x00000080;
            return cp;
        }
    }
}
