"""Clearly labeled fictional document used only for the hosted MCP workflow test."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from pypdf import PdfReader

root = Path(__file__).resolve().parents[1]
out = root / 'output/pdf/kamala-synthetic-age-proof.pdf'
out.parent.mkdir(parents=True, exist_ok=True)
c = canvas.Canvas(str(out), pagesize=A4)
c.setTitle('SYNTHETIC TEST DOCUMENT - Kamala Devi')
c.setFillColor(colors.HexColor('#9b1c1c'))
c.setFont('Helvetica-Bold', 20)
c.drawString(48, 780, 'SYNTHETIC TEST DOCUMENT')
c.setFont('Helvetica-Bold', 13)
c.drawString(48, 751, 'NOT A GOVERNMENT ID OR VALID AGE CERTIFICATE')
c.setFillColor(colors.HexColor('#202b3b'))
c.setFont('Helvetica', 12)
lines = [
    'Purpose: Seva Setu evaluation - document upload and officer review.',
    '',
    'Fictional applicant: Kamala Devi (Synthetic Test)',
    'Fictional date of birth: 01 January 1956',
    'Age on 30 October 2026: 70 years',
    'Fictional village: Synthetic Sonari Village',
    'Block used for evaluation: Sonari',
    '',
    'All applicant details are fictional. This file contains no real identity proof.',
    'It tests the evaluation portal only and must not support a real benefit claim.',
    'No official seal, signature, document number or issuing authority is claimed.',
]
y = 708
for line in lines:
    c.drawString(48, y, line)
    y -= 24
c.setStrokeColor(colors.HexColor('#9b1c1c'))
c.line(48, 365, 547, 365)
c.setFont('Helvetica-Bold', 11)
c.drawString(48, 340, 'EVALUATION ONLY - FICTIONAL DATA - NO REAL PENSION CLAIM')
c.showPage()
c.save()
reader = PdfReader(str(out))
assert len(reader.pages) == 1 and not reader.is_encrypted
text = reader.pages[0].extract_text()
assert 'SYNTHETIC TEST DOCUMENT' in text and '1956' in text
print('Created and text-verified one-page synthetic test PDF.')
