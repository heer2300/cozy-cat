import qrcode

url = "https://yourcafe.com/order/A01"

qr = qrcode.QRCode(
    version=None,
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=12,
    border=4
)

qr.add_data(url)
qr.make(fit=True)

img = qr.make_image()
img.save("table_A01.png")

print("QR created!")