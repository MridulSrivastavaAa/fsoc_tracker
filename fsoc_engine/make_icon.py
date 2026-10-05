"""
make_icon.py
============
Generates branded icon, splash, and Inno Setup installer assets for NETRA.
Outputs written to assets/:
  - netra_1024.png     (1024x1024 master icon)
  - netra.ico          (Multi-resolution Windows icon: 256, 128, 64, 48, 32, 24, 16)
  - splash.png         (640x360 startup splash banner)
  - wizard_side.bmp    (164x314 Inno Setup sidebar bitmap)
  - wizard_small.bmp   (55x58 Inno Setup top-right small bitmap)

Also generates version_info.txt for PyInstaller using fsoc.__version__.
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Add src to path so we can import fsoc.__version__
ENGINE_DIR = Path(__file__).resolve().parent
SRC_DIR = ENGINE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from fsoc.__version__ import VERSION
except ImportError:
    VERSION = "1.0.0"

ASSETS_DIR = ENGINE_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Color Palette
COLOR_BG_DARK = (11, 18, 32, 255)       # #0B1220 Dark Navy
COLOR_BG_SPLASH = (8, 14, 26, 255)      # #080E1A
COLOR_CYAN = (0, 229, 255, 255)         # #00E5FF Bright Cyan
COLOR_CYAN_DIM = (0, 180, 204, 180)     # Dim Cyan
COLOR_AMBER = (255, 171, 0, 255)        # #FFAB00 Amber
COLOR_WHITE = (240, 246, 252, 255)      # Crisp White
COLOR_MUTED = (139, 148, 158, 255)      # Muted Gray
COLOR_DIVIDER = (0, 229, 255, 100)      # Translucent Cyan


def get_font(size: int, bold: bool = False):
    """Find and return an appropriate TrueType font with fallbacks."""
    font_candidates = []
    if sys.platform == "win32":
        font_candidates = [
            "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        ]
    elif sys.platform == "darwin":
        font_candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    else:
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]

    for p in font_candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue

    # Fallback to default
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def draw_logo(size: int = 1024) -> Image.Image:
    """
    Draw the NETRA logo:
      - Dark rounded square (#0B1220)
      - Two concentric cyan (#00E5FF) rings
      - Cyan crosshair with a gap at the centre
      - Amber (#FFAB00) centre dot
    """
    scale = size / 1024.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Dark rounded square background
    pad = int(48 * scale)
    corner_r = int(180 * scale)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=corner_r,
        fill=COLOR_BG_DARK,
        outline=COLOR_CYAN_DIM,
        width=int(4 * scale)
    )

    cx, cy = size // 2, size // 2

    # 2. Concentric Cyan Rings
    # Outer ring
    r_outer = int(320 * scale)
    draw.ellipse(
        [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
        outline=COLOR_CYAN,
        width=int(14 * scale)
    )

    # Inner ring
    r_inner = int(190 * scale)
    draw.ellipse(
        [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
        outline=COLOR_CYAN,
        width=int(10 * scale)
    )

    # Subtle range ring (dashed/thin)
    r_mid = int(255 * scale)
    draw.ellipse(
        [cx - r_mid, cy - r_mid, cx + r_mid, cy + r_mid],
        outline=(0, 229, 255, 60),
        width=int(4 * scale)
    )

    # 3. Cyan crosshairs with center gap
    cross_len = int(400 * scale)
    gap = int(70 * scale)
    line_w = int(12 * scale)

    # Top arm
    draw.line([cx, cy - cross_len, cx, cy - gap], fill=COLOR_CYAN, width=line_w)
    # Bottom arm
    draw.line([cx, cy + gap, cx, cy + cross_len], fill=COLOR_CYAN, width=line_w)
    # Left arm
    draw.line([cx - cross_len, cy, cx - gap, cy], fill=COLOR_CYAN, width=line_w)
    # Right arm
    draw.line([cx + gap, cy, cx + cross_len, cy], fill=COLOR_CYAN, width=line_w)

    # 4. Tick marks along the outer ring
    tick_len = int(24 * scale)
    for angle_deg in [45, 135, 225, 315]:
        import math
        rad = math.radians(angle_deg)
        x1 = cx + (r_outer - tick_len) * math.cos(rad)
        y1 = cy + (r_outer - tick_len) * math.sin(rad)
        x2 = cx + (r_outer + tick_len) * math.cos(rad)
        y2 = cy + (r_outer + tick_len) * math.sin(rad)
        draw.line([x1, y1, x2, y2], fill=COLOR_CYAN, width=int(8 * scale))

    # 5. Amber centre dot (#FFAB00)
    r_amber = int(32 * scale)
    draw.ellipse(
        [cx - r_amber, cy - r_amber, cx + r_amber, cy + r_amber],
        fill=COLOR_AMBER,
        outline=COLOR_WHITE,
        width=int(4 * scale)
    )

    return img


def make_master_png_and_ico():
    """Create netra_1024.png and netra.ico with all required sizes."""
    png_path = ASSETS_DIR / "netra_1024.png"
    ico_path = ASSETS_DIR / "netra.ico"

    if png_path.exists():
        print(f"[ASSETS] Using existing master: {png_path}")
        master = Image.open(png_path).convert("RGBA")
    else:
        print("[ASSETS] Generating netra_1024.png...")
        master = draw_logo(1024)
        master.save(png_path, format="PNG")
        print(f"[ASSETS] Saved: {png_path}")

    # Generate multi-size .ico
    sizes = [(s, s) for s in [256, 128, 64, 48, 32, 24, 16]]
    master.save(ico_path, format="ICO", sizes=sizes)
    print(f"[ASSETS] Saved: {ico_path}")


def make_splash():
    """
    Generate splash.png (640x360):
      - Dark background
      - Logo at left
      - Title 'NETRA'
      - Subtitle 'FSOC PAT Workstation'
      - Small caption 'Pointing, Acquisition & Tracking Simulator'
      - Thin divider line near the bottom
    """
    w, h = 640, 360
    img = Image.new("RGBA", (w, h), COLOR_BG_SPLASH)
    draw = ImageDraw.Draw(img)

    # Subtle border
    draw.rectangle([0, 0, w - 1, h - 1], outline=(0, 229, 255, 60), width=1)

    # Draw logo at left (220x220)
    logo = draw_logo(220)
    img.paste(logo, (35, 55), mask=logo)

    # Typography
    font_title = get_font(42, bold=True)
    font_sub = get_font(20, bold=True)
    font_caption = get_font(13, bold=False)
    font_splash_hint = get_font(11, bold=False)

    text_x = 280

    # Title: NETRA
    draw.text((text_x, 60), "NETRA", font=font_title, fill=COLOR_CYAN)

    # Full form subtitle
    font_full = get_font(12, bold=True)
    draw.text((text_x, 118), "Next-Generation Emulation for Tracking & Real-Time Alignment", font=font_full, fill=COLOR_WHITE)

    # Subtitle: Team NavDrishti1
    font_team = get_font(16, bold=True)
    draw.text((text_x, 142), "Team NavDrishti1", font=font_team, fill=COLOR_CYAN)

    # Caption: Pointing, Acquisition & Tracking Workstation
    draw.text((text_x, 172), "Pointing, Acquisition & Tracking (PAT) Workstation", font=font_caption, fill=COLOR_MUTED)

    # System badges / tags (Removed ISRO PS, using Team NavDrishti1)
    draw.text((text_x, 210), f"Version {VERSION}  |  Virtual Camera PAT  |  Team NavDrishti1", font=font_caption, fill=COLOR_CYAN_DIM)

    # Thin divider line near the bottom (y=305)
    draw.line([30, 305, w - 30, 305], fill=COLOR_DIVIDER, width=1)

    # Splash status text placeholder area indicator
    draw.text((40, 325), "Initializing workstation...", font=font_splash_hint, fill=COLOR_CYAN)

    splash_path = ASSETS_DIR / "splash.png"
    img.save(splash_path, format="PNG")
    print(f"[ASSETS] Saved: {splash_path}")


def make_inno_bitmaps():
    """
    Generate wizard_side.bmp (164x314) and wizard_small.bmp (55x58) for Inno Setup.
    Must be BMP RGB (no alpha).
    """
    # 1. wizard_side.bmp (164 x 314)
    w_side, h_side = 164, 314
    side_img = Image.new("RGB", (w_side, h_side), (11, 18, 32))
    side_draw = ImageDraw.Draw(side_img)

    # Decorative background grid / borders
    side_draw.rectangle([0, 0, w_side - 1, h_side - 1], outline=(0, 229, 255), width=1)
    side_draw.line([0, 240, w_side, 240], fill=(0, 229, 255), width=1)

    # Add scaled logo at top-center (120x120)
    logo_side = draw_logo(120)
    side_img.paste(logo_side.convert("RGB"), (22, 35))

    # Add text
    font_bold = get_font(18, bold=True)
    font_small = get_font(10, bold=False)
    side_draw.text((45, 175), "NETRA", font=font_bold, fill=(0, 229, 255))
    side_draw.text((25, 202), "Team NavDrishti1", font=font_small, fill=(240, 246, 252))
    side_draw.text((10, 260), "Tracking & Real-Time Alignment", font=font_small, fill=(139, 148, 158))
    side_draw.text((45, 280), "Closed-Loop PAT", font=font_small, fill=(0, 229, 255))

    side_path = ASSETS_DIR / "wizard_side.bmp"
    side_img.save(side_path, format="BMP")
    print(f"[ASSETS] Saved: {side_path}")

    # 2. wizard_small.bmp (55 x 58)
    w_sm, h_sm = 55, 58
    sm_img = Image.new("RGB", (w_sm, h_sm), (11, 18, 32))
    sm_draw = ImageDraw.Draw(sm_img)
    sm_draw.rectangle([0, 0, w_sm - 1, h_sm - 1], outline=(0, 229, 255), width=1)

    logo_sm = draw_logo(48).resize((44, 44), Image.Resampling.LANCZOS)
    sm_img.paste(logo_sm.convert("RGB"), (5, 7))

    sm_path = ASSETS_DIR / "wizard_small.bmp"
    sm_img.save(sm_path, format="BMP")
    print(f"[ASSETS] Saved: {sm_path}")


def make_version_info():
    """Generate version_info.txt for PyInstaller with version matching __version__.py."""
    parts = VERSION.split(".")
    while len(parts) < 4:
        parts.append("0")
    try:
        v_tuple = tuple(int(p) for p in parts[:4])
    except ValueError:
        v_tuple = (1, 0, 0, 0)

    v_str = ".".join(str(p) for p in v_tuple)

    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v_tuple}, prodvers={v_tuple}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Team NavDrishti1'),
      StringStruct('FileDescription', 'NETRA - Next-Generation Emulation for Tracking & Real-Time Alignment'),
      StringStruct('FileVersion', '{v_str}'),
      StringStruct('InternalName', 'NETRA'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Team NavDrishti1'),
      StringStruct('OriginalFilename', 'NETRA.exe'),
      StringStruct('ProductName', 'NETRA (Next-Generation Emulation for Tracking & Real-Time Alignment)'),
      StringStruct('ProductVersion', '{v_str}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    vinfo_path = ENGINE_DIR / "version_info.txt"
    with open(vinfo_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[ASSETS] Saved: {vinfo_path}")


def main():
    print("=" * 60)
    print("NETRA Branding Asset Generator")
    print("=" * 60)
    make_master_png_and_ico()
    make_splash()
    make_inno_bitmaps()
    make_version_info()
    print("=" * 60)
    print("All branding assets generated successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
