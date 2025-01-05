from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os
from psd_tools import PSDImage  # Library untuk mendukung file PSD

app = Flask(__name__)

# Folder untuk cache
UPLOAD_FOLDER = 'cache/uploads'
OUTPUT_FOLDER = 'cache/outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Konfigurasi ukuran foto dan margin
PHOTO_SIZES = {'3x4': (30, 40), '4x6': (40, 60)}  # mm
MARGIN_IN = 1.5  # mm (Margin dalam untuk garis potong)
MARGIN_OUT = 10  # mm (Margin luar untuk kertas)


def get_unique_filename(folder, filename):
    """Buat nama file unik jika sudah ada."""
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(folder, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1
    return new_filename


def convert_psd_to_png(psd_path):
    """Konversi file PSD ke PNG."""
    psd = PSDImage.open(psd_path)
    composite = psd.composite()
    output_path = psd_path.replace(".psd", ".png")
    composite.save(output_path, format="PNG")
    return output_path


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("images")
        sizes = request.form.getlist("sizes")
        quantities = request.form.getlist("quantities")

        file_paths = []
        photo_sizes = []
        photo_quantities = []

        for file, size, quantity in zip(files, sizes, quantities):
            if size in PHOTO_SIZES:
                # Simpan file di cache dengan nama unik
                unique_filename = get_unique_filename(UPLOAD_FOLDER, file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                file.save(file_path)

                # Jika file PSD, konversi ke PNG
                if file_path.lower().endswith(".psd"):
                    file_path = convert_psd_to_png(file_path)

                file_paths.append(file_path)
                photo_sizes.append(size)
                photo_quantities.append(int(quantity))

        # Buat PDF dengan nama unik di folder cache
        output_filename = get_unique_filename(OUTPUT_FOLDER, "output.pdf")
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        generate_pdf(file_paths, photo_sizes, photo_quantities, output_path)

        # Kirim file PDF hasil
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    files = request.files.getlist("images")
    analysis = []

    for file in files:
        img = Image.open(file)
        width, height = img.size
        if width and height:
            ratio = width / height
            nearest_size = min(PHOTO_SIZES.keys(), key=lambda x: abs(ratio - (PHOTO_SIZES[x][0] / PHOTO_SIZES[x][1])))
            accuracy = min(ratio, PHOTO_SIZES[nearest_size][0] / PHOTO_SIZES[nearest_size][1]) / \
                       max(ratio, PHOTO_SIZES[nearest_size][0] / PHOTO_SIZES[nearest_size][1]) * 100
        else:
            nearest_size = "Unknown"
            accuracy = 0

        analysis.append({"filename": file.filename, "nearest_size": nearest_size, "accuracy": accuracy, "ratio": ratio})
    return jsonify(analysis)


def generate_pdf(image_paths, sizes, quantities, output_path):
    """Buat PDF dengan tata letak dua jenis halaman: tanpa rotasi dan dengan rotasi."""
    c = canvas.Canvas(output_path, pagesize=A4)
    page_width, page_height = A4

    # Konversi margin ke satuan pt
    MARGIN_IN_PT = MARGIN_IN * 2.83465
    MARGIN_OUT_PT = MARGIN_OUT * 2.83465

    def add_photo(img_path, img_width, img_height, img_margin_width, img_margin_height, rotate=False):
        """Tambahkan foto dengan atau tanpa rotasi."""
        nonlocal x, y

        # Jika rotasi, tukar lebar dan tinggi
        if rotate:
            img_width, img_height = img_height, img_width
            img_margin_width, img_margin_height = img_margin_height, img_margin_width

        if x + img_width > page_width - MARGIN_OUT_PT:
            x = MARGIN_OUT_PT
            y -= img_height

        if y < MARGIN_OUT_PT:
            c.showPage()
            x, y = MARGIN_OUT_PT, page_height - MARGIN_OUT_PT

        # Jika rotasi, simpan gambar yang telah dirotasi
        if rotate:
            img = Image.open(img_path).rotate(90, expand=True)
            rotated_path = get_unique_filename(UPLOAD_FOLDER, os.path.basename(img_path))
            img.save(rotated_path)
            img_path = rotated_path

        # Tambahkan gambar
        c.drawImage(img_path, x + MARGIN_IN_PT, y - img_height + MARGIN_IN_PT,
                    img_margin_width, img_margin_height)

        # Garis potong
        c.rect(x, y - img_height, img_width, img_height)
        x += img_width

    # Lembar pertama (tanpa rotasi)
    x, y = MARGIN_OUT_PT, page_height - MARGIN_OUT_PT
    for img_path, size, quantity in zip(image_paths, sizes, quantities):
        width, height = PHOTO_SIZES[size]
        img_width = width * 2.83465
        img_height = height * 2.83465
        img_margin_width = img_width - 2 * MARGIN_IN_PT
        img_margin_height = img_height - 2 * MARGIN_IN_PT

        for _ in range(quantity):
            add_photo(img_path, img_width, img_height, img_margin_width, img_margin_height)

    # Lembar kedua (dengan rotasi 90 derajat)
    c.showPage()
    x, y = MARGIN_OUT_PT, page_height - MARGIN_OUT_PT
    for img_path, size, quantity in zip(image_paths, sizes, quantities):
        width, height = PHOTO_SIZES[size]
        img_width = width * 2.83465
        img_height = height * 2.83465
        img_margin_width = img_width - 2 * MARGIN_IN_PT
        img_margin_height = img_height - 2 * MARGIN_IN_PT

        for _ in range(quantity):
            add_photo(img_path, img_width, img_height, img_margin_width, img_margin_height, rotate=True)

    c.save()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)