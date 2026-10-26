"""Create valid, exact-size PDFs for demonstrating real chunk transfers.

The extra bytes are an explicitly labelled embedded test-data attachment, not
fake page counts or a misleading file extension. Run with reportlab and pypdf.
"""
from io import BytesIO
from pathlib import Path
import hashlib
import json
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'samples'
OUTPUT.mkdir(exist_ok=True)

def cover(size):
    stream = BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842))
    page.setTitle(f'DeadlineGuard - {size} MiB demonstration assignment')
    page.setFillColor(HexColor('#172B4D'))
    page.rect(0, 716, 595, 126, fill=1, stroke=0)
    page.setFillColorRGB(1, 1, 1)
    page.setFont('Helvetica-Bold', 23)
    page.drawString(45, 784, 'DeadlineGuard')
    page.setFont('Helvetica', 12)
    page.drawString(45, 756, f'Assignment upload demonstration / {size} MiB')
    lines = [
        ('DEMO FILE - NOT A REAL STUDENT SUBMISSION', True),
        ('Course: CS204 - Operating Systems', False),
        ('Topic: Reliable submission near a deadline', False),
        ('', False),
        ('What this file demonstrates', True),
        ('1. Start an authenticated upload before the deadline.', False),
        ('2. Watch the server acknowledge numbered chunks.', False),
        ('3. Disconnect the demo connection; saved chunks remain.', False),
        ('4. Reconnect and send only the missing chunks.', False),
        ('5. Click Finalize submission to verify and issue a receipt.', False),
        ('', False),
        ('Transparent test padding', True),
        ('This PDF includes an embedded demo-padding.bin attachment.', False),
        ('It contains inert test bytes to make transfers visible during a viva.', False),
        ('It is not additional coursework, executable code, or a real scan.', False),
        ('', False),
        (f'Exact size: {size * 1024 * 1024:,} bytes ({size} MiB).', False),
        (f'At 512 KiB per chunk: {size * 2} chunks.', False),
        ('20 MiB example: 24 saved chunks = 12 MiB; 16 missing = 8 MiB.', False),
        ('', False),
        ('Deadline policy', True),
        ('A five-minute recovery window allows the same session to finish', False),
        ('after the deadline. The receipt is marked grace recovered.', False),
        ('A hash commitment protects integrity, not proof of possession time.', False),
    ]
    y = 677
    for text, bold in lines:
        page.setFillColor(HexColor('#172B4D' if bold else '#52647C'))
        page.setFont('Helvetica-Bold' if bold else 'Helvetica', 11 if bold else 10)
        page.drawString(45, y, text)
        y -= 21
    page.setStrokeColor(HexColor('#DCE4ED'))
    page.line(45, 80, 550, 80)
    page.setFont('Helvetica', 9)
    page.drawString(45, 60, 'Local university prototype | Use the website to upload this PDF')
    page.drawRightString(550, 60, '1 / 1')
    page.save()
    return stream.getvalue()

def make_pdf(size):
    target = size * 1024 * 1024
    base = cover(size)
    padding = target - len(base) - 2000
    for _ in range(8):
        writer = PdfWriter()
        writer.append(PdfReader(BytesIO(base)))
        writer.add_attachment('demo-padding.bin', b'D' * padding)
        output = BytesIO()
        writer.write(output)
        content = output.getvalue()
        if len(content) == target:
            break
        padding += target - len(content)
    assert len(content) == target, 'Exact-size generation did not converge'
    path = OUTPUT / f'demo-assignment-{size}mib.pdf'
    path.write_bytes(content)
    reader = PdfReader(path, strict=True)
    assert len(reader.pages) == 1 and not reader.is_encrypted
    assert 'Transparent test padding' in reader.pages[0].extract_text()
    return {'filename':path.name,'bytes':len(content),'chunks':size*2,'sha256':hashlib.sha256(content).hexdigest()}

if __name__ == '__main__':
    manifest = [make_pdf(size) for size in (5,20)]
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))
