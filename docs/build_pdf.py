import os
import sys
import subprocess

def main():
    workspace = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(workspace, "00_PROJECT_ROADMAP.html")
    pdf_path = os.path.join(workspace, "00_PROJECT_ROADMAP.pdf")

    print(f"Generating PDF from: {html_path}")
    print(f"Target PDF: {pdf_path}")

    # Check for Edge executable
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    browser_exe = None
    for p in edge_paths:
        if os.path.exists(p):
            browser_exe = p
            break

    if browser_exe:
        print(f"Using browser engine: {browser_exe}")
        cmd = [
            browser_exe,
            "--headless",
            "--disable-gpu",
            f"--print-to-pdf={pdf_path}",
            html_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
            print(f"SUCCESS: PDF generated successfully! ({os.path.getsize(pdf_path)} bytes)")
            return

    # Fallback to pure python basic PDF generation if browser is unavailable
    print("Falling back to pure Python PDF generator...")
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.drawString(100, 750, "FSOC Virtual Camera Tracking System — Roadmap")
        c.save()
        print("Generated via reportlab.")
    except ImportError:
        print("Browser and reportlab unavailable; please open 00_PROJECT_ROADMAP.html and print to PDF.")

if __name__ == "__main__":
    main()
