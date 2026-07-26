using System;
using System.IO;
using TobiiGazeVisualizer;

class Program
{
    static void Main()
    {
        using var tracker = new TobiiUsb();
        if (!tracker.Connect())
        {
            Console.WriteLine("Failed to connect");
            return;
        }
        tracker.StartTracking();

        Console.WriteLine("FOV Measurement Tool");
        Console.WriteLine("Look at each edge and note the gaze coordinates.");
        Console.WriteLine("Press ENTER to start logging, then look at edges.");
        Console.WriteLine();

        var logFile = "fov_measurement.csv";
        using var writer = new StreamWriter(logFile);
        writer.WriteLine("time,gazeX,gazeY,valid");

        var startTime = DateTime.UtcNow;
        tracker.OnGaze += (x, y, l, r) =>
        {
            var elapsed = (DateTime.UtcNow - startTime).TotalSeconds;
            writer.WriteLine($"{elapsed:F3},{x:F4},{y:F4},{l || r}");
        };

        Console.WriteLine("Logging started. Look at edges...");
        Console.WriteLine("When done, press ENTER to stop.");
        Console.ReadLine();

        tracker.StopTracking();
        Console.WriteLine($"Saved to {logFile}");
    }
}
