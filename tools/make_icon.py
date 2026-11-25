"""assets/icon.ico dosyasını üretir (bağımlılıksız: PNG'leri elle kodlar)."""
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.ico")


def rounded_rect_sdf(x, y, cx, cy, hw, hh, r):
    qx = abs(x - cx) - hw + r
    qy = abs(y - cy) - hh + r
    outside = (max(qx, 0) ** 2 + max(qy, 0) ** 2) ** 0.5
    return outside + min(max(qx, qy), 0) - r


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


def over(dst, src):
    a = src[3] + dst[3] * (1 - src[3])
    if a == 0:
        return (0, 0, 0, 0)
    return tuple((src[i] * src[3] + dst[i] * dst[3] * (1 - src[3])) / a for i in range(3)) + (a,)


def pixel(u, v):
    """u, v: 0..1 arası koordinat. Tuş başlığı: koyu gövde, turuncu üst yüz, parlayan nokta."""
    col = (0, 0, 0, 0)
    # Gövde (gölge tarafı)
    d = rounded_rect_sdf(u, v, 0.5, 0.53, 0.44, 0.42, 0.16)
    if d < 0.01:
        a = min(1, max(0, (0.01 - d) / 0.02))
        col = over(col, (0.09, 0.08, 0.10, a))
    # Üst yüz: turuncu degrade
    d = rounded_rect_sdf(u, v, 0.5, 0.45, 0.34, 0.31, 0.12)
    if d < 0.01:
        a = min(1, max(0, (0.01 - d) / 0.02))
        c = mix((1.0, 0.48, 0.16, 1), (1.0, 0.30, 0.10, 1), v)
        col = over(col, c[:3] + (a,))
    # "M" yerine üç dikey çubuk: makro dalgası
    for i, (x, h) in enumerate(((0.36, 0.14), (0.5, 0.22), (0.64, 0.14))):
        d = rounded_rect_sdf(u, v, x, 0.45, 0.04, h, 0.04)
        if d < 0.01:
            a = min(1, max(0, (0.01 - d) / 0.02))
            col = over(col, (0.10, 0.07, 0.06, a * 0.92))
    return col


def render(size, ss=4):
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    c = pixel((x + (sx + 0.5) / ss) / size, (y + (sy + 0.5) / ss) / size)
                    for i in range(3):
                        acc[i] += c[i] * c[3]
                    acc[3] += c[3]
            n = ss * ss
            a = acc[3] / n
            rgb = [acc[i] / acc[3] if acc[3] else 0 for i in range(3)]
            row += bytes([round(rgb[0] * 255), round(rgb[1] * 255), round(rgb[2] * 255), round(a * 255)])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    sizes = (16, 24, 32, 48, 64, 256)
    pngs = [render(s, 4 if s <= 64 else 2) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, png in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(header + entries + b"".join(pngs))
    print("yazıldı:", OUT)


if __name__ == "__main__":
    main()
