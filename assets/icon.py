#!/usr/bin/env python3
"""Generate Icosele Vault app icons programmatically."""

from pathlib import Path
from PIL import Image, ImageDraw


def _color_alpha(hex_color: str, alpha: float) -> tuple[int, int, int, int]:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (r, g, b, int(alpha * 255))


def generate_icon(size: int) -> Image.Image:
    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cr = int(S * 0.18)  # canvas corner radius

    # --- Canvas background ---
    draw.rounded_rectangle([0, 0, S - 1, S - 1], radius=cr, fill="#0a0e14")

    # --- Back window ---
    bx, by = int(S * 0.10), int(S * 0.20)
    bw, bh = int(S * 0.63), int(S * 0.50)
    wr = int(S * 0.06)
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=wr, fill="#141c28")

    # Back title bar
    tbh = int(S * 0.12)
    # Draw title bar as clipped rounded rect (top corners round, bottom square)
    draw.rounded_rectangle([bx, by, bx + bw, by + tbh + wr], radius=wr, fill="#1a2540")
    draw.rectangle([bx, by + tbh, bx + bw, by + tbh + wr], fill="#1a2540")
    # Clip to window bounds
    draw.rounded_rectangle([bx, by + tbh, bx + bw, by + bh], radius=0, fill="#141c28")

    # Back traffic lights
    dot_r = int(S * 0.027)
    dot_y = by + tbh // 2
    colors_back = ["#2d6b48", "#357a55", "#1e4d34"]
    for i, c in enumerate(colors_back):
        cx = bx + int(S * 0.05) + i * int(S * 0.045)
        draw.ellipse([cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r], fill=c)

    # Back content lines
    line_h = int(S * 0.025)
    line_y_start = by + tbh + int(S * 0.05)
    line_x = bx + int(S * 0.05)
    widths_back = [0.44, 0.54, 0.34, 0.47]
    for i, wf in enumerate(widths_back):
        ly = line_y_start + i * int(S * 0.06)
        lw = int(S * wf)
        draw.rounded_rectangle([line_x, ly, line_x + lw, ly + line_h],
                                radius=line_h // 2, fill="#1a2540")

    # --- Front window ---
    fx, fy = int(S * 0.26), int(S * 0.42)
    fw, fh = int(S * 0.68), int(S * 0.54)
    # Glow border (outer)
    glow_outer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_outer)
    gd.rounded_rectangle([fx - 3, fy - 3, fx + fw + 3, fy + fh + 3],
                          radius=wr + 2, outline=_color_alpha("#4caf7d", 0.55), width=2)
    img = Image.alpha_composite(img, glow_outer)
    draw = ImageDraw.Draw(img)

    # Glow border (inner)
    glow_inner = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gi = ImageDraw.Draw(glow_inner)
    gi.rounded_rectangle([fx - 1, fy - 1, fx + fw + 1, fy + fh + 1],
                          radius=wr + 1, outline=_color_alpha("#4caf7d", 0.20), width=1)
    img = Image.alpha_composite(img, glow_inner)
    draw = ImageDraw.Draw(img)

    # Front window body
    draw.rounded_rectangle([fx, fy, fx + fw, fy + fh], radius=wr, fill="#0d1420")

    # Front title bar
    ftbh = int(S * 0.13)
    draw.rounded_rectangle([fx, fy, fx + fw, fy + ftbh + wr], radius=wr, fill="#4caf7d")
    draw.rectangle([fx, fy + ftbh, fx + fw, fy + ftbh + wr], fill="#4caf7d")
    draw.rounded_rectangle([fx, fy + ftbh, fx + fw, fy + fh], radius=0, fill="#0d1420")

    # Front traffic lights
    fdot_r = int(S * 0.032)
    fdot_y = fy + ftbh // 2
    colors_front = ["#1a5c38", "#23784f", "#3dc47e"]
    for i, c in enumerate(colors_front):
        cx = fx + int(S * 0.06) + i * int(S * 0.055)
        draw.ellipse([cx - fdot_r, fdot_y - fdot_r, cx + fdot_r, fdot_y + fdot_r], fill=c)

    # Front title bar label (right side)
    lbl_w = int(S * 0.14)
    lbl_h = int(S * 0.05)
    lbl_x = fx + fw - lbl_w - int(S * 0.04)
    lbl_y = fdot_y - lbl_h // 2
    draw.rounded_rectangle([lbl_x, lbl_y, lbl_x + lbl_w, lbl_y + lbl_h],
                            radius=lbl_h // 2, fill="#1a5c38")

    # Accent bar on left of content
    bar_w = int(S * 0.023)
    bar_x = fx + int(S * 0.03)
    bar_y = fy + ftbh + int(S * 0.03)
    bar_h = fh - ftbh - int(S * 0.06)
    accent_bar = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    abd = ImageDraw.Draw(accent_bar)
    abd.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                           radius=bar_w // 2, fill=_color_alpha("#4caf7d", 0.80))
    img = Image.alpha_composite(img, accent_bar)
    draw = ImageDraw.Draw(img)

    # Front content lines
    fline_h = int(S * 0.022)
    fline_y_start = fy + ftbh + int(S * 0.045)
    fline_x = fx + int(S * 0.08)
    widths_front = [0.50, 0.42, 0.56, 0.38, 0.48]
    for i, wf in enumerate(widths_front):
        ly = fline_y_start + i * int(S * 0.055)
        lw = int(S * wf)
        if i == len(widths_front) - 1:
            # Last line in accent colour
            line_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            ld = ImageDraw.Draw(line_layer)
            ld.rounded_rectangle([fline_x, ly, fline_x + lw, ly + fline_h],
                                  radius=fline_h // 2, fill=_color_alpha("#4caf7d", 0.55))
            img = Image.alpha_composite(img, line_layer)
            draw = ImageDraw.Draw(img)
        else:
            draw.rounded_rectangle([fline_x, ly, fline_x + lw, ly + fline_h],
                                    radius=fline_h // 2, fill="#1a2540")

    return img


def generate_icon_padded(canvas_size: int) -> Image.Image:
    """Generate an icon with 10% padding for clean rendering in GNOME's icon grid."""
    padding = int(canvas_size * 0.10)
    inner_size = canvas_size - 2 * padding
    inner = generate_icon(inner_size)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.paste(inner, (padding, padding))
    return canvas


def main() -> None:
    out_dir = Path(__file__).resolve().parent

    icon256 = generate_icon_padded(256)
    icon256.save(out_dir / "icon.png")
    print(f"Saved {out_dir / 'icon.png'} (256x256)")

    icon512 = generate_icon_padded(512)
    icon512.save(out_dir / "icon512.png")
    print(f"Saved {out_dir / 'icon512.png'} (512x512)")


if __name__ == "__main__":
    main()
