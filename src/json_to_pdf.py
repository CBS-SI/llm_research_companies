"""
Convert JSON files containing markdown-formatted text to PDF files.

This script reads JSON files with markdown content and converts them to PDFs.
Supports multiple conversion methods: markdown2pdf, weasyprint, or pandoc.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional


def extract_markdown_from_json(json_path: str) -> Optional[str]:
    """
    Extract markdown text from JSON file.

    Args:
        json_path: Path to JSON file

    Returns:
        Markdown text if found, None otherwise
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Navigate the JSON structure to find the text content
        if 'response' in data and 'output' in data['response']:
            for output_item in data['response']['output']:
                if output_item.get('type') == 'message':
                    content = output_item.get('content', [])
                    for content_item in content:
                        if content_item.get('type') == 'output_text':
                            return content_item.get('text', '')

        print(f"Warning: No markdown text found in {json_path}")
        return None

    except Exception as e:
        print(f"Error reading {json_path}: {e}")
        return None


def convert_markdown_to_pdf_pdfkit(markdown_text: str, output_pdf_path: str) -> bool:
    """
    Convert markdown to PDF using markdown + pdfkit (wkhtmltopdf).

    Requires: pip install markdown pdfkit
              brew install wkhtmltopdf (on macOS)
    """
    try:
        import markdown
        import pdfkit

        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_text,
            extensions=['tables', 'fenced_code', 'codehilite']
        )

        # Add basic CSS styling
        css_styling = """
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 40px;
                line-height: 1.6;
            }
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
                font-size: 12px;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            th {
                background-color: #f2f2f2;
                font-weight: bold;
            }
            code {
                background-color: #f4f4f4;
                padding: 2px 4px;
                border-radius: 3px;
                font-size: 11px;
            }
            pre {
                background-color: #f4f4f4;
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
                font-size: 11px;
            }
            h1, h2, h3 {
                color: #333;
            }
        </style>
        """

        full_html = f"<html><head>{css_styling}</head><body>{html_content}</body></html>"

        # Convert HTML to PDF
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': 'UTF-8',
            'enable-local-file-access': None
        }
        pdfkit.from_string(full_html, output_pdf_path, options=options)
        return True

    except ImportError:
        print("Error: pdfkit or markdown not installed.")
        print("Install with: pip install markdown pdfkit")
        print("Also install wkhtmltopdf: brew install wkhtmltopdf")
        return False
    except OSError as e:
        if 'wkhtmltopdf' in str(e):
            print("Error: wkhtmltopdf not found.")
            print("Install with: brew install wkhtmltopdf")
        else:
            print(f"Error converting to PDF: {e}")
        return False
    except Exception as e:
        print(f"Error converting to PDF: {e}")
        return False


def convert_markdown_to_pdf_reportlab(markdown_text: str, output_pdf_path: str) -> bool:
    """
    Convert markdown to PDF using reportlab (pure Python, no external dependencies).

    Requires: pip install reportlab markdown
    """
    try:
        import markdown
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from html.parser import HTMLParser
        import re

        # Convert markdown to HTML first
        html_content = markdown.markdown(
            markdown_text,
            extensions=['tables', 'fenced_code']
        )

        # Create PDF
        doc = SimpleDocTemplate(output_pdf_path, pagesize=A4,
                              rightMargin=0.75*inch, leftMargin=0.75*inch,
                              topMargin=0.75*inch, bottomMargin=0.75*inch)

        # Container for PDF elements
        story = []
        styles = getSampleStyleSheet()

        # Custom styles
        styles.add(ParagraphStyle(name='CustomCode',
                                 parent=styles['Code'],
                                 fontSize=8,
                                 leftIndent=20,
                                 backColor=colors.HexColor('#f4f4f4')))

        # Parse HTML and build PDF
        class HTMLToPDFParser(HTMLParser):
            def __init__(self, story, styles):
                super().__init__()
                self.story = story
                self.styles = styles
                self.current_text = []
                self.in_table = False
                self.table_data = []
                self.current_row = []
                self.current_tag = None

            def handle_starttag(self, tag, attrs):
                self.current_tag = tag
                if tag == 'table':
                    self.in_table = True
                    self.table_data = []
                elif tag == 'tr':
                    self.current_row = []

            def handle_endtag(self, tag):
                if tag == 'table':
                    self.in_table = False
                    if self.table_data:
                        # Wrap cell contents in Paragraphs for text wrapping
                        wrapped_data = []
                        cell_style = ParagraphStyle(
                            'cell',
                            parent=self.styles['Normal'],
                            fontSize=7,
                            leading=9,
                            wordWrap='CJK'
                        )
                        header_style = ParagraphStyle(
                            'header',
                            parent=self.styles['Normal'],
                            fontSize=8,
                            leading=10,
                            fontName='Helvetica-Bold',
                            wordWrap='CJK'
                        )

                        for i, row in enumerate(self.table_data):
                            wrapped_row = []
                            for cell in row:
                                if i == 0:  # Header row
                                    wrapped_row.append(Paragraph(str(cell), header_style))
                                else:
                                    wrapped_row.append(Paragraph(str(cell), cell_style))
                            wrapped_data.append(wrapped_row)

                        # Calculate available width
                        available_width = doc.width
                        num_cols = len(self.table_data[0]) if self.table_data else 1

                        # Set column widths to fit page
                        col_widths = [available_width / num_cols] * num_cols

                        # Create table with specific column widths
                        t = Table(wrapped_data, colWidths=col_widths, repeatRows=1)
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 8),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                            ('TOPPADDING', (0, 0), (-1, -1), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                            ('FONTSIZE', (0, 1), (-1, -1), 7),
                            ('LEFTPADDING', (0, 0), (-1, -1), 3),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                        ]))
                        self.story.append(t)
                        self.story.append(Spacer(1, 0.2*inch))
                elif tag == 'tr':
                    if self.current_row:
                        self.table_data.append(self.current_row)
                elif tag in ['h1', 'h2', 'h3', 'p', 'code', 'pre']:
                    text = ''.join(self.current_text).strip()
                    if text:
                        if tag == 'h1':
                            self.story.append(Paragraph(text, self.styles['Heading1']))
                        elif tag == 'h2':
                            self.story.append(Paragraph(text, self.styles['Heading2']))
                        elif tag == 'h3':
                            self.story.append(Paragraph(text, self.styles['Heading3']))
                        elif tag in ['code', 'pre']:
                            self.story.append(Paragraph(text, self.styles['CustomCode']))
                        else:
                            self.story.append(Paragraph(text, self.styles['Normal']))
                        self.story.append(Spacer(1, 0.1*inch))
                    self.current_text = []
                self.current_tag = None

            def handle_data(self, data):
                data = data.strip()
                if not data:
                    return

                if self.in_table and self.current_tag in ['th', 'td']:
                    self.current_row.append(data)
                else:
                    self.current_text.append(data)

        parser = HTMLToPDFParser(story, styles)
        parser.feed(html_content)

        # Build PDF
        doc.build(story)
        return True

    except ImportError:
        print("Error: reportlab or markdown not installed.")
        print("Install with: pip install reportlab markdown")
        return False
    except Exception as e:
        print(f"Error converting to PDF: {e}")
        import traceback
        traceback.print_exc()
        return False


def convert_markdown_to_pdf_pandoc(markdown_text: str, output_pdf_path: str) -> bool:
    """
    Convert markdown to PDF using pandoc command-line tool.

    Requires: pandoc installed on system
    """
    import subprocess
    import tempfile

    try:
        # Write markdown to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as tmp:
            tmp.write(markdown_text)
            tmp_path = tmp.name

        # Use pandoc to convert
        result = subprocess.run(
            ['pandoc', tmp_path, '-o', output_pdf_path, '--pdf-engine=pdflatex'],
            capture_output=True,
            text=True
        )

        # Clean up temp file
        os.unlink(tmp_path)

        if result.returncode != 0:
            print(f"Pandoc error: {result.stderr}")
            return False

        return True

    except FileNotFoundError:
        print("Error: pandoc not found. Install from https://pandoc.org/installing.html")
        return False
    except Exception as e:
        print(f"Error using pandoc: {e}")
        return False


def convert_json_to_pdf(json_path: str, output_pdf_path: Optional[str] = None,
                       method: str = 'reportlab') -> bool:
    """
    Convert JSON file containing markdown to PDF.

    Args:
        json_path: Path to input JSON file
        output_pdf_path: Path to output PDF file (optional, auto-generated if not provided)
        method: Conversion method ('reportlab', 'pdfkit', or 'pandoc')

    Returns:
        True if successful, False otherwise
    """
    # Extract markdown from JSON
    markdown_text = extract_markdown_from_json(json_path)
    if not markdown_text:
        return False

    # Generate output path if not provided
    if output_pdf_path is None:
        json_file = Path(json_path)
        output_pdf_path = json_file.with_suffix('.pdf')

    # Convert based on method
    if method == 'reportlab':
        success = convert_markdown_to_pdf_reportlab(markdown_text, str(output_pdf_path))
    elif method == 'pdfkit':
        success = convert_markdown_to_pdf_pdfkit(markdown_text, str(output_pdf_path))
    elif method == 'pandoc':
        success = convert_markdown_to_pdf_pandoc(markdown_text, str(output_pdf_path))
    else:
        print(f"Error: Unknown method '{method}'. Use 'reportlab', 'pdfkit', or 'pandoc'")
        return False

    if success:
        print(f"Successfully created: {output_pdf_path}")

    return success


def main():
    """
    Main function to process command-line arguments and convert files.
    """
    if len(sys.argv) < 2:
        print("Usage: python json_to_pdf.py <json_file> [output_pdf] [method]")
        print("\nExamples:")
        print("  python json_to_pdf.py input.json")
        print("  python json_to_pdf.py input.json output.pdf")
        print("  python json_to_pdf.py input.json output.pdf reportlab")
        print("  python json_to_pdf.py input.json output.pdf pdfkit")
        print("  python json_to_pdf.py input.json output.pdf pandoc")
        print("\nMethods:")
        print("  reportlab (default) - Pure Python, no external dependencies")
        print("  pdfkit - Requires wkhtmltopdf (brew install wkhtmltopdf)")
        print("  pandoc - Requires pandoc (brew install pandoc)")
        sys.exit(1)

    json_path = sys.argv[1]
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else None
    method = sys.argv[3] if len(sys.argv) > 3 else 'reportlab'

    if not os.path.exists(json_path):
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    success = convert_json_to_pdf(json_path, output_pdf, method)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
