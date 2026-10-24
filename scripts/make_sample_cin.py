"""Create a fake demo ID image matching a seeded registry user (for OCR demos only)."""
import sys

from PIL import Image, ImageDraw, ImageFont

name = sys.argv[1] if len(sys.argv) > 1 else "Amine Ben Salah"
cin = sys.argv[2] if len(sys.argv) > 2 else "12345678"
img = Image.new("RGB", (1200, 700), "white")
d = ImageDraw.Draw(img)
font = ImageFont.load_default(size=48)
d.rectangle([20, 20, 1180, 680], outline="black", width=4)
d.text((60, 60), "REPUBLIQUE TUNISIENNE - DEMO", fill="black", font=font)
d.text((60, 250), f"Nom: {name}", fill="black", font=font)
d.text((60, 400), f"CIN: {cin}", fill="black", font=font)
img.save("sample_cin.png")
print("wrote sample_cin.png")
