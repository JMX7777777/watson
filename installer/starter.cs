// Watson-Setup.exe: entpackt den Installer in einen Temp-Ordner und startet das Installationsfenster.
// Läuft OHNE Administrator-Rechte (siehe starter.manifest: asInvoker).
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

class WatsonSetup
{
    [STAThread]
    static int Main(string[] args)
    {
        string tmp = Path.Combine(Path.GetTempPath(), "Watson-Setup-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        try
        {
            Directory.CreateDirectory(tmp);
            using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
            using (ZipArchive z = new ZipArchive(s))
                z.ExtractToDirectory(tmp);
            string extra = string.Join(" ", args);
            var psi = new ProcessStartInfo("powershell.exe",
                "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + Path.Combine(tmp, "setup.ps1") + "\" " + extra)
            { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = tmp };
            Process p = Process.Start(psi);
            p.WaitForExit();
            return p.ExitCode;
        }
        catch (Exception e)
        {
            MessageBox.Show("Watson setup could not be started / Watson konnte nicht gestartet werden:\n\n" + e.Message, "Watson", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        finally
        {
            try { Directory.Delete(tmp, true); } catch { }
        }
    }
}
